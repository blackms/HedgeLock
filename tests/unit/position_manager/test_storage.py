"""
Unit tests for Position Manager Storage.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.hedgelock.position_manager.storage import (
    RedisPositionStorage, 
    PostgresPositionStorage,
    create_storage,
    PositionStateRecord,
    Base
)
from src.hedgelock.position_manager.models import PositionState, MarketRegime


class TestRedisPositionStorage:
    """Test Redis storage implementation."""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        mock_client = Mock()
        mock_client.set = Mock(return_value=True)
        mock_client.get = Mock(return_value=None)
        mock_client.zadd = Mock(return_value=1)
        mock_client.zrangebyscore = Mock(return_value=[])
        mock_client.zremrangebyscore = Mock(return_value=0)
        mock_client.zremrangebyrank = Mock(return_value=0)
        return mock_client
    
    @pytest.fixture
    def storage(self, mock_redis):
        """Create storage with mocked Redis."""
        with patch('redis.from_url', return_value=mock_redis):
            return RedisPositionStorage("redis://localhost:6379")
    
    @pytest.fixture
    def position_state(self):
        """Create test position state."""
        return PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            market_regime=MarketRegime.NEUTRAL
        )
    
    @pytest.mark.asyncio
    async def test_save_state(self, storage, position_state, mock_redis):
        """Test saving position state."""
        result = await storage.save_state(position_state)
        
        assert result is True
        mock_redis.set.assert_called_once()
        mock_redis.zadd.assert_called_once()
        
        # Check correct key used
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "position_manager:current_state"
    
    @pytest.mark.asyncio
    async def test_save_state_failure(self, storage, position_state, mock_redis):
        """Test handling save failure."""
        mock_redis.set.side_effect = Exception("Redis error")
        
        result = await storage.save_state(position_state)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_latest_state(self, storage, position_state, mock_redis):
        """Test retrieving latest state."""
        # Mock Redis returning JSON
        mock_redis.get.return_value = position_state.model_dump_json()
        
        result = await storage.get_latest_state()
        
        assert result is not None
        assert result.spot_btc == position_state.spot_btc
        assert result.net_delta == position_state.net_delta
    
    @pytest.mark.asyncio
    async def test_get_latest_state_none(self, storage, mock_redis):
        """Test when no state exists."""
        mock_redis.get.return_value = None
        
        result = await storage.get_latest_state()
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_state_history(self, storage, position_state, mock_redis):
        """Test retrieving state history."""
        # Mock Redis returning list of JSON states
        mock_redis.zrangebyscore.return_value = [
            position_state.model_dump_json()
        ]
        
        result = await storage.get_state_history(hours=24)
        
        assert len(result) == 1
        assert result[0].spot_btc == position_state.spot_btc
        
        # Check time range calculation
        call_args = mock_redis.zrangebyscore.call_args
        assert call_args[0][0] == "position_manager:state_history"
    
    @pytest.mark.asyncio
    async def test_delete_old_states(self, storage, mock_redis):
        """Test deleting old states."""
        mock_redis.zremrangebyscore.return_value = 100
        
        result = await storage.delete_old_states(days=7)
        
        assert result == 100
        mock_redis.zremrangebyscore.assert_called_once()


class TestPostgresPositionStorage:
    """Test PostgreSQL storage implementation."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = Mock()
        session.add = Mock()
        session.commit = Mock()
        session.query = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)
        return session
    
    @pytest.fixture
    def mock_engine(self):
        """Mock database engine."""
        engine = Mock()
        return engine
    
    @pytest.fixture
    def storage(self, mock_engine, mock_session):
        """Create storage with mocked database."""
        with patch('sqlalchemy.create_engine', return_value=mock_engine):
            with patch('sqlalchemy.orm.sessionmaker') as mock_sessionmaker:
                mock_sessionmaker.return_value = Mock(return_value=mock_session)
                return PostgresPositionStorage("postgresql://localhost/test")
    
    @pytest.fixture
    def position_state(self):
        """Create test position state."""
        return PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            market_regime=MarketRegime.NEUTRAL
        )
    
    @pytest.mark.asyncio
    async def test_save_state(self, storage, position_state, mock_session):
        """Test saving position state."""
        result = await storage.save_state(position_state)
        
        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_save_state_failure(self, storage, position_state, mock_session):
        """Test handling save failure."""
        mock_session.commit.side_effect = Exception("DB error")
        
        result = await storage.save_state(position_state)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_latest_state(self, storage, position_state, mock_session):
        """Test retrieving latest state."""
        # Mock query result
        mock_record = PositionStateRecord(
            timestamp=position_state.timestamp,
            spot_btc=position_state.spot_btc,
            long_perp=position_state.long_perp,
            short_perp=position_state.short_perp,
            net_delta=position_state.net_delta,
            hedge_ratio=position_state.hedge_ratio,
            btc_price=position_state.btc_price,
            volatility_24h=position_state.volatility_24h,
            funding_rate=position_state.funding_rate,
            unrealized_pnl=position_state.unrealized_pnl,
            realized_pnl=position_state.realized_pnl,
            peak_pnl=position_state.peak_pnl,
            market_regime=position_state.market_regime.value,
            funding_regime=position_state.funding_regime
        )
        
        mock_query = Mock()
        mock_query.order_by.return_value.first.return_value = mock_record
        mock_session.query.return_value = mock_query
        
        result = await storage.get_latest_state()
        
        assert result is not None
        assert result.spot_btc == position_state.spot_btc
    
    @pytest.mark.asyncio
    async def test_get_state_history(self, storage, position_state, mock_session):
        """Test retrieving state history."""
        # Mock query result
        mock_record = PositionStateRecord(
            timestamp=position_state.timestamp,
            spot_btc=position_state.spot_btc,
            long_perp=position_state.long_perp,
            short_perp=position_state.short_perp,
            net_delta=position_state.net_delta,
            hedge_ratio=position_state.hedge_ratio,
            btc_price=position_state.btc_price,
            volatility_24h=position_state.volatility_24h,
            funding_rate=position_state.funding_rate,
            unrealized_pnl=position_state.unrealized_pnl,
            realized_pnl=position_state.realized_pnl,
            peak_pnl=position_state.peak_pnl,
            market_regime=position_state.market_regime.value,
            funding_regime=position_state.funding_regime
        )
        
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = [mock_record]
        mock_session.query.return_value = mock_query
        
        result = await storage.get_state_history(hours=24)
        
        assert len(result) == 1
        assert result[0].spot_btc == position_state.spot_btc
    
    @pytest.mark.asyncio
    async def test_delete_old_states(self, storage, mock_session):
        """Test deleting old states."""
        mock_query = Mock()
        mock_query.filter.return_value.delete.return_value = 50
        mock_session.query.return_value = mock_query
        
        result = await storage.delete_old_states(days=7)
        
        assert result == 50
        mock_session.commit.assert_called_once()


class TestStorageFactory:
    """Test storage factory function."""
    
    def test_create_redis_storage(self):
        """Test creating Redis storage."""
        with patch('redis.from_url'):
            storage = create_storage("redis", "redis://localhost:6379")
            assert isinstance(storage, RedisPositionStorage)
    
    def test_create_postgres_storage(self):
        """Test creating PostgreSQL storage."""
        with patch('sqlalchemy.create_engine'):
            storage = create_storage("postgres", "postgresql://localhost/test")
            assert isinstance(storage, PostgresPositionStorage)
    
    def test_create_invalid_storage(self):
        """Test error on invalid storage type."""
        with pytest.raises(ValueError):
            create_storage("invalid", "some://url")