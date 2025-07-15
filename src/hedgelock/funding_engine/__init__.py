"""
HedgeLock Funding Engine - Core funding awareness service.

This service processes funding rates, detects funding regimes,
and provides funding context for position sizing decisions.
"""

from .service import FundingEngineService
from .calculator import FundingCalculator

__all__ = ["FundingEngineService", "FundingCalculator"]