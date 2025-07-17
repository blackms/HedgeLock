"""
Position state storage for persistence and recovery.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

import redis
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from .models import PositionState

logger = logging.getLogger(__name__)

Base = declarative_base()


class PositionStateRecord(Base):
    """SQLAlchemy model for position state storage."""
    __tablename__ = 'position_states'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    spot_btc = Column(Float, nullable=False)
    long_perp = Column(Float, nullable=False)
    short_perp = Column(Float, nullable=False)
    net_delta = Column(Float, nullable=False)
    hedge_ratio = Column(Float, nullable=False)
    btc_price = Column(Float, nullable=False)
    volatility_24h = Column(Float, nullable=False)
    funding_rate = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    peak_pnl = Column(Float, default=0.0)
    market_regime = Column(String(50), default='NEUTRAL')
    funding_regime = Column(String(50), default='NORMAL')
    metadata = Column(JSON, nullable=True)


class PositionStorage(ABC):
    """Abstract base class for position state storage."""
    
    @abstractmethod
    async def save_state(self, state: PositionState) -> bool:
        """Save position state."""
        pass
    
    @abstractmethod
    async def get_latest_state(self) -> Optional[PositionState]:
        """Get the most recent position state."""
        pass
    
    @abstractmethod
    async def get_state_history(self, hours: int = 24) -> List[PositionState]:
        """Get position state history."""
        pass
    
    @abstractmethod
    async def delete_old_states(self, days: int = 7) -> int:
        """Delete states older than specified days."""
        pass


class RedisPositionStorage(PositionStorage):
    """Redis-based position state storage."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.state_key = "position_manager:current_state"
        self.history_key = "position_manager:state_history"
        self.max_history_items = 10000  # Keep last 10k states
    
    async def save_state(self, state: PositionState) -> bool:
        """Save position state to Redis."""
        try:
            # Save current state
            state_json = state.model_dump_json()
            self.redis_client.set(self.state_key, state_json)
            
            # Add to history with score as timestamp
            score = state.timestamp.timestamp()
            self.redis_client.zadd(self.history_key, {state_json: score})
            
            # Trim history to max items
            self.redis_client.zremrangebyrank(self.history_key, 0, -self.max_history_items-1)
            
            logger.info(f"Saved position state to Redis: delta={state.net_delta:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save state to Redis: {e}")
            return False
    
    async def get_latest_state(self) -> Optional[PositionState]:
        """Get the most recent position state from Redis."""
        try:
            state_json = self.redis_client.get(self.state_key)
            if state_json:
                return PositionState.model_validate_json(state_json)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get state from Redis: {e}")
            return None
    
    async def get_state_history(self, hours: int = 24) -> List[PositionState]:
        """Get position state history from Redis."""
        try:
            # Calculate time range
            end_time = datetime.utcnow().timestamp()
            start_time = (datetime.utcnow() - timedelta(hours=hours)).timestamp()
            
            # Get states in time range
            state_jsons = self.redis_client.zrangebyscore(
                self.history_key, 
                start_time, 
                end_time
            )
            
            states = []
            for state_json in state_jsons:
                try:
                    state = PositionState.model_validate_json(state_json)
                    states.append(state)
                except Exception as e:
                    logger.warning(f"Failed to parse historical state: {e}")
                    
            return states
            
        except Exception as e:
            logger.error(f"Failed to get history from Redis: {e}")
            return []
    
    async def delete_old_states(self, days: int = 7) -> int:
        """Delete states older than specified days."""
        try:
            cutoff_time = (datetime.utcnow() - timedelta(days=days)).timestamp()
            removed = self.redis_client.zremrangebyscore(
                self.history_key,
                0,
                cutoff_time
            )
            logger.info(f"Removed {removed} old states from Redis")
            return removed
            
        except Exception as e:
            logger.error(f"Failed to delete old states from Redis: {e}")
            return 0


