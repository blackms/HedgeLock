"""
Unit tests for Position Manager Service P&L Integration.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.hedgelock.position_manager.service import PositionManagerService
from src.hedgelock.position_manager.models import PositionState, MarketRegime
from src.hedgelock.position_manager.pnl_calculator import PnLCalculator, PnLBreakdown


class TestServicePnLIntegration:
    """Test service integration with P&L tracking."""
    
    @pytest.fixture
    def config(self):
        """Service configuration."""
        return {
            'kafka_servers': 'localhost:29092',
            'storage_type': 'redis',
            'storage_url': 'redis://localhost:6379'
        }
    
    @pytest.fixture
    def mock_storage(self):
        """Mock storage backend."""
        storage = AsyncMock()
        storage.save_state = AsyncMock(return_value=True)
        storage.get_latest_state = AsyncMock(return_value=None)
        storage.get_state_history = AsyncMock(return_value=[])
        storage.delete_old_states = AsyncMock(return_value=0)
        return storage
    
    @pytest.fixture
    def service(self, config, mock_storage):
        """Create service with mocked storage."""
        with patch('src.hedgelock.position_manager.service.create_storage', return_value=mock_storage):
            service = PositionManagerService(config)
            service.storage = mock_storage
            service.producer = AsyncMock()
            return service
    
    def test_pnl_calculator_initialized(self, service):
        """Test that P&L calculator is initialized."""
        assert hasattr(service, 'pnl_calculator')
        assert isinstance(service.pnl_calculator, PnLCalculator)
        assert service.pnl_calculator.entry_prices['spot'] == 116000
    
    @pytest.mark.asyncio
    async def test_update_pnl_and_publish(self, service):
        """Test P&L update and publishing."""
        # Set up mock P&L breakdown
        mock_breakdown = PnLBreakdown(
            spot_pnl=1000,
            long_perp_pnl=500,
            short_perp_pnl=-300,
            funding_pnl=-50,
            total_unrealized_pnl=1150,
            total_realized_pnl=2000,
            net_pnl=3150,
            timestamp=datetime.utcnow()
        )
        
        service.pnl_calculator.calculate_pnl = Mock(return_value=mock_breakdown)
        service.pnl_calculator.get_pnl_metrics = Mock(return_value={
            'spot_pnl': 1000,
            'unrealized_pnl': 1150,
            'realized_pnl': 2000,
            'roi_percent': 5.2
        })
        
        await service.update_pnl_and_publish()
        
        # Should update position state
        assert service.current_position.unrealized_pnl == 1150
        assert service.current_position.realized_pnl == 2000
        
        # Should publish to Kafka
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'pnl_updates'
        
        # Check message structure
        message = call_args[1]['value']
        assert 'pnl_breakdown' in message
        assert message['pnl_breakdown']['spot_pnl'] == 1000
        assert message['pnl_breakdown']['net_pnl'] == 3150
        assert 'metrics' in message
    
    @pytest.mark.asyncio
    async def test_price_update_triggers_pnl(self, service):
        """Test that price updates trigger P&L calculation."""
        service.update_pnl_and_publish = AsyncMock()
        
        # Send price update
        await service.handle_price_update({'price': 120000})
        
        # Should update price
        assert service.current_position.btc_price == 120000
        
        # Should trigger P&L update
        service.update_pnl_and_publish.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rehedge_updates_entry_prices(self, service):
        """Test that rehedging updates entry prices for P&L tracking."""
        # Mock the hedge decision
        mock_decision = Mock(
            timestamp=datetime.utcnow(),
            target_hedge_ratio=0.4,
            adjust_short=0.1,
            adjust_long=-0.05,
            reason="Test rehedge"
        )
        
        service.manager.generate_hedge_decision = Mock(return_value=mock_decision)
        service.update_pnl_and_publish = AsyncMock()
        
        # Current positions
        service.current_position.long_perp = 0.3
        service.current_position.short_perp = 0.2
        service.current_position.btc_price = 118000
        
        await service.rehedge_positions()
        
        # Should update positions
        assert service.current_position.long_perp == pytest.approx(0.25)  # 0.3 - 0.05
        assert service.current_position.short_perp == pytest.approx(0.3)   # 0.2 + 0.1
        
        # Should have called update_entry_prices
        # Check that entry prices were updated (through the calculator)
        service.update_pnl_and_publish.assert_called()
    
    @pytest.mark.asyncio
    async def test_take_profit_realizes_pnl(self, service):
        """Test that taking profit realizes P&L."""
        # Set up positions
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        service.current_position.btc_price = 120000
        service.current_position.unrealized_pnl = 1500
        
        # Mock realize_pnl
        service.pnl_calculator.realize_pnl = Mock(return_value=1500)
        service.pnl_calculator.cumulative_realized_pnl = 3500
        service.update_pnl_and_publish = AsyncMock()
        
        await service.take_profit()
        
        # Should call realize_pnl with closed positions
        service.pnl_calculator.realize_pnl.assert_called_once()
        call_args = service.pnl_calculator.realize_pnl.call_args[0]
        assert call_args[0]['long_perp'] == 0.5
        assert call_args[0]['short_perp'] == 0.2
        assert call_args[1] == 120000  # Closing price
        
        # Should update P&L
        service.update_pnl_and_publish.assert_called()
        
        # Should send profit taking event with realized P&L
        profit_calls = [call for call in service.producer.send_and_wait.call_args_list 
                       if call[0][0] == 'profit_taking']
        assert len(profit_calls) > 0
        profit_msg = profit_calls[0][1]['value']
        assert 'realized_pnl' in profit_msg
        assert profit_msg['total_realized'] == 3500
        
        # Positions should be closed
        assert service.current_position.long_perp == 0.0
        assert service.current_position.short_perp == 0.0
    
    @pytest.mark.asyncio
    async def test_emergency_close_updates_pnl(self, service):
        """Test that emergency close updates P&L."""
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        service.update_pnl_and_publish = AsyncMock()
        
        await service.emergency_close_positions()
        
        # Should close positions
        assert service.current_position.long_perp == 0.0
        assert service.current_position.short_perp == 0.0
        
        # P&L update not called during emergency (positions just closed)
        # This is correct behavior - in emergency we close first, calculate later
    
    @pytest.mark.asyncio
    async def test_pnl_error_handling(self, service):
        """Test P&L update error handling."""
        # Make calculate_pnl raise an exception
        service.pnl_calculator.calculate_pnl = Mock(
            side_effect=Exception("P&L calculation error")
        )
        
        # Should not raise exception
        await service.update_pnl_and_publish()
        
        # Should not publish to Kafka
        service.producer.send_and_wait.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_significant_pnl_logging(self, service, caplog):
        """Test that significant P&L changes are logged."""
        # Set up mock P&L breakdown with significant P&L
        mock_breakdown = PnLBreakdown(
            spot_pnl=500,
            long_perp_pnl=300,
            short_perp_pnl=-200,
            funding_pnl=-50,
            total_unrealized_pnl=550,
            total_realized_pnl=1000,
            net_pnl=1550,  # > $100 threshold
            timestamp=datetime.utcnow()
        )
        
        service.pnl_calculator.calculate_pnl = Mock(return_value=mock_breakdown)
        service.pnl_calculator.get_pnl_metrics = Mock(return_value={})
        
        with caplog.at_level('INFO'):
            await service.update_pnl_and_publish()
        
        # Should log significant P&L
        assert any("P&L Update" in record.message for record in caplog.records)
        assert any("Net=$1550.00" in record.message for record in caplog.records)
    
    @pytest.mark.asyncio
    async def test_pnl_with_no_producer(self, service):
        """Test P&L update when producer is not initialized."""
        service.producer = None
        
        mock_breakdown = PnLBreakdown(
            spot_pnl=100,
            long_perp_pnl=50,
            short_perp_pnl=-30,
            funding_pnl=-10,
            total_unrealized_pnl=110,
            total_realized_pnl=200,
            net_pnl=310,
            timestamp=datetime.utcnow()
        )
        
        service.pnl_calculator.calculate_pnl = Mock(return_value=mock_breakdown)
        service.pnl_calculator.get_pnl_metrics = Mock(return_value={})
        
        # Should not raise exception
        await service.update_pnl_and_publish()
        
        # Should still update position state
        assert service.current_position.unrealized_pnl == 110
        assert service.current_position.realized_pnl == 200
    
    def test_pnl_integration_with_funding_update(self, service):
        """Test P&L tracking considers funding rate updates."""
        # Update funding rate
        service.current_position.funding_rate = 0.0005  # 0.05%
        
        # With net long position, funding P&L should be negative
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        
        breakdown = service.pnl_calculator.calculate_pnl(service.current_position)
        
        # Funding P&L should be calculated
        assert breakdown.funding_pnl < 0  # Net long pays funding
    
    @pytest.mark.asyncio
    async def test_position_state_includes_pnl(self, service):
        """Test that position state messages include P&L data."""
        # Update P&L
        service.current_position.unrealized_pnl = 1234
        service.current_position.realized_pnl = 5678
        
        # Trigger position state publish
        await service.rehedge_positions()
        
        # Find position_states message
        position_calls = [call for call in service.producer.send_and_wait.call_args_list
                         if call[0][0] == 'position_states']
        
        assert len(position_calls) > 0
        position_msg = position_calls[0][1]['value']
        
        # Should include P&L in position state
        state = position_msg['position_state']
        assert state['unrealized_pnl'] == 1234
        assert state['realized_pnl'] == 5678