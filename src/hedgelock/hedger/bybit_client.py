"""
Bybit API client for order execution.
"""

import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import httpx

from src.hedgelock.config import settings
from src.hedgelock.hedger.models import OrderRequest, OrderResponse
from src.hedgelock.logging import get_logger

logger = get_logger(__name__)


class BybitClient:
    """Client for Bybit API interactions."""

    def __init__(self):
        self.config = settings.bybit
        self.api_key = self.config.api_key
        self.api_secret = self.config.api_secret
        self.base_url = self.config.rest_url
        self.recv_window = 5000
        self.client = httpx.AsyncClient(timeout=10.0)

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC signature for request."""
        param_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(
            self.api_secret.encode("utf-8"), param_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _get_headers(self) -> Dict[str, str]:
        """Get common headers for requests."""
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(int(time.time() * 1000)),
            "X-BAPI-RECV-WINDOW": str(self.recv_window),
            "Content-Type": "application/json",
        }

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place an order on Bybit."""
        endpoint = "/v5/order/create"
        url = f"{self.base_url}{endpoint}"

        # Prepare request data
        data = order.dict(exclude_none=True)

        # Add timestamp and recv window
        timestamp = str(int(time.time() * 1000))
        data["timestamp"] = timestamp
        data["recv_window"] = self.recv_window

        # Generate signature
        data["sign"] = self._generate_signature(data)

        # Prepare headers
        headers = self._get_headers()

        logger.info(
            "Placing order",
            symbol=order.symbol,
            side=order.side.value,
            qty=order.qty,
            order_type=order.orderType.value,
        )

        try:
            response = await self.client.post(url, json=data, headers=headers)
            response.raise_for_status()

            result = response.json()

            if result.get("retCode") != 0:
                error_msg = f"Order failed: {result.get('retMsg', 'Unknown error')}"
                logger.error(error_msg, response=result)
                raise Exception(error_msg)

            order_data = result["result"]
            order_response = OrderResponse(**order_data)

            logger.info(
                "Order placed successfully",
                order_id=order_response.orderId,
                status=order_response.orderStatus,
                avg_price=order_response.avgPrice,
            )

            return order_response

        except httpx.HTTPError as e:
            logger.error(f"HTTP error placing order: {e}")
            raise
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise

    async def get_order_status(
        self, order_id: str, symbol: str = "BTCUSDT"
    ) -> Optional[OrderResponse]:
        """Get order status from Bybit."""
        endpoint = "/v5/order/realtime"
        url = f"{self.base_url}{endpoint}"

        params = {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id,
            "timestamp": str(int(time.time() * 1000)),
            "recv_window": self.recv_window,
        }

        params["sign"] = self._generate_signature(params)
        headers = self._get_headers()

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()

            result = response.json()

            if result.get("retCode") != 0:
                logger.error(f"Failed to get order status: {result.get('retMsg')}")
                return None

            orders = result.get("result", {}).get("list", [])
            if orders:
                return OrderResponse(**orders[0])

            return None

        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
