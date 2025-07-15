"""
Trade Executor Service - Executes hedge trades on Bybit exchange.

This service consumes hedge trade decisions from Kafka and executes 
actual trades via Bybit API, tracking order status and confirmations.
"""

from src.hedgelock.trade_executor.models import (
    TradeExecution,
    TradeConfirmation,
    ExecutionStatus,
    ExecutionError
)
from src.hedgelock.trade_executor.service import TradeExecutorService
from src.hedgelock.trade_executor.bybit_client import BybitOrderClient

__all__ = [
    "TradeExecutorService",
    "BybitOrderClient",
    "TradeExecution",
    "TradeConfirmation",
    "ExecutionStatus",
    "ExecutionError"
]