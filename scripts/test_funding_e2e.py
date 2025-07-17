#!/usr/bin/env python3
"""
End-to-end test for funding awareness system.
Tests the complete flow from funding rate ingestion to hedge decisions.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, List
import aiohttp
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer


class FundingE2ETest:
    """End-to-end test for funding awareness."""
    
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"  # Use internal Kafka port
        self.test_results = {}
        
    async def send_funding_rate(self, symbol: str, rate: float, trace_id: str):
        """Send a funding rate message to Kafka."""
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await producer.start()
        
        try:
            # Create funding rate message
            # Note: Only send the 8h funding_rate, let the model calculate annualized_rate
            funding_msg = {
                "service": "e2e-test-collector",
                "funding_rate": {
                    "symbol": symbol,
                    "funding_rate": rate / 100 / 365 / 3,  # Convert from APR to 8h rate
                    "funding_time": datetime.now(timezone.utc).isoformat(),
                    "mark_price": 50000.0,
                    "index_price": 49950.0
                },
                "trace_id": trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Send to funding_rates topic
            await producer.send_and_wait('funding_rates', value=funding_msg)
            print(f"✅ Sent funding rate: {symbol} @ {rate}% APR (trace_id: {trace_id})")
            
        finally:
            await producer.stop()
    
    async def consume_funding_context(self, timeout: int = 10) -> List[Dict]:
        """Consume funding context messages."""
        consumer = AIOKafkaConsumer(
            'funding_context',
            bootstrap_servers=self.kafka_bootstrap,
            auto_offset_reset='latest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        await consumer.start()
        contexts = []
        
        try:
            end_time = time.time() + timeout
            while time.time() < end_time:
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=1.0)
                    contexts.append(msg.value)
                    print(f"📨 Received funding context: {msg.value['funding_context']['symbol']} - {msg.value['funding_context']['current_regime']}")
                except asyncio.TimeoutError:
                    continue
                    
        finally:
            await consumer.stop()
            
        return contexts
    
    async def check_service_status(self, service_name: str, port: int) -> Dict:
        """Check service status via API."""
        async with aiohttp.ClientSession() as session:
            try:
                # Map ports to service names
                service_map = {8005: 'funding-engine', 8002: 'risk-engine'}
                host = service_map.get(port, 'localhost')
                async with session.get(f'http://{host}:{port}/status') as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception as e:
                print(f"❌ Failed to check {service_name} status: {e}")
                return {}
    
    async def run_test_scenario(self):
        """Run complete test scenario."""
        print("\n🚀 Starting End-to-End Funding Awareness Test\n")
        
        # Test scenarios
        scenarios = [
            ("BTCUSDT", 25.0, "normal", "test-normal-001"),      # NORMAL regime
            ("BTCUSDT", 75.0, "heated", "test-heated-001"),      # HEATED regime 
            ("BTCUSDT", 150.0, "mania", "test-mania-001"),       # MANIA regime
            ("BTCUSDT", 350.0, "extreme", "test-extreme-001"),   # EXTREME regime
        ]
        
        print("📊 Test Scenarios:")
        for symbol, rate, expected_regime, trace_id in scenarios:
            print(f"  - {symbol}: {rate}% APR → Expected: {expected_regime.upper()}")
        
        print("\n📤 Sending funding rates...")
        
        # Start consuming contexts in background
        context_task = asyncio.create_task(self.consume_funding_context(timeout=30))
        
        # Send funding rates with delays
        for symbol, rate, expected_regime, trace_id in scenarios:
            await self.send_funding_rate(symbol, rate, trace_id)
            await asyncio.sleep(2)  # Wait between messages
        
        # Wait for contexts
        print("\n⏳ Waiting for funding contexts...")
        contexts = await context_task
        
        # Analyze results
        print(f"\n📊 Results Summary:")
        print(f"  - Funding rates sent: {len(scenarios)}")
        print(f"  - Funding contexts received: {len(contexts)}")
        
        # Check each context
        for ctx in contexts:
            funding_ctx = ctx['funding_context']
            decision = ctx['funding_decision']
            
            print(f"\n🔍 Context for {funding_ctx['symbol']}:")
            print(f"  - Rate: {funding_ctx['current_rate']:.1f}% APR")
            print(f"  - Regime: {funding_ctx['current_regime']}")
            print(f"  - Position Multiplier: {funding_ctx['position_multiplier']:.2f}")
            print(f"  - Should Exit: {funding_ctx['should_exit']}")
            print(f"  - Decision: {decision['action']} ({decision['urgency']})")
            print(f"  - Reason: {decision['reason']}")
        
        # Check service statuses
        print("\n🔍 Checking Service Status...")
        
        # Check funding engine
        funding_status = await self.check_service_status("Funding Engine", 8005)
        if funding_status:
            print(f"\n📊 Funding Engine Status:")
            print(f"  - Symbols tracked: {funding_status.get('symbols_tracked', 0)}")
            for symbol, ctx in funding_status.get('contexts', {}).items():
                print(f"  - {symbol}: {ctx['regime']} @ {ctx['current_rate']}")
        
        # Check risk engine
        risk_status = await self.check_service_status("Risk Engine", 8002)
        if risk_status:
            print(f"\n📊 Risk Engine Status:")
            print(f"  - Positions: {risk_status.get('positions', 0)}")
            print(f"  - Messages processed: {risk_status.get('account_updates', 0)}")
        
        # Validate extreme funding handling
        extreme_contexts = [c for c in contexts if c['funding_context']['current_regime'] == 'extreme']
        if extreme_contexts:
            print("\n🚨 EXTREME Funding Validation:")
            for ctx in extreme_contexts:
                assert ctx['funding_context']['should_exit'] == True
                assert ctx['funding_context']['position_multiplier'] == 0.0
                assert ctx['funding_decision']['action'] in ['emergency_exit', 'exit_all']
                print(f"  ✅ Emergency exit triggered for {ctx['funding_context']['symbol']}")
        
        print("\n✅ End-to-End Test Completed!")
        
        # Summary
        if len(contexts) == len(scenarios):
            print("\n🎉 SUCCESS: All funding rates were processed!")
        else:
            print(f"\n⚠️  WARNING: Expected {len(scenarios)} contexts, got {len(contexts)}")
        
        return contexts


async def main():
    """Run the test."""
    test = FundingE2ETest()
    await test.run_test_scenario()


if __name__ == "__main__":
    asyncio.run(main())