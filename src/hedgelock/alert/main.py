"""Alert service stub implementation."""

import asyncio
import logging
import os
import random
from datetime import datetime
from typing import Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HedgeLock Alert Service", version="0.1.0")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str
    environment: Dict[str, str]


class Alert(BaseModel):
    """Alert model."""

    alert_id: str
    timestamp: datetime
    severity: str
    channel: str
    title: str
    message: str
    delivered: bool


class AlertService:
    """Stub implementation of the Alert service."""

    def __init__(self) -> None:
        """Initialize the alert service."""
        self.is_running = False
        self.alert_count = 0
        self.alerts: List[Alert] = []
        self.telegram_enabled = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        self.email_enabled = bool(os.getenv("SMTP_USER"))

    async def start(self) -> None:
        """Start the alert service."""
        logger.info("Starting Alert service...")
        logger.info(
            f"Telegram: {'enabled' if self.telegram_enabled else 'disabled'}, "
            f"Email: {'enabled' if self.email_enabled else 'disabled'}"
        )
        self.is_running = True

        while self.is_running:
            await asyncio.sleep(30)
            self.alert_count += 1

            # Simulate alert generation
            if random.random() > 0.7:
                alert = self._create_stub_alert()
                self.alerts.append(alert)
                logger.info(
                    f"[STUB] Alert #{self.alert_count} - "
                    f"{alert.severity}: {alert.title}"
                )

    async def stop(self) -> None:
        """Stop the alert service."""
        logger.info("Stopping Alert service...")
        self.is_running = False

    def _create_stub_alert(self) -> Alert:
        """Create a stub alert."""
        severities = ["INFO", "WARNING", "CRITICAL"]
        channels = ["telegram", "email", "webhook"]
        titles = [
            "LTV Ratio Warning",
            "Hedge Position Update",
            "Treasury Action Completed",
            "System Health Check",
        ]

        severity = random.choice(severities)
        return Alert(
            alert_id=f"ALT-{self.alert_count:06d}",
            timestamp=datetime.utcnow(),
            severity=severity,
            channel=random.choice(channels),
            title=random.choice(titles),
            message=f"This is a stub {severity.lower()} alert for testing purposes.",
            delivered=random.random() > 0.1,  # 90% delivery success
        )

    def get_stats(self) -> Dict[str, any]:
        """Get service statistics."""
        delivered_count = sum(1 for a in self.alerts if a.delivered)
        critical_count = sum(1 for a in self.alerts if a.severity == "CRITICAL")

        return {
            "alert_count": self.alert_count,
            "total_alerts": len(self.alerts),
            "delivered_alerts": delivered_count,
            "critical_alerts": critical_count,
            "delivery_rate": (
                f"{(delivered_count / len(self.alerts) * 100):.1f}%"
                if self.alerts
                else "N/A"
            ),
            "is_running": self.is_running,
            "telegram_enabled": self.telegram_enabled,
            "email_enabled": self.email_enabled,
            "stub_mode": True,
        }


# Global service instance
service = AlertService()


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
        service="hedgelock-alert",
        version="0.1.0",
        environment={
            "telegram_enabled": str(service.telegram_enabled),
            "email_enabled": str(service.email_enabled),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        },
    )


@app.get("/alerts", response_model=List[Alert])
async def get_alerts() -> List[Alert]:
    """Get recent alerts."""
    return service.alerts[-20:]  # Return last 20 alerts


@app.get("/stats")
async def get_stats() -> Dict[str, any]:
    """Get service statistics."""
    return service.get_stats()


@app.post("/test-alert")
async def send_test_alert() -> Dict[str, str]:
    """Send a test alert."""
    alert = service._create_stub_alert()
    alert.title = "Test Alert"
    alert.message = "This is a manual test alert triggered via API."
    service.alerts.append(alert)
    return {"status": "sent", "alert_id": alert.alert_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
