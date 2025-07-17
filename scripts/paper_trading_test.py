#!/usr/bin/env python3
"""
Paper Trading Test Script for HedgeLock v2.0
Simulates real trading conditions to validate system behavior
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from typing import Dict, Any

import aiohttp
from aiokafka import AIOKafkaProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PaperTradingTest:
    """Simulates market conditions for paper trading."""
    
    def __init__(self):
        self.kafka_servers = "localhost:9092"
        self.base_price = 50000  # Starting BTC price
        self.producer = None
        self.session = None
        self.test_duration = 3600  # 1 hour default
        self.metrics = {
            "trades_executed": 0,
            "profits_taken": 0,
            "circuit_breakers_triggered": 0,
            "emergency_actions": 0,
            "max_ltv": 0,
            "total_pnl": 0
        }
    
    async def setup(self):
        """Initialize test infrastructure."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await self.producer.start()
        
        self.session = aiohttp.ClientSession()
        logger.info("Paper trading test initialized")
    
    async def cleanup(self):
        """Clean up resources."""
        if self.producer:
            await self.producer.stop()
        if self.session:
            await self.session.close()
    
    async def simulate_market_volatility(self):
        """Simulate realistic market price movements."""
        while True:
            # Random walk with trend
            volatility = random.uniform(0.0005, 0.002)  # 0.05% - 0.2% moves
            trend = random.choice([-1, -1, 0, 1, 1])  # Slight upward bias
            
            price_change = self.base_price * volatility * trend
            self.base_price += price_change
            
            # Add occasional larger moves
            if random.random() < 0.05:  # 5% chance
                spike = random.uniform(-0.02, 0.02)  # 2% spike
                self.base_price *= (1 + spike)
            
            # Send market data
            await self.producer.send_and_wait(
                'market_data',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'symbol': 'BTCUSDT',
                    'price': self.base_price,
                    'volume': random.uniform(100000, 1000000),
                    'volatility_24h': random.uniform(0.015, 0.035)
                }
            )
            
            await asyncio.sleep(5)  # Update every 5 seconds
    
    async def simulate_funding_rates(self):
        """Simulate funding rate changes."""
        while True:
            # Funding tends to cluster in regimes
            base_rate = random.uniform(-0.01, 0.03)
            
            for _ in range(random.randint(10, 30)):  # Regime lasts 50-150 seconds
                rate = base_rate + random.uniform(-0.005, 0.005)
                
                # Determine regime
                if abs(rate) < 0.01:
                    regime = "NORMAL"
                elif abs(rate) < 0.05:
                    regime = "HEATED"
                else:
                    regime = "EXTREME"
                
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
                
                await asyncio.sleep(5)
    
    async def monitor_system_health(self):
        """Monitor system metrics during test."""
        services = {
            "Position Manager": "http://localhost:8009",
            "Loan Manager": "http://localhost:8010",
            "Reserve Manager": "http://localhost:8011",
            "Safety Manager": "http://localhost:8012"
        }
        
        while True:
            try:
                # Check service health
                for name, url in services.items():
                    async with self.session.get(f"{url}/health") as resp:
                        if resp.status != 200:
                            logger.error(f"{name} unhealthy: {resp.status}")
                
                # Get key metrics
                async with self.session.get("http://localhost:8009/position") as resp:
                    if resp.status == 200:
                        position = await resp.json()
                        logger.info(f"Delta: {position.get('net_delta', 0):.4f}")
                
                async with self.session.get("http://localhost:8010/ltv/current") as resp:
                    if resp.status == 200:
                        ltv = await resp.json()
                        current_ltv = ltv.get('ltv_ratio', 0)
                        self.metrics['max_ltv'] = max(self.metrics['max_ltv'], current_ltv)
                        logger.info(f"LTV: {current_ltv:.2%}")
                
                async with self.session.get("http://localhost:8012/safety/metrics") as resp:
                    if resp.status == 200:
                        safety = await resp.json()
                        metrics = safety.get('metrics', {})
                        
                        if metrics.get('circuit_breakers_active', 0) > 0:
                            self.metrics['circuit_breakers_triggered'] += 1
                            logger.warning("Circuit breaker active!")
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
            
            await asyncio.sleep(10)
    
    async def simulate_trading_activity(self):
        """Simulate trade executions and results."""
        while True:
            # Simulate varying trading activity
            if random.random() < 0.3:  # 30% chance of trade
                # Simulate trade execution
                await self.producer.send_and_wait(
                    'trade_executions',
                    value={
                        'timestamp': datetime.utcnow().isoformat(),
                        'order_id': f"TEST-{int(time.time())}",
                        'symbol': 'BTCUSDT',
                        'side': random.choice(['Buy', 'Sell']),
                        'quantity': random.uniform(0.01, 0.1),
                        'price': self.base_price,
                        'status': 'Filled'
                    }
                )
                self.metrics['trades_executed'] += 1
            
            # Simulate occasional profits
            if random.random() < 0.1:  # 10% chance
                profit = random.uniform(50, 500)
                await self.producer.send_and_wait(
                    'profit_taking',
                    value={
                        'timestamp': datetime.utcnow().isoformat(),
                        'realized_pnl': profit,
                        'position_state': {
                            'btc_price': self.base_price,
                            'spot_btc': 0.27
                        }
                    }
                )
                self.metrics['profits_taken'] += 1
                self.metrics['total_pnl'] += profit
            
            await asyncio.sleep(10)
    
    async def run_test(self, duration: int = 3600):
        """Run the paper trading test."""
        self.test_duration = duration
        logger.info(f"Starting {duration}s paper trading test")
        
        # Start all simulation tasks
        tasks = [
            asyncio.create_task(self.simulate_market_volatility()),
            asyncio.create_task(self.simulate_funding_rates()),
            asyncio.create_task(self.monitor_system_health()),
            asyncio.create_task(self.simulate_trading_activity())
        ]
        
        # Run for specified duration
        await asyncio.sleep(duration)
        
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Print results
        self.print_results()
    
    def print_results(self):
        """Print test results summary."""
        print("\n" + "="*50)
        print("PAPER TRADING TEST RESULTS")
        print("="*50)
        print(f"Test Duration: {self.test_duration}s")
        print(f"Trades Executed: {self.metrics['trades_executed']}")
        print(f"Profits Taken: {self.metrics['profits_taken']}")
        print(f"Total P&L: ${self.metrics['total_pnl']:.2f}")
        print(f"Max LTV Reached: {self.metrics['max_ltv']:.2%}")
        print(f"Circuit Breakers Triggered: {self.metrics['circuit_breakers_triggered']}")
        print(f"Emergency Actions: {self.metrics['emergency_actions']}")
        
        # Basic success criteria
        success = (
            self.metrics['circuit_breakers_triggered'] == 0 and
            self.metrics['max_ltv'] < 0.75 and
            self.metrics['trades_executed'] > 0
        )
        
        print(f"\nTest Result: {'PASS' if success else 'FAIL'}")
        print("="*50)


async def main():
    """Run paper trading test."""
    test = PaperTradingTest()
    
    try:
        await test.setup()
        
        # Run 1 hour test by default
        # Can be adjusted: 300 (5min), 3600 (1hr), 86400 (24hr)
        await test.run_test(duration=3600)
        
    finally:
        await test.cleanup()


if __name__ == "__main__":
    asyncio.run(main())