"""
Unit tests for funding calculator with 100% coverage.
"""

from datetime import datetime, timedelta

import pytest

from src.hedgelock.shared.funding_calculator import FundingCalculator
from src.hedgelock.shared.funding_models import (
    FundingContext,
    FundingRate,
    FundingRegime,
    FundingSnapshot,
)


class TestRegimeDetection:
    """Test funding regime detection logic."""

    @pytest.mark.parametrize(
        "rate,expected_regime",
        [
            (5.0, FundingRegime.NEUTRAL),  # < 10%
            (9.9, FundingRegime.NEUTRAL),  # Just under threshold
            (10.0, FundingRegime.NORMAL),  # Exactly at threshold
            (25.0, FundingRegime.NORMAL),  # Mid-range
            (49.9, FundingRegime.NORMAL),  # Just under next threshold
            (50.0, FundingRegime.HEATED),  # Exactly at threshold
            (75.0, FundingRegime.HEATED),  # Mid-range
            (99.9, FundingRegime.HEATED),  # Just under next threshold
            (100.0, FundingRegime.MANIA),  # Exactly at threshold
            (200.0, FundingRegime.MANIA),  # Mid-range
            (299.9, FundingRegime.MANIA),  # Just under next threshold
            (300.0, FundingRegime.EXTREME),  # Exactly at threshold
            (500.0, FundingRegime.EXTREME),  # Well above threshold
        ],
    )
    def test_detect_regime_positive_rates(self, rate, expected_regime):
        """Test regime detection for positive funding rates."""
        detected = FundingCalculator.detect_regime(rate)
        assert detected == expected_regime

    @pytest.mark.parametrize(
        "rate,expected_regime",
        [
            (-5.0, FundingRegime.NEUTRAL),  # Negative but low
            (-25.0, FundingRegime.NORMAL),  # Negative medium
            (-75.0, FundingRegime.HEATED),  # Negative high
            (-150.0, FundingRegime.MANIA),  # Negative very high
            (-400.0, FundingRegime.EXTREME),  # Negative extreme
        ],
    )
    def test_detect_regime_negative_rates(self, rate, expected_regime):
        """Test regime detection for negative funding rates."""
        detected = FundingCalculator.detect_regime(rate)
        assert detected == expected_regime


class TestPositionMultiplier:
    """Test position multiplier calculation."""

    def test_neutral_regime_multiplier(self):
        """Test multiplier in neutral regime."""
        multiplier = FundingCalculator.calculate_position_multiplier(
            FundingRegime.NEUTRAL, 5.0, 4.0
        )
        assert multiplier == 1.0  # Max multiplier in neutral

    def test_extreme_regime_multiplier(self):
        """Test multiplier in extreme regime."""
        multiplier = FundingCalculator.calculate_position_multiplier(
            FundingRegime.EXTREME, 400.0, 350.0
        )
        assert multiplier == 0.0  # Always 0 in extreme

    def test_normal_regime_scaling(self):
        """Test position scaling within normal regime."""
        # At lower bound (10%)
        multiplier_low = FundingCalculator.calculate_position_multiplier(
            FundingRegime.NORMAL, 10.0, 10.0
        )
        assert 0.85 <= multiplier_low <= 0.9  # Near max for regime

        # At upper bound (50%)
        multiplier_high = FundingCalculator.calculate_position_multiplier(
            FundingRegime.NORMAL, 49.0, 49.0
        )
        assert 0.6 <= multiplier_high <= 0.65  # Near min for regime

    def test_trending_adjustment(self):
        """Test multiplier adjustment based on trend."""
        # Decreasing funding (good)
        mult_decreasing = FundingCalculator.calculate_position_multiplier(
            FundingRegime.NORMAL, 20.0, 25.0  # Current < 24h avg
        )

        # Increasing funding (bad)
        mult_increasing = FundingCalculator.calculate_position_multiplier(
            FundingRegime.NORMAL, 25.0, 20.0  # Current > 24h avg
        )

        # Decreasing should have higher multiplier
        assert mult_decreasing > mult_increasing

    def test_heated_regime_bounds(self):
        """Test multiplier bounds in heated regime."""
        multiplier = FundingCalculator.calculate_position_multiplier(
            FundingRegime.HEATED, 75.0, 70.0
        )
        assert 0.3 <= multiplier <= 0.6  # Within heated bounds

    def test_mania_regime_bounds(self):
        """Test multiplier bounds in mania regime."""
        multiplier = FundingCalculator.calculate_position_multiplier(
            FundingRegime.MANIA, 200.0, 180.0
        )
        assert 0.1 <= multiplier <= 0.3  # Within mania bounds


