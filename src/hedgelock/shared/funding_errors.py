"""
Funding-related error handling and exception classes.
"""

from datetime import datetime
from typing import Optional

from .funding_models import FundingRegime


class FundingError(Exception):
    """Base exception for funding-related errors."""

    def __init__(self, message: str, symbol: Optional[str] = None):
        self.symbol = symbol
        self.timestamp = datetime.utcnow()
        super().__init__(message)


class ExtremeFundingError(FundingError):
    """Raised when funding rates reach extreme levels requiring emergency action."""

    def __init__(
        self,
        message: str,
        symbol: str,
        current_rate: float,
        threshold: float = 300.0,
    ):
        self.current_rate = current_rate
        self.threshold = threshold
        super().__init__(
            f"EXTREME FUNDING ALERT: {message} "
            f"(Symbol: {symbol}, Rate: {current_rate:.1f}% APR, Threshold: {threshold:.1f}% APR)",
            symbol,
        )


class FundingDataError(FundingError):
    """Raised when funding data is invalid or unavailable."""

    pass


class FundingCalculationError(FundingError):
    """Raised when funding calculations fail."""

    pass


class FundingRegimeTransitionError(FundingError):
    """Raised when invalid regime transitions are detected."""

    def __init__(
        self,
        message: str,
        symbol: str,
        from_regime: FundingRegime,
        to_regime: FundingRegime,
    ):
        self.from_regime = from_regime
        self.to_regime = to_regime
        super().__init__(
            f"Invalid regime transition: {message} "
            f"(Symbol: {symbol}, From: {from_regime.value}, To: {to_regime.value})",
            symbol,
        )


class FundingRateLimitError(FundingError):
    """Raised when funding rate exceeds absolute limits."""

    def __init__(self, symbol: str, rate: float, max_rate: float = 1000.0):
        self.rate = rate
        self.max_rate = max_rate
        super().__init__(
            f"Funding rate exceeds absolute limit "
            f"(Symbol: {symbol}, Rate: {rate:.1f}% APR, Max: {max_rate:.1f}% APR)",
            symbol,
        )


class FundingPositionError(FundingError):
    """Raised when position adjustments fail due to funding constraints."""

    def __init__(
        self,
        message: str,
        symbol: str,
        current_position: float,
        target_position: float,
        reason: str,
    ):
        self.current_position = current_position
        self.target_position = target_position
        self.reason = reason
        super().__init__(
            f"Position adjustment failed: {message} "
            f"(Symbol: {symbol}, Current: {current_position:.4f}, "
            f"Target: {target_position:.4f}, Reason: {reason})",
            symbol,
        )


class FundingEmergencyExitError(FundingError):
    """Raised when emergency exit procedures fail."""

    def __init__(
        self, message: str, symbol: str, position_size: float, attempts: int = 1
    ):
        self.position_size = position_size
        self.attempts = attempts
        super().__init__(
            f"EMERGENCY EXIT FAILED: {message} "
            f"(Symbol: {symbol}, Position: {position_size:.4f}, Attempts: {attempts})",
            symbol,
        )


