"""
Data models for hedger service.
"""

from enum import Enum
from typing import Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from ..shared.funding_models import FundingContext, FundingRegime


class OrderSide(str, Enum):
    """Order side."""
    BUY = "Buy"
    SELL = "Sell"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "Market"
    LIMIT = "Limit"


class OrderStatus(str, Enum):
    """Order status."""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


class HedgeDecision(BaseModel):
    """Hedge decision based on risk state."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    risk_state: str
    current_delta: float
    target_delta: float
    hedge_size: float
    side: OrderSide
    reason: str
    urgency: str
    
    # Funding context
    funding_adjusted: bool = Field(default=False, description="Whether hedge was adjusted for funding")
    funding_regime: Optional[FundingRegime] = None
    position_multiplier: Optional[float] = Field(default=1.0, description="Funding-based position multiplier")
    
    trace_id: Optional[str] = None


class OrderRequest(BaseModel):
    """Order request to Bybit."""
    category: str = Field(default="linear", description="Product category")
    symbol: str = Field(default="BTCUSDT", description="Trading symbol")
    side: OrderSide
    orderType: OrderType
    qty: str = Field(description="Order quantity as string")
    timeInForce: str = Field(default="IOC", description="Time in force")
    positionIdx: int = Field(default=0, description="Position index for hedge mode")
    orderLinkId: Optional[str] = Field(default=None, description="User-defined order ID")


class OrderResponse(BaseModel):
    """Order response from Bybit."""
    orderId: str
    orderLinkId: str
    symbol: str
    side: str
    orderType: str
    price: Optional[float]
    qty: float
    orderStatus: str
    timeInForce: str
    createdTime: str
    updatedTime: str
    avgPrice: Optional[float] = None
    cumExecQty: Optional[float] = None
    cumExecValue: Optional[float] = None
    cumExecFee: Optional[float] = None


class HedgeTradeMessage(BaseModel):
    """Message published to hedge_trades topic."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str = Field(default="hedger")
    
    # Decision details
    hedge_decision: HedgeDecision
    
    # Order details
    order_request: OrderRequest
    order_response: Optional[OrderResponse] = None
    
    # Execution details
    executed: bool = False
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None
    
    # Risk context
    risk_state: str
    ltv: float
    risk_score: float
    funding_adjusted_score: Optional[float] = None
    
    # Funding context
    funding_context: Optional[FundingContext] = None
    funding_cost_24h: Optional[float] = Field(default=None, description="Projected 24h funding cost in USD")
    
    # Metadata
    trace_id: Optional[str] = None
    testnet: bool = True