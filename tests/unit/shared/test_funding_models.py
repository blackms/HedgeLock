"""
Unit tests for funding models with 100% coverage.
"""

import pytest
from datetime import datetime, timedelta
from src.hedgelock.shared.funding_models import (
    FundingRegime, FundingRate, FundingSnapshot, FundingContext,
    FundingDecision, FundingAlert, FundingRateMessage, FundingContextMessage
)


class TestFundingRegime:
    """Test FundingRegime enum."""
    
    def test_all_regimes_defined(self):
        """Test all funding regimes are properly defined."""
        assert FundingRegime.NEUTRAL == "neutral"
        assert FundingRegime.NORMAL == "normal"
        assert FundingRegime.HEATED == "heated"
        assert FundingRegime.MANIA == "mania"
        assert FundingRegime.EXTREME == "extreme"
        
    def test_regime_ordering(self):
        """Test regime severity ordering."""
        regimes = list(FundingRegime)
        assert regimes[0] == FundingRegime.NEUTRAL
        assert regimes[-1] == FundingRegime.EXTREME


class TestFundingRate:
    """Test FundingRate model."""
    
    @pytest.fixture
    def sample_funding_rate(self):
        """Create a sample funding rate."""
        return FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0001,  # 0.01% per 8 hours
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
    
    def test_funding_rate_creation(self, sample_funding_rate):
        """Test funding rate model creation."""
        assert sample_funding_rate.symbol == "BTCUSDT"
        assert sample_funding_rate.funding_rate == 0.0001
        assert sample_funding_rate.mark_price == 50000.0
        assert sample_funding_rate.index_price == 50000.0
        
    def test_annualized_rate_calculation(self, sample_funding_rate):
        """Test annualized rate calculation."""
        # 0.01% * 3 * 365 = 10.95%
        expected = 0.0001 * 3 * 365 * 100
        assert sample_funding_rate.annualized_rate == expected
        assert abs(sample_funding_rate.annualized_rate - 10.95) < 0.01
        
    def test_daily_rate_calculation(self, sample_funding_rate):
        """Test daily rate calculation."""
        # 0.01% * 3 = 0.03%
        expected = 0.0001 * 3 * 100
        assert sample_funding_rate.daily_rate == expected
        assert abs(sample_funding_rate.daily_rate - 0.03) < 0.001
        
    def test_negative_funding_rate(self):
        """Test negative funding rate handling."""
        rate = FundingRate(
            symbol="BTCUSDT",
            funding_rate=-0.0002,  # -0.02%
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
        assert rate.annualized_rate == -21.9  # -0.02% * 3 * 365
        assert rate.daily_rate == -0.06  # -0.02% * 3


class TestFundingSnapshot:
    """Test FundingSnapshot model."""
    
    @pytest.fixture
    def sample_rates(self):
        """Create sample funding rates for testing."""
        base_time = datetime.utcnow()
        rates = []
        # Create rates with increasing values
        for i in range(10):
            rate = FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0001 * (i + 1),  # 0.01% to 0.10%
                funding_time=base_time - timedelta(hours=8*i),
                mark_price=50000.0,
                index_price=50000.0
            )
            rates.append(rate)
        return rates
    
    def test_snapshot_creation(self, sample_rates):
        """Test funding snapshot creation."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=sample_rates[:3],  # Last 3 rates (24h)
            rates_7d=sample_rates  # All rates (7d)
        )
        assert snapshot.symbol == "BTCUSDT"
        assert len(snapshot.rates_24h) == 3
        assert len(snapshot.rates_7d) == 10
        
    def test_avg_rate_24h(self, sample_rates):
        """Test 24h average rate calculation."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=sample_rates[:3]  # 0.01%, 0.02%, 0.03%
        )
        # Average of annualized rates
        expected = sum(r.annualized_rate for r in sample_rates[:3]) / 3
        assert abs(snapshot.avg_rate_24h - expected) < 0.01
        
    def test_avg_rate_24h_empty(self, sample_rates):
        """Test 24h average with no historical data."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=[]
        )
        assert snapshot.avg_rate_24h == sample_rates[0].annualized_rate
        
    def test_avg_rate_7d(self, sample_rates):
        """Test 7d average rate calculation."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=sample_rates[:3],
            rates_7d=sample_rates
        )
        expected = sum(r.annualized_rate for r in sample_rates) / len(sample_rates)
        assert abs(snapshot.avg_rate_7d - expected) < 0.01
        
    def test_avg_rate_7d_empty(self, sample_rates):
        """Test 7d average with no historical data."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=sample_rates[:3],
            rates_7d=[]
        )
        # Should fall back to 24h average
        assert snapshot.avg_rate_7d == snapshot.avg_rate_24h
        
    def test_max_rate_24h(self, sample_rates):
        """Test maximum rate in 24h."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=sample_rates[:3]
        )
        expected = max(r.annualized_rate for r in sample_rates[:3])
        assert snapshot.max_rate_24h == expected
        
    def test_volatility_24h(self, sample_rates):
        """Test funding rate volatility calculation."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=sample_rates[:3]
        )
        # Calculate expected standard deviation
        rates = [r.annualized_rate for r in sample_rates[:3]]
        avg = sum(rates) / len(rates)
        variance = sum((r - avg) ** 2 for r in rates) / len(rates)
        expected_vol = variance ** 0.5
        assert abs(snapshot.volatility_24h - expected_vol) < 0.01
        
    def test_volatility_insufficient_data(self, sample_rates):
        """Test volatility with insufficient data."""
        snapshot = FundingSnapshot(
            symbol="BTCUSDT",
            current_rate=sample_rates[0],
            rates_24h=[sample_rates[0]]  # Only one rate
        )
        assert snapshot.volatility_24h == 0.0


class TestFundingContext:
    """Test FundingContext model."""
    
    @pytest.fixture
    def sample_context(self):
        """Create a sample funding context."""
        return FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=20.0,
            avg_rate_7d=15.0,
            max_rate_24h=30.0,
            volatility_24h=5.0,
            position_multiplier=0.8,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=7.5,
            weekly_cost_pct=0.525,
            trace_id="test-trace-123"
        )
    
    def test_context_creation(self, sample_context):
        """Test funding context creation."""
        assert sample_context.symbol == "BTCUSDT"
        assert sample_context.current_regime == FundingRegime.NORMAL
        assert sample_context.current_rate == 25.0
        assert sample_context.position_multiplier == 0.8
        
    def test_position_multiplier_bounds(self):
        """Test position multiplier validation."""
        # Should accept valid values
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=20.0,
            avg_rate_7d=15.0,
            max_rate_24h=30.0,
            volatility_24h=5.0,
            position_multiplier=0.5,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=7.5,
            weekly_cost_pct=0.525
        )
        assert context.position_multiplier == 0.5
        
        # Test bounds
        with pytest.raises(ValueError):
            FundingContext(
                symbol="BTCUSDT",
                current_regime=FundingRegime.NORMAL,
                current_rate=25.0,
                avg_rate_24h=20.0,
                avg_rate_7d=15.0,
                max_rate_24h=30.0,
                volatility_24h=5.0,
                position_multiplier=1.1,  # > 1.0
                should_exit=False,
                regime_change=False,
                daily_cost_bps=7.5,
                weekly_cost_pct=0.525
            )
            
    def test_emergency_exit_context(self):
        """Test context with emergency exit."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=350.0,  # 350% APR
            avg_rate_24h=300.0,
            avg_rate_7d=250.0,
            max_rate_24h=400.0,
            volatility_24h=50.0,
            position_multiplier=0.0,
            should_exit=True,
            regime_change=True,
            daily_cost_bps=95.9,
            weekly_cost_pct=6.71
        )
        assert context.should_exit is True
        assert context.position_multiplier == 0.0
        assert context.current_regime == FundingRegime.EXTREME