class PostgresPositionStorage(PositionStorage):
    """PostgreSQL-based position state storage."""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    async def save_state(self, state: PositionState) -> bool:
        """Save position state to PostgreSQL."""
        try:
            with self.SessionLocal() as session:
                record = PositionStateRecord(
                    timestamp=state.timestamp,
                    spot_btc=state.spot_btc,
                    long_perp=state.long_perp,
                    short_perp=state.short_perp,
                    net_delta=state.net_delta,
                    hedge_ratio=state.hedge_ratio,
                    btc_price=state.btc_price,
                    volatility_24h=state.volatility_24h,
                    funding_rate=state.funding_rate,
                    unrealized_pnl=state.unrealized_pnl,
                    realized_pnl=state.realized_pnl,
                    peak_pnl=state.peak_pnl,
                    market_regime=state.market_regime.value,
                    funding_regime=state.funding_regime,
                    metadata={}
                )
                session.add(record)
                session.commit()
                
            logger.info(f"Saved position state to PostgreSQL: delta={state.net_delta:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save state to PostgreSQL: {e}")
            return False
    
    async def get_latest_state(self) -> Optional[PositionState]:
        """Get the most recent position state from PostgreSQL."""
        try:
            with self.SessionLocal() as session:
                record = session.query(PositionStateRecord)\
                    .order_by(PositionStateRecord.timestamp.desc())\
                    .first()
                    
                if record:
                    return PositionState(
                        timestamp=record.timestamp,
                        spot_btc=record.spot_btc,
                        long_perp=record.long_perp,
                        short_perp=record.short_perp,
                        net_delta=record.net_delta,
                        hedge_ratio=record.hedge_ratio,
                        btc_price=record.btc_price,
                        volatility_24h=record.volatility_24h,
                        funding_rate=record.funding_rate,
                        unrealized_pnl=record.unrealized_pnl,
                        realized_pnl=record.realized_pnl,
                        peak_pnl=record.peak_pnl,
                        market_regime=record.market_regime,
                        funding_regime=record.funding_regime
                    )
                return None
                
        except Exception as e:
            logger.error(f"Failed to get state from PostgreSQL: {e}")
            return None
    
    async def get_state_history(self, hours: int = 24) -> List[PositionState]:
        """Get position state history from PostgreSQL."""
        try:
            with self.SessionLocal() as session:
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                records = session.query(PositionStateRecord)\
                    .filter(PositionStateRecord.timestamp >= cutoff_time)\
                    .order_by(PositionStateRecord.timestamp.asc())\
                    .all()
                
                states = []
                for record in records:
                    state = PositionState(
                        timestamp=record.timestamp,
                        spot_btc=record.spot_btc,
                        long_perp=record.long_perp,
                        short_perp=record.short_perp,
                        net_delta=record.net_delta,
                        hedge_ratio=record.hedge_ratio,
                        btc_price=record.btc_price,
                        volatility_24h=record.volatility_24h,
                        funding_rate=record.funding_rate,
                        unrealized_pnl=record.unrealized_pnl,
                        realized_pnl=record.realized_pnl,
                        peak_pnl=record.peak_pnl,
                        market_regime=record.market_regime,
                        funding_regime=record.funding_regime
                    )
                    states.append(state)
                    
                return states
                
        except Exception as e:
            logger.error(f"Failed to get history from PostgreSQL: {e}")
            return []
    
    async def delete_old_states(self, days: int = 7) -> int:
        """Delete states older than specified days."""
        try:
            with self.SessionLocal() as session:
                cutoff_time = datetime.utcnow() - timedelta(days=days)
                deleted = session.query(PositionStateRecord)\
                    .filter(PositionStateRecord.timestamp < cutoff_time)\
                    .delete()
                session.commit()
                
                logger.info(f"Removed {deleted} old states from PostgreSQL")
                return deleted
                
        except Exception as e:
            logger.error(f"Failed to delete old states from PostgreSQL: {e}")
            return 0


def create_storage(storage_type: str, connection_url: str) -> PositionStorage:
    """Factory function to create appropriate storage backend."""
    if storage_type.lower() == "redis":
        return RedisPositionStorage(connection_url)
    elif storage_type.lower() == "postgres":
        return PostgresPositionStorage(connection_url)
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")