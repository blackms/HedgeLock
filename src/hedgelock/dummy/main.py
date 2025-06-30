"""Dummy service implementation for testing CI/CD pipeline."""

import asyncio
import logging
from typing import Dict

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HedgeLock Dummy Service", version="0.1.0")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str


class DummyService:
    """Dummy service for testing purposes."""

    def __init__(self) -> None:
        """Initialize the dummy service."""
        self.is_running = False
        self.message_count = 0

    async def start(self) -> None:
        """Start the dummy service."""
        logger.info("Starting dummy service...")
        self.is_running = True

        while self.is_running:
            await asyncio.sleep(5)
            self.message_count += 1
            logger.info(f"Dummy service heartbeat #{self.message_count}")

    async def stop(self) -> None:
        """Stop the dummy service."""
        logger.info("Stopping dummy service...")
        self.is_running = False

    def get_stats(self) -> Dict[str, int]:
        """Get service statistics."""
        return {
            "message_count": self.message_count,
            "is_running": int(self.is_running),
        }


# Global service instance
service = DummyService()


@app.on_event("startup")
async def startup_event() -> None:
    """Handle application startup."""
    asyncio.create_task(service.start())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Handle application shutdown."""
    await service.stop()


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="hedgelock-dummy",
        version="0.1.0",
    )


@app.get("/stats")
async def get_stats() -> Dict[str, int]:
    """Get service statistics."""
    return service.get_stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)