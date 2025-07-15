"""Collector service implementation with Bybit integration."""

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

from src.hedgelock.config import settings
from src.hedgelock.logging import get_logger, trace_context
from .websocket_client import BybitWebSocketClient
from .rest_client import BybitRestClient
from .kafka_producer import KafkaMessageProducer
from .models import AccountUpdate, MarketData, OrderUpdate, Position, Balance
from src.hedgelock.shared.funding_models import FundingRate, FundingRateMessage

logger = get_logger(__name__)

app = FastAPI(title="HedgeLock Collector Service", version="0.1.0")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str
    environment: Dict[str, str]
    kafka_connected: bool
    websocket_connected: bool


class ServiceStats(BaseModel):
    """Service statistics model."""
    
    account_updates: int
    market_updates: int
    order_updates: int
    position_updates: int
    last_account_update: Optional[datetime]
    last_market_update: Optional[datetime]
    uptime_seconds: float
    is_running: bool
    testnet_mode: bool


class CollectorService:
    """Collector service implementation with Bybit and Kafka integration."""

    def __init__(self) -> None:
        """Initialize the collector service."""
        self.is_running = False
        self.start_time = datetime.now()
        
        # Initialize clients
        self.ws_client = BybitWebSocketClient(
            on_account_update=self._handle_account_update,
            on_market_data=self._handle_market_data,
            on_order_update=self._handle_order_update,
            on_position_update=self._handle_position_update
        )
        self.rest_client = BybitRestClient()
        self.kafka_producer = KafkaMessageProducer()
        
        # State tracking
        self.current_account_id = "default_account"  # TODO: Get from config
        self.current_balances: Dict[str, Balance] = {}
        self.current_positions: List[Position] = []
        
        # Statistics
        self.stats = {
            "account_updates": 0,
            "market_updates": 0,
            "order_updates": 0,
            "position_updates": 0,
            "last_account_update": None,
            "last_market_update": None,
        }
        
        # Configure WebSocket subscriptions
        self._configure_subscriptions()
        
    def _configure_subscriptions(self) -> None:
        """Configure WebSocket subscriptions."""
        # Public subscriptions
        self.ws_client.add_public_subscription("tickers.BTCUSDT")
        self.ws_client.add_public_subscription("tickers.BTCPERP")
        self.ws_client.add_public_subscription("orderbook.50.BTCUSDT")
        self.ws_client.add_public_subscription("orderbook.50.BTCPERP")
        
        # Private subscriptions
        self.ws_client.add_private_subscription("wallet")
        self.ws_client.add_private_subscription("position")
        self.ws_client.add_private_subscription("order")
        
    async def _handle_account_update(self, balances: Dict[str, Balance]) -> None:
        """Handle account balance updates from WebSocket."""
        self.current_balances = balances
        # Full account update will be sent by the polling task
        
    async def _handle_market_data(self, market_data: MarketData) -> None:
        """Handle market data updates."""
        with trace_context() as trace_id:
            success = await self.kafka_producer.publish_market_data(market_data, trace_id)
            if success:
                self.stats["market_updates"] += 1
                self.stats["last_market_update"] = datetime.now()
                
    async def _handle_order_update(self, order: OrderUpdate) -> None:
        """Handle order updates."""
        with trace_context() as trace_id:
            success = await self.kafka_producer.publish_order_update(order, trace_id)
            if success:
                self.stats["order_updates"] += 1
                
    async def _handle_position_update(self, positions: List[Position]) -> None:
        """Handle position updates."""
        self.current_positions = positions
        self.stats["position_updates"] += 1
        # Trigger account update with new position data
        await self._send_account_update()
        
    async def _poll_account_data(self) -> None:
        """Poll for collateral and loan information."""
        while self.is_running:
            try:
                with trace_context() as trace_id:
                    logger.info("Polling account data")
                    
                    # Get collateral info
                    collateral_info = await self.rest_client.get_collateral_info()
                    if not collateral_info:
                        logger.warning("Failed to get collateral info")
                        await asyncio.sleep(settings.bybit.collateral_poll_interval)
                        continue
                    
                    # Get loan info
                    loan_info = await self.rest_client.get_loan_info()
                    
                    # Get current balances if not available from WebSocket
                    if not self.current_balances:
                        self.current_balances = await self.rest_client.get_wallet_balance()
                    
                    # Create account update
                    account_update = AccountUpdate(
                        timestamp=datetime.now(),
                        account_id=self.current_account_id,
                        balances=self.current_balances,
                        positions=self.current_positions,
                        collateral_info=collateral_info,
                        loan_info=loan_info
                    )
                    
                    # Publish to Kafka
                    success = await self.kafka_producer.publish_account_update(account_update, trace_id)
                    if success:
                        self.stats["account_updates"] += 1
                        self.stats["last_account_update"] = datetime.now()
                        
                        logger.info(
                            "Account update published",
                            ltv=float(collateral_info.ltv),
                            collateral_value=float(collateral_info.collateral_value),
                            borrowed_amount=float(collateral_info.borrowed_amount),
                            positions=len(self.current_positions)
                        )
                    
            except Exception as e:
                logger.error(f"Error polling account data: {e}", exc_info=True)
                
            await asyncio.sleep(settings.bybit.collateral_poll_interval)
            
    async def _send_account_update(self) -> None:
        """Send account update with current state."""
        try:
            # Get latest collateral info
            collateral_info = await self.rest_client.get_collateral_info()
            if not collateral_info:
                return
                
            # Get loan info
            loan_info = await self.rest_client.get_loan_info()
            
            # Create account update
            account_update = AccountUpdate(
                timestamp=datetime.now(),
                account_id=self.current_account_id,
                balances=self.current_balances,
                positions=self.current_positions,
                collateral_info=collateral_info,
                loan_info=loan_info
            )
            
            # Publish to Kafka
            with trace_context() as trace_id:
                success = await self.kafka_producer.publish_account_update(account_update, trace_id)
                if success:
                    self.stats["account_updates"] += 1
                    self.stats["last_account_update"] = datetime.now()
                    
        except Exception as e:
            logger.error(f"Error sending account update: {e}", exc_info=True)

    async def _poll_funding_rates(self) -> None:
        """Poll for funding rate information."""
        # Initial delay to stagger polling
        await asyncio.sleep(30)
        
        while self.is_running:
            try:
                with trace_context() as trace_id:
                    logger.info("Polling funding rates")
                    
                    # Get current funding rate
                    current_funding = await self.rest_client.get_current_funding_rate()
                    if current_funding:
                        # Convert to FundingRate model
                        funding_rate = FundingRate(
                            symbol=current_funding["symbol"],
                            funding_rate=current_funding["fundingRate"],
                            funding_time=datetime.fromtimestamp(
                                int(current_funding["nextFundingTime"]) / 1000
                            ),
                            mark_price=current_funding["markPrice"],
                            index_price=current_funding["indexPrice"]
                        )
                        
                        # Create message
                        message = FundingRateMessage(
                            funding_rate=funding_rate,
                            trace_id=trace_id
                        )
                        
                        # Publish to Kafka
                        success = await self.kafka_producer.publish_funding_rate(message, trace_id)
                        if success:
                            logger.info(
                                f"Published funding rate: {funding_rate.symbol} "
                                f"rate={funding_rate.funding_rate:.4%} "
                                f"annualized={funding_rate.annualized_rate:.2f}%"
                            )
                    else:
                        logger.warning("Failed to get current funding rate")
                        
            except Exception as e:
                logger.error(f"Error polling funding rates: {e}", exc_info=True)
                
            # Poll every hour (funding updates every 8 hours)
            await asyncio.sleep(3600)

    async def start(self) -> None:
        """Start the collector service."""
        logger.info("Starting Collector service...")
        logger.info(f"Bybit testnet mode: {settings.bybit.testnet}")
        logger.info(f"Kafka bootstrap servers: {settings.kafka.bootstrap_servers}")
        
        self.is_running = True
        self.start_time = datetime.now()
        
        try:
            # Start Kafka producer
            await self.kafka_producer.start()
            
            # Create tasks
            tasks = [
                asyncio.create_task(self.ws_client.start()),
                asyncio.create_task(self._poll_account_data()),
                asyncio.create_task(self._poll_funding_rates())
            ]
            
            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Error in collector service: {e}", exc_info=True)
            await self.stop()

    async def stop(self) -> None:
        """Stop the collector service."""
        logger.info("Stopping Collector service...")
        self.is_running = False
        
        # Stop components
        await self.ws_client.stop()
        await self.rest_client.close()
        await self.kafka_producer.stop()

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return ServiceStats(
            account_updates=self.stats["account_updates"],
            market_updates=self.stats["market_updates"],
            order_updates=self.stats["order_updates"],
            position_updates=self.stats["position_updates"],
            last_account_update=self.stats["last_account_update"],
            last_market_update=self.stats["last_market_update"],
            uptime_seconds=uptime,
            is_running=self.is_running,
            testnet_mode=settings.bybit.testnet
        ).model_dump()
        
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        kafka_healthy = await self.kafka_producer.health_check()
        ws_connected = (
            self.ws_client.public_ws is not None and 
            not self.ws_client.public_ws.closed
        )
        
        return {
            "kafka_connected": kafka_healthy,
            "websocket_connected": ws_connected,
            "is_running": self.is_running
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
    health_info = await service.health_check()
    
    status = "healthy"
    if not health_info["kafka_connected"]:
        status = "degraded"
    if not health_info["is_running"]:
        status = "unhealthy"
    
    return HealthResponse(
        status=status,
        service="hedgelock-collector",
        version="0.1.0",
        environment={
            "bybit_testnet": str(settings.bybit.testnet),
            "log_level": settings.monitoring.log_level,
            "kafka_bootstrap": settings.kafka.bootstrap_servers,
            "bybit_rest_url": settings.bybit.rest_url,
        },
        kafka_connected=health_info["kafka_connected"],
        websocket_connected=health_info["websocket_connected"]
    )


@app.get("/stats", response_model=ServiceStats)
async def get_stats() -> ServiceStats:
    """Get service statistics."""
    return ServiceStats(**service.get_stats())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
