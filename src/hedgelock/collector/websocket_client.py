"""
Bybit WebSocket client for real-time data streaming.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import websockets
from websockets.client import WebSocketClientProtocol

from src.hedgelock.config import settings
from src.hedgelock.logging import get_logger

from .models import (
    Balance,
    MarketData,
    OrderStatus,
    OrderUpdate,
    Position,
    PositionSide,
)

logger = get_logger(__name__)


class BybitWebSocketClient:
    """WebSocket client for Bybit data streaming."""

    def __init__(
        self,
        on_account_update: Optional[Callable] = None,
        on_market_data: Optional[Callable] = None,
        on_order_update: Optional[Callable] = None,
        on_position_update: Optional[Callable] = None,
    ):
        self.config = settings.bybit
        self.api_key = self.config.api_key
        self.api_secret = self.config.api_secret

        # Callbacks
        self.on_account_update = on_account_update
        self.on_market_data = on_market_data
        self.on_order_update = on_order_update
        self.on_position_update = on_position_update

        # WebSocket connections
        self.public_ws: Optional[WebSocketClientProtocol] = None
        self.private_ws: Optional[WebSocketClientProtocol] = None

        # Connection state
        self.is_running = False
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        self.ping_interval = self.config.ws_ping_interval

        # Subscriptions
        self.public_subscriptions = []
        self.private_subscriptions = []

    def _generate_signature(self) -> tuple[str, str]:
        """Generate authentication signature."""
        expires = str(int((time.time() + 10) * 1000))
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            f"GET/realtime{expires}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return expires, signature

    async def _authenticate(self, ws: WebSocketClientProtocol) -> bool:
        """Authenticate WebSocket connection."""
        expires, signature = self._generate_signature()
        auth_msg = {"op": "auth", "args": [self.api_key, expires, signature]}

        await ws.send(json.dumps(auth_msg))

        # Wait for auth response
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(response)

            if data.get("success") or (
                data.get("op") == "auth" and data.get("ret_msg") == "OK"
            ):
                logger.info("WebSocket authentication successful")
                return True
            else:
                logger.error(f"WebSocket authentication failed: {data}")
                return False

        except asyncio.TimeoutError:
            logger.error("WebSocket authentication timeout")
            return False

    async def _subscribe(self, ws: WebSocketClientProtocol, topics: List[str]) -> None:
        """Subscribe to WebSocket topics."""
        if not topics:
            return

        sub_msg = {"op": "subscribe", "args": topics}

        await ws.send(json.dumps(sub_msg))
        logger.info(f"Subscribed to topics: {topics}")

    async def _handle_public_message(self, data: Dict[str, Any]) -> None:
        """Handle public WebSocket messages."""
        topic = data.get("topic", "")

        if topic.startswith("orderbook") or topic.startswith("trade"):
            # Handle market data
            if self.on_market_data and "data" in data:
                for item in data["data"]:
                    market_data = MarketData(
                        timestamp=datetime.fromtimestamp(item.get("ts", 0) / 1000),
                        symbol=item.get("s", topic.split(".")[-1]),
                        price=Decimal(str(item.get("p", 0))),
                        volume_24h=Decimal(str(item.get("v", 0))),
                        bid=Decimal(
                            str(
                                item.get("b", [0])[0]
                                if isinstance(item.get("b"), list)
                                else item.get("b", 0)
                            )
                        ),
                        ask=Decimal(
                            str(
                                item.get("a", [0])[0]
                                if isinstance(item.get("a"), list)
                                else item.get("a", 0)
                            )
                        ),
                    )
                    await self.on_market_data(market_data)

        elif topic.startswith("tickers"):
            # Handle ticker data
            if self.on_market_data and "data" in data:
                item = data["data"]
                market_data = MarketData(
                    timestamp=datetime.now(),
                    symbol=item.get("symbol"),
                    price=Decimal(str(item.get("lastPrice", 0))),
                    volume_24h=Decimal(str(item.get("volume24h", 0))),
                    bid=Decimal(str(item.get("bid1Price", 0))),
                    ask=Decimal(str(item.get("ask1Price", 0))),
                    open_interest=(
                        Decimal(str(item.get("openInterest", 0)))
                        if item.get("openInterest")
                        else None
                    ),
                    funding_rate=(
                        Decimal(str(item.get("fundingRate", 0)))
                        if item.get("fundingRate")
                        else None
                    ),
                )
                await self.on_market_data(market_data)

    async def _handle_private_message(self, data: Dict[str, Any]) -> None:
        """Handle private WebSocket messages."""
        topic = data.get("topic", "")

        if topic == "wallet":
            # Handle wallet/balance updates
            if self.on_account_update and "data" in data:
                for wallet_data in data["data"]:
                    balances = {}
                    for coin_data in wallet_data.get("coin", []):
                        coin = coin_data.get("coin")
                        balances[coin] = Balance(
                            coin=coin,
                            wallet_balance=Decimal(
                                str(coin_data.get("walletBalance", 0))
                            ),
                            available_balance=Decimal(
                                str(coin_data.get("availableToWithdraw", 0))
                            ),
                        )

                    # Trigger account update callback
                    await self.on_account_update(balances)

        elif topic == "position":
            # Handle position updates
            if self.on_position_update and "data" in data:
                positions = []
                for pos_data in data["data"]:
                    position = Position(
                        symbol=pos_data.get("symbol"),
                        side=PositionSide(pos_data.get("side")),
                        size=Decimal(str(pos_data.get("size", 0))),
                        avg_price=Decimal(str(pos_data.get("avgPrice", 0))),
                        mark_price=Decimal(str(pos_data.get("markPrice", 0))),
                        unrealized_pnl=Decimal(str(pos_data.get("unrealisedPnl", 0))),
                        realized_pnl=Decimal(str(pos_data.get("realisedPnl", 0))),
                        cum_realized_pnl=Decimal(
                            str(pos_data.get("cumRealisedPnl", 0))
                        ),
                        position_value=Decimal(str(pos_data.get("positionValue", 0))),
                        leverage=Decimal(str(pos_data.get("leverage", 1))),
                        updated_time=datetime.fromtimestamp(
                            int(pos_data.get("updatedTime", 0)) / 1000
                        ),
                    )
                    positions.append(position)

                await self.on_position_update(positions)

        elif topic == "order":
            # Handle order updates
            if self.on_order_update and "data" in data:
                for order_data in data["data"]:
                    order = OrderUpdate(
                        timestamp=datetime.now(),
                        order_id=order_data.get("orderId"),
                        symbol=order_data.get("symbol"),
                        side=PositionSide(order_data.get("side")),
                        order_type=order_data.get("orderType"),
                        qty=Decimal(str(order_data.get("qty", 0))),
                        price=(
                            Decimal(str(order_data.get("price", 0)))
                            if order_data.get("price")
                            else None
                        ),
                        status=OrderStatus(order_data.get("orderStatus")),
                        avg_price=(
                            Decimal(str(order_data.get("avgPrice", 0)))
                            if order_data.get("avgPrice")
                            else None
                        ),
                        cum_exec_qty=Decimal(str(order_data.get("cumExecQty", 0))),
                        cum_exec_value=Decimal(str(order_data.get("cumExecValue", 0))),
                        cum_exec_fee=Decimal(str(order_data.get("cumExecFee", 0))),
                        time_in_force=order_data.get("timeInForce"),
                        created_time=datetime.fromtimestamp(
                            int(order_data.get("createdTime", 0)) / 1000
                        ),
                        updated_time=datetime.fromtimestamp(
                            int(order_data.get("updatedTime", 0)) / 1000
                        ),
                    )
                    await self.on_order_update(order)

    async def _handle_message(
        self, ws: WebSocketClientProtocol, is_private: bool
    ) -> None:
        """Handle WebSocket messages."""
        try:
            async for message in ws:
                try:
                    data = json.loads(message)

                    # Handle ping/pong
                    if data.get("op") == "ping":
                        await ws.send(json.dumps({"op": "pong"}))
                        continue

                    # Handle subscription response
                    if data.get("op") == "subscribe":
                        if data.get("success"):
                            logger.info(
                                f"Successfully subscribed to: {data.get('ret_msg')}"
                            )
                        else:
                            logger.error(f"Subscription failed: {data.get('ret_msg')}")
                        continue

                    # Route message to appropriate handler
                    if is_private:
                        await self._handle_private_message(data)
                    else:
                        await self._handle_public_message(data)

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode message: {message}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)

    async def _connect_public(self) -> None:
        """Connect to public WebSocket."""
        while self.is_running:
            try:
                logger.info(
                    f"Connecting to public WebSocket: {self.config.ws_public_url}"
                )

                async with websockets.connect(self.config.ws_public_url) as ws:
                    self.public_ws = ws
                    self.reconnect_delay = 1

                    # Subscribe to public topics
                    await self._subscribe(ws, self.public_subscriptions)

                    # Handle messages
                    await self._handle_message(ws, is_private=False)

            except Exception as e:
                logger.error(f"Public WebSocket error: {e}")

            if self.is_running:
                logger.info(
                    f"Reconnecting public WebSocket in {self.reconnect_delay} seconds..."
                )
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, self.max_reconnect_delay
                )

    async def _connect_private(self) -> None:
        """Connect to private WebSocket."""
        if not self.api_key or not self.api_secret:
            logger.warning("API credentials not configured, skipping private WebSocket")
            return

        while self.is_running:
            try:
                logger.info(
                    f"Connecting to private WebSocket: {self.config.ws_private_url}"
                )

                async with websockets.connect(self.config.ws_private_url) as ws:
                    self.private_ws = ws

                    # Authenticate
                    if not await self._authenticate(ws):
                        logger.error("Private WebSocket authentication failed")
                        await asyncio.sleep(5)
                        continue

                    self.reconnect_delay = 1

                    # Subscribe to private topics
                    await self._subscribe(ws, self.private_subscriptions)

                    # Handle messages
                    await self._handle_message(ws, is_private=True)

            except Exception as e:
                logger.error(f"Private WebSocket error: {e}")

            if self.is_running:
                logger.info(
                    f"Reconnecting private WebSocket in {self.reconnect_delay} seconds..."
                )
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, self.max_reconnect_delay
                )

    async def _ping_loop(self) -> None:
        """Send periodic ping messages."""
        while self.is_running:
            await asyncio.sleep(self.ping_interval)

            # Ping public WebSocket
            if self.public_ws and not self.public_ws.closed:
                try:
                    await self.public_ws.send(json.dumps({"op": "ping"}))
                except Exception as e:
                    logger.error(f"Failed to ping public WebSocket: {e}")

            # Ping private WebSocket
            if self.private_ws and not self.private_ws.closed:
                try:
                    await self.private_ws.send(json.dumps({"op": "ping"}))
                except Exception as e:
                    logger.error(f"Failed to ping private WebSocket: {e}")

    def add_public_subscription(self, topic: str) -> None:
        """Add a public topic subscription."""
        if topic not in self.public_subscriptions:
            self.public_subscriptions.append(topic)
            logger.info(f"Added public subscription: {topic}")

    def add_private_subscription(self, topic: str) -> None:
        """Add a private topic subscription."""
        if topic not in self.private_subscriptions:
            self.private_subscriptions.append(topic)
            logger.info(f"Added private subscription: {topic}")

    async def start(self) -> None:
        """Start WebSocket connections."""
        logger.info("Starting Bybit WebSocket client...")
        self.is_running = True

        # Create connection tasks
        tasks = [
            asyncio.create_task(self._connect_public()),
            asyncio.create_task(self._connect_private()),
            asyncio.create_task(self._ping_loop()),
        ]

        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Stop WebSocket connections."""
        logger.info("Stopping Bybit WebSocket client...")
        self.is_running = False

        # Close connections
        if self.public_ws and not self.public_ws.closed:
            await self.public_ws.close()

        if self.private_ws and not self.private_ws.closed:
            await self.private_ws.close()