class TestFundingDecision:
    """Test FundingDecision model."""
    
    @pytest.fixture
    def sample_context(self):
        """Create sample context for decision."""
        return FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=75.0,
            avg_rate_24h=70.0,
            avg_rate_7d=60.0,
            max_rate_24h=80.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=20.5,
            weekly_cost_pct=1.44
        )
    
    def test_decision_creation(self, sample_context):
        """Test funding decision creation."""
        decision = FundingDecision(
            context=sample_context,
            action="reduce_position",
            position_adjustment=0.4,
            max_position_size=2.0,
            reason="Funding regime changed to HEATED",
            urgency="high",
            funding_risk_score=75.0,
            projected_cost_24h=150.0,
            trace_id="test-trace-123"
        )
        assert decision.action == "reduce_position"
        assert decision.position_adjustment == 0.4
        assert decision.urgency == "high"
        assert decision.funding_risk_score == 75.0
        
    def test_risk_score_bounds(self, sample_context):
        """Test risk score validation."""
        with pytest.raises(ValueError):
            FundingDecision(
                context=sample_context,
                action="maintain",
                position_adjustment=1.0,
                max_position_size=10.0,
                reason="Test",
                urgency="low",
                funding_risk_score=101.0,  # > 100
                projected_cost_24h=0.0
            )


