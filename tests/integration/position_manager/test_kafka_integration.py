"""
Kafka integration tests for Position Manager.
Tests end-to-end message flow and service interactions.
"""

import asyncio
import json
import logging
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from src.hedgelock.position_manager.service import PositionManagerService
from src.hedgelock.position_manager.models import PositionState, MarketRegime
from src.hedgelock.position_manager.storage import RedisStorage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KafkaIntegrationTest:
    """Base class for Kafka integration tests."""
    
    def __init__(self, kafka_servers: str = "localhost:19092"):
        self.kafka_servers = kafka_servers
        self.producer = None
        self.consumers = {}
        self.messages_received = {}
        self.test_topics = [
            'funding_context',
            'market_data', 
            'position_states',
            'hedge_trades',
            'pnl_updates',
            'profit_taking',
            'emergency_actions'
        ]
    
    async def setup(self):
        """Set up Kafka connections."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await self.producer.start()
        
        # Create consumers for each topic
        for topic in self.test_topics:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.kafka_servers,
                group_id=f'test-{topic}-group',
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='latest'
            )
            await consumer.start()
            self.consumers[topic] = consumer
            self.messages_received[topic] = []
    
    async def teardown(self):
        """Clean up Kafka connections."""
        if self.producer:
            await self.producer.stop()
        
        for consumer in self.consumers.values():
            await consumer.stop()
    
    async def send_message(self, topic: str, message: Dict[str, Any]):
        """Send a message to Kafka."""
        await self.producer.send_and_wait(topic, value=message)
        logger.info(f"Sent message to {topic}: {message}")
    
    async def collect_messages(self, duration: int = 5):
        """Collect messages from all subscribed topics."""
        async def collect_from_topic(topic: str, consumer):
            try:
                async for msg in consumer:
                    self.messages_received[topic].append(msg.value)
                    logger.info(f"Received message from {topic}: {msg.value}")
            except Exception as e:
                logger.error(f"Error collecting from {topic}: {e}")
        
        # Start collection tasks
        tasks = []
        for topic, consumer in self.consumers.items():
            task = asyncio.create_task(collect_from_topic(topic, consumer))
            tasks.append(task)
        
        # Wait for specified duration
        await asyncio.sleep(duration)
        
        # Cancel collection tasks
        for task in tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.integration
class TestPositionManagerKafkaIntegration:
    """Test Position Manager Kafka integration."""
    
    @pytest.fixture
    async def kafka_test(self):
        """Create Kafka test instance."""
        test = KafkaIntegrationTest()
        await test.setup()
        yield test
        await test.teardown()
    
    @pytest.fixture
    def position_service_config(self):
        """Position Manager service configuration."""
        return {
            'kafka_servers': 'localhost:19092',
            'storage_type': 'redis',
            'storage_url': 'redis://localhost:16379'
        }
    
    async def test_funding_context_processing(self, kafka_test, position_service_config):
        """Test that Position Manager processes funding context updates."""
        # Create service instance
        service = PositionManagerService(position_service_config)
        
        # Mock the start method to avoid full startup
        with patch.object(service, 'start') as mock_start:
            # Set up initial state
            service.current_position = PositionState(
                timestamp=datetime.utcnow(),
                spot_btc=0.27,
                long_perp=0.213,
                short_perp=0.213,
                net_delta=0.27,
                hedge_ratio=1.0,
                btc_price=116000,
                volatility_24h=0.02,
                funding_rate=0.0001,
                funding_regime='NORMAL'
            )
            
            # Send funding context update
            funding_message = {
                'timestamp': datetime.utcnow().isoformat(),
                'funding_context': {
                    'current_regime': 'HEATED',
                    'current_rate': 0.05,  # 5% annual = 0.05/365/3 per 8h
                    'should_exit': False
                }
            }
            
            await kafka_test.send_message('funding_context', funding_message)
            
            # Process the message
            await service.handle_funding_update(funding_message)
            
            # Verify state updated
            assert service.current_position.funding_regime == 'HEATED'
            assert service.current_position.funding_rate == pytest.approx(0.05/365/3, rel=0.1)
    
    async def test_market_data_processing(self, kafka_test, position_service_config):
        """Test that Position Manager processes market data updates."""
        service = PositionManagerService(position_service_config)
        
        # Set up initial state
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001
        )
        
        # Mock P&L calculator to avoid complex setup
        with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
            # Send market data update
            market_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'price': 118000,
                'volume': 1000,
                'source': 'bybit'
            }
            
            await kafka_test.send_message('market_data', market_data)
            
            # Process the message
            await service.handle_price_update(market_data)
            
            # Verify price updated
            assert service.current_position.btc_price == 118000
            
            # Verify P&L update was called
            mock_pnl_update.assert_called_once()
    
    async def test_hedge_decision_publishing(self, kafka_test, position_service_config):
        """Test that Position Manager publishes hedge decisions."""
        service = PositionManagerService(position_service_config)
        
        # Set up Kafka producer
        service.producer = kafka_test.producer
        
        # Set up position state that needs rebalancing
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.1,  # Underhedged
            short_perp=0.1,
            net_delta=0.47,  # 0.2 BTC over target
            hedge_ratio=0.5,
            btc_price=118000,
            volatility_24h=0.025,
            funding_rate=0.0001,
            funding_regime='NORMAL'
        )
        
        # Mock P&L calculator
        with patch.object(service, 'pnl_calculator') as mock_pnl:
            mock_pnl.update_entry_prices.return_value = None
            
            # Mock update_pnl_and_publish to avoid complex setup
            with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
                # Mock save_state_after_update
                with patch.object(service, 'save_state_after_update') as mock_save:
                    # Trigger rehedge
                    await service.rehedge_positions()
                    
                    # Start message collection
                    await kafka_test.collect_messages(duration=2)
                    
                    # Verify hedge trade message was published
                    hedge_messages = kafka_test.messages_received['hedge_trades']
                    assert len(hedge_messages) > 0
                    
                    hedge_msg = hedge_messages[0]
                    assert hedge_msg['service'] == 'position-manager'
                    assert 'hedge_decision' in hedge_msg
                    assert 'order_request' in hedge_msg
                    
                    # Verify hedge decision structure
                    decision = hedge_msg['hedge_decision']
                    assert decision['target_delta'] == 0.0
                    assert decision['funding_regime'] == 'NORMAL'
                    assert decision['reason'] == 'Rebalance required'
                    
                    # Verify order request structure
                    order = hedge_msg['order_request']
                    assert order['symbol'] == 'BTCUSDT'
                    assert order['orderType'] == 'Market'
                    assert order['timeInForce'] == 'IOC'
    
    async def test_position_state_publishing(self, kafka_test, position_service_config):
        """Test that Position Manager publishes position state updates."""
        service = PositionManagerService(position_service_config)
        service.producer = kafka_test.producer
        
        # Set up position state
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=118000,
            volatility_24h=0.025,
            funding_rate=0.0001,
            funding_regime='NORMAL'
        )
        
        # Mock dependencies
        with patch.object(service, 'pnl_calculator') as mock_pnl:
            mock_pnl.update_entry_prices.return_value = None
            
            with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
                with patch.object(service, 'save_state_after_update') as mock_save:
                    # Trigger rehedge (which publishes position state)
                    await service.rehedge_positions()
                    
                    # Collect messages
                    await kafka_test.collect_messages(duration=2)
                    
                    # Verify position state was published
                    position_messages = kafka_test.messages_received['position_states']
                    assert len(position_messages) > 0
                    
                    pos_msg = position_messages[0]
                    assert 'position_state' in pos_msg
                    assert pos_msg['position_state']['spot_btc'] == 0.27
                    assert pos_msg['position_state']['btc_price'] == 118000
    
    async def test_emergency_close_publishing(self, kafka_test, position_service_config):
        """Test that Position Manager publishes emergency close actions."""
        service = PositionManagerService(position_service_config)
        service.producer = kafka_test.producer
        
        # Set up position state with open positions
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.5,
            short_perp=0.3,
            net_delta=0.47,
            hedge_ratio=0.8,
            btc_price=118000,
            volatility_24h=0.025,
            funding_rate=0.01,  # Extreme funding
            funding_regime='EXTREME'
        )
        
        # Mock save_state_after_update
        with patch.object(service, 'save_state_after_update') as mock_save:
            # Trigger emergency close
            await service.emergency_close_positions()
            
            # Collect messages
            await kafka_test.collect_messages(duration=2)
            
            # Verify emergency action was published
            emergency_messages = kafka_test.messages_received['emergency_actions']
            assert len(emergency_messages) > 0
            
            emergency_msg = emergency_messages[0]
            assert emergency_msg['action'] == 'CLOSE_ALL'
            assert emergency_msg['reason'] == 'Extreme funding rate'
            assert 'position_state' in emergency_msg
            
            # Verify hedge trade for emergency close
            hedge_messages = kafka_test.messages_received['hedge_trades']
            assert len(hedge_messages) > 0
            
            hedge_msg = hedge_messages[0]
            assert hedge_msg['hedge_decision']['risk_state'] == 'EMERGENCY'
            assert hedge_msg['hedge_decision']['urgency'] == 'CRITICAL'
    
    async def test_pnl_updates_publishing(self, kafka_test, position_service_config):
        """Test that Position Manager publishes P&L updates."""
        service = PositionManagerService(position_service_config)
        service.producer = kafka_test.producer
        
        # Set up position state
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=118000,
            volatility_24h=0.025,
            funding_rate=0.0001,
            unrealized_pnl=1500,
            realized_pnl=3000
        )
        
        # Mock P&L calculator
        from src.hedgelock.position_manager.pnl_calculator import PnLBreakdown
        mock_pnl_breakdown = PnLBreakdown(
            spot_pnl=540,
            long_perp_pnl=900,
            short_perp_pnl=-200,
            funding_pnl=-80,
            total_unrealized_pnl=1160,
            total_realized_pnl=3000,
            net_pnl=4160,
            timestamp=datetime.utcnow()
        )
        
        mock_pnl_metrics = {
            'spot_pnl': 540,
            'long_perp_pnl': 900,
            'short_perp_pnl': -200,
            'funding_pnl': -80,
            'unrealized_pnl': 1160,
            'realized_pnl': 3000,
            'net_pnl': 4160,
            'roi_percent': 6.8,
            'position_value': 61200
        }
        
        with patch.object(service.pnl_calculator, 'calculate_pnl', return_value=mock_pnl_breakdown):
            with patch.object(service.pnl_calculator, 'get_pnl_metrics', return_value=mock_pnl_metrics):
                # Trigger P&L update
                await service.update_pnl_and_publish()
                
                # Collect messages
                await kafka_test.collect_messages(duration=2)
                
                # Verify P&L update was published
                pnl_messages = kafka_test.messages_received['pnl_updates']
                assert len(pnl_messages) > 0
                
                pnl_msg = pnl_messages[0]
                assert 'pnl_breakdown' in pnl_msg
                assert 'metrics' in pnl_msg
                assert pnl_msg['pnl_breakdown']['net_pnl'] == 4160
                assert pnl_msg['metrics']['roi_percent'] == 6.8
    
    async def test_profit_taking_flow(self, kafka_test, position_service_config):
        """Test complete profit taking flow with message publishing."""
        service = PositionManagerService(position_service_config)
        service.producer = kafka_test.producer
        
        # Set up profitable position
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.5,
            short_perp=0.3,
            net_delta=0.47,
            hedge_ratio=0.8,
            btc_price=125000,
            volatility_24h=0.025,
            funding_rate=0.0001,
            unrealized_pnl=5000,
            realized_pnl=2000,
            peak_pnl=5000
        )
        
        # Mock P&L calculator
        with patch.object(service.pnl_calculator, 'realize_pnl', return_value=5000):
            with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
                with patch.object(service, 'save_state_after_update') as mock_save:
                    # Trigger profit taking
                    await service.take_profit()
                    
                    # Collect messages
                    await kafka_test.collect_messages(duration=2)
                    
                    # Verify profit taking message was published
                    profit_messages = kafka_test.messages_received['profit_taking']
                    assert len(profit_messages) > 0
                    
                    profit_msg = profit_messages[0]
                    assert profit_msg['action'] == 'TAKE_PROFIT'
                    assert profit_msg['pnl'] == 5000
                    
                    # Verify hedge trade for position close
                    hedge_messages = kafka_test.messages_received['hedge_trades']
                    assert len(hedge_messages) > 0
                    
                    hedge_msg = hedge_messages[0]
                    assert hedge_msg['hedge_decision']['risk_state'] == 'TAKING_PROFIT'
                    assert hedge_msg['hedge_decision']['urgency'] == 'HIGH'
    
    async def test_message_flow_sequence(self, kafka_test, position_service_config):
        """Test complete message flow sequence."""
        service = PositionManagerService(position_service_config)
        service.producer = kafka_test.producer
        
        # Set up initial position
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            funding_regime='NORMAL'
        )
        
        # Mock dependencies
        with patch.object(service, 'pnl_calculator') as mock_pnl:
            mock_pnl.update_entry_prices.return_value = None
            
            with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
                with patch.object(service, 'save_state_after_update') as mock_save:
                    # 1. Send funding context update
                    await kafka_test.send_message('funding_context', {
                        'timestamp': datetime.utcnow().isoformat(),
                        'funding_context': {
                            'current_regime': 'HEATED',
                            'current_rate': 0.02,
                            'should_exit': False
                        }
                    })
                    
                    # 2. Send market data update
                    await kafka_test.send_message('market_data', {
                        'timestamp': datetime.utcnow().isoformat(),
                        'price': 120000,
                        'volume': 1000
                    })
                    
                    # 3. Trigger rehedge
                    await service.rehedge_positions()
                    
                    # 4. Collect all messages
                    await kafka_test.collect_messages(duration=3)
                    
                    # Verify message sequence
                    assert len(kafka_test.messages_received['hedge_trades']) > 0
                    assert len(kafka_test.messages_received['position_states']) > 0
                    
                    # Verify no emergency actions (normal operation)
                    assert len(kafka_test.messages_received['emergency_actions']) == 0


# Test runner configuration
if __name__ == "__main__":
    # Run with: python -m pytest tests/integration/position_manager/test_kafka_integration.py -v
    pytest.main([__file__, "-v", "--tb=short"])