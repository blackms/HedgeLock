"""
Integration test for complete data pipeline.
Tests data flow from collector → risk engine → hedger.
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import respx
import httpx

from src.hedgelock.config import settings
from src.hedgelock.risk_engine.models import AccountData, RiskState
from src.hedgelock.collector.models import AccountRawMessage


@pytest.fixture
async def kafka_producer():
    """Create test Kafka producer."""
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka.bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    await producer.start()
    yield producer
    await producer.stop()


@pytest.fixture
async def kafka_consumer():
    """Create test Kafka consumer."""
    consumer = AIOKafkaConsumer(
        settings.kafka.topic_hedge_trades,
        bootstrap_servers=settings.kafka.bootstrap_servers,
        group_id="test_integration_consumer",
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest'
    )
    await consumer.start()
    yield consumer
    await consumer.stop()


def create_test_account_data(ltv: float = 0.7, net_delta: float = 0.5):
    """Create test account data with specified LTV and delta."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "test",
        "total_collateral_value": 100000.0,
        "available_collateral": 30000.0,
        "used_collateral": 70000.0,
        "total_loan_value": ltv * 100000.0,  # Set loan to achieve desired LTV
        "total_interest": 0.0,
        "positions": {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": net_delta,
                "value": net_delta * 45000,
                "avgPrice": 45000.0
            }
        }
    }


@pytest.mark.asyncio
async def test_full_pipeline_caution_state(kafka_producer, kafka_consumer):
    """Test full pipeline when risk engine detects CAUTION state."""
    # Create account data that will trigger CAUTION state (LTV = 0.7)
    test_data = create_test_account_data(ltv=0.7, net_delta=0.5)
    
    # Send test message to account_raw topic
    await kafka_producer.send(
        settings.kafka.topic_account_raw,
        value=test_data,
        headers=[('trace_id', b'test-trace-123')]
    )
    await kafka_producer.flush()
    
    # Wait for message to propagate through pipeline
    await asyncio.sleep(5)
    
    # Check if hedge trade was produced
    messages = []
    try:
        async for msg in kafka_consumer:
            messages.append(msg.value)
            break  # Get first message
    except asyncio.TimeoutError:
        pass
    
    assert len(messages) > 0, "No hedge trade message received"
    
    hedge_trade = messages[0]
    assert hedge_trade["risk_state"] == "CAUTION"
    assert hedge_trade["hedge_decision"]["side"] == "Sell"  # Should sell to reduce delta
    assert abs(hedge_trade["hedge_decision"]["hedge_size"] - 0.48) < 0.01  # Target delta 0.02


@pytest.mark.asyncio
async def test_full_pipeline_critical_state(kafka_producer, kafka_consumer):
    """Test full pipeline when risk engine detects CRITICAL state."""
    # Create account data that will trigger CRITICAL state (LTV = 0.95)
    test_data = create_test_account_data(ltv=0.95, net_delta=0.5)
    
    # Send test message to account_raw topic
    await kafka_producer.send(
        settings.kafka.topic_account_raw,
        value=test_data,
        headers=[('trace_id', b'test-trace-456')]
    )
    await kafka_producer.flush()
    
    # Wait for message to propagate through pipeline
    await asyncio.sleep(5)
    
    # Check if hedge trade was produced
    messages = []
    try:
        async for msg in kafka_consumer:
            messages.append(msg.value)
            break  # Get first message
    except asyncio.TimeoutError:
        pass
    
    assert len(messages) > 0, "No hedge trade message received"
    
    hedge_trade = messages[0]
    assert hedge_trade["risk_state"] == "CRITICAL"
    assert hedge_trade["hedge_decision"]["urgency"] == "IMMEDIATE"
    assert hedge_trade["hedge_decision"]["side"] == "Sell"  # Should sell to reduce exposure


@pytest.mark.asyncio
async def test_pipeline_with_bybit_mock():
    """Test pipeline with mocked Bybit API response."""
    with respx.mock:
        # Mock Bybit order creation endpoint
        order_route = respx.post(f"{settings.bybit.rest_url}/v5/order/create").mock(
            return_value=httpx.Response(200, json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "orderId": "test-order-123",
                    "orderLinkId": "HL-test123",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "orderType": "Market",
                    "qty": "0.48",
                    "orderStatus": "Filled",
                    "timeInForce": "IOC",
                    "createdTime": "1234567890000",
                    "updatedTime": "1234567891000",
                    "avgPrice": 45000.0,
                    "cumExecQty": 0.48,
                    "cumExecValue": 21600.0,
                    "cumExecFee": 10.8
                }
            })
        )
        
        # Create test account data
        test_data = create_test_account_data(ltv=0.7, net_delta=0.5)
        
        # Inject into pipeline
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await producer.start()
        
        await producer.send(
            settings.kafka.topic_account_raw,
            value=test_data,
            headers=[('trace_id', b'test-trace-789')]
        )
        await producer.flush()
        await producer.stop()
        
        # Wait for processing
        await asyncio.sleep(5)
        
        # Verify Bybit API was called
        assert order_route.called
        call = order_route.calls.last
        request_data = json.loads(call.request.content)
        assert request_data["symbol"] == "BTCUSDT"
        assert request_data["side"] == "Sell"
        assert float(request_data["qty"]) == pytest.approx(0.48, rel=0.01)


@pytest.mark.asyncio
async def test_pipeline_error_handling():
    """Test pipeline handles errors gracefully."""
    # Send malformed data
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka.bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    await producer.start()
    
    malformed_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "test",
        # Missing required fields
    }
    
    await producer.send(
        settings.kafka.topic_account_raw,
        value=malformed_data
    )
    await producer.flush()
    await producer.stop()
    
    # Pipeline should handle error without crashing
    await asyncio.sleep(3)
    
    # Services should still be healthy
    # This would be verified by checking health endpoints in real test


@pytest.mark.asyncio
async def test_message_replay():
    """Test replaying canned messages through pipeline."""
    # Load canned messages
    canned_messages = [
        create_test_account_data(ltv=0.5, net_delta=0.1),  # NORMAL
        create_test_account_data(ltv=0.68, net_delta=0.3),  # CAUTION
        create_test_account_data(ltv=0.82, net_delta=0.5),  # DANGER
        create_test_account_data(ltv=0.92, net_delta=0.8),  # CRITICAL
    ]
    
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka.bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    await producer.start()
    
    # Send all messages
    for i, msg in enumerate(canned_messages):
        await producer.send(
            settings.kafka.topic_account_raw,
            value=msg,
            headers=[('trace_id', f'replay-{i}'.encode())]
        )
    
    await producer.flush()
    await producer.stop()
    
    # Wait for processing
    await asyncio.sleep(10)
    
    # Verify all messages were processed
    # In real test, would check metrics or consume from hedge_trades topic