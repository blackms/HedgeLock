"""
Bybit client for order execution.
"""

import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from src.hedgelock.trade_executor.config import BybitConfig
from src.hedgelock.trade_executor.models import OrderUpdate

logger = logging.getLogger(__name__)


class BybitOrderClient:
    """Client for executing orders on Bybit."""

    def __init__(self, config: BybitConfig):
        self.config = config
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.base_url = config.rest_url

        # Rate limiting
        self.max_orders_per_second = config.max_orders_per_second
        self.last_order_time = 0.0
        self.order_count = 0
        self.rate_limit_window = 1.0  # 1 second window

        # HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC signature for request."""
        # Sort parameters and create query string
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])

        # Generate signature
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        current_time = time.time()

        # Reset counter if window has passed
        if current_time - self.last_order_time > self.rate_limit_window:
            self.order_count = 0
            self.last_order_time = current_time

        # Check if we've hit the limit
        if self.order_count >= self.max_orders_per_second:
            # Calculate sleep time
            sleep_time = self.rate_limit_window - (current_time - self.last_order_time)
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                self.order_count = 0
                self.last_order_time = time.time()

        self.order_count += 1

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        order_link_id: str,
        time_in_force: Optional[str] = None,
        price: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place an order on Bybit."""
        await self._check_rate_limit()

        # Build request parameters
        timestamp = str(int(time.time() * 1000))
        params = {
            "api_key": self.api_key,
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "orderLinkId": order_link_id,
            "timeInForce": time_in_force or self.config.time_in_force,
            "positionIdx": self.config.position_idx,
            "timestamp": timestamp,
            "recv_window": "5000",
        }

        # Add price for limit orders
        if order_type == "Limit" and price:
            params["price"] = price

        # Generate signature
        params["sign"] = self._generate_signature(params)

        try:
            # Send request
            response = await self.client.post("/v5/order/create", json=params)
            response.raise_for_status()

            result = response.json()

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"Order placement failed: {error_msg}")
                raise Exception(f"Bybit API error: {error_msg}")

            logger.info(f"Order placed successfully: {order_link_id}")
            return result.get("result", {})

        except httpx.HTTPError as e:
            logger.error(f"HTTP error placing order: {e}")
            raise
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise

    async def get_order_status(
        self,
        symbol: str,
        order_link_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> Optional[OrderUpdate]:
        """Get order status from Bybit."""
        # Build request parameters
        timestamp = str(int(time.time() * 1000))
        params = {
            "api_key": self.api_key,
            "category": "linear",
            "symbol": symbol,
            "timestamp": timestamp,
            "recv_window": "5000",
        }

        if order_link_id:
            params["orderLinkId"] = order_link_id
        elif order_id:
            params["orderId"] = order_id
        else:
            raise ValueError("Either order_link_id or order_id must be provided")

        # Generate signature
        params["sign"] = self._generate_signature(params)

        try:
            # Send request
            response = await self.client.get("/v5/order/realtime", params=params)
            response.raise_for_status()

            result = response.json()

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"Failed to get order status: {error_msg}")
                return None

            orders = result.get("result", {}).get("list", [])
            if not orders:
                return None

            # Get first order (should only be one)
            order_data = orders[0]

            return OrderUpdate(
                order_id=order_data.get("orderId"),
                order_link_id=order_data.get("orderLinkId"),
                symbol=order_data.get("symbol"),
                side=order_data.get("side"),
                order_type=order_data.get("orderType"),
                order_status=order_data.get("orderStatus"),
                avg_price=float(order_data.get("avgPrice", 0)) or None,
                cum_exec_qty=float(order_data.get("cumExecQty", 0)) or None,
                cum_exec_value=float(order_data.get("cumExecValue", 0)) or None,
                cum_exec_fee=float(order_data.get("cumExecFee", 0)) or None,
                created_time=order_data.get("createdTime"),
                updated_time=order_data.get("updatedTime"),
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting order status: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None

    async def cancel_order(
        self,
        symbol: str,
        order_link_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> bool:
        """Cancel an order on Bybit."""
        # Build request parameters
        timestamp = str(int(time.time() * 1000))
        params = {
            "api_key": self.api_key,
            "category": "linear",
            "symbol": symbol,
            "timestamp": timestamp,
            "recv_window": "5000",
        }

        if order_link_id:
            params["orderLinkId"] = order_link_id
        elif order_id:
            params["orderId"] = order_id
        else:
            raise ValueError("Either order_link_id or order_id must be provided")

        # Generate signature
        params["sign"] = self._generate_signature(params)

        try:
            # Send request
            response = await self.client.post("/v5/order/cancel", json=params)
            response.raise_for_status()

            result = response.json()

            if result.get("retCode") != 0:
                error_msg = result.get("retMsg", "Unknown error")
                logger.error(f"Order cancellation failed: {error_msg}")
                return False

            logger.info(f"Order cancelled successfully: {order_link_id or order_id}")
            return True

        except httpx.HTTPError as e:
            logger.error(f"HTTP error cancelling order: {e}")
            return False
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    async def test_connection(self) -> bool:
        """Test connection to Bybit API."""
        try:
            response = await self.client.get("/v5/market/time")
            response.raise_for_status()

            result = response.json()
            if result.get("retCode") == 0:
                server_time = result.get("result", {}).get("timeSecond")
                logger.info(f"Bybit connection successful. Server time: {server_time}")
                return True
            else:
                logger.error(f"Bybit connection test failed: {result.get('retMsg')}")
                return False

        except Exception as e:
            logger.error(f"Failed to connect to Bybit: {e}")
            return False


# Add missing import
import asyncio
