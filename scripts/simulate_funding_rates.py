#!/usr/bin/env python3
"""
Simulate various funding rate scenarios for monitoring.
"""

import asyncio
import json
import random
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer


async def send_funding_rates():
    """Send simulated funding rates."""
    producer = AIOKafkaProducer(
        bootstrap_servers='kafka:29092',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    await producer.start()
    
    try:
        # Simulate different scenarios
        scenarios = [
            ("BTCUSDT", 15.0, "Low funding - Normal"),
            ("ETHUSDT", 45.0, "Medium funding - Normal"),
            ("SOLUSDT", 85.0, "High funding - Heated"),
            ("AVAXUSDT", 125.0, "Very high - Mania"),
            ("DOTUSDT", 25.0, "Low funding - Normal"),
        ]
        
        for symbol, base_rate, description in scenarios:
            # Add some randomness
            rate = base_rate + random.uniform(-5, 5)
            
            funding_msg = {
                "service": "simulator",
                "funding_rate": {
                    "symbol": symbol,
                    "funding_rate": rate / 100 / 365 / 3,  # Convert to 8h rate
                    "funding_time": datetime.now(timezone.utc).isoformat(),
                    "mark_price": random.uniform(40000, 60000) if symbol == "BTCUSDT" else random.uniform(100, 5000),
                    "index_price": random.uniform(40000, 60000) if symbol == "BTCUSDT" else random.uniform(100, 5000)
                },
                "trace_id": f"sim-{symbol}-{int(datetime.now().timestamp())}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await producer.send_and_wait('funding_rates', value=funding_msg)
            print(f"✅ Sent {symbol} @ {rate:.1f}% APR - {description}")
            await asyncio.sleep(0.5)
        
        print("\n📊 All funding rates sent!")
        
    finally:
        await producer.stop()


if __name__ == "__main__":
    print("🚀 Sending simulated funding rates...\n")
    asyncio.run(send_funding_rates())