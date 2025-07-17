"""
Unit tests for Position Manager models.
"""

import pytest
from datetime import datetime
from src.hedgelock.position_manager.models import (
    PositionState,
    HedgeDecision,
    ProfitTarget,
    PositionSide,
    MarketRegime
)


class TestPositionState:
    """Test PositionState model."""
    
    def test_position_state_creation(self):
        """Test creating a position state."""
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
        
        assert state.spot_btc == 0.27
        assert state.long_perp == 0.213
        assert state.short_perp == 0.213
        assert state.net_delta == 0.27
        assert state.btc_price == 116000
    
    def test_total_long_property(self):
        """Test total_long property calculation."""
        state = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.0,
            net_delta=0.483,
            hedge_ratio=0.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001
        )
        
        assert state.total_long == 0.483  # spot + long_perp
    
    def test_delta_neutral_property(self):
        """Test delta_neutral property."""
        # Delta neutral position
        state_neutral = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.0,
            short_perp=0.27,
            net_delta=0.0,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001
        )
        assert state_neutral.delta_neutral is True
        
        # Non-neutral position
        state_biased = PositionState(
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
        assert state_biased.delta_neutral is False
    
    def test_market_regime_enum(self):
        """Test market regime enum values."""
        state = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.0,
            short_perp=0.0,
            net_delta=0.27,
            hedge_ratio=0.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            market_regime=MarketRegime.LONG_BIASED
        )
        
        assert state.market_regime == MarketRegime.LONG_BIASED
        assert state.market_regime.value == "LONG_BIASED"
    
    def test_pnl_fields(self):
        """Test P&L tracking fields."""
        state = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.0,
            short_perp=0.0,
            net_delta=0.27,
            hedge_ratio=0.0,
            btc_price=120000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            unrealized_pnl=1000.0,
            realized_pnl=500.0,
            peak_pnl=1500.0
        )
        
        assert state.unrealized_pnl == 1000.0
        assert state.realized_pnl == 500.0
        assert state.peak_pnl == 1500.0


class TestHedgeDecision:
    """Test HedgeDecision model."""
    
    def test_hedge_decision_creation(self):
        """Test creating a hedge decision."""
        decision = HedgeDecision(
            timestamp=datetime.utcnow(),
            current_hedge_ratio=0.5,
            target_hedge_ratio=0.4,
            volatility_24h=0.03,
            reason="Volatility decrease",
            adjust_short=-0.05,
            adjust_long=0.05
        )
        
        assert decision.current_hedge_ratio == 0.5
        assert decision.target_hedge_ratio == 0.4
        assert decision.volatility_24h == 0.03
        assert decision.reason == "Volatility decrease"
        assert decision.adjust_short == -0.05
        assert decision.adjust_long == 0.05
    
    def test_hedge_decision_serialization(self):
        """Test hedge decision serialization."""
        decision = HedgeDecision(
            timestamp=datetime.utcnow(),
            current_hedge_ratio=0.6,
            target_hedge_ratio=0.4,
            volatility_24h=0.02,
            reason="Rehedge: vol=2.0%",
            adjust_short=0.1,
            adjust_long=-0.1
        )
        
        data = decision.model_dump()
        assert "timestamp" in data
        assert data["current_hedge_ratio"] == 0.6
        assert data["target_hedge_ratio"] == 0.4
        assert data["adjust_short"] == 0.1
        assert data["adjust_long"] == -0.1


class TestProfitTarget:
    """Test ProfitTarget model."""
    
    def test_profit_target_creation(self):
        """Test creating a profit target."""
        target = ProfitTarget(
            timestamp=datetime.utcnow(),
            target_price=120000,
            target_pnl=1000,
            trailing_stop_pct=0.30,
            volatility_multiplier=1.5
        )
        
        assert target.target_price == 120000
        assert target.target_pnl == 1000
        assert target.trailing_stop_pct == 0.30
        assert target.volatility_multiplier == 1.5
    
    def test_profit_target_defaults(self):
        """Test profit target default values."""
        target = ProfitTarget(
            timestamp=datetime.utcnow(),
            target_price=118000,
            target_pnl=500
        )
        
        assert target.trailing_stop_pct == 0.30  # Default
        assert target.volatility_multiplier == 1.5  # Default


class TestEnums:
    """Test enum values."""
    
    def test_position_side_enum(self):
        """Test PositionSide enum."""
        assert PositionSide.LONG.value == "LONG"
        assert PositionSide.SHORT.value == "SHORT"
        assert PositionSide.NEUTRAL.value == "NEUTRAL"
        
        # Test all values present
        assert len(PositionSide) == 3
    
    def test_market_regime_enum(self):
        """Test MarketRegime enum."""
        assert MarketRegime.NEUTRAL.value == "NEUTRAL"
        assert MarketRegime.LONG_BIASED.value == "LONG_BIASED"
        assert MarketRegime.SHORT_BIASED.value == "SHORT_BIASED"
        assert MarketRegime.TAKING_PROFIT.value == "TAKING_PROFIT"
        
        # Test all values present
        assert len(MarketRegime) == 4