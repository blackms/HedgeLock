"""Tests for the collector service."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hedgelock.collector.main import CollectorService, app


class TestCollectorService:
    """Test cases for CollectorService class."""

    def test_service_initialization(self) -> None:
        """Test service initializes correctly."""
        service = CollectorService()
        assert service.is_running is False
        assert service.message_count == 0
        assert service.bybit_testnet is True  # Default value

    @patch.dict("os.environ", {"BYBIT_TESTNET": "false"})
    def test_service_initialization_with_env(self) -> None:
        """Test service initialization with environment variables."""
        service = CollectorService()
        assert service.bybit_testnet is False

    @pytest.mark.asyncio
    async def test_service_start_stop(self) -> None:
        """Test service can start and stop."""
        service = CollectorService()

        # Start service in background
        start_task = asyncio.create_task(service.start())

        # Give it a moment to start
        await asyncio.sleep(0.1)
        assert service.is_running is True

        # Stop service
        await service.stop()
        assert service.is_running is False

        # Cancel the start task
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

    def test_get_stats(self) -> None:
        """Test getting service statistics."""
        service = CollectorService()
        service.message_count = 5
        stats = service.get_stats()

        assert stats["message_count"] == 5
        assert stats["is_running"] is False
        assert stats["testnet_mode"] is True
        assert stats["stub_mode"] is True


class TestAPI:
    """Test cases for FastAPI endpoints."""

    def test_health_check(self) -> None:
        """Test health check endpoint."""
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "hedgelock-collector"
            assert data["version"] == "0.1.0"
            assert "environment" in data
            assert data["environment"]["bybit_testnet"] == "True"
            assert data["environment"]["log_level"] == "INFO"

    def test_stats_endpoint(self) -> None:
        """Test stats endpoint."""
        with TestClient(app) as client:
            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "message_count" in data
            assert "is_running" in data
            assert "testnet_mode" in data
            assert "stub_mode" in data

    @patch.dict("os.environ", {"BYBIT_TESTNET": "false", "LOG_LEVEL": "DEBUG"})
    def test_health_check_with_custom_env(self) -> None:
        """Test health check with custom environment settings."""
        # Need to recreate the service to pick up the env var
        from hedgelock.collector.main import service

        service.bybit_testnet = False

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["environment"]["bybit_testnet"] == "False"
            assert data["environment"]["log_level"] == "DEBUG"
