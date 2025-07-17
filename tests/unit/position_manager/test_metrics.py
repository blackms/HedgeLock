"""
Unit tests for Position Manager Metrics.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.hedgelock.position_manager.metrics import (
    MetricsCollector,
    position_delta, position_spot, position_long_perp, position_short_perp,
    pnl_unrealized, pnl_realized, pnl_total, pnl_roi,
    btc_price, volatility_24h, funding_rate,
    health_score, position_balance_score, funding_health_score,
    rehedge_total, profit_take_total, emergency_close_total, errors_total
)
from src.hedgelock.position_manager.models import PositionState, MarketRegime
from src.hedgelock.position_manager.pnl_calculator import PnLBreakdown


class TestMetricsCollector:
    """Test metrics collection functionality."""
    
    @pytest.fixture
    def collector(self):
        """Create metrics collector instance."""
        return MetricsCollector()
    
    @pytest.fixture
    def position_state(self):
        """Create test position state."""
        return PositionState(
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
            market_regime=MarketRegime.NEUTRAL,
            funding_regime='NORMAL'
        )
    
    @pytest.fixture
    def pnl_breakdown(self):
        """Create test P&L breakdown."""
        return PnLBreakdown(
            spot_pnl=540,
            long_perp_pnl=900,
            short_perp_pnl=-200,
            funding_pnl=-80,
            total_unrealized_pnl=1160,
            total_realized_pnl=3000,
            net_pnl=4160,
            timestamp=datetime.utcnow()
        )
    
    @pytest.fixture
    def pnl_metrics(self):
        """Create test P&L metrics."""
        return {
            'spot_pnl': 540,
            'long_perp_pnl': 900,
            'short_perp_pnl': -200,
            'funding_pnl': -80,
            'unrealized_pnl': 1160,
            'realized_pnl': 3000,
            'net_pnl': 4160,
            'roi_percent': 6.8,
            'position_value': 61200
        }
    
    def test_update_position_metrics(self, collector, position_state):
        """Test updating position metrics."""
        # Get initial values (should be 0)
        initial_delta = position_delta._value.get()
        
        # Update metrics
        collector.update_position_metrics(position_state)
        
        # Check gauge values
        assert position_spot._value.get() == 0.27
        assert position_long_perp._value.get() == 0.3
        assert position_short_perp._value.get() == 0.2
        assert position_delta._value.get() == 0.37
        
        # Market metrics
        assert btc_price._value.get() == 118000
        assert volatility_24h._value.get() == 0.025
        assert funding_rate._value.get() == 0.0002
    
    def test_update_pnl_metrics(self, collector, pnl_breakdown, pnl_metrics):
        """Test updating P&L metrics."""
        collector.update_pnl_metrics(pnl_breakdown, pnl_metrics)
        
        # Check P&L gauges
        assert pnl_unrealized._value.get() == 1160
        assert pnl_realized._value.get() == 3000
        assert pnl_total._value.get() == 4160
        assert pnl_roi._value.get() == 6.8
    
    def test_record_operations(self, collector):
        """Test recording various operations."""
        # Record rehedge
        initial_rehedges = rehedge_total.labels(trigger='periodic')._value.get()
        collector.record_rehedge('periodic')
        assert rehedge_total.labels(trigger='periodic')._value.get() == initial_rehedges + 1
        
        # Record profit take
        initial_profits = profit_take_total.labels(reason='target_reached')._value.get()
        collector.record_profit_take('target_reached')
        assert profit_take_total.labels(reason='target_reached')._value.get() == initial_profits + 1
        
        # Record emergency close
        initial_emergency = emergency_close_total.labels(reason='funding_extreme')._value.get()
        collector.record_emergency_close('funding_extreme')
        assert emergency_close_total.labels(reason='funding_extreme')._value.get() == initial_emergency + 1
        
        # Record error
        initial_errors = errors_total.labels(operation='rehedge')._value.get()
        collector.record_error('rehedge')
        assert errors_total.labels(operation='rehedge')._value.get() == initial_errors + 1
    
    def test_calculate_health_scores_balanced(self, collector, position_state, pnl_metrics):
        """Test health score calculation for balanced position."""
        # Make position perfectly balanced
        position_state.net_delta = position_state.spot_btc
        position_state.funding_regime = 'NORMAL'
        pnl_metrics['net_pnl'] = 5000  # Positive P&L
        
        scores = collector.calculate_health_scores(position_state, pnl_metrics)
        
        assert scores['balance'] == 100  # Perfect balance
        assert scores['funding'] == 100  # Normal funding
        assert scores['pnl'] == 100  # Positive P&L
        assert scores['overall'] == 100  # Perfect health
        
        # Check gauge values
        assert health_score._value.get() == 100
        assert position_balance_score._value.get() == 100
        assert funding_health_score._value.get() == 100
    
    def test_calculate_health_scores_imbalanced(self, collector, position_state, pnl_metrics):
        """Test health score for imbalanced position."""
        # Make position imbalanced
        position_state.net_delta = 0.77  # 0.5 BTC deviation from spot
        position_state.funding_regime = 'HEATED'
        pnl_metrics['net_pnl'] = -1000  # Negative P&L
        
        scores = collector.calculate_health_scores(position_state, pnl_metrics)
        
        assert scores['balance'] == 0  # 0.5 BTC deviation
        assert scores['funding'] == 70  # Heated funding
        assert scores['pnl'] == 50  # Negative P&L
        assert scores['overall'] == pytest.approx(40, rel=0.1)  # Average of 0, 70, 50
    
    def test_calculate_health_scores_extreme(self, collector, position_state, pnl_metrics):
        """Test health scores in extreme conditions."""
        position_state.net_delta = 1.27  # 1.0 BTC deviation
        position_state.funding_regime = 'EXTREME'
        pnl_metrics['net_pnl'] = -10000  # Large loss
        
        scores = collector.calculate_health_scores(position_state, pnl_metrics)
        
        assert scores['balance'] == 0  # Large deviation
        assert scores['funding'] == 10  # Extreme funding
        assert scores['pnl'] == 50  # Negative P&L
        assert scores['overall'] == pytest.approx(20, rel=0.1)
    
    def test_record_api_request(self, collector):
        """Test API request metrics recording."""
        # Record a successful GET request
        collector.record_api_request(
            method='GET',
            endpoint='/position',
            status=200,
            duration=0.025
        )
        
        # Check counter incremented
        # Note: Can't easily check specific label values without internal access
        # Just verify the method works without error
    
    def test_record_message_processed(self, collector):
        """Test message processing metrics."""
        # Record successful message
        collector.record_message_processed(
            topic='market_data',
            success=True,
            duration=0.01
        )
        
        # Record failed message
        collector.record_message_processed(
            topic='funding_context',
            success=False,
            duration=0.0
        )
        
        # Verify methods work without error
    
    def test_health_score_edge_cases(self, collector, position_state, pnl_metrics):
        """Test health score calculation edge cases."""
        # Test with unknown funding regime
        position_state.funding_regime = 'UNKNOWN'
        scores = collector.calculate_health_scores(position_state, pnl_metrics)
        assert scores['funding'] == 50  # Default for unknown
        
        # Test with exact 0.5 BTC deviation (boundary)
        position_state.net_delta = 0.77  # 0.5 BTC from 0.27
        position_state.funding_regime = 'NORMAL'
        scores = collector.calculate_health_scores(position_state, pnl_metrics)
        assert scores['balance'] == 0  # At boundary
        
        # Test with small deviation
        position_state.net_delta = 0.3  # 0.03 BTC deviation
        scores = collector.calculate_health_scores(position_state, pnl_metrics)
        assert scores['balance'] == 94  # Small deviation = high score