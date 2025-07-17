"""
Collector service API endpoints.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest

from .main import CollectorService

# Global service instance
collector_service = CollectorService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle."""
    # Startup
    await collector_service.start()
    yield
    # Shutdown
    await collector_service.stop()


# Create FastAPI app
app = FastAPI(
    title="HedgeLock Collector Service",
    description="Market data collection service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "collector",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get service status."""
    return collector_service.get_stats()


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return collector_service.get_stats()


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)