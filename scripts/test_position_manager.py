#!/usr/bin/env python3
"""
Test script for Position Manager functionality.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
import sys


async def test_position_manager():
    """Test position manager API and functionality."""
    print("🧪 Testing Position Manager Service\n")
    
    # Test 1: Health check
    print("1. Testing health endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8009/health') as resp:
                if resp.status == 200:
                    print("✅ Health check passed")
                else:
                    print(f"❌ Health check failed: {resp.status}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return
    
    # Test 2: Get position status
    print("\n2. Getting current position...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8009/position') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Position retrieved:")
                    print(f"   - Delta: {data['metrics']['net_delta']}")
                    print(f"   - Delta Neutral: {data['metrics']['delta_neutral']}")
                    print(f"   - Hedge Ratio: {data['metrics']['hedge_ratio']}")
                    print(f"   - Volatility: {data['metrics']['volatility_24h']}")
                    print(f"   - Funding Regime: {data['metrics']['funding_regime']}")
                else:
                    print(f"❌ Position fetch failed: {resp.status}")
    except Exception as e:
        print(f"❌ Position fetch error: {e}")
    
    # Test 3: Get hedge parameters
    print("\n3. Getting hedge parameters...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8009/hedge-params') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Hedge parameters:")
                    print(f"   - Base Hedge Ratio: {data['base_hedge_ratio']}")
                    print(f"   - Funding Multiplier: {data['funding_multiplier']}")
                    print(f"   - Final Hedge Ratio: {data['final_hedge_ratio']}")
                else:
                    print(f"❌ Hedge params failed: {resp.status}")
    except Exception as e:
        print(f"❌ Hedge params error: {e}")
    
    # Test 4: Send funding update via Kafka
    print("\n4. Sending funding context update...")
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers='localhost:29092',
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await producer.start()
        
        # Send HEATED funding regime
        funding_msg = {
            "service": "test-script",
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
        print("✅ Sent HEATED funding regime update")
        
        await producer.stop()
    except Exception as e:
        print(f"❌ Kafka send error: {e}")
    
    # Test 5: Trigger manual rehedge
    print("\n5. Triggering manual rehedge...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post('http://localhost:8009/rehedge') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Rehedge triggered: {data['message']}")
                else:
                    print(f"❌ Rehedge failed: {resp.status}")
    except Exception as e:
        print(f"❌ Rehedge error: {e}")
    
    print("\n✨ Position Manager tests completed!")


if __name__ == "__main__":
    asyncio.run(test_position_manager())