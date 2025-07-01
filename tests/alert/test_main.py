"""Tests for the alert service."""

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hedgelock.alert.main import Alert, AlertService, app


class TestAlertService:
    """Test cases for AlertService class."""

    def test_service_initialization(self) -> None:
        """Test service initializes correctly."""
        service = AlertService()
        assert service.is_running is False
        assert service.alert_count == 0
        assert len(service.alerts) == 0
        assert service.telegram_enabled is False
        assert service.email_enabled is False

    @pytest.mark.asyncio
    async def test_service_start_stop(self) -> None:
        """Test service can start and stop."""
        service = AlertService()

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

    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "test_token", "SMTP_USER": "test@email.com"},
    )
    def test_service_with_enabled_channels(self) -> None:
        """Test service initialization with enabled notification channels."""
        service = AlertService()
        assert service.telegram_enabled is True
        assert service.email_enabled is True

    def test_create_stub_alert(self) -> None:
        """Test creating a stub alert."""
        service = AlertService()
        service.alert_count = 42

        alert = service._create_stub_alert()

        assert alert.alert_id == "ALT-000042"
        assert isinstance(alert.timestamp, datetime)
        assert alert.severity in ["INFO", "WARNING", "CRITICAL"]
        assert alert.channel in ["telegram", "email", "webhook"]
        assert alert.title in [
            "LTV Ratio Warning",
            "Hedge Position Update",
            "Treasury Action Completed",
            "System Health Check",
        ]
        assert isinstance(alert.delivered, bool)

    def test_get_stats_empty(self) -> None:
        """Test getting stats with no alerts."""
        service = AlertService()
        stats = service.get_stats()

        assert stats["alert_count"] == 0
        assert stats["total_alerts"] == 0
        assert stats["delivered_alerts"] == 0
        assert stats["critical_alerts"] == 0
        assert stats["delivery_rate"] == "N/A"
        assert stats["is_running"] is False
        assert stats["telegram_enabled"] is False
        assert stats["email_enabled"] is False
        assert stats["stub_mode"] is True

    def test_get_stats_with_alerts(self) -> None:
        """Test getting stats with various alerts."""
        service = AlertService()

        # Create some test alerts
        for i in range(10):
            alert = Alert(
                alert_id=f"ALT-{i:06d}",
                timestamp=datetime.utcnow(),
                severity="CRITICAL" if i < 3 else "INFO",
                channel="telegram",
                title="Test Alert",
                message="Test message",
                delivered=i < 8,  # 80% delivered
            )
            service.alerts.append(alert)

        service.alert_count = 10
        stats = service.get_stats()

        assert stats["alert_count"] == 10
        assert stats["total_alerts"] == 10
        assert stats["delivered_alerts"] == 8
        assert stats["critical_alerts"] == 3
        assert stats["delivery_rate"] == "80.0%"


class TestAPI:
    """Test cases for FastAPI endpoints."""

    def test_health_check(self) -> None:
        """Test health check endpoint."""
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "hedgelock-alert"
            assert data["version"] == "0.1.0"
            assert "environment" in data
            assert data["environment"]["telegram_enabled"] == "False"
            assert data["environment"]["email_enabled"] == "False"
            assert data["environment"]["log_level"] == "INFO"

    def test_get_alerts_empty(self) -> None:
        """Test getting alerts when none exist."""
        with TestClient(app) as client:
            response = client.get("/alerts")
            assert response.status_code == 200
            assert response.json() == []

    def test_get_alerts_with_data(self) -> None:
        """Test getting alerts with existing data."""
        # Create a custom service with alerts
        from hedgelock.alert.main import service

        # Add some test alerts
        for i in range(25):
            alert = Alert(
                alert_id=f"ALT-{i:06d}",
                timestamp=datetime.utcnow(),
                severity="INFO",
                channel="telegram",
                title=f"Alert {i}",
                message="Test message",
                delivered=True,
            )
            service.alerts.append(alert)

        with TestClient(app) as client:
            response = client.get("/alerts")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 20  # Should only return last 20
            assert data[0]["alert_id"] == "ALT-000005"  # First of last 20
            assert data[-1]["alert_id"] == "ALT-000024"  # Last alert

    def test_stats_endpoint(self) -> None:
        """Test stats endpoint."""
        with TestClient(app) as client:
            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "alert_count" in data
            assert "total_alerts" in data
            assert "delivered_alerts" in data
            assert "critical_alerts" in data
            assert "delivery_rate" in data
            assert "is_running" in data
            assert "telegram_enabled" in data
            assert "email_enabled" in data
            assert "stub_mode" in data

    def test_send_test_alert(self) -> None:
        """Test sending a test alert."""
        with TestClient(app) as client:
            response = client.post("/test-alert")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "sent"
            assert "alert_id" in data
            assert data["alert_id"].startswith("ALT-")

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_health_check_with_telegram_enabled(self) -> None:
        """Test health check with Telegram enabled."""
        # Need to recreate the service to pick up the env var
        from hedgelock.alert.main import service

        service.telegram_enabled = True

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["environment"]["telegram_enabled"] == "True"
