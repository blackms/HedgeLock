"""
Unit tests for Position Manager Service.
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.hedgelock.position_manager.service import PositionManagerService
from src.hedgelock.position_manager.models import PositionState, MarketRegime


class TestPositionManagerService:
    """Test PositionManagerService class."""
    
    @pytest.fixture
    def config(self):
        """Service configuration."""
        return {
            'kafka_servers': 'localhost:29092'
        }
    
    @pytest.fixture
    def service(self, config):
        """Create service instance."""
        return PositionManagerService(config)
    
    @pytest.fixture
    def mock_producer(self):
        """Mock Kafka producer."""
        producer = AsyncMock()
        producer.start = AsyncMock()
        producer.stop = AsyncMock()
        producer.send_and_wait = AsyncMock()
        return producer
    
    @pytest.fixture
    def mock_consumer(self):
        """Mock Kafka consumer."""
        consumer = AsyncMock()
        consumer.start = AsyncMock()
        consumer.stop = AsyncMock()
        return consumer
    
    def test_initialization(self, service, config):
        """Test service initialization."""
        assert service.config == config
        assert service.manager is not None
        assert service.consumer is None
        assert service.producer is None
        assert service.running is False
        
        # Check initial position
        assert service.current_position.spot_btc == 0.27
        assert service.current_position.long_perp == 0.213
        assert service.current_position.short_perp == 0.213
        assert service.current_position.btc_price == 116000
    
    @pytest.mark.asyncio
    async def test_start_service(self, service, mock_producer, mock_consumer):
        """Test starting the service."""
        with patch('src.hedgelock.position_manager.service.AIOKafkaProducer', return_value=mock_producer):
            with patch('src.hedgelock.position_manager.service.AIOKafkaConsumer', return_value=mock_consumer):
                # Mock the gather to not run forever
                with patch('asyncio.gather', new_callable=AsyncMock) as mock_gather:
                    await service.start()
                    
                    # Verify Kafka clients initialized
                    assert service.consumer is not None
                    assert service.producer is not None
                    assert service.running is True
                    
                    # Verify Kafka started
                    mock_consumer.start.assert_called_once()
                    mock_producer.start.assert_called_once()
                    
                    # Verify processing loops started
                    mock_gather.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_funding_update(self, service, mock_producer):
        """Test handling funding context updates."""
        service.producer = mock_producer
        
        # Normal funding update
        data = {
            'funding_context': {
                'current_regime': 'HEATED',
                'current_rate': 75.0,
                'should_exit': False
            }
        }
        
        await service.handle_funding_update(data)
        
        assert service.current_position.funding_regime == 'HEATED'
        assert service.current_position.funding_rate == pytest.approx(75.0 / 100 / 365 / 3)
        
        # Set up a position that needs closing
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        
        # Emergency exit
        data['funding_context']['should_exit'] = True
        await service.handle_funding_update(data)
        
        # Should trigger emergency close - check the calls
        calls = mock_producer.send_and_wait.call_args_list
        # Should have hedge_trades and emergency_actions
        assert len(calls) >= 2
        hedge_call = None
        emergency_call = None
        for call in calls:
            if call[0][0] == 'hedge_trades':
                hedge_call = call
            elif call[0][0] == 'emergency_actions':
                emergency_call = call
        
        assert hedge_call is not None
        assert emergency_call is not None
    
    @pytest.mark.asyncio
    async def test_handle_price_update(self, service):
        """Test handling price updates."""
        # Initial state
        assert len(service.manager.price_history) == 0
        
        # Send price update
        data = {'price': 120000}
        await service.handle_price_update(data)
        
        assert service.current_position.btc_price == 120000
        assert len(service.manager.price_history) == 1
        assert service.manager.price_history[0] == 120000
        
        # Add more prices
        for price in [121000, 122000, 123000]:
            await service.handle_price_update({'price': price})
        
        assert len(service.manager.price_history) == 4
        assert service.current_position.volatility_24h > 0
    
    @pytest.mark.asyncio
    async def test_price_history_limit(self, service):
        """Test price history is limited to 24 entries."""
        # Add 30 prices
        for i in range(30):
            await service.handle_price_update({'price': 100000 + i * 100})
        
        # Should only keep last 24
        assert len(service.manager.price_history) == 24
        assert service.manager.price_history[0] == 100600  # 6th price
        assert service.manager.price_history[-1] == 102900  # 30th price
    
    @pytest.mark.asyncio
    async def test_rehedge_positions(self, service, mock_producer):
        """Test rehedging positions."""
        service.producer = mock_producer
        service.running = True
        
        await service.rehedge_positions()
        
        # Should send hedge trade
        mock_producer.send_and_wait.assert_called()
        
        # Check message format
        calls = mock_producer.send_and_wait.call_args_list
        hedge_call = None
        for call in calls:
            if call[0][0] == 'hedge_trades':
                hedge_call = call
                break
        
        assert hedge_call is not None
        msg = hedge_call[1]['value']
        
        assert msg['service'] == 'position-manager'
        assert 'hedge_decision' in msg
        assert 'order_request' in msg
        assert msg['order_request']['symbol'] == 'BTCUSDT'
        assert msg['order_request']['orderType'] == 'Market'
    
    @pytest.mark.asyncio
    async def test_take_profit(self, service, mock_producer):
        """Test profit taking logic."""
        service.producer = mock_producer
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        service.current_position.unrealized_pnl = 1000
        
        await service.take_profit()
        
        # Should send two messages
        assert mock_producer.send_and_wait.call_count == 2
        
        # Check hedge trade sent
        hedge_call = mock_producer.send_and_wait.call_args_list[0]
        assert hedge_call[0][0] == 'hedge_trades'
        msg = hedge_call[1]['value']
        assert msg['hedge_decision']['risk_state'] == 'TAKING_PROFIT'
        assert msg['hedge_decision']['reason'] == 'Profit target reached'
        
        # Check profit taking event
        profit_call = mock_producer.send_and_wait.call_args_list[1]
        assert profit_call[0][0] == 'profit_taking'
        
        # Positions should be reset
        assert service.current_position.long_perp == 0.0
        assert service.current_position.short_perp == 0.0
        assert service.current_position.market_regime == MarketRegime.TAKING_PROFIT
    
    @pytest.mark.asyncio
    async def test_emergency_close_positions(self, service, mock_producer):
        """Test emergency position closure."""
        service.producer = mock_producer
        service.current_position.long_perp = 0.5
        service.current_position.short_perp = 0.2
        
        await service.emergency_close_positions()
        
        # Should send two messages
        assert mock_producer.send_and_wait.call_count == 2
        
        # Check emergency trade
        hedge_call = mock_producer.send_and_wait.call_args_list[0]
        assert hedge_call[0][0] == 'hedge_trades'
        msg = hedge_call[1]['value']
        assert msg['hedge_decision']['risk_state'] == 'EMERGENCY'
        assert msg['hedge_decision']['urgency'] == 'CRITICAL'
        assert 'EMERGENCY' in msg['hedge_decision']['reason']
        
        # Check emergency action event
        emergency_call = mock_producer.send_and_wait.call_args_list[1]
        assert emergency_call[0][0] == 'emergency_actions'
        
        # Positions should be closed
        assert service.current_position.long_perp == 0.0
        assert service.current_position.short_perp == 0.0
    
    @pytest.mark.asyncio
    async def test_periodic_rehedge_timing(self, service, mock_producer):
        """Test periodic rehedge checks."""
        service.producer = mock_producer
        service.running = True
        
        # Mock should_rehedge to return True
        service.manager.should_rehedge = Mock(return_value=True)
        service.rehedge_positions = AsyncMock()
        service.manager.check_profit_targets = Mock(return_value=False)
        
        # Run one iteration
        async def run_one_iteration():
            service.running = True
            await service.periodic_rehedge()
            
        # Start the task
        task = asyncio.create_task(run_one_iteration())
        
        # Let it run briefly
        await asyncio.sleep(0.1)
        
        # Stop it
        service.running = False
        
        # Clean up
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
        
        # Should have called rehedge
        service.rehedge_positions.assert_called()
    
    @pytest.mark.asyncio
    async def test_process_messages_funding(self, service, mock_producer):
        """Test processing funding messages."""
        service.producer = mock_producer
        service.running = True
        
        # Create mock message
        msg = MagicMock()
        msg.topic = 'funding_context'
        msg.value = {
            'funding_context': {
                'current_regime': 'MANIA',
                'current_rate': 150.0,
                'should_exit': False
            }
        }
        
        # Mock consumer to yield one message then stop
        async def mock_consumer_gen():
            yield msg
            service.running = False
            
        service.consumer = mock_consumer_gen()
        
        await service.process_messages()
        
        # Should update funding regime
        assert service.current_position.funding_regime == 'MANIA'
    
    @pytest.mark.asyncio
    async def test_process_messages_market_data(self, service):
        """Test processing market data messages."""
        service.running = True
        
        # Create mock message
        msg = MagicMock()
        msg.topic = 'market_data'
        msg.value = {'price': 125000}
        
        # Mock consumer
        async def mock_consumer_gen():
            yield msg
            service.running = False
            
        service.consumer = mock_consumer_gen()
        
        await service.process_messages()
        
        # Should update price
        assert service.current_position.btc_price == 125000
    
    @pytest.mark.asyncio
    async def test_process_messages_error_handling(self, service):
        """Test error handling in message processing."""
        service.running = True
        
        # Create message that will cause error
        msg = MagicMock()
        msg.topic = 'funding_context'
        msg.value = None  # Will cause error
        
        # Mock consumer
        async def mock_consumer_gen():
            yield msg
            service.running = False
            
        service.consumer = mock_consumer_gen()
        
        # Should not raise exception
        await service.process_messages()
    
    @pytest.mark.asyncio
    async def test_stop_service(self, service, mock_producer, mock_consumer):
        """Test stopping the service."""
        service.running = True
        service.consumer = mock_consumer
        service.producer = mock_producer
        
        await service.stop()
        
        assert service.running is False
        mock_consumer.stop.assert_called_once()
        mock_producer.stop.assert_called_once()
    
    def test_position_state_updates(self, service):
        """Test position state can be updated."""
        # Update positions
        service.current_position.long_perp = 0.3
        service.current_position.short_perp = 0.1
        service.current_position.btc_price = 125000
        
        # Calculate new delta
        new_delta = service.manager.calculate_delta(service.current_position)
        service.current_position.net_delta = new_delta
        
        assert service.current_position.long_perp == 0.3
        assert service.current_position.short_perp == 0.1
        assert service.current_position.net_delta == 0.27 + 0.3 - 0.1  # spot + long - short