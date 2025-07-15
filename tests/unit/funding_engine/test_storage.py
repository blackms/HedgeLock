"""
Unit tests for funding storage with 100% coverage.
"""

import pytest
import redis
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from src.hedgelock.funding_engine.storage import FundingStorage
from src.hedgelock.funding_engine.config import FundingEngineConfig
from src.hedgelock.shared.funding_models import FundingRate, FundingRegime


class TestFundingStorage:
    """Test funding storage operations."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = Mock(spec=redis.Redis)
        return mock
    
    @pytest.fixture
    def storage(self, mock_redis):
        """Create storage instance with mocked Redis."""
        config = FundingEngineConfig()
        with patch('redis.Redis', return_value=mock_redis):
            storage = FundingStorage(config)
        return storage
    
    @pytest.fixture
    def sample_funding_rate(self):
        """Create a sample funding rate."""
        return FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0001,
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
    
    def test_storage_initialization(self):
        """Test storage initialization."""
        config = FundingEngineConfig(
            redis_host="test-host",
            redis_port=6380,
            redis_db=1
        )
        
        with patch('redis.Redis') as mock_redis_class:
            storage = FundingStorage(config)
            
            mock_redis_class.assert_called_once_with(
                host="test-host",
                port=6380,
                db=1,
                decode_responses=True
            )
    
    def test_store_funding_rate(self, storage, mock_redis, sample_funding_rate):
        """Test storing a funding rate."""
        # Call store method
        storage.store_funding_rate(sample_funding_rate)
        
        # Verify zadd was called
        key = f"funding:history:{sample_funding_rate.symbol}"
        mock_redis.zadd.assert_called_once()
        
        # Verify the stored data
        call_args = mock_redis.zadd.call_args
        assert call_args[0][0] == key
        
        # Check the data contains required fields
        stored_data = list(call_args[0][1].keys())[0]
        data = json.loads(stored_data)
        assert data["symbol"] == "BTCUSDT"
        assert data["funding_rate"] == 0.0001
        assert data["annualized_rate"] == sample_funding_rate.annualized_rate
        
        # Verify cleanup of old entries
        mock_redis.zremrangebyscore.assert_called_once()
        
        # Verify current rate update
        current_key = f"funding:current:{sample_funding_rate.symbol}"
        mock_redis.setex.assert_called_once()
        setex_args = mock_redis.setex.call_args
        assert setex_args[0][0] == current_key
        assert setex_args[0][1] == 3600  # 1 hour TTL
    
    def test_get_funding_history(self, storage, mock_redis):
        """Test retrieving funding history."""
        # Mock Redis response
        mock_data = [
            json.dumps({
                "symbol": "BTCUSDT",
                "funding_rate": 0.0001,
                "funding_time": datetime.utcnow().isoformat(),
                "mark_price": 50000.0,
                "index_price": 50000.0,
                "annualized_rate": 10.95,
                "daily_rate": 0.03
            }),
            json.dumps({
                "symbol": "BTCUSDT",
                "funding_rate": 0.00015,
                "funding_time": (datetime.utcnow() - timedelta(hours=8)).isoformat(),
                "mark_price": 50100.0,
                "index_price": 50100.0,
                "annualized_rate": 16.425,
                "daily_rate": 0.045
            })
        ]
        mock_redis.zrangebyscore.return_value = mock_data
        
        # Get history
        rates = storage.get_funding_history("BTCUSDT", hours=24)
        
        # Verify results
        assert len(rates) == 2
        assert rates[0].symbol == "BTCUSDT"
        assert rates[0].funding_rate == 0.0001
        assert rates[1].funding_rate == 0.00015
        
        # Verify Redis call
        mock_redis.zrangebyscore.assert_called_once()
        call_args = mock_redis.zrangebyscore.call_args
        assert call_args[0][0] == "funding:history:BTCUSDT"
    
    def test_get_funding_history_empty(self, storage, mock_redis):
        """Test retrieving empty funding history."""
        mock_redis.zrangebyscore.return_value = []
        
        rates = storage.get_funding_history("BTCUSDT", hours=24)
        
        assert len(rates) == 0
    
    def test_get_current_funding_rate_from_cache(self, storage, mock_redis):
        """Test getting current funding rate from cache."""
        # Mock cached rate
        cached_data = json.dumps({
            "symbol": "BTCUSDT",
            "funding_rate": 0.0001,
            "funding_time": datetime.utcnow().isoformat(),
            "mark_price": 50000.0,
            "index_price": 50000.0,
            "annualized_rate": 10.95,
            "daily_rate": 0.03
        })
        mock_redis.get.return_value = cached_data
        
        # Get current rate
        rate = storage.get_current_funding_rate("BTCUSDT")
        
        # Verify result
        assert rate is not None
        assert rate.symbol == "BTCUSDT"
        assert rate.funding_rate == 0.0001
        
        # Verify only cache was checked
        mock_redis.get.assert_called_once_with("funding:current:BTCUSDT")
        mock_redis.zrange.assert_not_called()
    
    def test_get_current_funding_rate_from_history(self, storage, mock_redis):
        """Test getting current funding rate from history when cache miss."""
        # Mock no cache
        mock_redis.get.return_value = None
        
        # Mock history fallback
        history_data = json.dumps({
            "symbol": "BTCUSDT",
            "funding_rate": 0.00012,
            "funding_time": datetime.utcnow().isoformat(),
            "mark_price": 50050.0,
            "index_price": 50050.0,
            "annualized_rate": 13.14,
            "daily_rate": 0.036
        })
        mock_redis.zrange.return_value = [history_data]
        
        # Get current rate
        rate = storage.get_current_funding_rate("BTCUSDT")
        
        # Verify result
        assert rate is not None
        assert rate.funding_rate == 0.00012
        
        # Verify both cache and history were checked
        mock_redis.get.assert_called_once()
        mock_redis.zrange.assert_called_once_with("funding:history:BTCUSDT", -1, -1)
    
    def test_get_current_funding_rate_not_found(self, storage, mock_redis):
        """Test getting current funding rate when not found."""
        mock_redis.get.return_value = None
        mock_redis.zrange.return_value = []
        
        rate = storage.get_current_funding_rate("BTCUSDT")
        
        assert rate is None
    
    def test_store_funding_regime(self, storage, mock_redis):
        """Test storing funding regime."""
        storage.store_funding_regime("BTCUSDT", FundingRegime.HEATED)
        
        mock_redis.setex.assert_called_once_with(
            "funding:regime:BTCUSDT",
            3600,
            "heated"
        )
    
    def test_get_funding_regime_exists(self, storage, mock_redis):
        """Test getting existing funding regime."""
        mock_redis.get.return_value = "mania"
        
        regime = storage.get_funding_regime("BTCUSDT")
        
        assert regime == FundingRegime.MANIA
        mock_redis.get.assert_called_once_with("funding:regime:BTCUSDT")
    
    def test_get_funding_regime_not_found(self, storage, mock_redis):
        """Test getting funding regime when not found."""
        mock_redis.get.return_value = None
        
        regime = storage.get_funding_regime("BTCUSDT")
        
        assert regime is None
    
    def test_store_funding_rate_cleanup(self, storage, mock_redis, sample_funding_rate):
        """Test that old funding rates are cleaned up."""
        storage.store_funding_rate(sample_funding_rate)
        
        # Verify cleanup was called
        mock_redis.zremrangebyscore.assert_called_once()
        call_args = mock_redis.zremrangebyscore.call_args
        
        # Check the key
        assert call_args[0][0] == f"funding:history:{sample_funding_rate.symbol}"
        
        # Check the cutoff timestamp (should be ~7 days ago)
        cutoff_timestamp = call_args[0][2]
        expected_cutoff = datetime.utcnow() - timedelta(hours=168)
        # Allow 1 second tolerance
        assert abs(cutoff_timestamp - expected_cutoff.timestamp()) < 1
    
    def test_funding_history_time_range(self, storage, mock_redis):
        """Test that funding history respects time range."""
        storage.get_funding_history("BTCUSDT", hours=48)
        
        # Verify the time range in the Redis call
        call_args = mock_redis.zrangebyscore.call_args
        start_timestamp = call_args[0][1]
        end_timestamp = call_args[0][2]
        
        # Check timestamps
        expected_start = datetime.utcnow() - timedelta(hours=48)
        expected_end = datetime.utcnow()
        
        # Allow 1 second tolerance
        assert abs(start_timestamp - expected_start.timestamp()) < 1
        assert abs(end_timestamp - expected_end.timestamp()) < 1