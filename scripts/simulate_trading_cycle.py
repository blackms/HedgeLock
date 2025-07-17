#!/usr/bin/env python3
"""
Simulate a complete trading cycle with Position Manager.
"""

import asyncio
import json
import aiohttp
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
import random


async def simulate_price_movement():
    """Simulate BTC price movements."""
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:29092',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    await producer.start()
    
    try:
        # Starting price
        price = 116000
        
        print("🚀 Starting Trading Cycle Simulation\n")
        print(f"Initial BTC Price: ${price:,.0f}")
        
        # Simulate price movements
        for i in range(20):
            # Random walk with slight upward bias
            change = random.gauss(0.001, 0.005)  # 0.1% mean, 0.5% std dev
            price = price * (1 + change)
            
            # Send market data update
            market_data = {
                "service": "market-data-sim",
                "symbol": "BTCUSDT",
                "price": price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "volume_24h": random.uniform(1000000, 2000000),
                "bid": price - 10,
                "ask": price + 10,
                "trace_id": f"sim-{i}"
            }
            
            await producer.send_and_wait('market_data', value=market_data)
            
            print(f"  Price update {i+1}: ${price:,.0f} ({change:+.2%})")
            
            # Also send varying funding rates
            if i % 5 == 0:
                # Change funding regime
                regimes = [
                    (15, "NEUTRAL"),
                    (35, "NORMAL"),
                    (75, "HEATED"),
                    (150, "MANIA")
                ]
                
                rate, regime = random.choice(regimes)
                
                funding_msg = {
                    "service": "funding-sim",
                    "funding_context": {
                        "symbol": "BTCUSDT",
                        "current_rate": rate,
                        "current_regime": regime,
                        "multiplier": 1.0 if regime in ["NEUTRAL", "NORMAL"] else 0.5 if regime == "HEATED" else 0.2,
                        "should_exit": False
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                await producer.send_and_wait('funding_context', value=funding_msg)
                print(f"  📊 Funding regime changed to: {regime} ({rate}% APR)")
            
            await asyncio.sleep(2)
        
        print(f"\nFinal BTC Price: ${price:,.0f}")
        print(f"Total Change: {(price/116000 - 1)*100:+.1f}%")
        
    finally:
        await producer.stop()


async def check_position_state():
    """Check Position Manager state."""
    try:
        async with aiohttp.ClientSession() as session:
            # Get position
            async with session.get('http://localhost:8009/position') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print("\n📍 Current Position State:")
                    print(f"  Net Delta: {data['metrics']['net_delta']}")
                    print(f"  Hedge Ratio: {data['metrics']['hedge_ratio']}")
                    print(f"  Funding Regime: {data['metrics']['funding_regime']}")
                    print(f"  Volatility: {data['metrics']['volatility_24h']}")
                    
                    pnl = data['pnl']
                    if pnl['unrealized'] != 0:
                        print(f"  Unrealized P&L: ${pnl['unrealized']:,.2f}")
            
            # Get hedge params
            async with session.get('http://localhost:8009/hedge-params') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"\n🎯 Hedge Parameters:")
                    print(f"  Base Ratio: {data['base_hedge_ratio']}")
                    print(f"  Funding Multiplier: {data['funding_multiplier']}")
                    print(f"  Final Ratio: {data['final_hedge_ratio']}")
                    
    except Exception as e:
        print(f"❌ Error checking position: {e}")


async def main():
    """Run the trading cycle simulation."""
    print("=" * 60)
    print("HedgeLock Trading Cycle Simulation")
    print("=" * 60)
    
    # Check initial state
    await check_position_state()
    
    # Simulate price movements
    await simulate_price_movement()
    
    # Check final state
    print("\n" + "=" * 60)
    print("Final State After Simulation")
    print("=" * 60)
    await check_position_state()
    
    print("\n✅ Simulation complete!")
    print("\nTo monitor hedge trades:")
    print("  docker exec -it hedgelock-kafka-1 kafka-console-consumer \\")
    print("    --bootstrap-server localhost:29092 \\")
    print("    --topic hedge_trades --from-beginning")


if __name__ == "__main__":
    asyncio.run(main())