class TestFundingContextCalculation:
    """Test complete funding context calculation."""

    @pytest.fixture
    def create_snapshot(self):
        """Factory for creating funding snapshots."""

        def _create(current_rate_value, rates_24h_values, rates_7d_values):
            base_time = datetime.utcnow()
            current = FundingRate(
                symbol="BTCUSDT",
                funding_rate=current_rate_value / 100 / 3 / 365,  # Convert from APR
                funding_time=base_time,
                mark_price=50000.0,
                index_price=50000.0,
            )

            rates_24h = []
            for i, value in enumerate(rates_24h_values):
                rate = FundingRate(
                    symbol="BTCUSDT",
                    funding_rate=value / 100 / 3 / 365,
                    funding_time=base_time - timedelta(hours=8 * i),
                    mark_price=50000.0,
                    index_price=50000.0,
                )
                rates_24h.append(rate)

            rates_7d = []
            for i, value in enumerate(rates_7d_values):
                rate = FundingRate(
                    symbol="BTCUSDT",
                    funding_rate=value / 100 / 3 / 365,
                    funding_time=base_time - timedelta(hours=8 * i),
                    mark_price=50000.0,
                    index_price=50000.0,
                )
                rates_7d.append(rate)

            return FundingSnapshot(
                symbol="BTCUSDT",
                current_rate=current,
                rates_24h=rates_24h,
                rates_7d=rates_7d,
            )

        return _create

    def test_context_normal_conditions(self, create_snapshot):
        """Test context calculation under normal conditions."""
        snapshot = create_snapshot(
            current_rate_value=25.0,  # 25% APR
            rates_24h_values=[20.0, 22.0, 24.0],
            rates_7d_values=[15.0, 18.0, 20.0, 22.0, 24.0, 25.0, 25.0],
        )

        context = FundingCalculator.calculate_funding_context(snapshot)

        assert context.current_regime == FundingRegime.NORMAL
        assert context.current_rate == 25.0
        assert context.position_multiplier > 0.6
        assert context.position_multiplier < 0.9
        assert context.should_exit is False
        assert context.regime_change is False  # No previous regime

    def test_context_extreme_conditions(self, create_snapshot):
        """Test context calculation under extreme conditions."""
        snapshot = create_snapshot(
            current_rate_value=450.0,  # 450% APR
            rates_24h_values=[400.0, 420.0, 440.0],
            rates_7d_values=[300.0, 350.0, 380.0, 400.0, 420.0, 440.0, 450.0],
        )

        context = FundingCalculator.calculate_funding_context(snapshot)

        assert context.current_regime == FundingRegime.EXTREME
        assert context.should_exit is True
        assert context.position_multiplier == 0.0

    def test_context_with_regime_change(self, create_snapshot):
        """Test context with regime change detection."""
        snapshot = create_snapshot(
            current_rate_value=55.0,  # HEATED
            rates_24h_values=[45.0, 48.0, 52.0],
            rates_7d_values=[30.0, 35.0, 40.0, 45.0, 48.0, 52.0, 55.0],
        )

        # First call - no previous regime
        context1 = FundingCalculator.calculate_funding_context(snapshot)
        assert context1.regime_change is False

        # Second call with previous regime
        context2 = FundingCalculator.calculate_funding_context(
            snapshot, previous_regime=FundingRegime.NORMAL
        )
        assert context2.regime_change is True
        assert context2.current_regime == FundingRegime.HEATED

    def test_cost_projections(self, create_snapshot):
        """Test cost projection calculations."""
        snapshot = create_snapshot(
            current_rate_value=36.5,  # 36.5% APR = 0.1% daily
            rates_24h_values=[36.5, 36.5, 36.5],
            rates_7d_values=[36.5] * 7,
        )

        context = FundingCalculator.calculate_funding_context(snapshot)

        # Daily cost should be ~10 basis points
        assert abs(context.daily_cost_bps - 10.0) < 0.1
        # Weekly cost should be ~0.7%
        assert abs(context.weekly_cost_pct - 0.7) < 0.01


