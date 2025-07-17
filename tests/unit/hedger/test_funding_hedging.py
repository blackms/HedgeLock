"""
Unit tests for funding-aware hedging in Hedger service.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.hedgelock.hedger.main import HedgerService
from src.hedgelock.hedger.models import HedgeDecision, OrderSide
from src.hedgelock.risk_engine.models import RiskState, RiskStateMessage
from src.hedgelock.shared.funding_models import FundingContext, FundingRegime


class TestFundingAwareHedging:
    """Test funding-aware hedging functionality."""

    @pytest.fixture
    def hedger_service(self):
        """Create hedger service instance."""
        with patch("src.hedgelock.hedger.main.BybitClient"):
            service = HedgerService()
            # Mock config values
            service.config.hedger.min_order_size_btc = 0.001
            service.config.hedger.max_position_size_btc = 10.0
            return service

    @pytest.fixture
    def base_risk_message(self):
        """Create base risk state message."""
        return RiskStateMessage(
            risk_state=RiskState.NORMAL,
            previous_state=None,
            state_changed=False,
            ltv=0.4,
            net_delta=1.5,
            risk_score=40.0,
            hedge_recommendation={
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 0.5,
                "reason": "Reduce delta exposure",
                "urgency": "MEDIUM",
            },
            total_collateral_value=100000.0,
            total_loan_value=40000.0,
            available_collateral=50000.0,
            trace_id="test-123",
        )

    def test_hedge_decision_without_funding(self, hedger_service, base_risk_message):
        """Test hedge decision when no funding context."""
        decision = hedger_service._create_hedge_decision(base_risk_message)

        assert decision is not None
        assert decision.hedge_size == 0.5  # No adjustment
        assert decision.position_multiplier == 1.0
        assert decision.funding_adjusted is False
        assert decision.funding_regime is None

    def test_hedge_decision_with_normal_funding(
        self, hedger_service, base_risk_message
    ):
        """Test hedge decision with normal funding."""
        # Add funding context
        base_risk_message.funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=22.0,
            avg_rate_7d=20.0,
            max_rate_24h=30.0,
            volatility_24h=5.0,
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=6.85,
            weekly_cost_pct=0.48,
        )
        base_risk_message.funding_regime = FundingRegime.NORMAL
        base_risk_message.position_multiplier = 0.75

        decision = hedger_service._create_hedge_decision(base_risk_message)

        assert decision is not None
        assert decision.hedge_size == 0.375  # 0.5 * 0.75
        assert decision.position_multiplier == 0.75
        assert decision.funding_adjusted is True
        assert decision.funding_regime == FundingRegime.NORMAL

    def test_hedge_decision_with_extreme_funding(
        self, hedger_service, base_risk_message
    ):
        """Test emergency exit with extreme funding."""
        # Add extreme funding context
        base_risk_message.funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=350.0,
            avg_rate_24h=300.0,
            avg_rate_7d=250.0,
            max_rate_24h=400.0,
            volatility_24h=50.0,
            position_multiplier=0.0,
            should_exit=True,
            regime_change=True,
            daily_cost_bps=95.9,
            weekly_cost_pct=6.71,
        )
        base_risk_message.funding_regime = FundingRegime.EXTREME
        base_risk_message.position_multiplier = 0.0

        decision = hedger_service._create_hedge_decision(base_risk_message)

        assert decision is not None
        assert decision.hedge_size == 1.5  # Close entire position
        assert decision.side == OrderSide.SELL  # Sell to close long
        assert decision.target_delta == 0.0  # Target zero position
        assert decision.urgency == "IMMEDIATE"
        assert "EMERGENCY EXIT" in decision.reason
        assert decision.funding_regime == FundingRegime.EXTREME

    def test_hedge_size_too_small_after_adjustment(
        self, hedger_service, base_risk_message
    ):
        """Test when funding adjustment makes hedge too small."""
        # Small hedge with low multiplier
        base_risk_message.hedge_recommendation["quantity"] = 0.01
        base_risk_message.funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=75.0,
            avg_rate_24h=70.0,
            avg_rate_7d=65.0,
            max_rate_24h=80.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=20.5,
            weekly_cost_pct=1.44,
        )
        base_risk_message.position_multiplier = 0.4

        decision = hedger_service._create_hedge_decision(base_risk_message)

        # 0.01 * 0.4 = 0.004, which is less than min_order_size_btc (0.001)
        # But still above minimum
        assert decision is not None
        assert decision.hedge_size == 0.004

    def test_hedge_size_exceeds_max_after_adjustment(
        self, hedger_service, base_risk_message
    ):
        """Test when hedge size exceeds maximum."""
        # Large hedge
        base_risk_message.hedge_recommendation["quantity"] = 15.0

        decision = hedger_service._create_hedge_decision(base_risk_message)

        assert decision is not None
        assert decision.hedge_size == 10.0  # Capped at max

    def test_emergency_exit_short_position(self, hedger_service, base_risk_message):
        """Test emergency exit for short position."""
        # Short position
        base_risk_message.net_delta = -2.0
        base_risk_message.funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=400.0,
            avg_rate_24h=350.0,
            avg_rate_7d=300.0,
            max_rate_24h=450.0,
            volatility_24h=60.0,
            position_multiplier=0.0,
            should_exit=True,
            regime_change=True,
            daily_cost_bps=109.6,
            weekly_cost_pct=7.67,
        )
        base_risk_message.position_multiplier = 0.0

        decision = hedger_service._create_hedge_decision(base_risk_message)

        assert decision is not None
        assert decision.hedge_size == 2.0  # Close entire short
        assert decision.side == OrderSide.BUY  # Buy to close short
        assert decision.target_delta == 0.0

    @pytest.mark.asyncio
    async def test_hedge_trade_message_with_funding(
        self, hedger_service, base_risk_message
    ):
        """Test hedge trade message includes funding information."""
        # Add funding context
        base_risk_message.funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=30.0,
            avg_rate_24h=28.0,
            avg_rate_7d=25.0,
            max_rate_24h=35.0,
            volatility_24h=5.0,
            position_multiplier=0.7,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=8.22,
            weekly_cost_pct=0.58,
        )
        base_risk_message.funding_adjusted_score = 45.0
        base_risk_message.position_multiplier = 0.7

        # Mock the bybit client
        hedger_service.bybit_client.place_order = AsyncMock(
            return_value={
                "orderId": "test-order-123",
                "orderLinkId": "HL-12345678",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "orderType": "Market",
                "qty": 0.35,
                "orderStatus": "Filled",
                "avgPrice": 50000.0,
            }
        )

        # Mock producer
        hedger_service.producer = AsyncMock()

        decision = hedger_service._create_hedge_decision(base_risk_message)
        await hedger_service.execute_hedge(decision, base_risk_message, "test-123")

        # Get the sent message
        assert hedger_service.producer.send.called
        call_args = hedger_service.producer.send.call_args
        sent_message = call_args[1]["value"]

        # Verify funding fields
        assert sent_message["funding_context"] is not None
        assert sent_message["funding_adjusted_score"] == 45.0
        assert sent_message["funding_cost_24h"] is not None

        # Verify funding cost calculation
        # Position: 0.35 BTC * $50k = $17,500
        # Funding rate: 30% APR = 0.0082% per 8h
        # 24h cost: $17,500 * 0.000082 * 3 = $4.31
        expected_cost = 17500 * (30 / 100 / 365 / 3) * 3
        assert abs(sent_message["funding_cost_24h"] - expected_cost) < 0.1
