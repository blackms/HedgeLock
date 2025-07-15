"""
Shared funding rate models used across services.
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class FundingRegime(str, Enum):
    """Funding rate regime classification."""
    NEUTRAL = "neutral"     # < 10% APR - Normal market conditions
    NORMAL = "normal"       # 10-50% APR - Moderate funding
    HEATED = "heated"       # 50-100% APR - High funding
    MANIA = "mania"         # 100-300% APR - Extreme funding
    EXTREME = "extreme"     # > 300% APR - Unsustainable funding


class FundingRate(BaseModel):
    """Individual funding rate data point."""
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDT)")
    funding_rate: float = Field(description="8-hour funding rate as decimal")
    funding_time: datetime = Field(description="Funding timestamp")
    mark_price: float = Field(description="Mark price at funding time")
    index_price: float = Field(description="Index price at funding time")
    
    @property
    def annualized_rate(self) -> float:
        """Calculate annualized funding rate."""
        # 3 funding periods per day * 365 days
        return self.funding_rate * 3 * 365 * 100  # as percentage
    
    @property
    def daily_rate(self) -> float:
        """Calculate daily funding rate."""
        return self.funding_rate * 3 * 100  # as percentage


class FundingSnapshot(BaseModel):
    """Current funding rate snapshot with history."""
    symbol: str
    current_rate: FundingRate
    rates_24h: List[FundingRate] = Field(default_factory=list)
    rates_7d: List[FundingRate] = Field(default_factory=list)
    
    @property
    def avg_rate_24h(self) -> float:
        """Average annualized rate over 24 hours."""
        if not self.rates_24h:
            return self.current_rate.annualized_rate
        return sum(r.annualized_rate for r in self.rates_24h) / len(self.rates_24h)
    
    @property
    def avg_rate_7d(self) -> float:
        """Average annualized rate over 7 days."""
        if not self.rates_7d:
            return self.avg_rate_24h
        return sum(r.annualized_rate for r in self.rates_7d) / len(self.rates_7d)
    
    @property
    def max_rate_24h(self) -> float:
        """Maximum annualized rate over 24 hours."""
        if not self.rates_24h:
            return self.current_rate.annualized_rate
        return max(r.annualized_rate for r in self.rates_24h)
    
    @property
    def volatility_24h(self) -> float:
        """Funding rate volatility (std dev) over 24 hours."""
        if len(self.rates_24h) < 2:
            return 0.0
        rates = [r.annualized_rate for r in self.rates_24h]
        avg = sum(rates) / len(rates)
        variance = sum((r - avg) ** 2 for r in rates) / len(rates)
        return variance ** 0.5


class FundingContext(BaseModel):
    """Funding context for decision making."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str
    
    # Current state
    current_regime: FundingRegime
    current_rate: float = Field(description="Current annualized rate %")
    
    # Historical context
    avg_rate_24h: float = Field(description="24h average annualized rate %")
    avg_rate_7d: float = Field(description="7d average annualized rate %")
    max_rate_24h: float = Field(description="24h max annualized rate %")
    volatility_24h: float = Field(description="24h funding rate volatility")
    
    # Decision outputs
    position_multiplier: float = Field(
        description="Position size multiplier (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    should_exit: bool = Field(
        default=False,
        description="Emergency exit flag"
    )
    regime_change: bool = Field(
        default=False,
        description="Regime changed from previous"
    )
    
    # Cost projections
    daily_cost_bps: float = Field(
        description="Projected daily cost in basis points"
    )
    weekly_cost_pct: float = Field(
        description="Projected weekly cost as percentage"
    )
    
    # Metadata
    trace_id: Optional[str] = None


class FundingDecision(BaseModel):
    """Funding-based trading decision."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    context: FundingContext
    
    # Decisions
    action: str = Field(description="Recommended action")
    position_adjustment: float = Field(
        description="Recommended position adjustment factor"
    )
    max_position_size: float = Field(
        description="Maximum allowed position size"
    )
    
    # Reasoning
    reason: str
    urgency: str = Field(description="low/medium/high/critical")
    
    # Risk metrics
    funding_risk_score: float = Field(
        description="Funding risk score 0-100",
        ge=0,
        le=100
    )
    projected_cost_24h: float = Field(
        description="Projected funding cost next 24h in USD"
    )
    
    # Metadata
    trace_id: Optional[str] = None


class FundingAlert(BaseModel):
    """Funding rate alert/notification."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    alert_type: str = Field(description="regime_change/high_cost/emergency")
    severity: str = Field(description="info/warning/critical")
    
    # Alert details
    symbol: str
    current_regime: FundingRegime
    previous_regime: Optional[FundingRegime] = None
    current_rate: float
    threshold_breached: Optional[float] = None
    
    # Message
    title: str
    message: str
    recommended_action: Optional[str] = None
    
    # Metadata
    trace_id: Optional[str] = None


# Kafka message types
class FundingRateMessage(BaseModel):
    """Message published to funding_rates topic."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str = Field(default="collector")
    funding_rate: FundingRate
    trace_id: Optional[str] = None


class FundingContextMessage(BaseModel):
    """Message published to funding_context topic."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str = Field(default="funding_engine")
    funding_context: FundingContext
    funding_decision: Optional[FundingDecision] = None
    trace_id: Optional[str] = None