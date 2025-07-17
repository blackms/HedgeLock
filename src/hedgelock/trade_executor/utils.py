"""
Utility functions for Trade Executor service.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def generate_order_link_id(prefix: str = "HL") -> str:
    """Generate unique order link ID."""
    import uuid

    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def calculate_order_quantity(
    size: float, min_qty: float = 0.001, qty_step: float = 0.001
) -> str:
    """Calculate and format order quantity."""
    # Round to qty_step
    rounded = round(size / qty_step) * qty_step

    # Ensure minimum quantity
    final_qty = max(rounded, min_qty)

    # Format as string with appropriate decimal places
    if qty_step >= 1:
        return str(int(final_qty))
    else:
        decimals = len(str(qty_step).split(".")[-1])
        return f"{final_qty:.{decimals}f}"


def parse_bybit_timestamp(timestamp_str: str) -> datetime:
    """Parse Bybit timestamp string to datetime."""
    try:
        # Bybit timestamps are in milliseconds
        timestamp_ms = int(timestamp_str)
        return datetime.fromtimestamp(timestamp_ms / 1000)
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse timestamp: {timestamp_str}")
        return datetime.utcnow()


def calculate_commission_rate(
    order_type: str, is_maker: bool = False, vip_level: int = 0
) -> float:
    """Calculate commission rate based on order type and VIP level."""
    # Default rates for testnet
    if order_type == "Market":
        return 0.00075  # 0.075% taker fee
    else:  # Limit order
        if is_maker:
            return 0.00025  # 0.025% maker fee
        else:
            return 0.00075  # 0.075% taker fee


def validate_order_parameters(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
) -> None:
    """Validate order parameters."""
    # Validate symbol
    valid_symbols = ["BTCUSDT", "ETHUSDT", "BTCPERP", "ETHPERP"]
    if symbol not in valid_symbols:
        raise ValueError(f"Invalid symbol: {symbol}")

    # Validate side
    if side not in ["Buy", "Sell"]:
        raise ValueError(f"Invalid side: {side}")

    # Validate order type
    if order_type not in ["Market", "Limit"]:
        raise ValueError(f"Invalid order type: {order_type}")

    # Validate quantity
    if quantity <= 0:
        raise ValueError(f"Invalid quantity: {quantity}")

    # Validate price for limit orders
    if order_type == "Limit" and (not price or price <= 0):
        raise ValueError(f"Invalid price for limit order: {price}")


def calculate_position_impact(
    current_position: float, order_side: str, order_quantity: float
) -> Dict[str, float]:
    """Calculate impact of order on position."""
    if order_side == "Buy":
        new_position = current_position + order_quantity
    else:  # Sell
        new_position = current_position - order_quantity

    return {
        "current_position": current_position,
        "order_impact": order_quantity if order_side == "Buy" else -order_quantity,
        "new_position": new_position,
        "position_change_pct": (
            abs(order_quantity / current_position * 100) if current_position != 0 else 0
        ),
    }


def format_execution_summary(execution: Dict[str, Any]) -> str:
    """Format execution details for logging."""
    return (
        f"Order {execution.get('order_link_id')} - "
        f"{execution.get('side')} {execution.get('quantity')} {execution.get('symbol')} "
        f"@ {execution.get('order_type')} - "
        f"Status: {execution.get('status')} - "
        f"Filled: {execution.get('filled_quantity', 0)} @ {execution.get('avg_fill_price', 'N/A')}"
    )


def calculate_slippage(
    expected_price: float, actual_price: float, side: str
) -> Dict[str, float]:
    """Calculate order slippage."""
    if side == "Buy":
        # For buys, positive slippage means we paid more
        slippage_amount = actual_price - expected_price
    else:  # Sell
        # For sells, positive slippage means we received less
        slippage_amount = expected_price - actual_price

    slippage_pct = (slippage_amount / expected_price) * 100

    return {
        "expected_price": expected_price,
        "actual_price": actual_price,
        "slippage_amount": slippage_amount,
        "slippage_pct": slippage_pct,
        "is_positive": slippage_amount > 0,
    }
