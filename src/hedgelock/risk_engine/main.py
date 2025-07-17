"""
Risk Engine service - Consumes account_raw and produces risk_state.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from src.hedgelock.config import settings
from src.hedgelock.health import (
    ComponentHealth,
    HealthChecker,
    HealthStatus,
    create_health_endpoints,
)
from src.hedgelock.logging import get_logger, trace_context
from src.hedgelock.risk_engine.calculator import RiskCalculator
from src.hedgelock.risk_engine.models import AccountData, RiskStateMessage
from src.hedgelock.shared.funding_models import FundingContext, FundingContextMessage

logger = get_logger(__name__)

# Prometheus metrics
messages_processed = Counter(
    "risk_engine_messages_processed_total", "Total messages processed"
)
messages_failed = Counter("risk_engine_messages_failed_total", "Total messages failed")
processing_time = Histogram(
    "risk_engine_processing_seconds", "Processing time in seconds"
)
current_ltv = Gauge("risk_engine_current_ltv", "Current LTV ratio")
current_risk_score = Gauge("risk_engine_current_risk_score", "Current risk score")
risk_state_changes = Counter(
    "risk_engine_state_changes_total",
    "Total risk state changes",
    ["from_state", "to_state"],
)


class RiskEngineService:
    """Risk Engine service implementation."""

    def __init__(self):
        self.config = settings
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.funding_consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.calculator = RiskCalculator()
        self.is_running = False
        self.funding_contexts: Dict[str, FundingContext] = (
            {}
        )  # Store funding context by symbol
        self.stats = {
            "messages_processed": 0,
            "messages_failed": 0,
            "last_message_time": None,
            "current_risk_state": None,
        }

    async def start(self):
        """Start the risk engine service."""
        logger.info("Starting Risk Engine service...")

        # Initialize Kafka consumer for account data
        self.consumer = AIOKafkaConsumer(
            self.config.kafka.topic_account_raw,
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            group_id=f"{self.config.kafka.consumer_group_prefix}_risk_engine",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            enable_auto_commit=self.config.kafka.enable_auto_commit,
            max_poll_records=self.config.kafka.max_poll_records,
        )

        # Initialize Kafka consumer for funding context
        self.funding_consumer = AIOKafkaConsumer(
            "funding_context",  # Funding context topic
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            group_id=f"{self.config.kafka.consumer_group_prefix}_risk_engine_funding",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            enable_auto_commit=self.config.kafka.enable_auto_commit,
        )

        # Initialize Kafka producer
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )

        try:
            await self.consumer.start()
            await self.funding_consumer.start()
            await self.producer.start()
            logger.info("Kafka consumers and producer started successfully")
            self.is_running = True

            # Start consuming messages
            await asyncio.gather(
                self.consume_messages(), self.consume_funding_context()
            )

        except Exception as e:
            logger.error(f"Failed to start Risk Engine: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop the risk engine service."""
        logger.info("Stopping Risk Engine service...")
        self.is_running = False

        if self.consumer:
            await self.consumer.stop()
        if self.funding_consumer:
            await self.funding_consumer.stop()
        if self.producer:
            await self.producer.stop()

        logger.info("Risk Engine stopped")

    async def consume_messages(self):
        """Consume messages from account_raw topic."""
        logger.info(f"Starting to consume from {self.config.kafka.topic_account_raw}")

        async for message in self.consumer:
            if not self.is_running:
                break

            trace_id = message.headers.get("trace_id", str(message.offset))

            with trace_context(trace_id):
                try:
                    await self.process_message(message.value, trace_id)
                    messages_processed.inc()
                    self.stats["messages_processed"] += 1
                    self.stats["last_message_time"] = datetime.utcnow()

                    # Commit offset after successful processing
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(f"Failed to process message: {e}", exc_info=True)
                    messages_failed.inc()
                    self.stats["messages_failed"] += 1

    async def process_message(self, message: Dict[str, Any], trace_id: str):
        """Process a single account_raw message."""
        start_time = time.time()

        try:
            # Parse account data
            account_data = AccountData(**message)

            # Get funding context for BTC (main trading pair)
            funding_context = self.funding_contexts.get("BTCUSDT")

            # Calculate risk with funding context
            calculation = self.calculator.calculate_risk(
                account_data, funding_context, trace_id
            )

            # Create risk state message
            risk_message = self.calculator.create_risk_state_message(calculation)

            # Update metrics
            current_ltv.set(calculation.ltv)
            current_risk_score.set(calculation.risk_score)

            if risk_message.state_changed:
                risk_state_changes.labels(
                    from_state=(
                        risk_message.previous_state.value
                        if risk_message.previous_state
                        else "UNKNOWN"
                    ),
                    to_state=risk_message.risk_state.value,
                ).inc()

            # Publish to risk_state topic
            await self.producer.send(
                self.config.kafka.topic_risk_state,
                value=risk_message.dict(),
                headers=[("trace_id", trace_id.encode())],
            )

            self.stats["current_risk_state"] = risk_message.risk_state.value

            # Check processing latency
            elapsed_ms = (time.time() - start_time) * 1000
            processing_time.observe(elapsed_ms / 1000)

            if elapsed_ms > self.config.risk.max_processing_latency_ms:
                logger.warning(
                    f"Processing latency exceeded threshold: {elapsed_ms:.2f}ms > "
                    f"{self.config.risk.max_processing_latency_ms}ms"
                )

            logger.info(
                "Processed risk calculation",
                ltv=calculation.ltv,
                risk_state=calculation.risk_state.value,
                processing_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            **self.stats,
            "is_running": self.is_running,
            "risk_thresholds": {
                "normal": self.config.risk.ltv_normal_threshold,
                "caution": self.config.risk.ltv_caution_threshold,
                "danger": self.config.risk.ltv_danger_threshold,
                "critical": self.config.risk.ltv_critical_threshold,
            },
        }

    async def consume_funding_context(self):
        """Consume funding context messages."""
        logger.info("Starting to consume funding context messages")

        async for message in self.funding_consumer:
            if not self.is_running:
                break

            try:
                # Parse funding context message
                funding_msg = FundingContextMessage(**message.value)
                funding_context = funding_msg.funding_context

                # Store funding context
                self.funding_contexts[funding_context.symbol] = funding_context

                logger.info(
                    f"Updated funding context for {funding_context.symbol}",
                    regime=funding_context.current_regime.value,
                    rate=funding_context.current_rate,
                    multiplier=funding_context.position_multiplier,
                )

            except Exception as e:
                logger.error(f"Failed to process funding context: {e}", exc_info=True)


