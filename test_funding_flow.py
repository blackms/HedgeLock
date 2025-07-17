#!/usr/bin/env python3
"""
Quick test to verify funding awareness flow is working.
"""
import asyncio
import json
from datetime import datetime
from aiokafka import AIOKafkaProducer


async def send_test_funding_rate():
    """Send a test funding rate to Kafka."""
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    await producer.start()
    
    try:
        # Create a test funding rate message
        funding_msg = {
            "service": "test-collector",
            "funding_rate": {
                "symbol": "BTCUSDT",
                "funding_rate": 0.0025,  # 0.25% per 8h = 273.75% APR (HEATED)
                "funding_time": datetime.utcnow().isoformat(),
                "mark_price": 50000.0,
                "index_price": 49900.0,
                "daily_rate": 0.0075,  # 0.75% daily
                "annualized_rate": 273.75  # 273.75% APR
            },
            "trace_id": "test-001",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to funding_rates topic
        await producer.send_and_wait('funding_rates', value=funding_msg)
        print(f"✅ Sent funding rate: {funding_msg['funding_rate']['symbol']} @ {funding_msg['funding_rate']['annualized_rate']}% APR")
        
        # Wait a bit for processing
        await asyncio.sleep(2)
        
        # Check funding engine status
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8005/status') as resp:
                if resp.status == 200:
                    status = await resp.json()
                    print(f"\n📊 Funding Engine Status:")
                    print(f"   - Service: {status['service']}")
                    print(f"   - Running: {status['running']}")
                    print(f"   - Symbols tracked: {status['symbols_tracked']}")
                    if status['symbols_tracked'] > 0:
                        print(f"   - Contexts: {json.dumps(status['contexts'], indent=4)}")
                        
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(send_test_funding_rate())