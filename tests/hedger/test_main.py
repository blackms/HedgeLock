"""Tests for the hedger service."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hedgelock.hedger.main import HedgerService, Order, app


class TestHedgerService:
    """Test cases for HedgerService class."""

    def test_service_initialization(self) -> None:
        """Test service initializes correctly."""
        service = HedgerService()
        assert service.is_running is False
        assert service.order_count == 0
        assert len(service.orders) == 0
        assert service.max_order_size == 10.0
        assert service.max_position_size == 50.0

    @patch.dict(
        "os.environ", {"MAX_ORDER_SIZE_BTC": "5.0", "MAX_POSITION_SIZE_BTC": "25.0"}
    )
    def test_service_initialization_with_env(self) -> None:
        """Test service initialization with environment variables."""
        service = HedgerService()
        assert service.max_order_size == 5.0
        assert service.max_position_size == 25.0

    @pytest.mark.asyncio
    async def test_service_start_stop(self) -> None:
        """Test service can start and stop."""
        service = HedgerService()

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

    def test_create_stub_order(self) -> None:
        """Test creating a stub order."""
        service = HedgerService()
        service.order_count = 10

        order = service._create_stub_order()

        assert order.order_id == "ORD-000010"
        assert order.symbol in ["BTCUSDT", "ETHUSDT"]
        assert order.side in ["BUY", "SELL"]
        assert 0.1 <= order.size <= service.max_order_size
        assert order.price > 0
        assert order.status == "FILLED"

    def test_get_stats(self) -> None:
        """Test getting service statistics."""
        service = HedgerService()

        # Add some test orders
        for i in range(5):
            order = Order(
                order_id=f"ORD-{i:06d}",
                symbol="BTCUSDT",
                side="Buy" if i % 2 == 0 else "Sell",
                size=1.0,
                price=50000.0,
                status="FILLED",  # All orders are FILLED in implementation
            )
            service.orders.append(order)

        service.order_count = 5
        stats = service.get_stats()

        assert stats["order_count"] == 5
        assert stats["total_orders"] == 5
        assert stats["active_orders"] == 0  # All orders are FILLED in test
        assert stats["is_running"] is False
        assert stats["max_order_size"] == 10.0
        assert stats["max_position_size"] == 50.0
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
            assert data["service"] == "hedgelock-hedger"
            assert data["version"] == "0.1.0"
            assert "environment" in data
            assert data["environment"]["max_order_size"] == "10.0"
            assert data["environment"]["max_position_size"] == "50.0"
            assert data["environment"]["log_level"] == "INFO"

    def test_get_orders_empty(self) -> None:
        """Test getting orders when none exist."""
        with TestClient(app) as client:
            response = client.get("/orders")
            assert response.status_code == 200
            assert response.json() == []

    def test_get_orders_with_data(self) -> None:
        """Test getting orders with existing data."""
        from hedgelock.hedger.main import service

        # Add some test orders
        for i in range(25):
            order = Order(
                order_id=f"ORD-{i:06d}",
                symbol="BTCUSDT",
                side="Buy",
                size=1.0,
                price=50000.0,
                status="Filled",
            )
            service.orders.append(order)

        with TestClient(app) as client:
            response = client.get("/orders")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 10  # Should only return last 10
            assert data[0]["order_id"] == "ORD-000015"  # First of last 10
            assert data[-1]["order_id"] == "ORD-000024"  # Last order

    def test_stats_endpoint(self) -> None:
        """Test stats endpoint."""
        with TestClient(app) as client:
            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "order_count" in data
            assert "total_orders" in data
            assert "active_orders" in data
            assert "total_orders" in data
            assert "is_running" in data
            assert "max_order_size" in data
            assert "max_position_size" in data
            assert "stub_mode" in data

    @patch.dict(
        "os.environ",
        {
            "MAX_ORDER_SIZE_BTC": "2.5",
            "MAX_POSITION_SIZE_BTC": "15.0",
            "LOG_LEVEL": "DEBUG",
        },
    )
    def test_health_check_with_custom_env(self) -> None:
        """Test health check with custom environment settings."""
        # Need to recreate the service to pick up the env vars
        from hedgelock.hedger.main import service

        service.max_order_size = 2.5
        service.max_position_size = 15.0

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["environment"]["max_order_size"] == "2.5"
            assert data["environment"]["max_position_size"] == "15.0"
            assert data["environment"]["log_level"] == "DEBUG"
