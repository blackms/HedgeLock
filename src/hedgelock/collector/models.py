"""
Data models for the collector service.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class PositionSide(str, Enum):
    """Position side."""
    BUY = "Buy"
    SELL = "Sell"


class OrderStatus(str, Enum):
    """Order status."""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


class Position(BaseModel):
    """Position data model."""
    symbol: str
    side: PositionSide
    size: Decimal
    avg_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    cum_realized_pnl: Decimal
    position_value: Decimal
    leverage: Decimal
    updated_time: datetime


class Balance(BaseModel):
    """Balance data model."""
    coin: str
    wallet_balance: Decimal
    available_balance: Decimal
    
    
class CollateralInfo(BaseModel):
    """Collateral information."""
    ltv: Decimal = Field(description="Loan-to-Value ratio")
    collateral_value: Decimal = Field(description="Total collateral value in USD")
    borrowed_amount: Decimal = Field(description="Total borrowed amount in USD")
    collateral_ratio: Decimal = Field(description="Collateral ratio")
    free_collateral: Decimal = Field(description="Free collateral in USD")
    

class LoanInfo(BaseModel):
    """Loan information."""
    loan_currency: str
    loan_amount: Decimal
    collateral_currency: str
    collateral_amount: Decimal
    hourly_interest_rate: Decimal
    loan_term: Optional[int] = Field(None, description="Loan term in days")
    loan_order_id: str
    

class AccountUpdate(BaseModel):
    """Account update message for Kafka."""
    timestamp: datetime
    account_id: str
    balances: Dict[str, Balance]
    positions: List[Position]
    collateral_info: CollateralInfo
    loan_info: Optional[LoanInfo] = None
    source: str = "collector"
    

class MarketData(BaseModel):
    """Market data message for Kafka."""
    timestamp: datetime
    symbol: str
    price: Decimal
    volume_24h: Decimal
    bid: Decimal
    ask: Decimal
    open_interest: Optional[Decimal] = None
    funding_rate: Optional[Decimal] = None
    source: str = "collector"


class OrderUpdate(BaseModel):
    """Order update message."""
    timestamp: datetime
    order_id: str
    symbol: str
    side: PositionSide
    order_type: str
    qty: Decimal
    price: Optional[Decimal]
    status: OrderStatus
    avg_price: Optional[Decimal]
    cum_exec_qty: Decimal
    cum_exec_value: Decimal
    cum_exec_fee: Decimal
    time_in_force: str
    created_time: datetime
    updated_time: datetime