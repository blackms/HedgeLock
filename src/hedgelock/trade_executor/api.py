"""
FastAPI application for Trade Executor service.
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, Gauge, generate_latest

from src.hedgelock.trade_executor.config import get_config
from src.hedgelock.trade_executor.service import TradeExecutorService
from src.hedgelock.trade_executor.models import ExecutorState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
trades_submitted = Counter(
    'trade_executor_trades_submitted_total',
    'Total number of trades submitted'
)
trades_filled = Counter(
    'trade_executor_trades_filled_total',
    'Total number of trades filled'
)
trades_failed = Counter(
    'trade_executor_trades_failed_total',
    'Total number of trades failed'
)
execution_latency = Histogram(
    'trade_executor_execution_latency_seconds',
    'Trade execution latency',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)
active_orders = Gauge(
    'trade_executor_active_orders',
    'Number of active orders'
)
daily_volume = Gauge(
    'trade_executor_daily_volume_btc',
    'Daily trading volume in BTC'
)

# Global service instance
service: TradeExecutorService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global service
    
    # Startup
    config = get_config()
    service = TradeExecutorService(config)
    
    try:
        await service.start()
        logger.info("Trade Executor API started successfully")
        yield
    finally:
        # Shutdown
        await service.stop()
        logger.info("Trade Executor API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Trade Executor Service",
    description="Executes hedge trades on Bybit exchange",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint."""
    return {
        "service": "trade-executor",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    state = service.get_state()
    
    # Basic health check
    health_status = {
        "status": "healthy" if state.is_healthy else "unhealthy",
        "kafka_connected": state.kafka_connected,
        "bybit_connected": state.bybit_connected,
        "is_running": state.is_running
    }
    
    if not state.is_healthy:
        raise HTTPException(status_code=503, detail=health_status)
        
    return health_status


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> Dict[str, Any]:
    """Kubernetes readiness probe."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not ready")
        
    state = service.get_state()
    
    if not (state.kafka_connected and state.bybit_connected):
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "kafka": state.kafka_connected,
                "bybit": state.bybit_connected
            }
        )
        
    return {
        "ready": True,
        "kafka": state.kafka_connected,
        "bybit": state.bybit_connected
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    if service:
        state = service.get_state()
        
        # Update metrics
        trades_submitted.inc(state.trades_submitted)
        trades_filled.inc(state.trades_filled)
        trades_failed.inc(state.trades_failed)
        active_orders.set(len(service.pending_executions))
        daily_volume.set(service.daily_volume)
        
    return JSONResponse(
        content=generate_latest().decode('utf-8'),
        media_type="text/plain"
    )


@app.get("/status")
async def status() -> ExecutorState:
    """Get detailed service status."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    return service.get_state()


@app.get("/executions")
async def recent_executions() -> Dict[str, Any]:
    """Get recent trade executions."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    state = service.get_state()
    
    return {
        "pending": len(service.pending_executions),
        "recent": [
            {
                "execution_id": ex.execution_id,
                "symbol": ex.symbol,
                "side": ex.side,
                "quantity": ex.quantity,
                "status": ex.status,
                "filled_quantity": ex.filled_quantity,
                "avg_price": ex.avg_fill_price,
                "created_at": ex.created_at.isoformat()
            }
            for ex in state.recent_executions
        ]
    }


@app.get("/statistics")
async def statistics() -> Dict[str, Any]:
    """Get execution statistics."""
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
        
    state = service.get_state()
    
    total_trades = (
        state.trades_submitted + 
        state.trades_filled + 
        state.trades_failed + 
        state.trades_rejected
    )
    
    fill_rate = (
        state.trades_filled / total_trades if total_trades > 0 else 0
    )
    
    return {
        "total_trades": total_trades,
        "trades_submitted": state.trades_submitted,
        "trades_filled": state.trades_filled,
        "trades_failed": state.trades_failed,
        "trades_rejected": state.trades_rejected,
        "fill_rate": f"{fill_rate * 100:.2f}%",
        "avg_submission_latency_ms": round(state.avg_submission_latency_ms, 2),
        "avg_fill_latency_ms": round(state.avg_fill_latency_ms, 2),
        "daily_volume_btc": round(service.daily_volume, 4),
        "last_update": state.last_update.isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    
    config = get_config()
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8004,
        log_level=config.log_level.lower()
    )