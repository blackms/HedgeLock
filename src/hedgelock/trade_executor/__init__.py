"""
Trade Executor Service - Executes hedge trades on Bybit exchange.

This service consumes hedge trade decisions from Kafka and executes 
actual trades via Bybit API, tracking order status and confirmations.
"""

from src.hedgelock.trade_executor.bybit_client import BybitOrderClient
from src.hedgelock.trade_executor.models import (
    ExecutionError,
    ExecutionStatus,
    TradeConfirmation,
    TradeExecution,
)
from src.hedgelock.trade_executor.service import TradeExecutorService

__all__ = [
    "TradeExecutorService",
    "BybitOrderClient",
    "TradeExecution",
    "TradeConfirmation",
    "ExecutionStatus",
    "ExecutionError",
]
