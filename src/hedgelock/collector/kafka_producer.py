"""
Kafka producer for publishing account and market data.
"""

import json
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.hedgelock.config import settings
from src.hedgelock.logging import get_logger, trace_context
from .models import AccountUpdate, MarketData, OrderUpdate
from src.hedgelock.shared.funding_models import FundingRateMessage

logger = get_logger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class KafkaMessageProducer:
    """Kafka producer for collector messages."""
    
    def __init__(self):
        self.config = settings.kafka
        self.producer: Optional[AIOKafkaProducer] = None
        self._is_connected = False
        
    async def start(self) -> None:
        """Start the Kafka producer."""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.config.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, cls=DecimalEncoder).encode('utf-8'),
                acks='all',  # Wait for all replicas to acknowledge
                enable_idempotence=True,  # Ensure exactly-once delivery
                max_in_flight_requests_per_connection=5,
                compression_type='gzip',
                request_timeout_ms=self.config.producer_timeout_ms,
                retry_backoff_ms=100,
                metadata_max_age_ms=300000,  # 5 minutes
            )
            
            await self.producer.start()
            self._is_connected = True
            logger.info("Kafka producer started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            self._is_connected = False
            raise
    
    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self.producer:
            try:
                await self.producer.stop()
                self._is_connected = False
                logger.info("Kafka producer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")
    
    async def publish_account_update(self, account_update: AccountUpdate, trace_id: Optional[str] = None) -> bool:
        """Publish account update to Kafka."""
        if not self._is_connected:
            logger.error("Kafka producer not connected")
            return False
        
        with trace_context(trace_id) as tid:
            try:
                # Convert to dict for serialization
                message = account_update.model_dump(mode='json')
                message['trace_id'] = tid
                
                # Send to Kafka
                await self.producer.send_and_wait(
                    self.config.topic_account_raw,
                    value=message,
                    key=account_update.account_id.encode('utf-8')
                )
                
                logger.info(
                    "Published account update",
                    account_id=account_update.account_id,
                    ltv=float(account_update.collateral_info.ltv),
                    collateral_value=float(account_update.collateral_info.collateral_value),
                    topic=self.config.topic_account_raw
                )
                
                return True
                
            except KafkaError as e:
                logger.error(
                    "Kafka error publishing account update",
                    error=str(e),
                    account_id=account_update.account_id
                )
                return False
            except Exception as e:
                logger.error(
                    "Error publishing account update",
                    error=str(e),
                    account_id=account_update.account_id,
                    exc_info=True
                )
                return False
    
    async def publish_market_data(self, market_data: MarketData, trace_id: Optional[str] = None) -> bool:
        """Publish market data to Kafka."""
        if not self._is_connected:
            logger.error("Kafka producer not connected")
            return False
        
        with trace_context(trace_id) as tid:
            try:
                # Convert to dict for serialization
                message = market_data.model_dump(mode='json')
                message['trace_id'] = tid
                
                # Send to Kafka (using a separate topic for market data)
                topic = "market_data"  # Consider adding this to config
                await self.producer.send_and_wait(
                    topic,
                    value=message,
                    key=market_data.symbol.encode('utf-8')
                )
                
                logger.debug(
                    "Published market data",
                    symbol=market_data.symbol,
                    price=float(market_data.price),
                    topic=topic
                )
                
                return True
                
            except KafkaError as e:
                logger.error(
                    "Kafka error publishing market data",
                    error=str(e),
                    symbol=market_data.symbol
                )
                return False
            except Exception as e:
                logger.error(
                    "Error publishing market data",
                    error=str(e),
                    symbol=market_data.symbol,
                    exc_info=True
                )
                return False
    
    async def publish_order_update(self, order_update: OrderUpdate, trace_id: Optional[str] = None) -> bool:
        """Publish order update to Kafka."""
        if not self._is_connected:
            logger.error("Kafka producer not connected")
            return False
        
        with trace_context(trace_id) as tid:
            try:
                # Convert to dict for serialization
                message = order_update.model_dump(mode='json')
                message['trace_id'] = tid
                
                # Send to Kafka (using a separate topic for order updates)
                topic = "order_updates"  # Consider adding this to config
                await self.producer.send_and_wait(
                    topic,
                    value=message,
                    key=order_update.order_id.encode('utf-8')
                )
                
                logger.info(
                    "Published order update",
                    order_id=order_update.order_id,
                    status=order_update.status,
                    symbol=order_update.symbol,
                    topic=topic
                )
                
                return True
                
            except KafkaError as e:
                logger.error(
                    "Kafka error publishing order update",
                    error=str(e),
                    order_id=order_update.order_id
                )
                return False
            except Exception as e:
                logger.error(
                    "Error publishing order update",
                    error=str(e),
                    order_id=order_update.order_id,
                    exc_info=True
                )
                return False
    
    async def publish_funding_rate(self, funding_message: FundingRateMessage, trace_id: Optional[str] = None) -> bool:
        """Publish funding rate to Kafka."""
        if not self._is_connected:
            logger.error("Kafka producer not connected")
            return False
        
        with trace_context(trace_id) as tid:
            try:
                # Convert to dict for serialization
                message = funding_message.model_dump(mode='json')
                message['trace_id'] = tid
                
                # Add headers with trace ID
                headers = [('trace_id', tid.encode('utf-8'))]
                
                # Publish to funding_rates topic
                topic = self.config.topic_funding_rates
                await self.producer.send(
                    topic,
                    value=message,
                    headers=headers,
                    key=funding_message.funding_rate.symbol.encode('utf-8')
                )
                
                logger.info(
                    "Published funding rate",
                    symbol=funding_message.funding_rate.symbol,
                    rate=funding_message.funding_rate.funding_rate,
                    annualized=funding_message.funding_rate.annualized_rate,
                    topic=topic
                )
                
                return True
                
            except KafkaError as e:
                logger.error(
                    "Kafka error publishing funding rate",
                    error=str(e),
                    symbol=funding_message.funding_rate.symbol
                )
                return False
            except Exception as e:
                logger.error(
                    "Error publishing funding rate",
                    error=str(e),
                    symbol=funding_message.funding_rate.symbol,
                    exc_info=True
                )
                return False
    
    async def health_check(self) -> bool:
        """Check if Kafka producer is healthy."""
        if not self._is_connected or not self.producer:
            return False
        
        try:
            # Check if we can get metadata
            metadata = await self.producer._metadata()
            return metadata is not None
        except Exception as e:
            logger.error(f"Kafka health check failed: {e}")
            return False