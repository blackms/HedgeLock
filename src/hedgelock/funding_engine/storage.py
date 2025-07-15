"""
Storage layer for funding rate history.
"""

import redis
import json
from datetime import datetime, timedelta
from typing import List, Optional
import logging

from ..shared.funding_models import FundingRate, FundingRegime
from .config import FundingEngineConfig

logger = logging.getLogger(__name__)


class FundingStorage:
    """Redis-based storage for funding rate history."""
    
    def __init__(self, config: FundingEngineConfig):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True
        )
        
    def store_funding_rate(self, rate: FundingRate):
        """Store a funding rate in history."""
        key = f"funding:history:{rate.symbol}"
        
        # Store as sorted set with timestamp as score
        score = rate.funding_time.timestamp()
        value = json.dumps({
            "symbol": rate.symbol,
            "funding_rate": rate.funding_rate,
            "funding_time": rate.funding_time.isoformat(),
            "mark_price": rate.mark_price,
            "index_price": rate.index_price,
            "annualized_rate": rate.annualized_rate,
            "daily_rate": rate.daily_rate
        })
        
        self.redis_client.zadd(key, {value: score})
        
        # Expire old entries (keep 7 days)
        cutoff_time = datetime.utcnow() - timedelta(hours=self.config.history_window_hours)
        self.redis_client.zremrangebyscore(key, 0, cutoff_time.timestamp())
        
        # Update current rate
        current_key = f"funding:current:{rate.symbol}"
        self.redis_client.setex(
            current_key,
            3600,  # 1 hour TTL
            value
        )
        
        logger.debug(f"Stored funding rate for {rate.symbol}: {rate.annualized_rate:.2f}% APR")
        
    def get_funding_history(
        self,
        symbol: str,
        hours: int = 24
    ) -> List[FundingRate]:
        """Get funding rate history for specified hours."""
        key = f"funding:history:{symbol}"
        
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Get rates in time range
        raw_rates = self.redis_client.zrangebyscore(
            key,
            start_time.timestamp(),
            end_time.timestamp()
        )
        
        rates = []
        for raw_rate in raw_rates:
            data = json.loads(raw_rate)
            rate = FundingRate(
                symbol=data["symbol"],
                funding_rate=data["funding_rate"],
                funding_time=datetime.fromisoformat(data["funding_time"]),
                mark_price=data["mark_price"],
                index_price=data["index_price"]
            )
            rates.append(rate)
            
        return rates
        
    def get_current_funding_rate(self, symbol: str) -> Optional[FundingRate]:
        """Get the most recent funding rate."""
        current_key = f"funding:current:{symbol}"
        raw_rate = self.redis_client.get(current_key)
        
        if raw_rate:
            data = json.loads(raw_rate)
            return FundingRate(
                symbol=data["symbol"],
                funding_rate=data["funding_rate"],
                funding_time=datetime.fromisoformat(data["funding_time"]),
                mark_price=data["mark_price"],
                index_price=data["index_price"]
            )
            
        # Fallback to latest from history
        key = f"funding:history:{symbol}"
        raw_rates = self.redis_client.zrange(key, -1, -1)
        
        if raw_rates:
            data = json.loads(raw_rates[0])
            return FundingRate(
                symbol=data["symbol"],
                funding_rate=data["funding_rate"],
                funding_time=datetime.fromisoformat(data["funding_time"]),
                mark_price=data["mark_price"],
                index_price=data["index_price"]
            )
            
        return None
        
    def store_funding_regime(self, symbol: str, regime: FundingRegime):
        """Store current funding regime."""
        key = f"funding:regime:{symbol}"
        self.redis_client.setex(
            key,
            3600,  # 1 hour TTL
            regime.value
        )
        
    def get_funding_regime(self, symbol: str) -> Optional[FundingRegime]:
        """Get current funding regime."""
        key = f"funding:regime:{symbol}"
        regime_str = self.redis_client.get(key)
        
        if regime_str:
            return FundingRegime(regime_str)
            
        return None