"""
Market data models.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PriceUpdate(BaseModel):
    """Price update from exchange."""
    symbol: str
    price: float
    timestamp: datetime
    volume_24h: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    

class MarketData(BaseModel):
    """Market data message for Kafka."""
    service: str = "market-data"
    symbol: str
    price: float
    timestamp: datetime
    volume_24h: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    trace_id: str = Field(default_factory=lambda: f"md-{datetime.utcnow().timestamp()}")