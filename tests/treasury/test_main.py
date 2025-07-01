"""Tests for the treasury service."""

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hedgelock.treasury.main import TreasuryAction, TreasuryService, app


class TestTreasuryService:
    """Test cases for TreasuryService class."""

    def test_service_initialization(self) -> None:
        """Test service initializes correctly."""
        service = TreasuryService()
        assert service.is_running is False
        assert service.action_count == 0
        assert len(service.actions) == 0
        assert service.min_buffer == 5.0
        assert service.max_operation == 10000.0

    @patch.dict(
        "os.environ", {"MIN_BUFFER_PERCENT": "3", "MAX_SINGLE_OPERATION_USD": "5000"}
    )
    def test_service_initialization_with_env(self) -> None:
        """Test service initialization with environment variables."""
        service = TreasuryService()
        assert service.min_buffer == 3.0
        assert service.max_operation == 5000.0

    @pytest.mark.asyncio
    async def test_service_start_stop(self) -> None:
        """Test service can start and stop."""
        service = TreasuryService()

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

    def test_create_stub_action(self) -> None:
        """Test creating a stub treasury action."""
        service = TreasuryService()
        service.action_count = 5

        action = service._create_stub_action()

        assert action.action_id == "TRS-000005"
        assert isinstance(action.timestamp, datetime)
        assert action.action_type in ["REPAY_PRINCIPAL", "ADD_COLLATERAL", "WITHDRAW_PROFIT"]
        assert 100.0 <= action.amount_usd <= service.max_operation
        assert isinstance(action.description, str)
        assert len(action.description) > 0

    def test_get_stats(self) -> None:
        """Test getting service statistics."""
        service = TreasuryService()

        # Add some test actions
        for i in range(10):
            action = TreasuryAction(
                action_id=f"TRE-{i:06d}",
                timestamp=datetime.utcnow(),
                action_type=(
                    "REPAY_PRINCIPAL" if i < 4 else "ADD_COLLATERAL" if i < 7 else "WITHDRAW_PROFIT"
                ),
                amount_usd=1000.0,
                description="Test action",
            )
            service.actions.append(action)

        service.action_count = 10
        stats = service.get_stats()

        assert stats["action_count"] == 10
        assert stats["total_actions"] == 10
        assert stats["total_repaid_usd"] == 4000.0  # 4 * 1000
        assert stats["total_collateral_added_usd"] == 3000.0  # 3 * 1000
        assert stats["is_running"] is False
        assert stats["min_buffer_percent"] == 5.0
        assert stats["max_operation_usd"] == 10000.0
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
            assert data["service"] == "hedgelock-treasury"
            assert data["version"] == "0.1.0"
            assert "environment" in data
            assert data["environment"]["min_buffer"] == "5.0"
            assert data["environment"]["max_operation"] == "10000.0"
            assert data["environment"]["log_level"] == "INFO"

    def test_get_actions_empty(self) -> None:
        """Test getting actions when none exist."""
        with TestClient(app) as client:
            response = client.get("/actions")
            assert response.status_code == 200
            assert response.json() == []

    def test_get_actions_with_data(self) -> None:
        """Test getting actions with existing data."""
        from hedgelock.treasury.main import service

        # Add some test actions
        for i in range(25):
            action = TreasuryAction(
                action_id=f"TRE-{i:06d}",
                timestamp=datetime.utcnow(),
                action_type="REPAY_PRINCIPAL",
                amount_usd=1000.0,
                description=f"Action {i}",
            )
            service.actions.append(action)

        with TestClient(app) as client:
            response = client.get("/actions")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 10  # Should only return last 10
            assert data[0]["action_id"] == "TRE-000015"  # First of last 10
            assert data[-1]["action_id"] == "TRE-000024"  # Last action

    def test_stats_endpoint(self) -> None:
        """Test stats endpoint."""
        with TestClient(app) as client:
            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "action_count" in data
            assert "total_actions" in data
            assert "total_repaid_usd" in data
            assert "total_collateral_added_usd" in data
            assert "is_running" in data
            assert "min_buffer_percent" in data
            assert "max_operation_usd" in data
            assert "stub_mode" in data

    # Note: /simulate-deposit endpoint doesn't exist in the actual implementation
    # This test should be removed or the endpoint should be added

    @patch.dict(
        "os.environ",
        {
            "MIN_BUFFER_PERCENT": "2.5",
            "MAX_SINGLE_OPERATION_USD": "7500",
            "LOG_LEVEL": "DEBUG",
        },
    )
    def test_health_check_with_custom_env(self) -> None:
        """Test health check with custom environment settings."""
        # Need to recreate the service to pick up the env vars
        from hedgelock.treasury.main import service

        service.min_buffer = 2.5
        service.max_operation = 7500.0

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["environment"]["min_buffer"] == "2.5"
            assert data["environment"]["max_operation"] == "7500.0"
            assert data["environment"]["log_level"] == "DEBUG"
