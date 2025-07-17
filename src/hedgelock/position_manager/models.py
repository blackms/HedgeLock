"""
Position Manager models for delta-neutral trading.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class MarketRegime(str, Enum):
    NEUTRAL = "NEUTRAL"
    LONG_BIASED = "LONG_BIASED"
    SHORT_BIASED = "SHORT_BIASED"
    TAKING_PROFIT = "TAKING_PROFIT"


class PositionState(BaseModel):
    """Current position state snapshot."""
    timestamp: datetime
    
    # Core positions
    spot_btc: float = Field(default=0.27, description="BTC held as collateral")
    long_perp: float = Field(default=0.0, description="Long perpetual position")
    short_perp: float = Field(default=0.0, description="Short perpetual position")
    
    # Calculated fields
    net_delta: float = Field(description="Net BTC exposure")
    hedge_ratio: float = Field(default=1.0, description="Current hedge ratio")
    
    # Market data
    btc_price: float
    volatility_24h: float
    funding_rate: float
    
    # P&L tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    peak_pnl: float = 0.0
    
    # State
    market_regime: MarketRegime = MarketRegime.NEUTRAL
    funding_regime: str = "NORMAL"  # From funding engine
    
    @property
    def total_long(self) -> float:
        return self.spot_btc + self.long_perp
    
    @property
    def delta_neutral(self) -> bool:
        return abs(self.net_delta) < 0.01  # Within 1% of neutral


class HedgeDecision(BaseModel):
    """Hedge adjustment decision."""
    timestamp: datetime
    current_hedge_ratio: float
    target_hedge_ratio: float
    volatility_24h: float
    reason: str
    
    # Actions
    adjust_short: float  # BTC to add/remove from short
    adjust_long: float   # BTC to add/remove from long


class ProfitTarget(BaseModel):
    """Profit taking parameters."""
    timestamp: datetime
    target_price: float
    target_pnl: float
    trailing_stop_pct: float = 0.30  # 30% of peak
    volatility_multiplier: float = 1.5  # k in PT = k*Ã