"""
Kafka configuration for Funding Engine.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from ..shared.funding_models import FundingContextMessage, FundingRateMessage
from .config import FundingEngineConfig

logger = logging.getLogger(__name__)


class FundingEngineProducer:
    """Producer for funding context messages."""

    def __init__(self, config: FundingEngineConfig):
        self.config = config
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start the Kafka producer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await self.producer.start()
        logger.info("Funding Engine producer started")

    async def stop(self):
        """Stop the Kafka producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("Funding Engine producer stopped")

    async def send_funding_context(self, message: FundingContextMessage):
        """Send funding context message."""
        if not self.producer:
            raise RuntimeError("Producer not started")

        await self.producer.send(
            self.config.funding_context_topic, value=message.dict()
        )
        logger.debug(f"Sent funding context for {message.funding_context.symbol}")


class FundingEngineConsumer:
    """Consumer for funding rate messages."""

    def __init__(self, config: FundingEngineConfig):
        self.config = config
        self.consumer: Optional[AIOKafkaConsumer] = None

    async def start(self):
        """Start the Kafka consumer."""
        logger.info(f"Starting Kafka consumer with bootstrap_servers: {self.config.kafka_bootstrap_servers}")
        self.consumer = AIOKafkaConsumer(
            self.config.funding_rates_topic,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.consumer_group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        logger.info("Funding Engine consumer started")

    async def stop(self):
        """Stop the Kafka consumer."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("Funding Engine consumer stopped")

    async def consume_messages(self):
        """Consume funding rate messages."""
        if not self.consumer:
            raise RuntimeError("Consumer not started")

        async for msg in self.consumer:
            try:
                # Parse the message
                funding_msg = FundingRateMessage(**msg.value)
                yield funding_msg
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                continue
