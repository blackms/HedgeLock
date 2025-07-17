"""
Unit tests for Position Manager API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from src.hedgelock.position_manager.api import app, position_service
from src.hedgelock.position_manager.models import PositionState, MarketRegime


class TestPositionManagerAPI:
    """Test Position Manager API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_service(self):
        """Create mock position service."""
        service = Mock()
        service.running = True
        service.manager = Mock()
        service.manager.last_hedge_update = datetime.utcnow()
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            funding_regime="NORMAL",
            unrealized_pnl=100.0,
            realized_pnl=50.0,
            peak_pnl=150.0,
            market_regime=MarketRegime.NEUTRAL
        )
        return service
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Position Manager"
        assert data["version"] == "1.0.0"
        assert data["status"] == "active"
    
    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "position-manager"
        assert "status" in data
        assert "timestamp" in data
    
    def test_status_endpoint_no_service(self, client):
        """Test status endpoint when service not initialized."""
        with patch('src.hedgelock.position_manager.api.position_service', None):
            response = client.get("/status")
            assert response.status_code == 503
            assert response.json()["detail"] == "Service not initialized"
    
    def test_status_endpoint_with_service(self, client, mock_service):
        """Test status endpoint with service running."""
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/status")
            assert response.status_code == 200
            data = response.json()
            
            assert data["service"] == "position-manager"
            assert data["status"] == "active"
            assert "current_position" in data
            assert "last_hedge_update" in data
    
    def test_position_endpoint_no_service(self, client):
        """Test position endpoint when service not initialized."""
        with patch('src.hedgelock.position_manager.api.position_service', None):
            response = client.get("/position")
            assert response.status_code == 404
    
    def test_position_endpoint_no_position(self, client, mock_service):
        """Test position endpoint when no position data."""
        mock_service.current_position = None
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/position")
            assert response.status_code == 404
    
    def test_position_endpoint_with_data(self, client, mock_service):
        """Test position endpoint with position data."""
        mock_service.manager.calculate_delta.return_value = 0.27
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/position")
            assert response.status_code == 200
            data = response.json()
            
            # Check structure
            assert "timestamp" in data
            assert "positions" in data
            assert "metrics" in data
            assert "pnl" in data
            assert "market" in data
            
            # Check positions
            positions = data["positions"]
            assert positions["spot_btc"] == 0.27
            assert positions["long_perp"] == 0.213
            assert positions["short_perp"] == 0.213
            
            # Check metrics
            metrics = data["metrics"]
            assert metrics["net_delta"] == 0.27
            assert metrics["delta_neutral"] is False
            assert metrics["hedge_ratio"] == 1.0
            assert metrics["volatility_24h"] == "2.0%"
            assert metrics["funding_rate_8h"] == "0.0100%"
            assert metrics["funding_regime"] == "NORMAL"
            
            # Check P&L
            pnl = data["pnl"]
            assert pnl["unrealized"] == 100.0
            assert pnl["realized"] == 50.0
            assert pnl["peak"] == 150.0
            
            # Check market
            market = data["market"]
            assert market["btc_price"] == 116000
            assert market["regime"] == "NEUTRAL"
    
    def test_hedge_params_endpoint_no_service(self, client):
        """Test hedge params endpoint when service not initialized."""
        with patch('src.hedgelock.position_manager.api.position_service', None):
            response = client.get("/hedge-params")
            assert response.status_code == 503
    
    def test_hedge_params_endpoint_no_position(self, client, mock_service):
        """Test hedge params endpoint when no position."""
        mock_service.current_position = None
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/hedge-params")
            assert response.status_code == 404
    
    def test_hedge_params_endpoint_with_data(self, client, mock_service):
        """Test hedge params endpoint with data."""
        mock_service.manager.calculate_hedge_ratio.return_value = 0.4
        mock_service.manager.apply_funding_multiplier.return_value = 0.4
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/hedge-params")
            assert response.status_code == 200
            data = response.json()
            
            assert "timestamp" in data
            assert data["volatility_24h"] == "2.0%"
            assert data["base_hedge_ratio"] == 0.4
            assert data["funding_multiplier"] == 1.0  # 0.4 / 0.4
            assert data["final_hedge_ratio"] == 0.4
            assert data["funding_regime"] == "NORMAL"
            assert "last_update" in data
    
    def test_hedge_params_zero_hedge_ratio(self, client, mock_service):
        """Test hedge params with zero base hedge ratio."""
        mock_service.manager.calculate_hedge_ratio.return_value = 0.0
        mock_service.manager.apply_funding_multiplier.return_value = 0.0
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/hedge-params")
            assert response.status_code == 200
            data = response.json()
            assert data["funding_multiplier"] == 0  # Special case for zero ratio
    
    def test_rehedge_endpoint_no_service(self, client):
        """Test rehedge endpoint when service not initialized."""
        with patch('src.hedgelock.position_manager.api.position_service', None):
            response = client.post("/rehedge")
            assert response.status_code == 503
    
    def test_rehedge_endpoint_success(self, client, mock_service):
        """Test successful rehedge trigger."""
        mock_service.rehedge_positions = AsyncMock()
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.post("/rehedge")
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "success"
            assert data["message"] == "Rehedge triggered"
            assert "timestamp" in data
            
            # Verify rehedge was called
            mock_service.rehedge_positions.assert_called_once()
    
    def test_rehedge_endpoint_failure(self, client, mock_service):
        """Test rehedge trigger failure."""
        mock_service.rehedge_positions = AsyncMock(side_effect=Exception("Test error"))
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.post("/rehedge")
            assert response.status_code == 500
            assert response.json()["detail"] == "Test error"
    
    def test_startup_event(self):
        """Test startup event handler."""
        from src.hedgelock.position_manager.api import startup_event
        
        with patch('src.hedgelock.position_manager.api.position_service', None):
            with patch('asyncio.create_task') as mock_create_task:
                # Run startup
                import asyncio
                asyncio.run(startup_event())
                
                # Should create background task
                mock_create_task.assert_called_once()
    
    def test_shutdown_event(self):
        """Test shutdown event handler."""
        from src.hedgelock.position_manager.api import shutdown_event
        
        mock_service = Mock()
        mock_service.stop = AsyncMock()
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            import asyncio
            asyncio.run(shutdown_event())
            
            # Should stop service
            mock_service.stop.assert_called_once()
    
    def test_shutdown_event_no_service(self):
        """Test shutdown when no service."""
        from src.hedgelock.position_manager.api import shutdown_event
        
        with patch('src.hedgelock.position_manager.api.position_service', None):
            # Should not raise error
            import asyncio
            asyncio.run(shutdown_event())