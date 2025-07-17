#!/usr/bin/env python3
"""
Simplified stress test for HedgeLock Funding Awareness.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
import aiohttp


class SimpleStressTest:
    """Simplified stress test focusing on key scenarios."""
    
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"
        self.results = {}
    
    async def run_tests(self):
        """Run simplified stress tests."""
        print("🚀 HedgeLock Funding Awareness - Simple Stress Test\n")
        
        # Test 1: Normal operation
        print("Test 1: Normal Funding Rates (10-50% APR)")
        await self.test_normal_rates()
        
        # Test 2: Extreme rates
        print("\nTest 2: Extreme Funding Rates (>300% APR)")
        await self.test_extreme_rates()
        
        # Test 3: Rapid changes
        print("\nTest 3: Rapid Rate Changes")
        await self.test_rapid_changes()
        
        print("\n✅ Stress tests completed!")
    
    async def test_normal_rates(self):
        """Test normal funding rates."""
        producer = await self._create_producer()
        
        try:
            rates = [15, 25, 35, 45]  # Normal range
            for rate in rates:
                msg = self._create_message("BTCUSDT", rate, f"normal-{rate}")
                await producer.send_and_wait('funding_rates', value=msg)
                print(f"  Sent: {rate}% APR")
                await asyncio.sleep(0.5)
            
            # Check results
            await asyncio.sleep(2)
            status = await self._check_status()
            if status:
                ctx = status.get('contexts', {}).get('BTCUSDT', {})
                print(f"  Result: {ctx.get('regime', 'unknown')} regime, multiplier: {ctx.get('multiplier', 0)}")
        
        finally:
            await producer.stop()
    
    async def test_extreme_rates(self):
        """Test extreme funding rates."""
        producer = await self._create_producer()
        
        try:
            # Send extreme rate
            rate = 400  # 400% APR
            msg = self._create_message("BTCUSDT", rate, "extreme-test")
            await producer.send_and_wait('funding_rates', value=msg)
            print(f"  Sent: {rate}% APR")
            
            # Check for emergency exit
            await asyncio.sleep(2)
            status = await self._check_status()
            if status:
                ctx = status.get('contexts', {}).get('BTCUSDT', {})
                if ctx.get('should_exit'):
                    print(f"  ✅ Emergency exit triggered! Regime: {ctx.get('regime', 'unknown')}")
                else:
                    print(f"  ❌ No emergency exit. Regime: {ctx.get('regime', 'unknown')}")
        
        finally:
            await producer.stop()
    
    async def test_rapid_changes(self):
        """Test rapid funding rate changes."""
        producer = await self._create_producer()
        
        try:
            print("  Sending 20 updates in 2 seconds...")
            start = time.time()
            
            for i in range(20):
                rate = 50 + (i * 10) % 100  # Oscillate between 50-140%
                msg = self._create_message("BTCUSDT", rate, f"rapid-{i}")
                await producer.send_and_wait('funding_rates', value=msg)
                await asyncio.sleep(0.1)
            
            duration = time.time() - start
            print(f"  Completed in {duration:.1f}s ({20/duration:.1f} msg/s)")
            
            # Check final state
            await asyncio.sleep(2)
            status = await self._check_status()
            if status:
                tracked = status.get('symbols_tracked', 0)
                print(f"  Funding engine tracking: {tracked} symbols")
        
        finally:
            await producer.stop()
    
    async def _create_producer(self):
        """Create Kafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await producer.start()
        return producer
    
    def _create_message(self, symbol: str, rate: float, trace_id: str):
        """Create funding rate message."""
        return {
            "service": "stress-test",
            "funding_rate": {
                "symbol": symbol,
                "funding_rate": rate / 100 / 365 / 3,
                "funding_time": datetime.now(timezone.utc).isoformat(),
                "mark_price": 50000.0,
                "index_price": 49950.0
            },
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def _check_status(self):
        """Check funding engine status."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://funding-engine:8005/status') as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            print(f"  Status check error: {e}")
        return None


async def main():
    """Run simple stress tests."""
    test = SimpleStressTest()
    await test.run_tests()


if __name__ == "__main__":
    asyncio.run(main())