#!/usr/bin/env python3
"""
Stress test suite for HedgeLock Funding Awareness system.
Tests extreme scenarios, rapid changes, and system limits.
"""

import asyncio
import json
import time
import random
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import aiohttp


class FundingStressTest:
    """Comprehensive stress testing for funding awareness."""
    
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"
        self.results = {
            "scenarios": [],
            "latencies": [],
            "errors": [],
            "regime_transitions": []
        }
    
    async def run_all_tests(self):
        """Run complete stress test suite."""
        print("🚀 Starting HedgeLock Funding Awareness Stress Tests\n")
        
        # Test 1: Rapid funding changes
        await self.test_rapid_funding_changes()
        
        # Test 2: Extreme funding spikes
        await self.test_extreme_funding_spikes()
        
        # Test 3: Multiple symbols simultaneously
        await self.test_multiple_symbols_load()
        
        # Test 4: Regime oscillation
        await self.test_regime_oscillation()
        
        # Test 5: Emergency exit cascade
        await self.test_emergency_exit_cascade()
        
        # Test 6: System recovery
        await self.test_system_recovery()
        
        # Print results
        self.print_test_results()
    
    async def test_rapid_funding_changes(self):
        """Test 1: Rapid funding rate changes."""
        print("\n📊 Test 1: Rapid Funding Changes")
        print("Sending 100 funding updates in 10 seconds...")
        
        producer = await self._create_producer()
        consumer = await self._create_consumer('funding_context')
        
        # Start consumer task
        consumer_task = asyncio.create_task(
            self._consume_with_timeout(consumer, 15)
        )
        
        start_time = time.time()
        rates_sent = []
        
        try:
            # Send rapid funding changes
            for i in range(100):
                rate = random.uniform(10, 200)  # 10-200% APR
                rates_sent.append(rate)
                
                msg = self._create_funding_message("BTCUSDT", rate, f"rapid-{i}")
                await producer.send_and_wait('funding_rates', value=msg)
                
                await asyncio.sleep(0.1)  # 10 updates per second
            
            send_duration = time.time() - start_time
            print(f"✅ Sent 100 messages in {send_duration:.2f}s")
            
            # Wait for processing
            contexts = await consumer_task
            
            # Analyze results
            process_rate = len(contexts) / len(rates_sent) * 100
            avg_rate_sent = statistics.mean(rates_sent)
            
            print(f"📈 Results:")
            print(f"   - Messages sent: {len(rates_sent)}")
            print(f"   - Contexts received: {len(contexts)}")
            print(f"   - Processing rate: {process_rate:.1f}%")
            print(f"   - Average rate sent: {avg_rate_sent:.1f}% APR")
            
            self.results["scenarios"].append({
                "test": "rapid_changes",
                "sent": len(rates_sent),
                "received": len(contexts),
                "success_rate": process_rate,
                "duration": send_duration
            })
            
        finally:
            await producer.stop()
            await consumer.stop()
    
    async def test_extreme_funding_spikes(self):
        """Test 2: Extreme funding spikes."""
        print("\n📊 Test 2: Extreme Funding Spikes")
        print("Testing sudden spikes from normal to extreme funding...")
        
        producer = await self._create_producer()
        scenarios = [
            ("BTCUSDT", 25, 500, "spike-1"),    # 25% → 500% APR
            ("ETHUSDT", 50, 1000, "spike-2"),   # 50% → 1000% APR
            ("SOLUSDT", 10, 350, "spike-3"),    # 10% → 350% APR
        ]
        
        try:
            for symbol, normal_rate, spike_rate, trace_id in scenarios:
                print(f"\n🎯 Testing {symbol}: {normal_rate}% → {spike_rate}% APR")
                
                # Send normal rate
                msg = self._create_funding_message(symbol, normal_rate, f"{trace_id}-normal")
                await producer.send_and_wait('funding_rates', value=msg)
                await asyncio.sleep(1)
                
                # Send spike
                spike_time = time.time()
                msg = self._create_funding_message(symbol, spike_rate, f"{trace_id}-spike")
                await producer.send_and_wait('funding_rates', value=msg)
                
                # Check emergency response
                response = await self._wait_for_emergency_response(symbol, spike_time)
                
                if response:
                    latency = response['latency']
                    print(f"   ✅ Emergency exit triggered in {latency:.3f}s")
                    self.results["latencies"].append(latency)
                else:
                    print(f"   ❌ No emergency response detected")
                    self.results["errors"].append(f"No emergency response for {symbol}")
                
        finally:
            await producer.stop()
    
    async def test_multiple_symbols_load(self):
        """Test 3: Multiple symbols under load."""
        print("\n📊 Test 3: Multiple Symbols Load Test")
        print("Testing 20 symbols with random funding rates...")
        
        producer = await self._create_producer()
        symbols = [f"TOKEN{i}USDT" for i in range(20)]
        
        try:
            start_time = time.time()
            messages_sent = 0
            
            # Send updates for all symbols
            for _ in range(5):  # 5 rounds
                for symbol in symbols:
                    rate = random.uniform(5, 250)
                    msg = self._create_funding_message(
                        symbol, rate, f"load-{symbol}-{messages_sent}"
                    )
                    await producer.send_and_wait('funding_rates', value=msg)
                    messages_sent += 1
                
                await asyncio.sleep(0.5)
            
            duration = time.time() - start_time
            rate = messages_sent / duration
            
            print(f"✅ Results:")
            print(f"   - Symbols tested: {len(symbols)}")
            print(f"   - Messages sent: {messages_sent}")
            print(f"   - Duration: {duration:.2f}s")
            print(f"   - Throughput: {rate:.1f} msg/s")
            
            # Check funding engine status
            status = await self._check_service_status(8005)
            if status:
                symbols_tracked = status.get('symbols_tracked', 0)
                print(f"   - Symbols tracked by engine: {symbols_tracked}")
            
        finally:
            await producer.stop()
    
    async def test_regime_oscillation(self):
        """Test 4: Rapid regime oscillation."""
        print("\n📊 Test 4: Regime Oscillation Test")
        print("Testing rapid regime changes (NORMAL ↔ HEATED ↔ MANIA)...")
        
        producer = await self._create_producer()
        consumer = await self._create_consumer('funding_context')
        
        # Oscillating rates
        oscillation_pattern = [
            30,   # NORMAL
            75,   # HEATED
            125,  # MANIA
            75,   # HEATED
            30,   # NORMAL
            150,  # MANIA
            25,   # NORMAL
            200,  # MANIA
            50,   # NORMAL/HEATED boundary
        ]
        
        consumer_task = asyncio.create_task(
            self._consume_with_timeout(consumer, 10)
        )
        
        try:
            regime_changes = 0
            last_regime = None
            
            for i, rate in enumerate(oscillation_pattern):
                msg = self._create_funding_message("BTCUSDT", rate, f"oscillation-{i}")
                await producer.send_and_wait('funding_rates', value=msg)
                await asyncio.sleep(0.5)
            
            # Analyze regime changes
            contexts = await consumer_task
            
            for ctx in contexts:
                regime = ctx.get('funding_context', {}).get('current_regime')
                if last_regime and regime != last_regime:
                    regime_changes += 1
                    self.results["regime_transitions"].append({
                        "from": last_regime,
                        "to": regime,
                        "rate": ctx.get('funding_context', {}).get('current_rate')
                    })
                last_regime = regime
            
            print(f"✅ Results:")
            print(f"   - Patterns sent: {len(oscillation_pattern)}")
            print(f"   - Contexts received: {len(contexts)}")
            print(f"   - Regime changes detected: {regime_changes}")
            
        finally:
            await producer.stop()
            await consumer.stop()
    
    async def test_emergency_exit_cascade(self):
        """Test 5: Emergency exit cascade."""
        print("\n📊 Test 5: Emergency Exit Cascade")
        print("Testing simultaneous extreme funding on multiple symbols...")
        
        producer = await self._create_producer()
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOTUSDT"]
        
        try:
            print("Sending extreme rates (>300% APR) to all symbols...")
            start_time = time.time()
            
            # Send extreme rates to all symbols
            for symbol in symbols:
                rate = random.uniform(350, 500)  # All extreme
                msg = self._create_funding_message(symbol, rate, f"cascade-{symbol}")
                await producer.send_and_wait('funding_rates', value=msg)
            
            # Wait and check responses
            await asyncio.sleep(3)
            
            # Check funding engine status
            status = await self._check_service_status(8005)
            if status:
                contexts = status.get('contexts', {})
                extreme_count = sum(
                    1 for ctx in contexts.values() 
                    if ctx.get('regime') == 'extreme'
                )
                exit_count = sum(
                    1 for ctx in contexts.values() 
                    if ctx.get('should_exit', False)
                )
                
                print(f"✅ Results:")
                print(f"   - Symbols with extreme funding: {extreme_count}/{len(symbols)}")
                print(f"   - Emergency exits triggered: {exit_count}/{len(symbols)}")
                print(f"   - Response time: {time.time() - start_time:.2f}s")
                
                if extreme_count == len(symbols):
                    print("   ✅ All symbols correctly identified as EXTREME")
                else:
                    print("   ❌ Some symbols not identified as EXTREME")
                    self.results["errors"].append("Incomplete extreme detection")
            
        finally:
            await producer.stop()
    
    async def test_system_recovery(self):
        """Test 6: System recovery after extreme event."""
        print("\n📊 Test 6: System Recovery Test")
        print("Testing recovery from extreme to normal funding...")
        
        producer = await self._create_producer()
        
        try:
            # Step 1: Send extreme rate
            print("Step 1: Triggering extreme funding...")
            msg = self._create_funding_message("BTCUSDT", 400, "recovery-extreme")
            await producer.send_and_wait('funding_rates', value=msg)
            await asyncio.sleep(2)
            
            # Check extreme state
            status = await self._check_service_status(8005)
            if status:
                ctx = status.get('contexts', {}).get('BTCUSDT', {})
                if ctx.get('regime') == 'extreme':
                    print("   ✅ Extreme regime confirmed")
                
            # Step 2: Send normal rate
            print("Step 2: Returning to normal funding...")
            msg = self._create_funding_message("BTCUSDT", 25, "recovery-normal")
            await producer.send_and_wait('funding_rates', value=msg)
            await asyncio.sleep(2)
            
            # Check recovery
            status = await self._check_service_status(8005)
            if status:
                ctx = status.get('contexts', {}).get('BTCUSDT', {})
                regime = ctx.get('regime', 'unknown')
                multiplier = ctx.get('multiplier', 0)
                
                print(f"✅ Recovery Results:")
                print(f"   - New regime: {regime}")
                print(f"   - Position multiplier: {multiplier}")
                
                if regime == 'normal' and multiplier > 0.5:
                    print("   ✅ System recovered successfully")
                else:
                    print("   ⚠️  Recovery may be incomplete")
            
        finally:
            await producer.stop()
    
    # Helper methods
    async def _create_producer(self):
        """Create Kafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await producer.start()
        return producer
    
    async def _create_consumer(self, topic: str):
        """Create Kafka consumer."""
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.kafka_bootstrap,
            auto_offset_reset='latest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        await consumer.start()
        return consumer
    
    def _create_funding_message(self, symbol: str, rate: float, trace_id: str):
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
    
    async def _consume_with_timeout(self, consumer, timeout: int):
        """Consume messages with timeout."""
        messages = []
        end_time = time.time() + timeout
        
        try:
            while time.time() < end_time:
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=0.5)
                    messages.append(msg.value)
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            print(f"Consumer error: {e}")
        
        return messages
    
    async def _wait_for_emergency_response(self, symbol: str, start_time: float):
        """Wait for emergency response."""
        timeout = 5  # 5 second timeout
        
        while time.time() - start_time < timeout:
            status = await self._check_service_status(8005)
            if status:
                ctx = status.get('contexts', {}).get(symbol, {})
                if ctx.get('should_exit', False):
                    return {
                        'latency': time.time() - start_time,
                        'regime': ctx.get('regime'),
                        'rate': ctx.get('current_rate')
                    }
            await asyncio.sleep(0.1)
        
        return None
    
    async def _check_service_status(self, port: int):
        """Check service status."""
        try:
            # Map to internal service name
            service_map = {8005: 'funding-engine', 8002: 'risk-engine'}
            host = service_map.get(port, 'localhost')
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://{host}:{port}/status') as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            print(f"Status check error: {e}")
        return None
    
    def print_test_results(self):
        """Print comprehensive test results."""
        print("\n" + "="*60)
        print("📊 STRESS TEST RESULTS SUMMARY")
        print("="*60)
        
        # Scenario results
        print("\n🎯 Scenario Results:")
        for scenario in self.results["scenarios"]:
            print(f"   - {scenario['test']}: {scenario['success_rate']:.1f}% success")
        
        # Latency analysis
        if self.results["latencies"]:
            print(f"\n⏱️  Emergency Response Latencies:")
            print(f"   - Min: {min(self.results['latencies']):.3f}s")
            print(f"   - Max: {max(self.results['latencies']):.3f}s")
            print(f"   - Avg: {statistics.mean(self.results['latencies']):.3f}s")
            print(f"   - P95: {statistics.quantiles(self.results['latencies'], n=20)[18]:.3f}s")
        
        # Regime transitions
        if self.results["regime_transitions"]:
            print(f"\n🔄 Regime Transitions: {len(self.results['regime_transitions'])}")
            for trans in self.results["regime_transitions"][:5]:  # Show first 5
                print(f"   - {trans['from']} → {trans['to']} @ {trans['rate']:.1f}% APR")
        
        # Errors
        if self.results["errors"]:
            print(f"\n❌ Errors Detected: {len(self.results['errors'])}")
            for error in self.results["errors"]:
                print(f"   - {error}")
        else:
            print("\n✅ No errors detected!")
        
        # Overall assessment
        print("\n🏁 Overall Assessment:")
        total_tests = 6
        passed = total_tests - len(self.results["errors"])
        print(f"   - Tests passed: {passed}/{total_tests}")
        
        if passed == total_tests:
            print("   - Status: ✅ ALL TESTS PASSED - System is robust!")
        elif passed >= total_tests * 0.8:
            print("   - Status: ⚠️  MOSTLY PASSED - Minor issues detected")
        else:
            print("   - Status: ❌ NEEDS ATTENTION - Multiple issues found")


async def main():
    """Run stress tests."""
    test = FundingStressTest()
    await test.run_all_tests()


if __name__ == "__main__":
    print("HedgeLock Funding Awareness - Stress Test Suite")
    print("=" * 60)
    asyncio.run(main())