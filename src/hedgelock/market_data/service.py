"""
Market data producer service.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import aiohttp

from aiokafka import AIOKafkaProducer
from .models import MarketData, PriceUpdate

logger = logging.getLogger(__name__)


class MarketDataService:
    """Service for fetching and publishing market data."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.producer: Optional[AIOKafkaProducer] = None
        self.running = False
        self.bybit_base_url = "https://api-testnet.bybit.com" if config.get('testnet', True) else "https://api.bybit.com"
        self.poll_interval = config.get('poll_interval', 5)  # seconds
        self.symbols = config.get('symbols', ['BTCUSDT'])
        
    async def start(self):
        """Start the service."""
        logger.info("Starting Market Data service...")
        
        # Initialize Kafka producer
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await self.producer.start()
        self.running = True
        
        # Start polling for each symbol
        tasks = [self.poll_market_data(symbol) for symbol in self.symbols]
        await asyncio.gather(*tasks)
    
    async def poll_market_data(self, symbol: str):
        """Poll market data for a symbol."""
        logger.info(f"Starting market data polling for {symbol}")
        
        while self.running:
            try:
                # Fetch ticker data
                ticker_data = await self.fetch_ticker(symbol)
                
                if ticker_data:
                    # Create market data message
                    market_data = MarketData(
                        symbol=symbol,
                        price=float(ticker_data['lastPrice']),
                        timestamp=datetime.utcnow(),
                        volume_24h=float(ticker_data.get('volume24h', 0)),
                        bid=float(ticker_data.get('bid1Price', 0)),
                        ask=float(ticker_data.get('ask1Price', 0))
                    )
                    
                    # Publish to Kafka
                    await self.producer.send_and_wait(
                        'market_data',
                        value=market_data.dict()
                    )
                    
                    logger.debug(f"Published price update: {symbol} @ {market_data.price}")
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error polling market data for {symbol}: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """Fetch ticker data from Bybit."""
        url = f"{self.bybit_base_url}/v5/market/tickers"
        params = {
            'category': 'inverse',  # For BTC perpetual
            'symbol': symbol
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data['retCode'] == 0 and data['result']['list']:
                            return data['result']['list'][0]
                    else:
                        logger.error(f"Failed to fetch ticker: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error fetching ticker: {e}")
            
        return None
    
    async def stop(self):
        """Stop the service."""
        logger.info("Stopping Market Data service...")
        self.running = False
        
        if self.producer:
            await self.producer.stop()