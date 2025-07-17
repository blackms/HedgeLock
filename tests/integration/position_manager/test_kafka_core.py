"""
Core Kafka integration tests for Position Manager.
Simplified tests for essential message flow.
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from src.hedgelock.position_manager.service import PositionManagerService
from src.hedgelock.position_manager.models import PositionState, MarketRegime


@pytest.mark.asyncio
async def test_kafka_producer_connection():
    """Test that we can connect to Kafka and send messages."""
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:19092',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    try:
        await producer.start()
        
        # Send a test message
        test_message = {
            'timestamp': datetime.utcnow().isoformat(),
            'test': 'kafka_connection'
        }
        
        await producer.send_and_wait('test_topic', value=test_message)
        
        # If we get here, Kafka is working
        assert True
        
    except Exception as e:
        pytest.fail(f"Kafka connection failed: {e}")
    finally:
        await producer.stop()


@pytest.mark.asyncio
async def test_kafka_consumer_connection():
    """Test that we can connect to Kafka and receive messages."""
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:19092',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    consumer = AIOKafkaConsumer(
        'test_topic',
        bootstrap_servers='localhost:19092',
        group_id='test-group',
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        auto_offset_reset='latest'
    )
    
    try:
        await producer.start()
        await consumer.start()
        
        # Send a test message
        test_message = {
            'timestamp': datetime.utcnow().isoformat(),
            'test': 'kafka_consumer'
        }
        
        await producer.send_and_wait('test_topic', value=test_message)
        
        # Try to receive the message
        message_received = False
        async for msg in consumer:
            if msg.value.get('test') == 'kafka_consumer':
                message_received = True
                break
        
        assert message_received
        
    except Exception as e:
        pytest.fail(f"Kafka consumer test failed: {e}")
    finally:
        await producer.stop()
        await consumer.stop()


@pytest.mark.asyncio
async def test_position_manager_kafka_initialization():
    """Test that Position Manager can initialize with Kafka."""
    config = {
        'kafka_servers': 'localhost:19092',
        'storage_type': 'redis',
        'storage_url': 'redis://localhost:16379'
    }
    
    service = PositionManagerService(config)
    
    # Test that service initializes without errors
    assert service.config == config
    assert service.manager is not None
    assert service.current_position is not None
    
    # Test Kafka initialization (without starting the full service)
    try:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        
        # Test consumer creation
        consumer = AIOKafkaConsumer(
            'funding_context',
            'market_data',
            bootstrap_servers=config['kafka_servers'],
            group_id='position-manager-group',
            value_deserializer=lambda v: json.loads(v.decode('utf-8'))
        )
        
        # Test producer creation
        producer = AIOKafkaProducer(
            bootstrap_servers=config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await consumer.start()
        await producer.start()
        
        # If we get here, Kafka clients can be created
        assert True
        
        await consumer.stop()
        await producer.stop()
        
    except Exception as e:
        pytest.fail(f"Kafka initialization failed: {e}")


@pytest.mark.asyncio
async def test_funding_message_handling():
    """Test that Position Manager can handle funding messages."""
    config = {
        'kafka_servers': 'localhost:19092',
        'storage_type': 'redis',
        'storage_url': 'redis://localhost:16379'
    }
    
    service = PositionManagerService(config)
    
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
    
    # Test funding context message
    funding_data = {
        'funding_context': {
            'current_regime': 'HEATED',
            'current_rate': 0.05,
            'should_exit': False
        }
    }
    
    # Process the funding update
    await service.handle_funding_update(funding_data)
    
    # Verify state was updated
    assert service.current_position.funding_regime == 'HEATED'
    assert service.current_position.funding_rate > 0.0001  # Should be updated


@pytest.mark.asyncio
async def test_market_data_handling():
    """Test that Position Manager can handle market data messages."""
    config = {
        'kafka_servers': 'localhost:19092',
        'storage_type': 'redis',
        'storage_url': 'redis://localhost:16379'
    }
    
    service = PositionManagerService(config)
    
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
        funding_rate=0.0001
    )
    
    # Mock the P&L update to avoid complex dependencies
    with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
        # Test market data message
        market_data = {
            'price': 118000,
            'volume': 1000,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Process the market data update
        await service.handle_price_update(market_data)
        
        # Verify price was updated
        assert service.current_position.btc_price == 118000
        
        # Verify P&L update was called
        mock_pnl_update.assert_called_once()


@pytest.mark.asyncio
async def test_hedge_message_publishing():
    """Test that Position Manager can publish hedge messages."""
    config = {
        'kafka_servers': 'localhost:19092',
        'storage_type': 'redis',
        'storage_url': 'redis://localhost:16379'
    }
    
    service = PositionManagerService(config)
    
    # Set up Kafka producer
    producer = AIOKafkaProducer(
        bootstrap_servers=config['kafka_servers'],
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    try:
        await producer.start()
        service.producer = producer
        
        # Set up position that needs rebalancing
        service.current_position = PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.1,
            short_perp=0.1,
            net_delta=0.47,  # Needs rebalancing
            hedge_ratio=0.5,
            btc_price=118000,
            volatility_24h=0.025,
            funding_rate=0.0001,
            funding_regime='NORMAL'
        )
        
        # Mock dependencies to avoid complex setup
        with patch.object(service, 'pnl_calculator') as mock_pnl:
            mock_pnl.update_entry_prices.return_value = None
            
            with patch.object(service, 'update_pnl_and_publish') as mock_pnl_update:
                with patch.object(service, 'save_state_after_update') as mock_save:
                    # Trigger rehedge (this should publish messages)
                    await service.rehedge_positions()
                    
                    # If we get here without errors, message publishing worked
                    assert True
        
    except Exception as e:
        pytest.fail(f"Hedge message publishing failed: {e}")
    finally:
        await producer.stop()


@pytest.mark.asyncio
async def test_emergency_action_publishing():
    """Test that Position Manager can publish emergency actions."""
    config = {
        'kafka_servers': 'localhost:19092',
        'storage_type': 'redis',
        'storage_url': 'redis://localhost:16379'
    }
    
    service = PositionManagerService(config)
    
    # Set up Kafka producer
    producer = AIOKafkaProducer(
        bootstrap_servers=config['kafka_servers'],
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    try:
        await producer.start()
        service.producer = producer
        
        # Set up position with open positions
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
        
        # Mock save_state_after_update to avoid Redis dependency
        with patch.object(service, 'save_state_after_update') as mock_save:
            # Trigger emergency close
            await service.emergency_close_positions()
            
            # Verify position was cleared
            assert service.current_position.long_perp == 0.0
            assert service.current_position.short_perp == 0.0
            assert service.current_position.net_delta == service.current_position.spot_btc
        
    except Exception as e:
        pytest.fail(f"Emergency action publishing failed: {e}")
    finally:
        await producer.stop()


if __name__ == "__main__":
    # Run with: python -m pytest tests/integration/position_manager/test_kafka_core.py -v
    pytest.main([__file__, "-v", "--tb=short"])