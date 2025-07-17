"""
Unit tests for P&L API endpoint.
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from src.hedgelock.position_manager.api import app
from src.hedgelock.position_manager.models import PositionState, MarketRegime
from src.hedgelock.position_manager.pnl_calculator import PnLBreakdown


class TestPnLAPI:
    """Test P&L API endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_service(self):
        """Create mock position service with P&L calculator."""
        service = Mock()
        service.running = True
        
        # Mock position state
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.3,
            short_perp=0.2,
            net_delta=0.37,
            hedge_ratio=0.8,
            btc_price=118000,
            volatility_24h=0.025,
            funding_rate=0.0002,
            unrealized_pnl=1500,
            realized_pnl=3000,
            peak_pnl=2000,
            market_regime=MarketRegime.NEUTRAL
        )
        
        # Mock P&L calculator
        service.pnl_calculator = Mock()
        service.pnl_calculator.entry_prices = {
            'spot': 116000,
            'long_perp': 115000,
            'short_perp': 117000
        }
        
        # Mock P&L breakdown
        mock_breakdown = PnLBreakdown(
            spot_pnl=540,  # (118000-116000)*0.27
            long_perp_pnl=900,  # (118000-115000)*0.3
            short_perp_pnl=200,  # (117000-118000)*0.2
            funding_pnl=-80,
            total_unrealized_pnl=1560,
            total_realized_pnl=3000,
            net_pnl=4560,
            timestamp=datetime.utcnow()
        )
        service.pnl_calculator.calculate_pnl.return_value = mock_breakdown
        
        # Mock P&L metrics
        service.pnl_calculator.get_pnl_metrics.return_value = {
            'spot_pnl': 540,
            'long_perp_pnl': 900,
            'short_perp_pnl': 200,
            'funding_pnl': -80,
            'unrealized_pnl': 1560,
            'realized_pnl': 3000,
            'net_pnl': 4560,
            'roi_percent': 7.5,
            'cumulative_funding_paid': 150,
            'cumulative_funding_received': 70,
            'position_value': 60840  # Total position value in USD
        }
        
        return service
    
    def test_get_pnl_report_success(self, client, mock_service):
        """Test successful P&L report retrieval."""
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/pnl")
            
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert 'timestamp' in data
        assert 'pnl_breakdown' in data
        assert 'metrics' in data
        assert 'entry_prices' in data
        assert 'position_value' in data
        assert 'roi_percent' in data
        
        # Check P&L breakdown
        breakdown = data['pnl_breakdown']
        assert breakdown['spot_pnl'] == 540
        assert breakdown['long_perp_pnl'] == 900
        assert breakdown['short_perp_pnl'] == 200
        assert breakdown['funding_pnl'] == -80
        assert breakdown['total_unrealized'] == 1560
        assert breakdown['total_realized'] == 3000
        assert breakdown['net_pnl'] == 4560
        
        # Check metrics
        metrics = data['metrics']
        assert metrics['roi_percent'] == 7.5
        assert metrics['cumulative_funding_paid'] == 150
        assert metrics['cumulative_funding_received'] == 70
        
        # Check entry prices
        assert data['entry_prices']['spot'] == 116000
        assert data['entry_prices']['long_perp'] == 115000
        assert data['entry_prices']['short_perp'] == 117000
        
        # Check summary values
        assert data['position_value'] == 60840
        assert data['roi_percent'] == 7.5
    
    def test_get_pnl_report_no_service(self, client):
        """Test P&L report when service not initialized."""
        with patch('src.hedgelock.position_manager.api.position_service', None):
            response = client.get("/pnl")
            
        assert response.status_code == 503
        assert response.json()['detail'] == "Service not initialized"
    
    def test_get_pnl_report_no_calculator(self, client):
        """Test P&L report when calculator not initialized."""
        mock_service = Mock()
        mock_service.running = True
        # No pnl_calculator attribute
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/pnl")
            
        assert response.status_code == 503
        assert response.json()['detail'] == "P&L calculator not initialized"
    
    def test_position_endpoint_includes_pnl(self, client, mock_service):
        """Test that position endpoint includes P&L data."""
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/position")
            
        assert response.status_code == 200
        data = response.json()
        
        # Check P&L section
        assert 'pnl' in data
        pnl = data['pnl']
        assert pnl['unrealized'] == 1500
        assert pnl['realized'] == 3000
        assert pnl['peak'] == 2000
    
    def test_pnl_with_negative_values(self, client, mock_service):
        """Test P&L report with losses."""
        # Set up losing positions
        mock_breakdown = PnLBreakdown(
            spot_pnl=-500,
            long_perp_pnl=-800,
            short_perp_pnl=300,
            funding_pnl=-120,
            total_unrealized_pnl=-1120,
            total_realized_pnl=-500,
            net_pnl=-1620,
            timestamp=datetime.utcnow()
        )
        mock_service.pnl_calculator.calculate_pnl.return_value = mock_breakdown
        
        mock_service.pnl_calculator.get_pnl_metrics.return_value = {
            'spot_pnl': -500,
            'long_perp_pnl': -800,
            'short_perp_pnl': 300,
            'funding_pnl': -120,
            'unrealized_pnl': -1120,
            'realized_pnl': -500,
            'net_pnl': -1620,
            'roi_percent': -2.5,
            'cumulative_funding_paid': 200,
            'cumulative_funding_received': 80,
            'position_value': 64800
        }
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/pnl")
            
        assert response.status_code == 200
        data = response.json()
        
        # Check negative values are properly reported
        breakdown = data['pnl_breakdown']
        assert breakdown['spot_pnl'] == -500
        assert breakdown['long_perp_pnl'] == -800
        assert breakdown['net_pnl'] == -1620
        
        assert data['roi_percent'] == -2.5
    
    def test_pnl_with_zero_positions(self, client, mock_service):
        """Test P&L report with no positions."""
        # Set up zero positions
        mock_service.current_position.spot_btc = 0
        mock_service.current_position.long_perp = 0
        mock_service.current_position.short_perp = 0
        
        mock_breakdown = PnLBreakdown(
            spot_pnl=0,
            long_perp_pnl=0,
            short_perp_pnl=0,
            funding_pnl=0,
            total_unrealized_pnl=0,
            total_realized_pnl=1000,  # Previous realized P&L
            net_pnl=1000,
            timestamp=datetime.utcnow()
        )
        mock_service.pnl_calculator.calculate_pnl.return_value = mock_breakdown
        
        mock_service.pnl_calculator.get_pnl_metrics.return_value = {
            'spot_pnl': 0,
            'long_perp_pnl': 0,
            'short_perp_pnl': 0,
            'funding_pnl': 0,
            'unrealized_pnl': 0,
            'realized_pnl': 1000,
            'net_pnl': 1000,
            'roi_percent': 0,
            'position_value': 0
        }
        
        with patch('src.hedgelock.position_manager.api.position_service', mock_service):
            response = client.get("/pnl")
            
        assert response.status_code == 200
        data = response.json()
        
        # Should show zero unrealized but retain realized P&L
        assert data['pnl_breakdown']['total_unrealized'] == 0
        assert data['pnl_breakdown']['total_realized'] == 1000
        assert data['pnl_breakdown']['net_pnl'] == 1000
        assert data['position_value'] == 0