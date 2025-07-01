"""Tests for the risk engine service."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hedgelock.risk_engine.main import RiskEngineService, RiskState, app


class TestRiskEngineService:
    """Test cases for RiskEngineService class."""

    def test_service_initialization(self) -> None:
        """Test service initializes correctly."""
        service = RiskEngineService()
        assert service.is_running is False
        assert service.calculation_count == 0
        assert service.ltv_target == 40.0
        assert service.ltv_max == 50.0

    @patch.dict("os.environ", {"LTV_TARGET_RATIO": "35", "LTV_MAX_RATIO": "45"})
    def test_service_initialization_with_env(self) -> None:
        """Test service initialization with environment variables."""
        service = RiskEngineService()
        assert service.ltv_target == 35.0
        assert service.ltv_max == 45.0

    @pytest.mark.asyncio
    async def test_service_start_stop(self) -> None:
        """Test service can start and stop."""
        service = RiskEngineService()

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

    def test_calculate_stub_risk(self) -> None:
        """Test calculating stub risk metrics."""
        service = RiskEngineService()
        
        risk_state = service._calculate_stub_risk()
        
        assert isinstance(risk_state, RiskState)
        assert 30.0 <= risk_state.ltv_ratio <= 60.0
        assert risk_state.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert -1.0 <= risk_state.net_delta <= 1.0
        assert 0.0 <= risk_state.required_hedge <= 5.0

    def test_get_stats(self) -> None:
        """Test getting service statistics."""
        service = RiskEngineService()
        service.calculation_count = 42
        
        stats = service.get_stats()

        assert stats["calculation_count"] == 42
        assert stats["is_running"] is False
        assert stats["ltv_target_ratio"] == 40.0
        assert stats["ltv_max_ratio"] == 50.0
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
            assert data["service"] == "hedgelock-risk-engine"
            assert data["version"] == "0.1.0"
            assert "environment" in data
            assert data["environment"]["ltv_target_ratio"] == "40.0"
            assert data["environment"]["ltv_max_ratio"] == "50.0"
            assert data["environment"]["log_level"] == "INFO"

    def test_get_risk_state(self) -> None:
        """Test getting current risk state."""
        with TestClient(app) as client:
            response = client.get("/risk-state")
            assert response.status_code == 200
            
            data = response.json()
            assert "ltv_ratio" in data
            assert "risk_level" in data
            assert "net_delta" in data
            assert "required_hedge" in data
            assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def test_stats_endpoint(self) -> None:
        """Test stats endpoint."""
        with TestClient(app) as client:
            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "calculation_count" in data
            assert "is_running" in data
            assert "ltv_target_ratio" in data
            assert "ltv_max_ratio" in data
            assert "stub_mode" in data

    @patch.dict("os.environ", {"LTV_TARGET_RATIO": "38", "LTV_MAX_RATIO": "48", "LOG_LEVEL": "DEBUG"})
    def test_health_check_with_custom_env(self) -> None:
        """Test health check with custom environment settings."""
        # Need to recreate the service to pick up the env vars
        from hedgelock.risk_engine.main import service
        service.ltv_target = 38.0
        service.ltv_max = 48.0
        
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert data["environment"]["ltv_target_ratio"] == "38.0"
            assert data["environment"]["ltv_max_ratio"] == "48.0"
            assert data["environment"]["log_level"] == "DEBUG"