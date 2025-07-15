"""
Kafka configuration for Trade Executor service.
"""

import json
import logging
from typing import Optional, Dict, Any
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.hedgelock.trade_executor.config import Config

logger = logging.getLogger(__name__)


class KafkaManager:
    """Manages Kafka consumer and producer connections."""
    
    def __init__(self, config: Config):
        self.config = config
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self._consumer_task = None
        
    async def start(self) -> None:
        """Start Kafka connections."""
        await self._start_producer()
        await self._start_consumer()
        
    async def stop(self) -> None:
        """Stop Kafka connections."""
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
            
        if self.producer:
            await self.producer.stop()
            self.producer = None
            
    async def _start_producer(self) -> None:
        """Start Kafka producer."""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.config.kafka.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                compression_type='gzip',
                acks='all',
                retries=3,
                max_in_flight_requests_per_connection=5
            )
            await self.producer.start()
            logger.info("Kafka producer started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise
            
    async def _start_consumer(self) -> None:
        """Start Kafka consumer."""
        try:
            self.consumer = AIOKafkaConsumer(
                self.config.kafka.topic_hedge_trades,
                bootstrap_servers=self.config.kafka.bootstrap_servers,
                group_id=self.config.kafka.consumer_group,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=False,
                max_poll_records=self.config.kafka.max_poll_records,
                session_timeout_ms=self.config.kafka.session_timeout_ms,
                heartbeat_interval_ms=self.config.kafka.heartbeat_interval_ms
            )
            await self.consumer.start()
            logger.info(
                f"Kafka consumer started for topic: {self.config.kafka.topic_hedge_trades}"
            )
            
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise
            
    async def consume_message(self) -> Optional[Dict[str, Any]]:
        """Consume a single message from Kafka."""
        try:
            # This will return immediately if no messages
            records = await self.consumer.getmany(timeout_ms=1000)
            
            for topic_partition, messages in records.items():
                for message in messages:
                    # Extract trace_id from headers
                    trace_id = None
                    if message.headers:
                        for key, value in message.headers:
                            if key == 'trace_id':
                                trace_id = value.decode('utf-8')
                                break
                    
                    return {
                        'value': message.value,
                        'trace_id': trace_id,
                        'partition': message.partition,
                        'offset': message.offset,
                        'timestamp': message.timestamp
                    }
                    
            return None
            
        except KafkaError as e:
            logger.error(f"Kafka consume error: {e}")
            raise
            
    async def commit_offset(self) -> None:
        """Commit current consumer offset."""
        try:
            await self.consumer.commit()
            
        except KafkaError as e:
            logger.error(f"Failed to commit offset: {e}")
            raise
            
    async def publish_confirmation(
        self,
        confirmation: Dict[str, Any],
        trace_id: Optional[str] = None
    ) -> None:
        """Publish trade confirmation to Kafka."""
        try:
            headers = []
            if trace_id:
                headers.append(('trace_id', trace_id.encode('utf-8')))
                
            await self.producer.send(
                self.config.kafka.topic_trade_confirmations,
                value=confirmation,
                headers=headers
            )
            
        except KafkaError as e:
            logger.error(f"Failed to publish confirmation: {e}")
            raise
            
    def is_connected(self) -> bool:
        """Check if Kafka connections are active."""
        consumer_connected = (
            self.consumer is not None and 
            not self.consumer._closed
        )
        producer_connected = (
            self.producer is not None and 
            self.producer._sender.sender_task is not None
        )
        return consumer_connected and producer_connected