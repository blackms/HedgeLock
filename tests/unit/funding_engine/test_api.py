"""
Unit tests for funding engine API with 100% coverage.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.hedgelock.funding_engine.api import app, funding_service
from src.hedgelock.funding_engine.service import FundingEngineService
from src.hedgelock.shared.funding_models import (
    FundingContext,
    FundingDecision,
    FundingRate,
    FundingRegime,
)


class TestFundingEngineAPI:
    """Test funding engine API endpoints."""

    @pytest.fixture
    def mock_service(self):
        """Create mock funding service."""
        mock = Mock(spec=FundingEngineService)
        mock.running = True
        mock.current_contexts = {}
        mock.storage = Mock()
        mock._generate_funding_decision = Mock()
        mock.get_funding_status = Mock()
        return mock

    @pytest.fixture
    def client(self, mock_service):
        """Create test client with mocked service."""
        # Patch the global service
        with patch("src.hedgelock.funding_engine.api.funding_service", mock_service):
            with TestClient(app) as client:
                yield client

    @pytest.fixture
    def sample_context(self):
        """Create sample funding context."""
        return FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=22.0,
            avg_rate_7d=20.0,
            max_rate_24h=30.0,
            volatility_24h=5.0,
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=6.85,
            weekly_cost_pct=0.48,
            timestamp=datetime.utcnow(),
        )

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "funding-engine"
        assert "timestamp" in data

    def test_get_status(self, client, mock_service):
        """Test status endpoint."""
        mock_service.get_funding_status.return_value = {
            "service": "funding-engine",
            "running": True,
            "symbols_tracked": 1,
        }

        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "funding-engine"
        assert data["running"] is True
        mock_service.get_funding_status.assert_called_once()

    def test_get_status_service_not_initialized(self, client):
        """Test status when service not initialized."""
        with patch("src.hedgelock.funding_engine.api.funding_service", None):
            response = client.get("/status")

        assert response.status_code == 503
        assert response.json()["detail"] == "Service not initialized"

    def test_get_funding_context(self, client, mock_service, sample_context):
        """Test getting funding context for a symbol."""
        mock_service.current_contexts["BTCUSDT"] = sample_context

        response = client.get("/funding/context/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["current_regime"] == "normal"
        assert data["current_rate"] == 25.0
        assert data["position_multiplier"] == 0.75
        assert data["should_exit"] is False

    def test_get_funding_context_not_found(self, client, mock_service):
        """Test getting context for unknown symbol."""
        mock_service.current_contexts = {}

        response = client.get("/funding/context/UNKNOWN")

        assert response.status_code == 404
        assert "No funding context" in response.json()["detail"]

    def test_get_funding_history(self, client, mock_service):
        """Test getting funding history."""
        # Mock storage response
        mock_rates = [
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                funding_time=datetime.utcnow(),
                mark_price=50000.0,
                index_price=50000.0,
            ),
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.00012,
                funding_time=datetime.utcnow() - timedelta(hours=8),
                mark_price=50100.0,
                index_price=50100.0,
            ),
        ]
        mock_service.storage.get_funding_history.return_value = mock_rates

        response = client.get("/funding/history/BTCUSDT?hours=24")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["hours"] == 24
        assert data["count"] == 2
        assert len(data["rates"]) == 2
        assert data["rates"][0]["funding_rate"] == 0.0001

    def test_get_funding_history_max_hours(self, client, mock_service):
        """Test funding history with too many hours."""
        response = client.get("/funding/history/BTCUSDT?hours=200")

        assert response.status_code == 400
        assert "Maximum 168 hours" in response.json()["detail"]

    def test_get_all_regimes(self, client, mock_service, sample_context):
        """Test getting all funding regimes."""
        mock_service.current_contexts = {
            "BTCUSDT": sample_context,
            "ETHUSDT": FundingContext(
                symbol="ETHUSDT",
                current_regime=FundingRegime.HEATED,
                current_rate=75.0,
                avg_rate_24h=70.0,
                avg_rate_7d=65.0,
                max_rate_24h=80.0,
                volatility_24h=10.0,
                position_multiplier=0.4,
                should_exit=False,
                regime_change=False,
                daily_cost_bps=20.5,
                weekly_cost_pct=1.44,
            ),
        }

        response = client.get("/funding/regimes")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert "BTCUSDT" in data["regimes"]
        assert data["regimes"]["BTCUSDT"]["regime"] == "normal"
        assert data["regimes"]["ETHUSDT"]["regime"] == "heated"

    def test_get_funding_risk(self, client, mock_service, sample_context):
        """Test getting funding risk assessment."""
        mock_service.current_contexts["BTCUSDT"] = sample_context

        # Mock decision
        mock_decision = FundingDecision(
            context=sample_context,
            action="maintain_position",
            position_adjustment=0.75,
            max_position_size=1.5,
            reason="Normal funding conditions",
            urgency="low",
            funding_risk_score=25.0,
            projected_cost_24h=30.0,
        )
        mock_service._generate_funding_decision.return_value = mock_decision

        response = client.get("/funding/risk/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["risk_score"] == 25.0
        assert data["action"] == "maintain_position"
        assert data["urgency"] == "low"
        assert data["current_regime"] == "normal"

    def test_get_funding_risk_not_found(self, client, mock_service):
        """Test funding risk for unknown symbol."""
        mock_service.current_contexts = {}

        response = client.get("/funding/risk/UNKNOWN")

        assert response.status_code == 404

    def test_simulate_funding_regime(self, client):
        """Test funding regime simulation."""
        request_data = {
            "symbol": "BTCUSDT",
            "current_rate": 75.0,
            "rates_24h": [70.0, 72.0, 73.0],
            "rates_7d": [60.0, 65.0, 68.0, 70.0, 71.0, 72.0, 73.0],
        }

        response = client.post("/funding/simulate", params=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["regime"] == "heated"  # 75% APR = heated
        assert "position_multiplier" in data
        assert data["should_exit"] is False
        assert "daily_cost_bps" in data
        assert "weekly_cost_pct" in data

    def test_simulate_funding_regime_error(self, client):
        """Test simulation with invalid data."""
        # Missing required fields
        request_data = {
            "symbol": "BTCUSDT",
            "current_rate": 75.0,
            # Missing rates_24h and rates_7d
        }

        response = client.post("/funding/simulate", params=request_data)

        assert response.status_code == 422  # Validation error

    def test_service_not_initialized_endpoints(self, client):
        """Test all endpoints when service not initialized."""
        with patch("src.hedgelock.funding_engine.api.funding_service", None):
            # Test each endpoint
            endpoints = [
                ("/status", "get"),
                ("/funding/context/BTCUSDT", "get"),
                ("/funding/history/BTCUSDT", "get"),
                ("/funding/regimes", "get"),
                ("/funding/risk/BTCUSDT", "get"),
            ]

            for endpoint, method in endpoints:
                if method == "get":
                    response = client.get(endpoint)
                else:
                    response = client.post(endpoint)

                assert response.status_code == 503
                assert response.json()["detail"] == "Service not initialized"

    @pytest.mark.asyncio
    async def test_lifespan(self):
        """Test application lifespan management."""
        # Import lifespan context manager
        from src.hedgelock.funding_engine.api import lifespan

        # Mock FundingEngineService
        mock_service_class = Mock()
        mock_service_instance = AsyncMock()
        mock_service_class.return_value = mock_service_instance

        with patch(
            "src.hedgelock.funding_engine.api.FundingEngineService", mock_service_class
        ):
            # Test lifespan
            async with lifespan(app):
                # Verify service was started
                mock_service_instance.start.assert_called_once()

            # Verify service was stopped
            mock_service_instance.stop.assert_called_once()