class TestFundingAlert:
    """Test FundingAlert model."""
    
    def test_regime_change_alert(self):
        """Test regime change alert creation."""
        alert = FundingAlert(
            alert_type="regime_change",
            severity="warning",
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            previous_regime=FundingRegime.NORMAL,
            current_rate=75.0,
            threshold_breached=50.0,
            title="Funding Regime Change",
            message="Funding regime changed from NORMAL to HEATED",
            recommended_action="Consider reducing position size",
            trace_id="test-trace-123"
        )
        assert alert.alert_type == "regime_change"
        assert alert.severity == "warning"
        assert alert.previous_regime == FundingRegime.NORMAL
        
    def test_emergency_alert(self):
        """Test emergency alert creation."""
        alert = FundingAlert(
            alert_type="emergency",
            severity="critical",
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=400.0,
            threshold_breached=300.0,
            title="Emergency: Extreme Funding Rate",
            message="Funding rate exceeded 300% APR",
            recommended_action="Exit all positions immediately"
        )
        assert alert.severity == "critical"
        assert alert.recommended_action == "Exit all positions immediately"


class TestKafkaMessages:
    """Test Kafka message models."""
    
    def test_funding_rate_message(self):
        """Test FundingRateMessage creation."""
        rate = FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0001,
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
        message = FundingRateMessage(
            service="collector",
            funding_rate=rate,
            trace_id="test-trace-123"
        )
        assert message.service == "collector"
        assert message.funding_rate.symbol == "BTCUSDT"
        assert message.trace_id == "test-trace-123"
        
    def test_funding_context_message(self):
        """Test FundingContextMessage creation."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=20.0,
            avg_rate_7d=15.0,
            max_rate_24h=30.0,
            volatility_24h=5.0,
            position_multiplier=0.8,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=7.5,
            weekly_cost_pct=0.525
        )
        decision = FundingDecision(
            context=context,
            action="maintain",
            position_adjustment=1.0,
            max_position_size=10.0,
            reason="Funding within normal range",
            urgency="low",
            funding_risk_score=25.0,
            projected_cost_24h=50.0
        )
        message = FundingContextMessage(
            service="funding_engine",
            funding_context=context,
            funding_decision=decision,
            trace_id="test-trace-123"
        )
        assert message.service == "funding_engine"
        assert message.funding_context.current_regime == FundingRegime.NORMAL
        assert message.funding_decision.action == "maintain"