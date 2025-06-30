"""Collector service stub implementation."""

import asyncio
import logging
import os
from typing import Dict

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HedgeLock Collector Service", version="0.1.0")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str
    environment: Dict[str, str]


class CollectorService:
    """Stub implementation of the Collector service."""

    def __init__(self) -> None:
        """Initialize the collector service."""
        self.is_running = False
        self.message_count = 0
        self.bybit_testnet = os.getenv("BYBIT_TESTNET", "true") == "true"

    async def start(self) -> None:
        """Start the collector service."""
        logger.info("Starting Collector service...")
        logger.info(f"Bybit testnet mode: {self.bybit_testnet}")
        self.is_running = True

        while self.is_running:
            await asyncio.sleep(10)
            self.message_count += 1
            logger.info(
                f"[STUB] Collector heartbeat #{self.message_count} - "
                f"Would collect market data and account updates"
            )

    async def stop(self) -> None:
        """Stop the collector service."""
        logger.info("Stopping Collector service...")
        self.is_running = False

    def get_stats(self) -> Dict[str, any]:
        """Get service statistics."""
        return {
            "message_count": self.message_count,
            "is_running": self.is_running,
            "testnet_mode": self.bybit_testnet,
            "stub_mode": True,
        }


# Global service instance
service = CollectorService()


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
        service="hedgelock-collector",
        version="0.1.0",
        environment={
            "bybit_testnet": str(service.bybit_testnet),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        },
    )


@app.get("/stats")
async def get_stats() -> Dict[str, any]:
    """Get service statistics."""
    return service.get_stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
