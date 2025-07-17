#!/usr/bin/env python3
"""
Full integration test for funding-aware hedging.
Tests: Account Data → Risk Assessment → Funding Context → Hedge Decision
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, List
import aiohttp
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer


class FullFlowTest:
    """Full integration test for funding-aware hedging."""
    
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"
        
    async def send_account_data(self, trace_id: str):
        """Send account data to simulate a position."""
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await producer.start()
        
        try:
            # Create account data with a leveraged position
            account_msg = {
                "service": "test-collector",
                "account_data": {
                    "symbol": "BTCUSDT",
                    "position_value": 100000.0,  # $100k position
                    "position_qty": 2.0,  # 2 BTC
                    "entry_price": 50000.0,
                    "mark_price": 51000.0,
                    "unrealized_pnl": 2000.0,
                    "margin_balance": 20000.0,  # $20k margin
                    "available_balance": 15000.0,
                    "maintenance_margin": 5000.0,
                    "initial_margin": 10000.0,
                    "ltv": 0.5,  # 50% LTV
                    "position_side": "LONG",
                    "leverage": 5
                },
                "trace_id": trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await producer.send_and_wait('account_raw', value=account_msg)
            print(f"✅ Sent account data: {account_msg['account_data']['symbol']} position=${account_msg['account_data']['position_value']:,.0f}")
            
        finally:
            await producer.stop()
    
    async def monitor_topics(self, duration: int = 30):
        """Monitor multiple Kafka topics for the flow."""
        topics = ['risk_state', 'funding_context', 'hedge_trades']
        consumers = {}
        
        # Create consumers for each topic
        for topic in topics:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.kafka_bootstrap,
                auto_offset_reset='latest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            await consumer.start()
            consumers[topic] = consumer
        
        results = {topic: [] for topic in topics}
        
        try:
            print(f"\n📡 Monitoring topics for {duration}s...")
            end_time = time.time() + duration
            
            while time.time() < end_time:
                for topic, consumer in consumers.items():
                    try:
                        msg = await asyncio.wait_for(consumer.getone(), timeout=0.5)
                        results[topic].append(msg.value)
                        print(f"  📨 {topic}: Received message")
                        
                        # Print key details
                        if topic == 'risk_state':
                            data = msg.value.get('risk_state', {})
                            print(f"     → Risk: {data.get('risk_level', 'N/A')}, LTV: {data.get('ltv', 0):.2%}")
                        elif topic == 'funding_context':
                            ctx = msg.value.get('funding_context', {})
                            print(f"     → Funding: {ctx.get('current_regime', 'N/A')}, Rate: {ctx.get('current_rate', 0):.1f}% APR")
                        elif topic == 'hedge_trades':
                            decision = msg.value.get('hedge_decision', {})
                            print(f"     → Hedge: {decision.get('action', 'N/A')}, Size: ${decision.get('hedge_size', 0):,.0f}")
                            
                    except asyncio.TimeoutError:
                        continue
                        
        finally:
            for consumer in consumers.values():
                await consumer.stop()
                
        return results
    
    async def run_funding_aware_hedge_test(self):
        """Run complete funding-aware hedging test."""
        print("\n🚀 Starting Full Integration Test: Funding-Aware Hedging\n")
        
        # Step 1: Send account data
        print("Step 1: Sending Account Data")
        trace_id = "full-flow-test-001"
        await self.send_account_data(trace_id)
        await asyncio.sleep(2)
        
        # Step 2: Send funding rate
        print("\nStep 2: Sending Funding Rate")
        funding_test = FundingE2ETest()  # Reuse from previous test
        await funding_test.send_funding_rate("BTCUSDT", 150.0, trace_id)  # MANIA regime
        
        # Step 3: Monitor the flow
        print("\nStep 3: Monitoring Message Flow")
        results = await self.monitor_topics(duration=15)
        
        # Step 4: Analyze results
        print("\n📊 Results Summary:")
        for topic, messages in results.items():
            print(f"\n{topic}: {len(messages)} messages")
            
            if topic == 'hedge_trades' and messages:
                for msg in messages:
                    decision = msg.get('hedge_decision', {})
                    print(f"  - Action: {decision.get('action', 'N/A')}")
                    print(f"  - Hedge Size: ${decision.get('hedge_size', 0):,.0f}")
                    print(f"  - Funding Aware: {decision.get('funding_aware', False)}")
                    print(f"  - Funding Multiplier: {decision.get('funding_multiplier', 1.0):.2f}")
        
        # Validate funding awareness
        hedge_trades = results.get('hedge_trades', [])
        if hedge_trades:
            for trade in hedge_trades:
                decision = trade.get('hedge_decision', {})
                if decision.get('funding_aware'):
                    print("\n✅ FUNDING AWARENESS CONFIRMED!")
                    print(f"   - Original hedge would be: ${decision.get('base_hedge_size', 0):,.0f}")
                    print(f"   - Adjusted for funding: ${decision.get('hedge_size', 0):,.0f}")
                    print(f"   - Reduction: {(1 - decision.get('funding_multiplier', 1.0)) * 100:.0f}%")
        else:
            print("\n⚠️  No hedge trades generated - may need position data")
        
        return results


# Import the funding test class
class FundingE2ETest:
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"
        
    async def send_funding_rate(self, symbol: str, rate: float, trace_id: str):
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await producer.start()
        
        try:
            funding_msg = {
                "service": "e2e-test-collector",
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
            
            await producer.send_and_wait('funding_rates', value=funding_msg)
            print(f"✅ Sent funding rate: {symbol} @ {rate}% APR")
            
        finally:
            await producer.stop()


async def main():
    """Run the full integration test."""
    test = FullFlowTest()
    await test.run_funding_aware_hedge_test()


if __name__ == "__main__":
    asyncio.run(main())