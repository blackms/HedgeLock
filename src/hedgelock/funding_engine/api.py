"""
FastAPI application for Funding Engine service.
"""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging
from typing import Dict, Optional
from datetime import datetime

from ..shared.funding_models import FundingRegime, FundingSnapshot
from .service import FundingEngineService
from .config import FundingEngineConfig

logger = logging.getLogger(__name__)

# Global service instance
funding_service: Optional[FundingEngineService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle."""
    global funding_service
    
    # Startup
    config = FundingEngineConfig()
    funding_service = FundingEngineService(config)
    await funding_service.start()
    
    yield
    
    # Shutdown
    await funding_service.stop()


# Create FastAPI app
app = FastAPI(
    title="HedgeLock Funding Engine",
    description="Funding rate processing and regime detection service",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "funding-engine",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status")
async def get_status():
    """Get current service status."""
    if not funding_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    return funding_service.get_funding_status()


@app.get("/funding/context/{symbol}")
async def get_funding_context(symbol: str):
    """Get current funding context for a symbol."""
    if not funding_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    context = funding_service.current_contexts.get(symbol)
    if not context:
        raise HTTPException(status_code=404, detail=f"No funding context for {symbol}")
        
    return {
        "symbol": context.symbol,
        "current_regime": context.current_regime.value,
        "current_rate": context.current_rate,
        "avg_rate_24h": context.avg_rate_24h,
        "avg_rate_7d": context.avg_rate_7d,
        "max_rate_24h": context.max_rate_24h,
        "volatility_24h": context.volatility_24h,
        "position_multiplier": context.position_multiplier,
        "should_exit": context.should_exit,
        "regime_change": context.regime_change,
        "daily_cost_bps": context.daily_cost_bps,
        "weekly_cost_pct": context.weekly_cost_pct,
        "timestamp": context.timestamp.isoformat()
    }


@app.get("/funding/history/{symbol}")
async def get_funding_history(symbol: str, hours: int = 24):
    """Get funding rate history for a symbol."""
    if not funding_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    if hours > 168:  # Max 7 days
        raise HTTPException(status_code=400, detail="Maximum 168 hours (7 days) allowed")
        
    rates = funding_service.storage.get_funding_history(symbol, hours)
    
    return {
        "symbol": symbol,
        "hours": hours,
        "count": len(rates),
        "rates": [
            {
                "funding_rate": rate.funding_rate,
                "annualized_rate": rate.annualized_rate,
                "daily_rate": rate.daily_rate,
                "funding_time": rate.funding_time.isoformat(),
                "mark_price": rate.mark_price,
                "index_price": rate.index_price
            }
            for rate in rates
        ]
    }


@app.get("/funding/regimes")
async def get_all_regimes():
    """Get current funding regimes for all tracked symbols."""
    if not funding_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    regimes = {}
    for symbol, context in funding_service.current_contexts.items():
        regimes[symbol] = {
            "regime": context.current_regime.value,
            "rate": context.current_rate,
            "multiplier": context.position_multiplier
        }
        
    return {
        "regimes": regimes,
        "count": len(regimes),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/funding/risk/{symbol}")
async def get_funding_risk(symbol: str):
    """Get funding risk assessment for a symbol."""
    if not funding_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    context = funding_service.current_contexts.get(symbol)
    if not context:
        raise HTTPException(status_code=404, detail=f"No funding context for {symbol}")
        
    # Get decision from service
    decision = funding_service._generate_funding_decision(context)
    
    return {
        "symbol": symbol,
        "risk_score": decision.funding_risk_score,
        "action": decision.action,
        "reason": decision.reason,
        "urgency": decision.urgency,
        "position_adjustment": decision.position_adjustment,
        "max_position_size": decision.max_position_size,
        "projected_cost_24h": decision.projected_cost_24h,
        "current_regime": context.current_regime.value,
        "current_rate": context.current_rate
    }


@app.post("/funding/simulate")
async def simulate_funding_regime(
    symbol: str,
    current_rate: float,
    rates_24h: list[float],
    rates_7d: list[float]
):
    """Simulate funding regime detection with custom rates."""
    try:
        # Create mock funding rates
        current_funding = FundingRate(
            symbol=symbol,
            funding_rate=current_rate / 100 / 365 / 3,  # Convert from APR
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
        
        mock_24h = []
        for i, rate in enumerate(rates_24h):
            mock_24h.append(FundingRate(
                symbol=symbol,
                funding_rate=rate / 100 / 365 / 3,
                funding_time=datetime.utcnow() - timedelta(hours=8*i),
                mark_price=50000.0,
                index_price=50000.0
            ))
            
        mock_7d = []
        for i, rate in enumerate(rates_7d):
            mock_7d.append(FundingRate(
                symbol=symbol,
                funding_rate=rate / 100 / 365 / 3,
                funding_time=datetime.utcnow() - timedelta(hours=8*i),
                mark_price=50000.0,
                index_price=50000.0
            ))
            
        # Create snapshot
        snapshot = FundingSnapshot(
            symbol=symbol,
            current_rate=current_funding,
            rates_24h=mock_24h,
            rates_7d=mock_7d
        )
        
        # Calculate context
        from ..shared.funding_calculator import FundingCalculator
        context = FundingCalculator.calculate_funding_context(snapshot)
        
        return {
            "regime": context.current_regime.value,
            "position_multiplier": context.position_multiplier,
            "should_exit": context.should_exit,
            "daily_cost_bps": context.daily_cost_bps,
            "weekly_cost_pct": context.weekly_cost_pct,
            "avg_rate_24h": context.avg_rate_24h,
            "avg_rate_7d": context.avg_rate_7d,
            "volatility_24h": context.volatility_24h
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    config = FundingEngineConfig()
    uvicorn.run(app, host="0.0.0.0", port=config.service_port)