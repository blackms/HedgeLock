"""
Unit tests for DeltaNeutralManager.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from src.hedgelock.position_manager.manager import DeltaNeutralManager
from src.hedgelock.position_manager.models import PositionState, MarketRegime


class TestDeltaNeutralManager:
    """Test DeltaNeutralManager class."""
    
    @pytest.fixture
    def manager(self):
        """Create a manager instance."""
        return DeltaNeutralManager()
    
    @pytest.fixture
    def position_state(self):
        """Create a sample position state."""
        return PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            funding_regime="NORMAL"
        )
    
    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager.position_state is None
        assert manager.price_history == []
        assert isinstance(manager.last_hedge_update, datetime)
    
    def test_calculate_delta(self, manager, position_state):
        """Test delta calculation."""
        # Delta = spot + long - short
        delta = manager.calculate_delta(position_state)
        expected = 0.27 + 0.213 - 0.213
        assert delta == expected
        assert delta == 0.27
    
    def test_calculate_delta_various_positions(self, manager):
        """Test delta calculation with various positions."""
        # All long
        state_long = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.5,
            long_perp=0.3,
            short_perp=0.0,
            net_delta=0.8,
            hedge_ratio=0.0,
            btc_price=100000,
            volatility_24h=0.02,
            funding_rate=0.0001
        )
        assert manager.calculate_delta(state_long) == 0.8
        
        # Delta neutral
        state_neutral = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.5,
            long_perp=0.0,
            short_perp=0.5,
            net_delta=0.0,
            hedge_ratio=1.0,
            btc_price=100000,
            volatility_24h=0.02,
            funding_rate=0.0001
        )
        assert manager.calculate_delta(state_neutral) == 0.0
        
        # Net short
        state_short = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.2,
            long_perp=0.0,
            short_perp=0.5,
            net_delta=-0.3,
            hedge_ratio=1.0,
            btc_price=100000,
            volatility_24h=0.02,
            funding_rate=0.0001
        )
        assert manager.calculate_delta(state_short) == -0.3
    
    def test_calculate_volatility_empty_prices(self, manager):
        """Test volatility calculation with empty price list."""
        vol = manager.calculate_volatility_24h([])
        assert vol == 0.02  # Default
        
        vol = manager.calculate_volatility_24h([100000])
        assert vol == 0.02  # Default for single price
    
    def test_calculate_volatility_24h(self, manager):
        """Test 24h volatility calculation."""
        # Create price series with known volatility
        prices = [100000]
        for i in range(23):
            # Add some random walk
            change = np.random.normal(0, 0.01)  # 1% std dev
            prices.append(prices[-1] * (1 + change))
        
        vol = manager.calculate_volatility_24h(prices)
        # Should be annualized volatility
        assert 0 < vol < 1  # Between 0% and 100%
    
    def test_calculate_hedge_ratio_low_vol(self, manager):
        """Test hedge ratio for low volatility."""
        ratio = manager.calculate_hedge_ratio(0.01)  # 1% vol
        assert ratio == 0.20
        
        ratio = manager.calculate_hedge_ratio(0.019)  # 1.9% vol
        assert ratio == 0.20
    
    def test_calculate_hedge_ratio_medium_vol(self, manager):
        """Test hedge ratio for medium volatility."""
        ratio = manager.calculate_hedge_ratio(0.02)  # 2% vol
        assert ratio == 0.40
        
        ratio = manager.calculate_hedge_ratio(0.03)  # 3% vol
        assert ratio == 0.40
        
        ratio = manager.calculate_hedge_ratio(0.039)  # 3.9% vol
        assert ratio == 0.40
    
    def test_calculate_hedge_ratio_high_vol(self, manager):
        """Test hedge ratio for high volatility."""
        ratio = manager.calculate_hedge_ratio(0.04)  # 4% vol
        assert ratio == 0.60
        
        ratio = manager.calculate_hedge_ratio(0.05)  # 5% vol
        assert ratio == 0.60
        
        ratio = manager.calculate_hedge_ratio(0.10)  # 10% vol
        assert ratio == 0.60
    
    def test_calculate_profit_target(self, manager):
        """Test profit target calculation."""
        # PT = current_price * (1 + k * σ_24h), k=1.5
        target = manager.calculate_profit_target(0.02, 100000)
        expected = 100000 * (1 + 1.5 * 0.02)
        assert target == expected
        assert target == 103000
        
        # Higher volatility
        target = manager.calculate_profit_target(0.04, 100000)
        expected = 100000 * (1 + 1.5 * 0.04)
        assert target == expected
        assert target == 106000
    
    def test_should_rehedge_timing(self, manager):
        """Test rehedge timing logic."""
        # Just initialized - should rehedge
        assert manager.should_rehedge() is False  # Within 1 hour
        
        # Set last update to 2 hours ago
        manager.last_hedge_update = datetime.utcnow() - timedelta(hours=2)
        assert manager.should_rehedge() is True
        
        # Set to 30 minutes ago
        manager.last_hedge_update = datetime.utcnow() - timedelta(minutes=30)
        assert manager.should_rehedge() is False
    
    def test_apply_funding_multiplier(self, manager):
        """Test funding-based position multipliers."""
        base_position = 1.0
        
        # NEUTRAL/NORMAL - full position
        assert manager.apply_funding_multiplier(base_position, "NEUTRAL") == 1.0
        assert manager.apply_funding_multiplier(base_position, "NORMAL") == 1.0
        
        # HEATED - half position
        assert manager.apply_funding_multiplier(base_position, "HEATED") == 0.5
        
        # MANIA - 20% position
        assert manager.apply_funding_multiplier(base_position, "MANIA") == 0.2
        
        # EXTREME - no position
        assert manager.apply_funding_multiplier(base_position, "EXTREME") == 0.0
        
        # Unknown regime - default to full
        assert manager.apply_funding_multiplier(base_position, "UNKNOWN") == 1.0
    
    def test_generate_hedge_decision_reduce_delta(self, manager, position_state):
        """Test hedge decision when reducing delta."""
        # Current delta is 0.27, target is 0
        decision = manager.generate_hedge_decision(position_state, target_delta=0.0)
        
        assert decision.current_hedge_ratio == 1.0
        assert decision.target_hedge_ratio == 0.4  # Medium volatility
        assert decision.volatility_24h == 0.02
        assert "vol=2.0%" in decision.reason
        
        # Delta adjustment needed: 0.0 - 0.27 = -0.27
        # Since delta_adjustment < 0:
        # adjust_short = 0.27 * 0.4 = 0.108
        # adjust_long = -0.27 * 0.6 = -0.162
        assert decision.adjust_short == pytest.approx(0.108, abs=0.001)
        assert decision.adjust_long == pytest.approx(-0.162, abs=0.001)
    
    def test_generate_hedge_decision_increase_delta(self, manager):
        """Test hedge decision when increasing delta."""
        state = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.1,
            long_perp=0.0,
            short_perp=0.2,
            net_delta=-0.1,
            hedge_ratio=1.0,
            btc_price=100000,
            volatility_24h=0.03,
            funding_rate=0.0001,
            funding_regime="NORMAL"
        )
        
        # Current delta is -0.1, target is 0.1
        decision = manager.generate_hedge_decision(state, target_delta=0.1)
        
        # Delta adjustment needed: 0.1 - (-0.1) = 0.2
        assert decision.adjust_short < 0  # Reduce short
        assert decision.adjust_long > 0   # Increase long
    
    def test_generate_hedge_decision_with_funding(self, manager, position_state):
        """Test hedge decision with funding adjustment."""
        position_state.funding_regime = "HEATED"
        position_state.volatility_24h = 0.05  # High vol
        
        decision = manager.generate_hedge_decision(position_state, target_delta=0.0)
        
        # High vol gives 0.6 ratio, HEATED multiplier is 0.5
        assert decision.target_hedge_ratio == 0.6 * 0.5
        assert decision.target_hedge_ratio == 0.3
    
    def test_check_profit_targets_no_profit(self, manager, position_state):
        """Test profit target check with no profit."""
        position_state.unrealized_pnl = -100
        assert manager.check_profit_targets(position_state) is False
        
        position_state.unrealized_pnl = 0
        assert manager.check_profit_targets(position_state) is False
    
    def test_check_profit_targets_trailing_stop(self, manager, position_state):
        """Test trailing stop trigger."""
        position_state.unrealized_pnl = 699  # 30.1% drawdown
        position_state.peak_pnl = 1000
        
        # >30% drawdown from peak should trigger
        assert manager.check_profit_targets(position_state) is True
        
        # Update peak
        position_state.unrealized_pnl = 1100
        assert manager.check_profit_targets(position_state) is False
        assert position_state.peak_pnl == 1100  # Peak updated
        
        # 20% drawdown - not triggered
        position_state.unrealized_pnl = 880
        assert manager.check_profit_targets(position_state) is False
    
    def test_check_profit_targets_volatility_based(self, manager, position_state):
        """Test volatility-based profit target."""
        # Profit target calculation: PT = current_price * (1 + k * σ)
        # With 2% vol, target_price = 116000 * (1 + 1.5 * 0.02) = 119480
        # Target move = 119480 / 116000 - 1 = 3%
        
        position_state.unrealized_pnl = 100
        position_state.btc_price = 119480  # Exactly 3% move
        
        assert manager.check_profit_targets(position_state) is True
        
        # Less than target move
        position_state.btc_price = 118000  # ~1.7% move
        assert manager.check_profit_targets(position_state) is False
    
    def test_price_history_management(self, manager):
        """Test price history tracking."""
        assert len(manager.price_history) == 0
        
        # Add some prices
        for price in [100000, 101000, 102000]:
            manager.price_history.append(price)
        
        assert len(manager.price_history) == 3
        assert manager.price_history[-1] == 102000