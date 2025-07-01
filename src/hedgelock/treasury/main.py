"""Treasury service stub implementation."""

import asyncio
import logging
import os
import random
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HedgeLock Treasury Service", version="0.1.0")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str
    environment: Dict[str, str]


class TreasuryAction(BaseModel):
    """Treasury action model."""

    action_id: str
    timestamp: datetime
    action_type: str
    amount_usd: float
    description: str


class TreasuryService:
    """Stub implementation of the Treasury service."""

    def __init__(self) -> None:
        """Initialize the treasury service."""
        self.is_running = False
        self.action_count = 0
        self.actions: List[TreasuryAction] = []
        self.min_buffer = float(os.getenv("MIN_BUFFER_PERCENT", "5"))
        self.max_operation = float(os.getenv("MAX_SINGLE_OPERATION_USD", "10000"))

    async def start(self) -> None:
        """Start the treasury service."""
        logger.info("Starting Treasury service...")
        logger.info(
            f"Min buffer: {self.min_buffer}%, " f"Max operation: ${self.max_operation}"
        )
        self.is_running = True

        while self.is_running:
            await asyncio.sleep(20)
            self.action_count += 1

            # Simulate treasury action
            if random.random() > 0.6:
                action = self._create_stub_action()
                self.actions.append(action)
                logger.info(
                    f"[STUB] Treasury action #{self.action_count} - "
                    f"{action.action_type}: ${action.amount_usd:.2f}"
                )

    async def stop(self) -> None:
        """Stop the treasury service."""
        logger.info("Stopping Treasury service...")
        self.is_running = False

    def _create_stub_action(self) -> TreasuryAction:
        """Create a stub treasury action."""
        action_types = ["REPAY_PRINCIPAL", "ADD_COLLATERAL", "WITHDRAW_PROFIT"]
        return TreasuryAction(
            action_id=f"TRS-{self.action_count:06d}",
            timestamp=datetime.utcnow(),
            action_type=random.choice(action_types),
            amount_usd=round(random.uniform(100, min(5000, self.max_operation)), 2),
            description="Stub treasury action for testing",
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        total_repaid = sum(
            a.amount_usd for a in self.actions if a.action_type == "REPAY_PRINCIPAL"
        )
        total_collateral = sum(
            a.amount_usd for a in self.actions if a.action_type == "ADD_COLLATERAL"
        )

        return {
            "action_count": self.action_count,
            "total_actions": len(self.actions),
            "total_repaid_usd": total_repaid,
            "total_collateral_added_usd": total_collateral,
            "is_running": self.is_running,
            "min_buffer_percent": self.min_buffer,
            "max_operation_usd": self.max_operation,
            "stub_mode": True,
        }


# Global service instance
service = TreasuryService()


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
        service="hedgelock-treasury",
        version="0.1.0",
        environment={
            "min_buffer": str(service.min_buffer),
            "max_operation": str(service.max_operation),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        },
    )


@app.get("/actions", response_model=List[TreasuryAction])
async def get_actions() -> List[TreasuryAction]:
    """Get recent treasury actions."""
    return service.actions[-10:]  # Return last 10 actions


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return service.get_stats()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