# Global service instance
service = RiskEngineService()
health_checker = HealthChecker("risk_engine")


# Health check functions
def kafka_consumer_health() -> ComponentHealth:
    """Check Kafka consumer health."""
    if service.consumer is None:
        return ComponentHealth(
            name="kafka_consumer",
            status=HealthStatus.UNHEALTHY,
            message="Consumer not initialized",
        )

    # Check if we've processed messages recently
    if service.stats["last_message_time"]:
        time_since_last = (
            datetime.utcnow() - service.stats["last_message_time"]
        ).total_seconds()
        if time_since_last > 60:  # No messages for 1 minute
            return ComponentHealth(
                name="kafka_consumer",
                status=HealthStatus.DEGRADED,
                message=f"No messages processed for {time_since_last:.0f} seconds",
                metadata={
                    "last_message_time": service.stats["last_message_time"].isoformat()
                },
            )

    return ComponentHealth(
        name="kafka_consumer",
        status=HealthStatus.HEALTHY,
        message="Consumer active",
        metadata={"messages_processed": service.stats["messages_processed"]},
    )


def kafka_producer_health() -> ComponentHealth:
    """Check Kafka producer health."""
    if service.producer is None:
        return ComponentHealth(
            name="kafka_producer",
            status=HealthStatus.UNHEALTHY,
            message="Producer not initialized",
        )

    return ComponentHealth(
        name="kafka_producer", status=HealthStatus.HEALTHY, message="Producer active"
    )


# Register health checks
health_checker.register_check("kafka_consumer", kafka_consumer_health)
health_checker.register_check("kafka_producer", kafka_producer_health)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    asyncio.create_task(service.start())
    yield
    # Shutdown
    await service.stop()


# Create FastAPI app
app = FastAPI(title="HedgeLock Risk Engine Service", version="1.0.0", lifespan=lifespan)

# Add health endpoints
create_health_endpoints(app, health_checker)


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return service.get_stats()


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
