"""
Market Data API endpoints.
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, Any, Optional
import logging
from datetime import datetime
import asyncio

from hedgelock.health import HealthStatus, create_health_router
from .models import MarketData
from .service import MarketDataService

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="HedgeLock Market Data")

# Global service instance
market_service: Optional[MarketDataService] = None
last_prices: Dict[str, float] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global market_service
    
    logger.info("Starting Market Data API...")
    
    # Configure service
    config = {
        'kafka_servers': 'kafka:29092',
        'testnet': True,
        'poll_interval': 5,
        'symbols': ['BTCUSDT']
    }
    
    # Create and start service
    market_service = MarketDataService(config)
    asyncio.create_task(market_service.start())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global market_service
    
    if market_service:
        await market_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Market Data",
        "version": "1.0.0",
        "status": "active",
        "description": "Market data producer for HedgeLock"
    }


@app.get("/status")
async def get_status():
    """Get service status."""
    if not market_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "market-data",
        "status": "active" if market_service.running else "inactive",
        "symbols": market_service.symbols,
        "poll_interval": market_service.poll_interval,
        "last_prices": last_prices
    }


@app.get("/prices")
async def get_prices():
    """Get latest prices for all symbols."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "prices": last_prices
    }


@app.get("/price/{symbol}")
async def get_price(symbol: str):
    """Get latest price for a symbol."""
    if symbol not in last_prices:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    
    return {
        "symbol": symbol,
        "price": last_prices[symbol],
        "timestamp": datetime.utcnow().isoformat()
    }


# Add health check endpoints
app.include_router(
    create_health_router(
        service_name="market-data",
        version="1.0.0",
        dependencies=["kafka", "bybit-api"]
    ),
    prefix=""
)