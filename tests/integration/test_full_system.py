"""
Full system integration test for HedgeLock v2.0
Tests the complete flow from market data to position management
"""

import asyncio
import json
import pytest
from datetime import datetime
from typing import Dict, Any, List
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SystemIntegrationTest:
    """Test complete HedgeLock v2.0 system integration."""
    
    def __init__(self, kafka_servers: str = "localhost:9092"):
        self.kafka_servers = kafka_servers
        self.producer = None
        self.consumers = {}
        self.messages_collected = {}
        
    async def setup(self):
        """Set up test infrastructure."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await self.producer.start()
        
        # Subscribe to key topics
        topics = [
            'position_states', 'hedge_decisions', 'loan_repayments',
            'reserve_deployments', 'emergency_actions', 'risk_alerts'
        ]
        
        for topic in topics:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.kafka_servers,
                group_id=f'test-integration-{topic}',
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='latest'
            )
            await consumer.start()
            self.consumers[topic] = consumer
            self.messages_collected[topic] = []
    
    async def teardown(self):
        """Clean up test infrastructure."""
        if self.producer:
            await self.producer.stop()
        
        for consumer in self.consumers.values():
            await consumer.stop()
    
    async def simulate_market_data(self, price: float, volatility: float = 0.02):
        """Simulate market data update."""
        await self.producer.send_and_wait(
            'market_data',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'symbol': 'BTCUSDT',
                'price': price,
                'volume': 1000000,
                'volatility_24h': volatility
            }
        )
    
    async def simulate_funding_rate(self, rate: float, regime: str = "NORMAL"):
        """Simulate funding rate update."""
        await self.producer.send_and_wait(
            'funding_context',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'funding_context': {
                    'current_rate': rate,
                    'current_regime': regime,
                    'should_exit': regime == "EXTREME"
                }
            }
        )
    
    async def simulate_profit(self, amount: float):
        """Simulate profit taking event."""
        await self.producer.send_and_wait(
            'profit_taking',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'realized_pnl': amount,
                'position_state': {
                    'btc_price': 50000,
                    'spot_btc': 0.27
                }
            }
        )
    
    async def collect_messages(self, duration: int = 5):
        """Collect messages from subscribed topics."""
        async def collect_from_topic(topic: str, consumer):
            try:
                async for msg in consumer:
                    self.messages_collected[topic].append(msg.value)
                    logger.info(f"Collected from {topic}: {msg.value}")
            except asyncio.CancelledError:
                pass
        
        tasks = []
        for topic, consumer in self.consumers.items():
            task = asyncio.create_task(collect_from_topic(topic, consumer))
            tasks.append(task)
        
        await asyncio.sleep(duration)
        
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.integration
class TestFullSystemIntegration:
    """Test complete system integration."""
    
    async def test_normal_operation_flow(self):
        """Test normal trading operation flow."""
        test = SystemIntegrationTest()
        await test.setup()
        
        try:
            # 1. Simulate market conditions
            await test.simulate_market_data(price=50000, volatility=0.025)
            await test.simulate_funding_rate(rate=0.01, regime="NORMAL")
            
            # 2. Wait for position manager to process
            await asyncio.sleep(2)
            
            # 3. Simulate profit
            await test.simulate_profit(amount=1000)
            
            # 4. Collect messages
            await test.collect_messages(duration=5)
            
            # Verify position states were published
            assert len(test.messages_collected['position_states']) > 0
            
            # Verify loan repayment was triggered
            assert len(test.messages_collected['loan_repayments']) > 0
            
            logger.info("Normal operation flow test passed")
            
        finally:
            await test.teardown()
    
    async def test_high_ltv_response(self):
        """Test system response to high LTV."""
        test = SystemIntegrationTest()
        await test.setup()
        
        try:
            # Simulate high LTV conditions
            # This would be done by adjusting collateral values
            # For now, we'll simulate the LTV update directly
            await test.producer.send_and_wait(
                'ltv_updates',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'ltv_state': {
                        'ltv_ratio': 0.75,  # 75% LTV - Critical
                        'current_action': 'CRITICAL'
                    }
                }
            )
            
            # Collect responses
            await test.collect_messages(duration=5)
            
            # Verify reserve deployment
            assert len(test.messages_collected['reserve_deployments']) > 0
            
            # Verify risk alerts
            assert len(test.messages_collected['risk_alerts']) > 0
            
            logger.info("High LTV response test passed")
            
        finally:
            await test.teardown()
    
    async def test_emergency_shutdown_flow(self):
        """Test emergency shutdown sequence."""
        test = SystemIntegrationTest()
        await test.setup()
        
        try:
            # Simulate extreme funding
            await test.simulate_funding_rate(rate=0.5, regime="EXTREME")
            
            # Simulate panic conditions
            await test.producer.send_and_wait(
                'safety_metrics',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'metrics': {
                        'distance_to_liquidation': 0.03,  # 3% - Emergency
                        'net_equity_drop': 0.15  # 15% drop
                    }
                }
            )
            
            # Collect emergency responses
            await test.collect_messages(duration=5)
            
            # Verify emergency actions
            assert len(test.messages_collected['emergency_actions']) > 0
            
            # Check for close all positions
            emergency_actions = test.messages_collected['emergency_actions']
            assert any(
                action.get('action') in ['close_all_positions', 'panic_close']
                for action in emergency_actions
            )
            
            logger.info("Emergency shutdown test passed")
            
        finally:
            await test.teardown()
    
    async def test_circuit_breaker_trigger(self):
        """Test circuit breaker activation."""
        test = SystemIntegrationTest()
        await test.setup()
        
        try:
            # Simulate daily loss exceeding limit
            await test.producer.send_and_wait(
                'pnl_updates',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'pnl_breakdown': {
                        'net_pnl': -1500  # Exceeds $1000 daily loss limit
                    },
                    'metrics': {
                        'daily_loss': -1500
                    }
                }
            )
            
            # Collect responses
            await test.collect_messages(duration=5)
            
            # Verify risk alerts for circuit breaker
            risk_alerts = test.messages_collected['risk_alerts']
            assert any(
                alert.get('alert_type') == 'CIRCUIT_BREAKER'
                for alert in risk_alerts
            )
            
            logger.info("Circuit breaker test passed")
            
        finally:
            await test.teardown()


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])