"""
Data models for Trade Executor service.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Trade execution status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class ExecutionError(BaseModel):
    """Error details for failed executions."""

    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    is_retryable: bool = True


class TradeExecution(BaseModel):
    """Trade execution details."""

    execution_id: str = Field(description="Unique execution ID")
    hedge_trade_id: str = Field(description="Original hedge trade ID")
    order_id: Optional[str] = Field(default=None, description="Bybit order ID")
    order_link_id: str = Field(description="Client order ID")

    # Order details
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None

    # Execution state
    status: ExecutionStatus
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None

    # Execution results
    avg_fill_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    commission: Optional[float] = None

    # Error handling
    error: Optional[ExecutionError] = None
    retry_count: int = 0
    max_retries: int = 3

    # Metadata
    trace_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OrderUpdate(BaseModel):
    """Order status update from Bybit."""

    order_id: str
    order_link_id: str
    symbol: str
    side: str
    order_type: str
    order_status: str

    # Fill information
    avg_price: Optional[float] = None
    cum_exec_qty: Optional[float] = None
    cum_exec_value: Optional[float] = None
    cum_exec_fee: Optional[float] = None

    # Timestamps
    created_time: str
    updated_time: str


class TradeConfirmation(BaseModel):
    """Trade execution confirmation message."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str = Field(default="trade_executor")

    # Original hedge trade reference
    hedge_trade_id: str
    hedge_decision_id: str

    # Execution details
    execution: TradeExecution

    # Performance metrics
    submission_latency_ms: float = Field(description="Time to submit order")
    fill_latency_ms: Optional[float] = Field(description="Time to fill order")
    total_latency_ms: float = Field(description="Total execution time")

    # Risk context (carried forward)
    risk_state: str
    ltv: float
    hedge_size: float

    # Result summary
    success: bool
    filled_quantity: float
    avg_price: Optional[float] = None
    commission: Optional[float] = None

    # Error details if failed
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    # Metadata
    trace_id: Optional[str] = None
    testnet: bool = True


class ExecutorState(BaseModel):
    """Trade executor service state."""

    is_running: bool = False
    is_healthy: bool = True

    # Connection states
    kafka_connected: bool = False
    bybit_connected: bool = False

    # Execution statistics
    trades_submitted: int = 0
    trades_filled: int = 0
    trades_failed: int = 0
    trades_rejected: int = 0

    # Performance metrics
    avg_submission_latency_ms: float = 0.0
    avg_fill_latency_ms: float = 0.0

    # Rate limiting
    orders_per_second: float = 0.0
    rate_limit_remaining: int = 10

    # Recent executions
    recent_executions: List[TradeExecution] = Field(default_factory=list)

    # Last update
    last_update: datetime = Field(default_factory=datetime.utcnow)
