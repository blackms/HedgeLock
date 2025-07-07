"""
Hedger service - Consumes risk_state and executes hedge trades.
"""

import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi.responses import PlainTextResponse

from src.hedgelock.config import settings
from src.hedgelock.logging import get_logger, trace_context
from src.hedgelock.health import HealthChecker, create_health_endpoints, ComponentHealth, HealthStatus
from src.hedgelock.risk_engine.models import RiskState, RiskStateMessage
from src.hedgelock.hedger.models import (
    HedgeDecision, OrderSide, OrderType, OrderRequest, 
    OrderResponse, HedgeTradeMessage
)
from src.hedgelock.hedger.bybit_client import BybitClient

logger = get_logger(__name__)

# Prometheus metrics
messages_processed = Counter('hedger_messages_processed_total', 'Total messages processed')
messages_failed = Counter('hedger_messages_failed_total', 'Total messages failed')
orders_placed = Counter('hedger_orders_placed_total', 'Total orders placed', ['side', 'status'])
processing_time = Histogram('hedger_processing_seconds', 'Processing time in seconds')
current_position = Gauge('hedger_current_position_btc', 'Current position in BTC')


class HedgerService:
    """Hedger service implementation."""
    
    def __init__(self):
        self.config = settings
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.bybit_client = BybitClient()
        self.is_running = False
        self.current_position = 0.0
        self.orders: List[HedgeTradeMessage] = []
        self.stats = {
            "messages_processed": 0,
            "messages_failed": 0,
            "orders_placed": 0,
            "orders_failed": 0,
            "last_message_time": None,
            "current_risk_state": None
        }
    
    async def start(self):
        """Start the hedger service."""
        logger.info("Starting Hedger service...")
        
        # Initialize Kafka consumer
        self.consumer = AIOKafkaConsumer(
            self.config.kafka.topic_risk_state,
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            group_id=f"{self.config.kafka.consumer_group_prefix}_hedger",
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            enable_auto_commit=self.config.kafka.enable_auto_commit,
            max_poll_records=self.config.kafka.max_poll_records
        )
        
        # Initialize Kafka producer
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await self.consumer.start()
            await self.producer.start()
            logger.info("Kafka consumer and producer started successfully")
            self.is_running = True
            
            # Start consuming messages
            await self.consume_messages()
            
        except Exception as e:
            logger.error(f"Failed to start Hedger: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the hedger service."""
        logger.info("Stopping Hedger service...")
        self.is_running = False
        
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        await self.bybit_client.close()
        
        logger.info("Hedger stopped")
    
    async def consume_messages(self):
        """Consume messages from risk_state topic."""
        logger.info(f"Starting to consume from {self.config.kafka.topic_risk_state}")
        
        async for message in self.consumer:
            if not self.is_running:
                break
            
            trace_id = message.headers.get('trace_id', str(message.offset))
            
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
        """Process a single risk_state message."""
        start_time = time.time()
        
        try:
            # Parse risk state message
            risk_message = RiskStateMessage(**message)
            self.stats["current_risk_state"] = risk_message.risk_state.value
            
            # Check if we need to hedge
            if risk_message.hedge_recommendation:
                decision = self._create_hedge_decision(risk_message)
                
                if decision:
                    # Execute hedge trade
                    await self.execute_hedge(decision, risk_message, trace_id)
            else:
                logger.info(
                    "No hedge action required",
                    risk_state=risk_message.risk_state.value,
                    ltv=risk_message.ltv,
                    net_delta=risk_message.net_delta
                )
            
            # Track processing time
            elapsed_ms = (time.time() - start_time) * 1000
            processing_time.observe(elapsed_ms / 1000)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            raise
    
    def _create_hedge_decision(self, risk_message: RiskStateMessage) -> Optional[HedgeDecision]:
        """Create hedge decision based on risk state."""
        recommendation = risk_message.hedge_recommendation
        
        # Validate hedge size
        hedge_size = abs(recommendation["quantity"])
        
        if hedge_size < self.config.hedger.min_order_size_btc:
            logger.info(
                f"Hedge size too small: {hedge_size} < {self.config.hedger.min_order_size_btc}"
            )
            return None
        
        if hedge_size > self.config.hedger.max_position_size_btc:
            logger.warning(
                f"Hedge size exceeds limit: {hedge_size} > {self.config.hedger.max_position_size_btc}"
            )
            hedge_size = self.config.hedger.max_position_size_btc
        
        # Determine order side
        side = OrderSide.BUY if recommendation["action"] == "BUY" else OrderSide.SELL
        
        return HedgeDecision(
            risk_state=risk_message.risk_state.value,
            current_delta=risk_message.net_delta,
            target_delta=recommendation["quantity"] + risk_message.net_delta,
            hedge_size=hedge_size,
            side=side,
            reason=recommendation["reason"],
            urgency=recommendation["urgency"],
            trace_id=risk_message.trace_id
        )
    
    async def execute_hedge(self, decision: HedgeDecision, risk_message: RiskStateMessage, trace_id: str):
        """Execute hedge trade on Bybit."""
        execution_start = time.time()
        
        # Create order request
        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=decision.side,
            orderType=OrderType.MARKET,
            qty=str(decision.hedge_size),
            timeInForce=self.config.hedger.time_in_force,
            orderLinkId=f"HL-{uuid.uuid4().hex[:8]}"
        )
        
        # Create hedge trade message
        hedge_trade = HedgeTradeMessage(
            hedge_decision=decision,
            order_request=order_request,
            risk_state=risk_message.risk_state.value,
            ltv=risk_message.ltv,
            risk_score=risk_message.risk_score,
            trace_id=trace_id,
            testnet=self.config.bybit.testnet
        )
        
        try:
            # Place order on Bybit
            logger.info(
                f"Placing hedge order",
                side=decision.side.value,
                size=decision.hedge_size,
                reason=decision.reason
            )
            
            if self.config.bybit.api_key and self.config.bybit.api_secret:
                # Real order execution
                order_response = await self.bybit_client.place_order(order_request)
                hedge_trade.order_response = order_response
                hedge_trade.executed = True
                
                # Update position tracking
                if decision.side == OrderSide.BUY:
                    self.current_position += decision.hedge_size
                else:
                    self.current_position -= decision.hedge_size
                
                current_position.set(self.current_position)
                
                orders_placed.labels(
                    side=decision.side.value,
                    status=order_response.orderStatus
                ).inc()
                
                self.stats["orders_placed"] += 1
                
                logger.info(
                    f"Hedge order executed",
                    order_id=order_response.orderId,
                    status=order_response.orderStatus,
                    avg_price=order_response.avgPrice
                )
            else:
                # Testnet mode without credentials
                logger.warning("No API credentials configured, simulating order execution")
                hedge_trade.executed = False
                hedge_trade.error = "Testnet mode - no API credentials"
            
        except Exception as e:
            logger.error(f"Failed to execute hedge order: {e}")
            hedge_trade.executed = False
            hedge_trade.error = str(e)
            orders_placed.labels(side=decision.side.value, status="FAILED").inc()
            self.stats["orders_failed"] += 1
        
        # Set execution time
        hedge_trade.execution_time_ms = (time.time() - execution_start) * 1000
        
        # Store order
        self.orders.append(hedge_trade)
        if len(self.orders) > 100:
            self.orders = self.orders[-100:]  # Keep last 100 orders
        
        # Publish to hedge_trades topic
        await self.producer.send(
            self.config.kafka.topic_hedge_trades,
            value=hedge_trade.dict(),
            headers=[('trace_id', trace_id.encode())]
        )
        
        logger.info(
            "Hedge trade message published",
            executed=hedge_trade.executed,
            execution_time_ms=hedge_trade.execution_time_ms
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            **self.stats,
            "is_running": self.is_running,
            "current_position_btc": self.current_position,
            "recent_orders": len(self.orders),
            "testnet_mode": self.config.bybit.testnet
        }


