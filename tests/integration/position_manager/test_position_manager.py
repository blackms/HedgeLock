"""
Integration tests for Position Manager.
"""

import pytest
from datetime import datetime
from src.hedgelock.position_manager.manager import DeltaNeutralManager
from src.hedgelock.position_manager.models import PositionState, MarketRegime


def test_delta_calculation():
    """Test delta calculation."""
    manager = DeltaNeutralManager()
    
    state = PositionState(
        timestamp=datetime.utcnow(),
        spot_btc=0.27,
        long_perp=0.213,
        short_perp=0.213,
        net_delta=0.27,
        hedge_ratio=1.0,
        btc_price=116000,
        volatility_24h=0.02,
        funding_rate=0.0001
    )
    
    delta = manager.calculate_delta(state)
    assert abs(delta - 0.27) < 0.001  # Should equal spot position


def test_hedge_ratio_calculation():
    """Test volatility-based hedge ratio."""
    manager = DeltaNeutralManager()
    
    assert manager.calculate_hedge_ratio(0.01) == 0.20  # Low vol
    assert manager.calculate_hedge_ratio(0.03) == 0.40  # Med vol
    assert manager.calculate_hedge_ratio(0.05) == 0.60  # High vol


def test_funding_multiplier():
    """Test funding-based position scaling."""
    manager = DeltaNeutralManager()
    
    assert manager.apply_funding_multiplier(1.0, "NORMAL") == 1.0
    assert manager.apply_funding_multiplier(1.0, "HEATED") == 0.5
    assert manager.apply_funding_multiplier(1.0, "EXTREME") == 0.0


def test_hedge_decision_generation():
    """Test hedge decision generation."""
    manager = DeltaNeutralManager()
    
    state = PositionState(
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
    
    # Generate decision for delta-neutral target
    decision = manager.generate_hedge_decision(state, target_delta=0.0)
    
    assert decision.target_hedge_ratio == 0.40  # Med volatility
    assert abs(decision.adjust_short + decision.adjust_long + 0.27) < 0.001  # Should reduce delta by 0.27


def test_profit_target_calculation():
    """Test profit target calculation."""
    manager = DeltaNeutralManager()
    
    # 2% volatility, $100k price
    target = manager.calculate_profit_target(0.02, 100000)
    expected = 100000 * (1 + 1.5 * 0.02)  # PT = price * (1 + k*σ)
    assert abs(target - expected) < 0.01


def test_trailing_stop_logic():
    """Test trailing stop detection."""
    manager = DeltaNeutralManager()
    
    # Position with profit
    state = PositionState(
        timestamp=datetime.utcnow(),
        spot_btc=0.27,
        long_perp=0.213,
        short_perp=0.213,
        net_delta=0.27,
        hedge_ratio=1.0,
        btc_price=120000,
        volatility_24h=0.02,
        funding_rate=0.0001,
        unrealized_pnl=1000,
        peak_pnl=1500  # Had higher PnL before
    )
    
    # 33% drawdown from peak - should trigger
    should_take_profit = manager.check_profit_targets(state)
    assert should_take_profit is True


def test_no_profit_no_target():
    """Test that no profit target is triggered when in loss."""
    manager = DeltaNeutralManager()
    
    state = PositionState(
        timestamp=datetime.utcnow(),
        spot_btc=0.27,
        long_perp=0.213,
        short_perp=0.213,
        net_delta=0.27,
        hedge_ratio=1.0,
        btc_price=110000,
        volatility_24h=0.02,
        funding_rate=0.0001,
        unrealized_pnl=-500  # In loss
    )
    
    should_take_profit = manager.check_profit_targets(state)
    assert should_take_profit is False