# Error handlers for different scenarios
class FundingErrorHandler:
    """Centralized error handling for funding-related issues."""

    @staticmethod
    def handle_extreme_funding(
        symbol: str, current_rate: float, position_size: float
    ) -> dict:
        """
        Handle extreme funding scenarios with appropriate actions.

        Returns:
            dict: Action plan with emergency procedures
        """
        if current_rate > 1000:  # >1000% APR - Critical emergency
            return {
                "action": "emergency_exit_critical",
                "priority": "IMMEDIATE",
                "max_attempts": 5,
                "steps": [
                    "Cancel all open orders immediately",
                    "Close position with market order",
                    "If market order fails, try limit order at -0.5% from market",
                    "If still fails, split position and retry",
                    "Alert operations team immediately",
                ],
                "fallback": "manual_intervention_required",
                "estimated_loss": position_size * (current_rate / 100 / 365) * 0.03,  # 8h
            }
        elif current_rate > 500:  # >500% APR - Urgent
            return {
                "action": "emergency_exit_urgent",
                "priority": "HIGH",
                "max_attempts": 3,
                "steps": [
                    "Cancel non-essential orders",
                    "Close position with aggressive limit order",
                    "If fails, use market order",
                ],
                "fallback": "reduce_position_by_half",
                "estimated_loss": position_size * (current_rate / 100 / 365) * 0.03,
            }
        elif current_rate > 300:  # >300% APR - Standard emergency
            return {
                "action": "emergency_exit_standard",
                "priority": "MEDIUM",
                "max_attempts": 2,
                "steps": [
                    "Place limit order to close position",
                    "If not filled in 30s, convert to market order",
                ],
                "fallback": "gradual_position_reduction",
                "estimated_loss": position_size * (current_rate / 100 / 365) * 0.03,
            }
        else:
            return {
                "action": "monitor",
                "priority": "LOW",
                "steps": ["Continue monitoring funding rates"],
                "fallback": None,
                "estimated_loss": 0,
            }

    @staticmethod
    def validate_funding_rate(symbol: str, rate: float, is_annualized: bool = True) -> None:
        """
        Validate funding rate is within acceptable bounds.

        Args:
            symbol: Trading symbol
            rate: Funding rate (either annualized % or 8h rate)
            is_annualized: True if rate is already annualized %, False if 8h rate

        Raises:
            FundingRateLimitError: If rate exceeds limits
            FundingDataError: If rate is invalid
        """
        # Check for invalid rates
        if rate != rate:  # NaN check
            raise FundingDataError(f"Invalid funding rate (NaN)", symbol)

        if rate == float("inf") or rate == float("-inf"):
            raise FundingDataError(f"Invalid funding rate (Infinite)", symbol)

        # Get APR for validation
        if is_annualized:
            apr = rate  # Already in annualized percentage
        else:
            apr = rate * 3 * 365 * 100  # Convert 8h rate to APR

        # Check absolute limits
        if abs(apr) > 1000:  # ±1000% APR absolute limit
            raise FundingRateLimitError(symbol, apr)

        # Check suspicious rates
        if abs(apr) > 500:
            # Log warning but allow processing
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Extremely high funding rate detected: {symbol} at {apr:.1f}% APR"
            )

    @staticmethod
    def validate_regime_transition(
        symbol: str, from_regime: FundingRegime, to_regime: FundingRegime
    ) -> None:
        """
        Validate regime transitions are logical.

        Raises:
            FundingRegimeTransitionError: If transition is invalid
        """
        # Define valid transitions (can skip one level in extreme cases)
        valid_transitions = {
            FundingRegime.NEUTRAL: [
                FundingRegime.NEUTRAL,
                FundingRegime.NORMAL,
                FundingRegime.HEATED,
            ],
            FundingRegime.NORMAL: [
                FundingRegime.NEUTRAL,
                FundingRegime.NORMAL,
                FundingRegime.HEATED,
                FundingRegime.MANIA,
            ],
            FundingRegime.HEATED: [
                FundingRegime.NORMAL,
                FundingRegime.HEATED,
                FundingRegime.MANIA,
                FundingRegime.EXTREME,
            ],
            FundingRegime.MANIA: [
                FundingRegime.NORMAL,
                FundingRegime.HEATED,
                FundingRegime.MANIA,
                FundingRegime.EXTREME,
            ],
            FundingRegime.EXTREME: [
                FundingRegime.HEATED,
                FundingRegime.MANIA,
                FundingRegime.EXTREME,
            ],
        }

        if to_regime not in valid_transitions.get(from_regime, []):
            # Allow any transition but log warning
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Unusual regime transition for {symbol}: "
                f"{from_regime.value} → {to_regime.value}"
            )

    @staticmethod
    def calculate_emergency_cost(
        position_size_usd: float, funding_rate_apr: float, hours: int = 24
    ) -> dict:
        """
        Calculate the cost of holding position under extreme funding.

        Args:
            position_size_usd: Position size in USD
            funding_rate_apr: Annual funding rate percentage
            hours: Hours to calculate cost for

        Returns:
            dict: Cost breakdown and recommendations
        """
        # Calculate funding cost
        periods = hours / 8  # Funding paid every 8 hours
        period_rate = funding_rate_apr / 100 / 365 / 3  # Convert APR to 8h rate
        total_cost = position_size_usd * period_rate * periods

        # Calculate break-even move needed
        breakeven_move_pct = (total_cost / position_size_usd) * 100

        return {
            "total_cost_usd": total_cost,
            "cost_per_hour": total_cost / hours,
            "cost_as_pct": (total_cost / position_size_usd) * 100,
            "breakeven_move_required": breakeven_move_pct,
            "recommendation": (
                "CLOSE_IMMEDIATELY"
                if breakeven_move_pct > 2
                else "MONITOR_CLOSELY" if breakeven_move_pct > 1 else "ACCEPTABLE"
            ),
            "time_to_1pct_loss": 1 / (period_rate * 3) if period_rate > 0 else float("inf"),
        }