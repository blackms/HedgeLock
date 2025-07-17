"""
Position Manager API endpoints.
"""

from fastapi import FastAPI, HTTPException, Request, Response
from typing import Dict, Any, Optional
import logging
import time
from datetime import datetime

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from hedgelock.health import HealthStatus, create_health_router
from .models import PositionState, HedgeDecision
from .service import PositionManagerService
from .manager import DeltaNeutralManager
from .metrics import metrics_collector

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="HedgeLock Position Manager")

# Global service instance
position_service: Optional[PositionManagerService] = None


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record API metrics for all requests."""
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Record metrics
    duration = time.time() - start_time
    metrics_collector.record_api_request(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
        duration=duration
    )
    
    return response
service_config: Dict[str, Any] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global position_service
    
    logger.info("Starting Position Manager API...")
    
    # Configure service
    config = {
        'kafka_servers': 'kafka:29092'
    }
    
    # Create and start service
    position_service = PositionManagerService(config)
    # Note: Don't await start() here as it runs forever
    # Instead, create a background task
    import asyncio
    asyncio.create_task(position_service.start())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global position_service
    
    if position_service:
        await position_service.stop()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Position Manager",
        "version": "1.0.0",
        "status": "active",
        "description": "Delta-neutral position management for HedgeLock"
    }


@app.get("/status")
async def get_status():
    """Get service status."""
    if not position_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "position-manager",
        "status": "active" if position_service.running else "inactive",
        "current_position": position_service.current_position.dict() if position_service.current_position else None,
        "last_hedge_update": position_service.manager.last_hedge_update.isoformat() if position_service.manager.last_hedge_update else None
    }


@app.get("/position")
async def get_position():
    """Get current position state."""
    if not position_service or not position_service.current_position:
        raise HTTPException(status_code=404, detail="No position data available")
    
    position = position_service.current_position
    delta = position_service.manager.calculate_delta(position)
    
    return {
        "timestamp": position.timestamp.isoformat(),
        "positions": {
            "spot_btc": position.spot_btc,
            "long_perp": position.long_perp,
            "short_perp": position.short_perp
        },
        "metrics": {
            "net_delta": delta,
            "delta_neutral": position.delta_neutral,
            "hedge_ratio": position.hedge_ratio,
            "volatility_24h": f"{position.volatility_24h:.1%}",
            "funding_rate_8h": f"{position.funding_rate:.4%}",
            "funding_regime": position.funding_regime
        },
        "pnl": {
            "unrealized": position.unrealized_pnl,
            "realized": position.realized_pnl,
            "peak": position.peak_pnl
        },
        "market": {
            "btc_price": position.btc_price,
            "regime": position.market_regime
        }
    }


@app.get("/hedge-params")
async def get_hedge_parameters():
    """Get current hedging parameters."""
    if not position_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    manager = position_service.manager
    position = position_service.current_position
    
    if not position:
        raise HTTPException(status_code=404, detail="No position data available")
    
    # Calculate hedge ratio for current volatility
    current_hedge_ratio = manager.calculate_hedge_ratio(position.volatility_24h)
    
    # Apply funding multiplier
    adjusted_hedge_ratio = manager.apply_funding_multiplier(
        current_hedge_ratio,
        position.funding_regime
    )
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "volatility_24h": f"{position.volatility_24h:.1%}",
        "base_hedge_ratio": current_hedge_ratio,
        "funding_multiplier": adjusted_hedge_ratio / current_hedge_ratio if current_hedge_ratio > 0 else 0,
        "final_hedge_ratio": adjusted_hedge_ratio,
        "funding_regime": position.funding_regime,
        "last_update": manager.last_hedge_update.isoformat()
    }


@app.post("/rehedge")
async def trigger_rehedge():
    """Manually trigger rehedging."""
    if not position_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        await position_service.rehedge_positions()
        return {
            "status": "success",
            "message": "Rehedge triggered",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Rehedge failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pnl")
async def get_pnl_report():
    """Get comprehensive P&L report."""
    if not position_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not hasattr(position_service, 'pnl_calculator'):
        raise HTTPException(status_code=503, detail="P&L calculator not initialized")
    
    # Get current P&L breakdown
    pnl_breakdown = position_service.pnl_calculator.calculate_pnl(
        position_service.current_position
    )
    
    # Get comprehensive metrics
    pnl_metrics = position_service.pnl_calculator.get_pnl_metrics(
        position_service.current_position
    )
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "pnl_breakdown": {
            "spot_pnl": pnl_breakdown.spot_pnl,
            "long_perp_pnl": pnl_breakdown.long_perp_pnl,
            "short_perp_pnl": pnl_breakdown.short_perp_pnl,
            "funding_pnl": pnl_breakdown.funding_pnl,
            "total_unrealized": pnl_breakdown.total_unrealized_pnl,
            "total_realized": pnl_breakdown.total_realized_pnl,
            "net_pnl": pnl_breakdown.net_pnl
        },
        "metrics": pnl_metrics,
        "entry_prices": position_service.pnl_calculator.entry_prices,
        "position_value": pnl_metrics.get('position_value', 0),
        "roi_percent": pnl_metrics.get('roi_percent', 0)
    }


@app.get("/metrics/health")
async def get_health_metrics():
    """Get health metrics for the position manager."""
    if not position_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Calculate current health scores
    pnl_metrics = position_service.pnl_calculator.get_pnl_metrics(
        position_service.current_position
    )
    health_scores = metrics_collector.calculate_health_scores(
        position_service.current_position,
        pnl_metrics
    )
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "health_scores": health_scores,
        "position_balance": {
            "delta": position_service.current_position.net_delta,
            "target_delta": position_service.current_position.spot_btc,
            "deviation": abs(position_service.current_position.net_delta - position_service.current_position.spot_btc),
            "is_balanced": position_service.current_position.delta_neutral
        },
        "funding_health": {
            "regime": position_service.current_position.funding_regime,
            "rate": position_service.current_position.funding_rate,
            "score": health_scores['funding']
        },
        "pnl_health": {
            "net_pnl": pnl_metrics.get('net_pnl', 0),
            "roi_percent": pnl_metrics.get('roi_percent', 0),
            "score": health_scores['pnl']
        }
    }


@app.get("/metrics")
async def get_prometheus_metrics():
    """Expose Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Add health check endpoints
app.include_router(
    create_health_router(
        service_name="position-manager",
        version="1.0.0",
        dependencies=["kafka", "funding-engine"]
    ),
    prefix=""
)