"""Hedger service stub implementation."""

import asyncio
import logging
import os
import random
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HedgeLock Hedger Service", version="0.1.0")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str
    environment: Dict[str, str]


class Order(BaseModel):
    """Order model."""

    order_id: str
    symbol: str
    side: str
    size: float
    price: float
    status: str


class HedgerService:
    """Stub implementation of the Hedger service."""

    def __init__(self) -> None:
        """Initialize the hedger service."""
        self.is_running = False
        self.order_count = 0
        self.orders: List[Order] = []
        self.max_order_size = float(os.getenv("MAX_ORDER_SIZE_BTC", "10.0"))
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE_BTC", "50.0"))

    async def start(self) -> None:
        """Start the hedger service."""
        logger.info("Starting Hedger service...")
        logger.info(
            f"Max order size: {self.max_order_size} BTC, "
            f"Max position: {self.max_position_size} BTC"
        )
        self.is_running = True

        while self.is_running:
            await asyncio.sleep(15)
            self.order_count += 1

            # Simulate order placement
            if random.random() > 0.5:
                order = self._create_stub_order()
                self.orders.append(order)
                logger.info(
                    f"[STUB] Placed order #{self.order_count} - "
                    f"{order.side} {order.size} BTC @ ${order.price}"
                )

    async def stop(self) -> None:
        """Stop the hedger service."""
        logger.info("Stopping Hedger service...")
        self.is_running = False

    def _create_stub_order(self) -> Order:
        """Create a stub order."""
        return Order(
            order_id=f"ORD-{self.order_count:06d}",
            symbol="BTCUSDT",
            side=random.choice(["BUY", "SELL"]),
            size=round(random.uniform(0.001, min(1.0, self.max_order_size)), 4),
            price=round(random.uniform(40000, 45000), 2),
            status="FILLED",
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "order_count": self.order_count,
            "active_orders": len([o for o in self.orders if o.status != "FILLED"]),
            "total_orders": len(self.orders),
            "is_running": self.is_running,
            "max_order_size": self.max_order_size,
            "max_position_size": self.max_position_size,
            "stub_mode": True,
        }


# Global service instance
service = HedgerService()


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
        service="hedgelock-hedger",
        version="0.1.0",
        environment={
            "max_order_size": str(service.max_order_size),
            "max_position_size": str(service.max_position_size),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        },
    )


@app.get("/orders", response_model=List[Order])
async def get_orders() -> List[Order]:
    """Get recent orders."""
    return service.orders[-10:]  # Return last 10 orders


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return service.get_stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
