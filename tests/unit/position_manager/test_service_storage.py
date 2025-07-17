"""
Unit tests for Position Manager Service with Storage Integration.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.hedgelock.position_manager.service import PositionManagerService
from src.hedgelock.position_manager.models import PositionState, MarketRegime
from src.hedgelock.position_manager.storage import PositionStorage


class TestServiceStorageIntegration:
    """Test service integration with storage."""
    
    @pytest.fixture
    def mock_storage(self):
        """Mock storage backend."""
        storage = AsyncMock(spec=PositionStorage)
        storage.save_state = AsyncMock(return_value=True)
        storage.get_latest_state = AsyncMock(return_value=None)
        storage.get_state_history = AsyncMock(return_value=[])
        storage.delete_old_states = AsyncMock(return_value=0)
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
            return service
    
    @pytest.fixture
    def saved_position(self):
        """Create a saved position state."""
        return PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.5,
            long_perp=0.3,
            short_perp=0.2,
            net_delta=0.6,
            hedge_ratio=0.8,
            btc_price=120000,
            volatility_24h=0.03,
            funding_rate=0.0002,
            unrealized_pnl=1000,
            peak_pnl=1500,
            market_regime=MarketRegime.VOLATILE
        )
    
    @pytest.mark.asyncio
    async def test_recover_state_success(self, service, mock_storage, saved_position):
        """Test successful state recovery on startup."""
        mock_storage.get_latest_state.return_value = saved_position
        mock_storage.get_state_history.return_value = [
            PositionState(
                timestamp=datetime.utcnow(),
                spot_btc=0.5,
                long_perp=0.3,
                short_perp=0.2,
                net_delta=0.6,
                hedge_ratio=0.8,
                btc_price=price,
                volatility_24h=0.03,
                funding_rate=0.0002
            ) for price in [118000, 119000, 120000]
        ]
        
        await service.recover_state()
        
        # Verify state was recovered
        assert service.current_position.spot_btc == 0.5
        assert service.current_position.long_perp == 0.3
        assert service.current_position.short_perp == 0.2
        assert service.current_position.btc_price == 120000
        assert service.current_position.unrealized_pnl == 1000
        
        # Verify price history was loaded
        assert len(service.manager.price_history) == 3
        assert service.manager.price_history[-1] == 120000
        
        mock_storage.get_latest_state.assert_called_once()
        mock_storage.get_state_history.assert_called_once_with(hours=24)
    
    @pytest.mark.asyncio
    async def test_recover_state_no_saved_state(self, service, mock_storage):
        """Test recovery when no saved state exists."""
        mock_storage.get_latest_state.return_value = None
        
        await service.recover_state()
        
        # Should keep default state
        assert service.current_position.spot_btc == 0.27
        assert service.current_position.long_perp == 0.213
        assert service.current_position.short_perp == 0.213
    
    @pytest.mark.asyncio
    async def test_recover_state_error(self, service, mock_storage):
        """Test recovery error handling."""
        mock_storage.get_latest_state.side_effect = Exception("Storage error")
        
        await service.recover_state()
        
        # Should keep default state on error
        assert service.current_position.spot_btc == 0.27
    
    @pytest.mark.asyncio
    async def test_periodic_state_save(self, service, mock_storage):
        """Test periodic state saving."""
        service.running = True
        
        # Run save task briefly
        task = asyncio.create_task(service.periodic_state_save())
        await asyncio.sleep(0.1)  # Let it start
        service.running = False
        
        # Clean up task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Should not have saved yet (60s interval)
        mock_storage.save_state.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_save_state_after_update(self, service, mock_storage):
        """Test saving state after update."""
        await service.save_state_after_update()
        
        mock_storage.save_state.assert_called_once_with(service.current_position)
    
    @pytest.mark.asyncio
    async def test_save_state_after_update_error(self, service, mock_storage):
        """Test error handling in save after update."""
        mock_storage.save_state.side_effect = Exception("Save error")
        
        # Should not raise exception
        await service.save_state_after_update()
    
    @pytest.mark.asyncio
    async def test_stop_saves_final_state(self, service, mock_storage):
        """Test that stop() saves final state."""
        service.running = True
        service.consumer = AsyncMock()
        service.producer = AsyncMock()
        
        await service.stop()
        
        assert service.running is False
        mock_storage.save_state.assert_called_once_with(service.current_position)
    
    @pytest.mark.asyncio
    async def test_rehedge_saves_state(self, service, mock_storage):
        """Test that rehedging saves state."""
        service.producer = AsyncMock()
        service.running = True
        
        # Mock manager to return a decision
        service.manager.generate_hedge_decision = Mock()
        service.manager.generate_hedge_decision.return_value = Mock(
            timestamp=datetime.utcnow(),
            target_hedge_ratio=0.4,
            adjust_short=0.1,
            adjust_long=-0.1,
            reason="Test rehedge"
        )
        
        await service.rehedge_positions()
        
        # Should save state after rehedge
        mock_storage.save_state.assert_called_with(service.current_position)
    
    @pytest.mark.asyncio
    async def test_take_profit_saves_state(self, service, mock_storage):
        """Test that profit taking saves state."""
        service.producer = AsyncMock()
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        service.current_position.unrealized_pnl = 1000
        
        await service.take_profit()
        
        # Should save state after profit taking
        mock_storage.save_state.assert_called_with(service.current_position)
        
        # Verify positions were closed
        assert service.current_position.long_perp == 0.0
        assert service.current_position.short_perp == 0.0
    
    @pytest.mark.asyncio
    async def test_emergency_close_saves_state(self, service, mock_storage):
        """Test that emergency close saves state."""
        service.producer = AsyncMock()
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        
        await service.emergency_close_positions()
        
        # Should save state after emergency close
        mock_storage.save_state.assert_called_with(service.current_position)
        
        # Verify positions were closed
        assert service.current_position.long_perp == 0.0
        assert service.current_position.short_perp == 0.0
    
    @pytest.mark.asyncio
    async def test_no_storage_configured(self):
        """Test service works without storage."""
        config = {
            'kafka_servers': 'localhost:29092'
        }
        
        with patch('src.hedgelock.position_manager.service.create_storage', side_effect=Exception("No storage")):
            service = PositionManagerService(config)
            service.storage = None
            
            # Should work without storage
            await service.recover_state()
            await service.save_state_after_update()
            
            # Default state should be maintained
            assert service.current_position.spot_btc == 0.27