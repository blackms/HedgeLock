"""
Data models for risk engine.
"""

from enum import Enum
from typing import Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from ..shared.funding_models import FundingContext, FundingRegime


class RiskState(str, Enum):
    """Risk state levels."""
    NORMAL = "NORMAL"
    CAUTION = "CAUTION" 
    DANGER = "DANGER"
    CRITICAL = "CRITICAL"


class AccountData(BaseModel):
    """Raw account data from collector."""
    timestamp: datetime
    source: str
    
    # Collateral info
    total_collateral_value: float = Field(description="Total collateral value in USD")
    available_collateral: float = Field(description="Available collateral in USD")
    used_collateral: float = Field(description="Used collateral in USD")
    
    # Loan info
    total_loan_value: float = Field(description="Total loan value in USD")
    total_interest: float = Field(description="Total interest in USD")
    
    # Position info
    positions: Dict[str, dict] = Field(default_factory=dict, description="Position data by symbol")
    
    # Computed fields
    @property
    def ltv(self) -> float:
        """Calculate Loan-to-Value ratio."""
        if self.total_collateral_value == 0:
            return 0.0
        return (self.total_loan_value + self.total_interest) / self.total_collateral_value
    
    @property
    def net_delta(self) -> float:
        """Calculate net delta across all positions."""
        total_delta = 0.0
        for symbol, position in self.positions.items():
            if "BTC" in symbol:
                size = position.get("size", 0)
                side = position.get("side", "None")
                if side == "Buy":
                    total_delta += size
                elif side == "Sell":
                    total_delta -= size
        return total_delta


class RiskCalculation(BaseModel):
    """Risk calculation result."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    account_data: AccountData
    
    # Risk metrics
    ltv: float = Field(description="Loan-to-Value ratio")
    net_delta: float = Field(description="Net delta in BTC")
    risk_state: RiskState = Field(description="Current risk state")
    
    # Risk details
    risk_score: float = Field(description="Overall risk score 0-100")
    risk_factors: Dict[str, float] = Field(default_factory=dict, description="Individual risk factors")
    
    # Funding context
    funding_context: Optional[FundingContext] = Field(default=None, description="Current funding context")
    funding_adjusted_score: Optional[float] = Field(default=None, description="Risk score adjusted for funding")
    
    # Processing metadata
    processing_time_ms: float = Field(description="Processing time in milliseconds")
    trace_id: Optional[str] = Field(default=None, description="Trace ID for correlation")


class RiskStateMessage(BaseModel):
    """Message published to risk_state topic."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str = Field(default="risk_engine")
    
    # Current state
    risk_state: RiskState
    previous_state: Optional[RiskState] = None
    state_changed: bool = False
    
    # Risk metrics
    ltv: float
    net_delta: float
    risk_score: float
    
    # Hedge recommendations
    hedge_recommendation: Optional[Dict[str, any]] = None
    
    # Account snapshot
    total_collateral_value: float
    total_loan_value: float
    available_collateral: float
    
    # Funding context
    funding_context: Optional[FundingContext] = Field(default=None, description="Current funding context")
    funding_adjusted_score: Optional[float] = Field(default=None, description="Risk score adjusted for funding")
    funding_regime: Optional[FundingRegime] = Field(default=None, description="Current funding regime")
    position_multiplier: Optional[float] = Field(default=None, description="Funding-based position multiplier")
    
    # Metadata
    trace_id: Optional[str] = None
    processing_time_ms: float