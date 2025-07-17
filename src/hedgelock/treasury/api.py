"""
Treasury service API endpoints.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException

from .main import TreasuryService

# Global service instance
treasury_service = TreasuryService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle."""
    # Startup
    await treasury_service.start()
    yield
    # Shutdown
    await treasury_service.stop()


# Create FastAPI app
app = FastAPI(
    title="HedgeLock Treasury Service",
    description="Fund management and treasury operations",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "treasury",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get service status."""
    return {
        "is_running": treasury_service.is_running,
        "stub_mode": True,
        "message": "Treasury service in stub mode",
    }


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return treasury_service.get_stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)