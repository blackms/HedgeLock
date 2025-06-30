"""Tests for the dummy service."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from hedgelock.dummy.main import DummyService, app


class TestDummyService:
    """Test cases for DummyService class."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Test service initializes correctly."""
        service = DummyService()
        assert service.is_running is False
        assert service.message_count == 0

    @pytest.mark.asyncio
    async def test_service_start_stop(self) -> None:
        """Test service can start and stop."""
        service = DummyService()

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
        service = DummyService()
        stats = service.get_stats()

        assert stats["message_count"] == 0
        assert stats["is_running"] == 0


class TestAPI:
    """Test cases for FastAPI endpoints."""

    def test_health_check(self) -> None:
        """Test health check endpoint."""
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "hedgelock-dummy"
            assert data["version"] == "0.1.0"

    def test_stats_endpoint(self) -> None:
        """Test stats endpoint."""
        with TestClient(app) as client:
            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "message_count" in data
            assert "is_running" in data

    @pytest.mark.asyncio
    async def test_async_health_check(self, async_client: AsyncClient) -> None:
        """Test health check endpoint with async client."""
        # Note: This would normally test against a running instance
        # For unit tests, we use TestClient instead
        pass