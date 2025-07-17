"""
Integration test for Position Manager to Trade Executor flow.
"""

import asyncio
import json
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import pytest


@pytest.mark.asyncio
async def test_position_to_trade_flow():
    """Test the flow from Position Manager decisions to Trade Executor."""
    
    # Setup Kafka
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:29092',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    consumer = AIOKafkaConsumer(
        'hedge_trades',
        bootstrap_servers='localhost:29092',
        group_id='test-position-trade',
        auto_offset_reset='latest',
        value_deserializer=lambda v: json.loads(v.decode('utf-8'))
    )
    
    await producer.start()
    await consumer.start()
    
    try:
        # Test 1: Send funding context update to trigger rehedge
        print("Test 1: Sending HEATED funding regime...")
        
        funding_msg = {
            "service": "test",
            "funding_context": {
                "symbol": "BTCUSDT",
                "current_rate": 75.0,  # 75% APR = HEATED
                "current_regime": "HEATED",
                "multiplier": 0.5,
                "should_exit": False
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await producer.send_and_wait('funding_context', value=funding_msg)
        
        # Wait for Position Manager to process and send hedge trade
        hedge_trade_received = False
        
        async def consume_hedge_trades():
            nonlocal hedge_trade_received
            async for msg in consumer:
                hedge_trade = msg.value
                print(f"\nReceived hedge trade:")
                print(f"  Service: {hedge_trade.get('service')}")
                print(f"  Decision: {hedge_trade['hedge_decision']['reason']}")
                print(f"  Side: {hedge_trade['order_request']['side']}")
                print(f"  Quantity: {hedge_trade['order_request']['qty']}")
                print(f"  Funding Regime: {hedge_trade['hedge_decision']['funding_regime']}")
                
                # Verify it's from Position Manager
                assert hedge_trade.get('service') == 'position-manager'
                assert 'hedge_decision' in hedge_trade
                assert 'order_request' in hedge_trade
                
                hedge_trade_received = True
                break
        
        # Consume with timeout
        try:
            await asyncio.wait_for(consume_hedge_trades(), timeout=10.0)
            assert hedge_trade_received, "No hedge trade received"
            print("✅ Hedge trade successfully sent to Trade Executor")
        except asyncio.TimeoutError:
            print("❌ Timeout waiting for hedge trade")
        
        # Test 2: Send extreme funding to trigger emergency exit
        print("\n\nTest 2: Sending EXTREME funding regime...")
        
        extreme_funding_msg = {
            "service": "test",
            "funding_context": {
                "symbol": "BTCUSDT",
                "current_rate": 400.0,  # 400% APR = EXTREME
                "current_regime": "EXTREME",
                "multiplier": 0.0,
                "should_exit": True
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await producer.send_and_wait('funding_context', value=extreme_funding_msg)
        
        # Wait for emergency close
        emergency_received = False
        
        async def consume_emergency():
            nonlocal emergency_received
            async for msg in consumer:
                hedge_trade = msg.value
                if hedge_trade['hedge_decision']['risk_state'] == 'EMERGENCY':
                    print(f"\nReceived EMERGENCY hedge trade:")
                    print(f"  Reason: {hedge_trade['hedge_decision']['reason']}")
                    print(f"  Urgency: {hedge_trade['hedge_decision']['urgency']}")
                    emergency_received = True
                    break
        
        try:
            await asyncio.wait_for(consume_emergency(), timeout=10.0)
            assert emergency_received, "No emergency trade received"
            print("✅ Emergency exit successfully triggered")
        except asyncio.TimeoutError:
            print("❌ Timeout waiting for emergency trade")
            
    finally:
        await producer.stop()
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(test_position_to_trade_flow())