class TestFundingRiskScore:
    """Test funding risk score calculation."""

    def test_low_risk_score(self):
        """Test risk score for low funding environment."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NEUTRAL,
            current_rate=5.0,
            avg_rate_24h=4.0,
            avg_rate_7d=3.0,
            max_rate_24h=6.0,
            volatility_24h=1.0,
            position_multiplier=1.0,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=1.37,
            weekly_cost_pct=0.096,
        )

        score = FundingCalculator.calculate_funding_risk_score(context)
        assert score < 20  # Low risk

    def test_high_risk_score(self):
        """Test risk score for high funding environment."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.MANIA,
            current_rate=200.0,
            avg_rate_24h=180.0,
            avg_rate_7d=150.0,
            max_rate_24h=220.0,
            volatility_24h=40.0,
            position_multiplier=0.2,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=54.8,
            weekly_cost_pct=3.84,
        )

        score = FundingCalculator.calculate_funding_risk_score(context)
        assert score > 70  # High risk

    def test_risk_score_components(self):
        """Test individual components of risk score."""
        # Test with rapidly increasing funding
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=80.0,
            avg_rate_24h=50.0,  # Much lower 24h avg
            avg_rate_7d=30.0,  # Even lower 7d avg
            max_rate_24h=85.0,
            volatility_24h=25.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=21.9,
            weekly_cost_pct=1.53,
        )

        score = FundingCalculator.calculate_funding_risk_score(context)
        # Should be high due to rapid increase
        assert score > 50

    def test_risk_score_bounds(self):
        """Test risk score stays within 0-100 bounds."""
        # Test maximum conditions
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=500.0,  # Extreme rate
            avg_rate_24h=400.0,
            avg_rate_7d=200.0,
            max_rate_24h=550.0,
            volatility_24h=100.0,  # High volatility
            position_multiplier=0.0,
            should_exit=True,
            regime_change=True,
            daily_cost_bps=137.0,
            weekly_cost_pct=9.59,
        )

        score = FundingCalculator.calculate_funding_risk_score(context)
        assert 0 <= score <= 100


class TestUtilityFunctions:
    """Test utility functions in calculator."""

    def test_project_funding_cost(self):
        """Test funding cost projection."""
        position_size = 100000  # $100k position
        funding_rate = 0.0001  # 0.01% per 8h

        # Default 24h (3 periods)
        cost_24h = FundingCalculator.project_funding_cost(position_size, funding_rate)
        assert cost_24h == 30.0  # $30

        # Custom periods
        cost_7d = FundingCalculator.project_funding_cost(
            position_size, funding_rate, periods=21  # 7 days
        )
        assert cost_7d == 210.0  # $210

    def test_recommend_action(self):
        """Test action recommendations."""
        # Test emergency exit
        context_exit = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=350.0,
            avg_rate_24h=300.0,
            avg_rate_7d=250.0,
            max_rate_24h=400.0,
            volatility_24h=50.0,
            position_multiplier=0.0,
            should_exit=True,
            regime_change=False,
            daily_cost_bps=95.9,
            weekly_cost_pct=6.71,
        )
        action, reason = FundingCalculator.recommend_action(context_exit)
        assert action == "exit_all"
        assert "extreme" in reason.lower()

        # Test regime change to high
        context_reduce = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.MANIA,
            current_rate=150.0,
            avg_rate_24h=120.0,
            avg_rate_7d=80.0,
            max_rate_24h=160.0,
            volatility_24h=30.0,
            position_multiplier=0.2,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=41.1,
            weekly_cost_pct=2.88,
        )
        action, reason = FundingCalculator.recommend_action(context_reduce)
        assert action == "reduce_position"
        assert "regime" in reason.lower()

        # Test return to neutral
        context_increase = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NEUTRAL,
            current_rate=8.0,
            avg_rate_24h=15.0,
            avg_rate_7d=25.0,
            max_rate_24h=20.0,
            volatility_24h=5.0,
            position_multiplier=1.0,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=2.19,
            weekly_cost_pct=0.15,
        )
        action, reason = FundingCalculator.recommend_action(context_increase)
        assert action == "increase_position"
        assert "neutral" in reason.lower()

        # Test heated trending higher
        context_trending = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=80.0,
            avg_rate_24h=70.0,  # Trending up
            avg_rate_7d=60.0,
            max_rate_24h=85.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=21.9,
            weekly_cost_pct=1.53,
        )
        action, reason = FundingCalculator.recommend_action(context_trending)
        assert action == "reduce_position"
        assert "trending higher" in reason.lower()

        # Test low multiplier maintenance
        context_maintain_low = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=65.0,
            avg_rate_24h=65.0,
            avg_rate_7d=65.0,
            max_rate_24h=70.0,
            volatility_24h=5.0,
            position_multiplier=0.45,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=17.8,
            weekly_cost_pct=1.25,
        )
        action, reason = FundingCalculator.recommend_action(context_maintain_low)
        assert action == "maintain_reduced"

        # Test normal maintenance
        context_maintain = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=30.0,
            avg_rate_24h=30.0,
            avg_rate_7d=30.0,
            max_rate_24h=35.0,
            volatility_24h=3.0,
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=8.22,
            weekly_cost_pct=0.58,
        )
        action, reason = FundingCalculator.recommend_action(context_maintain)
        assert action == "maintain_position"
        assert "acceptable" in reason.lower()
