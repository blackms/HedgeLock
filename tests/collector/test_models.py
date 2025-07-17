"""Tests for collector data models."""

from datetime import datetime
from decimal import Decimal

import pytest

from hedgelock.collector.models import (
    AccountUpdate,
    Balance,
    CollateralInfo,
    LoanInfo,
    MarketData,
    OrderStatus,
    OrderUpdate,
    Position,
    PositionSide,
)


def test_position_model():
    """Test Position model creation."""
    position = Position(
        symbol="BTCUSDT",
        side=PositionSide.BUY,
        size=Decimal("1.5"),
        avg_price=Decimal("45000.00"),
        mark_price=Decimal("45100.00"),
        unrealized_pnl=Decimal("150.00"),
        realized_pnl=Decimal("0.00"),
        cum_realized_pnl=Decimal("0.00"),
        position_value=Decimal("67650.00"),
        leverage=Decimal("10"),
        updated_time=datetime.now(),
    )

    assert position.symbol == "BTCUSDT"
    assert position.side == PositionSide.BUY
    assert position.size == Decimal("1.5")
    assert position.unrealized_pnl == Decimal("150.00")


def test_balance_model():
    """Test Balance model creation."""
    balance = Balance(
        coin="BTC", wallet_balance=Decimal("2.5"), available_balance=Decimal("2.0")
    )

    assert balance.coin == "BTC"
    assert balance.wallet_balance == Decimal("2.5")
    assert balance.available_balance == Decimal("2.0")


def test_collateral_info_model():
    """Test CollateralInfo model creation."""
    collateral_info = CollateralInfo(
        ltv=Decimal("0.65"),
        collateral_value=Decimal("100000.00"),
        borrowed_amount=Decimal("65000.00"),
        collateral_ratio=Decimal("1.54"),
        free_collateral=Decimal("35000.00"),
    )

    assert collateral_info.ltv == Decimal("0.65")
    assert collateral_info.collateral_value == Decimal("100000.00")
    assert collateral_info.borrowed_amount == Decimal("65000.00")


def test_loan_info_model():
    """Test LoanInfo model creation."""
    loan_info = LoanInfo(
        loan_currency="USDT",
        loan_amount=Decimal("50000.00"),
        collateral_currency="BTC",
        collateral_amount=Decimal("1.2"),
        hourly_interest_rate=Decimal("0.0001"),
        loan_term=30,
        loan_order_id="LOAN123456",
    )

    assert loan_info.loan_currency == "USDT"
    assert loan_info.loan_amount == Decimal("50000.00")
    assert loan_info.collateral_currency == "BTC"
    assert loan_info.loan_order_id == "LOAN123456"


def test_account_update_model():
    """Test AccountUpdate model creation."""
    timestamp = datetime.now()

    balances = {
        "BTC": Balance(
            coin="BTC", wallet_balance=Decimal("2.5"), available_balance=Decimal("2.0")
        ),
        "USDT": Balance(
            coin="USDT",
            wallet_balance=Decimal("10000.00"),
            available_balance=Decimal("8000.00"),
        ),
    }

    positions = [
        Position(
            symbol="BTCUSDT",
            side=PositionSide.BUY,
            size=Decimal("1.5"),
            avg_price=Decimal("45000.00"),
            mark_price=Decimal("45100.00"),
            unrealized_pnl=Decimal("150.00"),
            realized_pnl=Decimal("0.00"),
            cum_realized_pnl=Decimal("0.00"),
            position_value=Decimal("67650.00"),
            leverage=Decimal("10"),
            updated_time=timestamp,
        )
    ]

    collateral_info = CollateralInfo(
        ltv=Decimal("0.65"),
        collateral_value=Decimal("100000.00"),
        borrowed_amount=Decimal("65000.00"),
        collateral_ratio=Decimal("1.54"),
        free_collateral=Decimal("35000.00"),
    )

    loan_info = LoanInfo(
        loan_currency="USDT",
        loan_amount=Decimal("50000.00"),
        collateral_currency="BTC",
        collateral_amount=Decimal("1.2"),
        hourly_interest_rate=Decimal("0.0001"),
        loan_term=30,
        loan_order_id="LOAN123456",
    )

    account_update = AccountUpdate(
        timestamp=timestamp,
        account_id="test_account",
        balances=balances,
        positions=positions,
        collateral_info=collateral_info,
        loan_info=loan_info,
    )

    assert account_update.account_id == "test_account"
    assert account_update.timestamp == timestamp
    assert len(account_update.balances) == 2
    assert len(account_update.positions) == 1
    assert account_update.collateral_info.ltv == Decimal("0.65")
    assert account_update.loan_info.loan_currency == "USDT"
    assert account_update.source == "collector"


def test_market_data_model():
    """Test MarketData model creation."""
    timestamp = datetime.now()

    market_data = MarketData(
        timestamp=timestamp,
        symbol="BTCUSDT",
        price=Decimal("45000.00"),
        volume_24h=Decimal("1000000.00"),
        bid=Decimal("44990.00"),
        ask=Decimal("45010.00"),
        open_interest=Decimal("500000.00"),
        funding_rate=Decimal("0.0001"),
    )

    assert market_data.symbol == "BTCUSDT"
    assert market_data.price == Decimal("45000.00")
    assert market_data.bid == Decimal("44990.00")
    assert market_data.ask == Decimal("45010.00")
    assert market_data.source == "collector"


def test_order_update_model():
    """Test OrderUpdate model creation."""
    timestamp = datetime.now()

    order_update = OrderUpdate(
        timestamp=timestamp,
        order_id="ORDER123456",
        symbol="BTCUSDT",
        side=PositionSide.BUY,
        order_type="Limit",
        qty=Decimal("0.5"),
        price=Decimal("45000.00"),
        status=OrderStatus.FILLED,
        avg_price=Decimal("45000.00"),
        cum_exec_qty=Decimal("0.5"),
        cum_exec_value=Decimal("22500.00"),
        cum_exec_fee=Decimal("11.25"),
        time_in_force="GTC",
        created_time=timestamp,
        updated_time=timestamp,
    )

    assert order_update.order_id == "ORDER123456"
    assert order_update.side == PositionSide.BUY
    assert order_update.status == OrderStatus.FILLED
    assert order_update.qty == Decimal("0.5")
    assert order_update.avg_price == Decimal("45000.00")
