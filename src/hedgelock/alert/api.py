"""
Alert service API endpoints.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, HTTPException

from .main import AlertService

# Global service instance
alert_service = AlertService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle."""
    # Startup
    await alert_service.start()
    yield
    # Shutdown
    await alert_service.stop()


# Create FastAPI app
app = FastAPI(
    title="HedgeLock Alert Service",
    description="Notification and alerting service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "alert",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get service status."""
    return {
        "is_running": alert_service.is_running,
        "stub_mode": True,
        "message": "Alert service in stub mode",
    }


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return alert_service.get_stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8007)