# Global service instance
service = HedgerService()
health_checker = HealthChecker("hedger")


# Health check functions
def kafka_consumer_health() -> ComponentHealth:
    """Check Kafka consumer health."""
    if service.consumer is None:
        return ComponentHealth(
            name="kafka_consumer",
            status=HealthStatus.UNHEALTHY,
            message="Consumer not initialized"
        )
    
    # Check if we've processed messages recently
    if service.stats["last_message_time"]:
        time_since_last = (datetime.utcnow() - service.stats["last_message_time"]).total_seconds()
        if time_since_last > 120:  # No messages for 2 minutes
            return ComponentHealth(
                name="kafka_consumer",
                status=HealthStatus.DEGRADED,
                message=f"No messages processed for {time_since_last:.0f} seconds",
                metadata={"last_message_time": service.stats["last_message_time"].isoformat()}
            )
    
    return ComponentHealth(
        name="kafka_consumer",
        status=HealthStatus.HEALTHY,
        message="Consumer active",
        metadata={"messages_processed": service.stats["messages_processed"]}
    )


def bybit_connection_health() -> ComponentHealth:
    """Check Bybit connection health."""
    if not service.config.bybit.api_key:
        return ComponentHealth(
            name="bybit_connection",
            status=HealthStatus.DEGRADED,
            message="No API credentials configured (testnet mode)",
            metadata={"testnet": True}
        )
    
    return ComponentHealth(
        name="bybit_connection",
        status=HealthStatus.HEALTHY,
        message="Bybit connection configured",
        metadata={"testnet": service.config.bybit.testnet}
    )


# Register health checks
health_checker.register_check("kafka_consumer", kafka_consumer_health)
health_checker.register_check("bybit_connection", bybit_connection_health)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    asyncio.create_task(service.start())
    yield
    # Shutdown
    await service.stop()


# Create FastAPI app
app = FastAPI(
    title="HedgeLock Hedger Service",
    version="0.9.0",
    lifespan=lifespan
)

# Add health endpoints
create_health_endpoints(app, health_checker)


@app.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get service statistics."""
    return service.get_stats()


@app.get("/orders")
async def get_orders(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent orders."""
    return [order.dict() for order in service.orders[-limit:]]


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)