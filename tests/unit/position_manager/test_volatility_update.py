"""
Unit tests for hourly volatility update feature.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.hedgelock.position_manager.service import PositionManagerService
from src.hedgelock.position_manager.models import PositionState, MarketRegime


class TestHourlyVolatilityUpdate:
    """Test hourly volatility update functionality."""
    
    @pytest.fixture
    def mock_storage(self):
        """Mock storage backend."""
        storage = AsyncMock()
        storage.save_state = AsyncMock(return_value=True)
        storage.get_latest_state = AsyncMock(return_value=None)
        storage.get_state_history = AsyncMock(return_value=[])
        return storage
    
    @pytest.fixture
    def config(self):
        """Service configuration."""
        return {
            'kafka_servers': 'localhost:29092',
            'storage_type': 'redis',
            'storage_url': 'redis://localhost:6379'
        }
    
    @pytest.fixture
    def service(self, config, mock_storage):
        """Create service with mocked storage."""
        with patch('src.hedgelock.position_manager.service.create_storage', return_value=mock_storage):
            service = PositionManagerService(config)
            service.storage = mock_storage
            service.producer = AsyncMock()
            return service
    
    @pytest.fixture
    def price_history(self):
        """Create price history for volatility calculation."""
        base_price = 100000
        prices = []
        for i in range(24):
            # Add some volatility
            price = base_price * (1 + (i % 4 - 2) * 0.01)
            state = PositionState(
                timestamp=datetime.utcnow() - timedelta(hours=23-i),
                spot_btc=0.27,
                long_perp=0.213,
                short_perp=0.213,
                net_delta=0.27,
                hedge_ratio=1.0,
                btc_price=price,
                volatility_24h=0.02,
                funding_rate=0.0001
            )
            prices.append(state)
        return prices
    
    @pytest.mark.asyncio
    async def test_hourly_volatility_calculation(self, service, mock_storage, price_history):
        """Test volatility recalculation with historical data."""
        service.running = True
        mock_storage.get_state_history.return_value = price_history
        
        # Mock sleep to return immediately
        with patch('asyncio.sleep', return_value=None) as mock_sleep:
            # Run one iteration
            task = asyncio.create_task(service.hourly_volatility_update())
            await asyncio.sleep(0.1)
            service.running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Should have called get_state_history
        mock_storage.get_state_history.assert_called_with(hours=24)
        
        # Should have updated volatility
        assert service.current_position.volatility_24h != 0.02  # Changed from default
    
    @pytest.mark.asyncio
    async def test_volatility_change_triggers_rehedge(self, service, mock_storage, price_history):
        """Test that significant volatility change triggers rehedge."""
        service.running = True
        service.current_position.volatility_24h = 0.02
        
        # Create high volatility history
        for state in price_history:
            state.btc_price *= 1.1  # 10% higher prices
        
        mock_storage.get_state_history.return_value = price_history
        service.rehedge_positions = AsyncMock()
        
        # Mock time calculations
        with patch('asyncio.sleep', return_value=None):
            # Run one iteration
            task = asyncio.create_task(service.hourly_volatility_update())
            await asyncio.sleep(0.1)
            service.running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Should have triggered rehedge due to volatility change
        service.rehedge_positions.assert_called()
    
    @pytest.mark.asyncio
    async def test_no_rehedge_small_volatility_change(self, service, mock_storage, price_history):
        """Test that small volatility changes don't trigger rehedge."""
        service.running = True
        service.current_position.volatility_24h = 0.02
        
        # Small price changes
        for i, state in enumerate(price_history):
            state.btc_price = 100000 + i * 10  # Small linear change
        
        mock_storage.get_state_history.return_value = price_history
        service.rehedge_positions = AsyncMock()
        
        with patch('asyncio.sleep', return_value=None):
            task = asyncio.create_task(service.hourly_volatility_update())
            await asyncio.sleep(0.1)
            service.running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Should not trigger rehedge for small change
        service.rehedge_positions.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_volatility_update_without_storage(self, service):
        """Test volatility update when storage is not configured."""
        service.running = True
        service.storage = None
        
        # Add manual price history
        service.manager.price_history = [100000, 101000, 99000, 102000]
        
        with patch('asyncio.sleep', return_value=None):
            task = asyncio.create_task(service.hourly_volatility_update())
            await asyncio.sleep(0.1)
            service.running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Should still calculate volatility from buffer
        assert service.current_position.volatility_24h > 0
    
    @pytest.mark.asyncio
    async def test_volatility_update_error_handling(self, service, mock_storage):
        """Test error handling in volatility update."""
        service.running = True
        mock_storage.get_state_history.side_effect = Exception("Storage error")
        
        # Should not crash
        with patch('asyncio.sleep', side_effect=[None, asyncio.CancelledError()]):
            task = asyncio.create_task(service.hourly_volatility_update())
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_wait_for_next_hour(self, service, mock_storage):
        """Test that update waits for the next hour."""
        service.running = True
        
        # Mock datetime to control timing
        now = datetime(2024, 1, 1, 10, 30, 0)  # 10:30
        next_hour = datetime(2024, 1, 1, 11, 0, 0)  # 11:00
        
        with patch('src.hedgelock.position_manager.service.datetime') as mock_dt:
            mock_dt.utcnow.return_value = now
            
            sleep_times = []
            async def mock_sleep(seconds):
                sleep_times.append(seconds)
                service.running = False  # Stop after first sleep
                
            with patch('asyncio.sleep', side_effect=mock_sleep):
                await service.hourly_volatility_update()
            
            # Should wait 30 minutes (1800 seconds)
            assert len(sleep_times) > 0
            assert sleep_times[0] == 1800  # 30 minutes
    
    @pytest.mark.asyncio
    async def test_insufficient_history(self, service, mock_storage):
        """Test handling of insufficient price history."""
        service.running = True
        
        # Only one data point
        mock_storage.get_state_history.return_value = [
            PositionState(
                timestamp=datetime.utcnow(),
                spot_btc=0.27,
                long_perp=0.213,
                short_perp=0.213,
                net_delta=0.27,
                hedge_ratio=1.0,
                btc_price=100000,
                volatility_24h=0.02,
                funding_rate=0.0001
            )
        ]
        
        old_volatility = service.current_position.volatility_24h
        
        with patch('asyncio.sleep', return_value=None):
            task = asyncio.create_task(service.hourly_volatility_update())
            await asyncio.sleep(0.1)
            service.running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Volatility should not change with insufficient data
        assert service.current_position.volatility_24h == old_volatility