"""
Funding rate calculations and regime detection.
"""

from typing import List, Tuple

from src.hedgelock.shared.funding_models import (
    FundingContext,
    FundingRate,
    FundingRegime,
    FundingSnapshot,
)


class FundingCalculator:
    """Calculator for funding rate analysis and regime detection."""

    # Regime thresholds (annualized percentage)
    REGIME_THRESHOLDS = {
        FundingRegime.NEUTRAL: 10.0,
        FundingRegime.NORMAL: 50.0,
        FundingRegime.HEATED: 100.0,
        FundingRegime.MANIA: 300.0,
    }

    # Position multiplier ranges
    POSITION_MULTIPLIERS = {
        FundingRegime.NEUTRAL: (0.9, 1.0),  # 90-100% of max position
        FundingRegime.NORMAL: (0.6, 0.9),  # 60-90% of max position
        FundingRegime.HEATED: (0.3, 0.6),  # 30-60% of max position
        FundingRegime.MANIA: (0.1, 0.3),  # 10-30% of max position
        FundingRegime.EXTREME: (0.0, 0.0),  # 0% - exit all positions
    }

    @classmethod
    def detect_regime(cls, annualized_rate: float) -> FundingRegime:
        """Detect funding regime based on annualized rate."""
        rate_abs = abs(annualized_rate)

        if rate_abs < cls.REGIME_THRESHOLDS[FundingRegime.NEUTRAL]:
            return FundingRegime.NEUTRAL
        elif rate_abs < cls.REGIME_THRESHOLDS[FundingRegime.NORMAL]:
            return FundingRegime.NORMAL
        elif rate_abs < cls.REGIME_THRESHOLDS[FundingRegime.HEATED]:
            return FundingRegime.HEATED
        elif rate_abs < cls.REGIME_THRESHOLDS[FundingRegime.MANIA]:
            return FundingRegime.MANIA
        else:
            return FundingRegime.EXTREME

    @classmethod
    def calculate_position_multiplier(
        cls, regime: FundingRegime, current_rate: float, avg_rate_24h: float
    ) -> float:
        """Calculate position size multiplier based on regime and rates."""
        min_mult, max_mult = cls.POSITION_MULTIPLIERS[regime]

        if regime == FundingRegime.EXTREME:
            return 0.0

        # Within regime, scale based on position within the regime band
        if regime == FundingRegime.NEUTRAL:
            # In neutral, use max multiplier
            return max_mult

        # Get regime bounds
        regime_idx = list(FundingRegime).index(regime)
        if regime_idx > 0:
            lower_threshold = list(cls.REGIME_THRESHOLDS.values())[regime_idx - 1]
        else:
            lower_threshold = 0

        upper_threshold = cls.REGIME_THRESHOLDS[regime]

        # Calculate position within regime (0-1)
        regime_range = upper_threshold - lower_threshold
        position_in_regime = (abs(current_rate) - lower_threshold) / regime_range
        position_in_regime = max(0, min(1, position_in_regime))

        # Linear interpolation within multiplier range
        # Higher funding = lower multiplier
        multiplier = max_mult - (max_mult - min_mult) * position_in_regime

        # Adjust for trend (if 24h avg is rising, be more conservative)
        if abs(avg_rate_24h) > abs(current_rate):
            # Funding is decreasing, can be slightly more aggressive
            multiplier *= 1.1
        else:
            # Funding is increasing, be more conservative
            multiplier *= 0.9

        return max(min_mult, min(max_mult, multiplier))

    @classmethod
    def calculate_funding_context(
        cls, snapshot: FundingSnapshot, previous_regime: FundingRegime = None
    ) -> FundingContext:
        """Calculate complete funding context from snapshot."""
        current_rate = snapshot.current_rate.annualized_rate
        avg_24h = snapshot.avg_rate_24h
        avg_7d = snapshot.avg_rate_7d

        # Detect regime
        regime = cls.detect_regime(current_rate)

        # Calculate position multiplier
        multiplier = cls.calculate_position_multiplier(regime, current_rate, avg_24h)

        # Determine if emergency exit needed
        should_exit = regime == FundingRegime.EXTREME or abs(current_rate) > 400

        # Check for regime change
        regime_change = previous_regime is not None and regime != previous_regime

        # Calculate cost projections
        daily_cost_bps = abs(snapshot.current_rate.daily_rate) * 100  # basis points
        weekly_cost_pct = daily_cost_bps * 7 / 100  # percentage

        return FundingContext(
            symbol=snapshot.symbol,
            current_regime=regime,
            current_rate=current_rate,
            avg_rate_24h=avg_24h,
            avg_rate_7d=avg_7d,
            max_rate_24h=snapshot.max_rate_24h,
            volatility_24h=snapshot.volatility_24h,
            position_multiplier=multiplier,
            should_exit=should_exit,
            regime_change=regime_change,
            daily_cost_bps=daily_cost_bps,
            weekly_cost_pct=weekly_cost_pct,
        )

    @classmethod
    def calculate_funding_risk_score(cls, context: FundingContext) -> float:
        """Calculate funding risk score 0-100."""
        score = 0.0

        # Base score from current rate (0-40 points)
        rate_score = min(40, abs(context.current_rate) / 10)
        score += rate_score

        # Trend score (0-20 points)
        if context.avg_rate_24h > context.avg_rate_7d * 1.5:
            # Rapidly increasing funding
            score += 20
        elif context.avg_rate_24h > context.avg_rate_7d * 1.2:
            # Moderately increasing
            score += 10
        elif context.avg_rate_24h < context.avg_rate_7d * 0.8:
            # Decreasing (good)
            score -= 5

        # Volatility score (0-20 points)
        vol_score = min(20, context.volatility_24h / 50 * 20)
        score += vol_score

        # Regime score (0-20 points)
        regime_scores = {
            FundingRegime.NEUTRAL: 0,
            FundingRegime.NORMAL: 5,
            FundingRegime.HEATED: 10,
            FundingRegime.MANIA: 15,
            FundingRegime.EXTREME: 20,
        }
        score += regime_scores[context.current_regime]

        # Cap at 100
        return min(100, max(0, score))

    @classmethod
    def project_funding_cost(
        cls, position_size_usd: float, funding_rate: float, periods: int = 3
    ) -> float:
        """Project funding cost in USD for given periods (default 24h = 3 periods)."""
        return position_size_usd * funding_rate * periods

    @classmethod
    def recommend_action(cls, context: FundingContext) -> Tuple[str, str]:
        """Recommend action based on funding context."""
        if context.should_exit:
            return "exit_all", "Emergency exit due to extreme funding rates"

        if context.regime_change:
            if context.current_regime in [FundingRegime.MANIA, FundingRegime.EXTREME]:
                return "reduce_position", f"Regime changed to {context.current_regime}"
            elif context.current_regime == FundingRegime.NEUTRAL:
                return "increase_position", "Funding returned to neutral"

        if (
            context.current_regime == FundingRegime.HEATED
            and context.avg_rate_24h > context.current_rate
        ):
            return "reduce_position", "Funding trending higher in heated regime"

        if context.position_multiplier < 0.5:
            return "maintain_reduced", "High funding environment"

        return "maintain_position", "Funding within acceptable range"
