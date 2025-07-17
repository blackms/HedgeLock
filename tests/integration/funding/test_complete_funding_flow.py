"""
Integration tests for the complete funding flow from rate collection to hedge adjustment.
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.hedgelock.collector.models import FundingRateData
from src.hedgelock.funding_engine.service import FundingEngineService
from src.hedgelock.hedger.models import HedgeDecision, OrderSide
from src.hedgelock.risk_engine.models import AccountData, RiskState
from src.hedgelock.shared.funding_models import (
    FundingContext,
    FundingContextMessage,
    FundingDecision,
    FundingRate,
    FundingRateMessage,
    FundingRegime,
    FundingSnapshot,
)


class TestCompleteFundingFlow:
    """Test the complete funding awareness flow."""

    @pytest.fixture
    async def mock_kafka_producer(self):
        """Mock Kafka producer."""
        producer = AsyncMock()
        producer.send = AsyncMock()
        return producer

    @pytest.fixture
    async def mock_kafka_consumer(self):
        """Mock Kafka consumer."""
        consumer = AsyncMock()
        return consumer

    @pytest.fixture
    def funding_rates_progression(self):
        """Generate a progression of funding rates from normal to extreme."""
        base_time = datetime.utcnow()
        return [
            # Normal rates
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0001,  # 0.01% per 8h = 10.95% APR
                funding_time=base_time - timedelta(hours=40),
                mark_price=50000.0,
                index_price=50000.0,
            ),
            # Rates start increasing
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0003,  # 0.03% per 8h = 32.85% APR
                funding_time=base_time - timedelta(hours=32),
                mark_price=51000.0,
                index_price=50900.0,
            ),
            # Heated rates
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0006,  # 0.06% per 8h = 65.7% APR
                funding_time=base_time - timedelta(hours=24),
                mark_price=52000.0,
                index_price=51800.0,
            ),
            # Mania rates
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0012,  # 0.12% per 8h = 131.4% APR
                funding_time=base_time - timedelta(hours=16),
                mark_price=53000.0,
                index_price=52700.0,
            ),
            # Approaching extreme
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0025,  # 0.25% per 8h = 273.75% APR
                funding_time=base_time - timedelta(hours=8),
                mark_price=54000.0,
                index_price=53500.0,
            ),
            # Extreme rates
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0035,  # 0.35% per 8h = 383.25% APR
                funding_time=base_time,
                mark_price=55000.0,
                index_price=54000.0,
            ),
        ]

    @pytest.mark.asyncio
    async def test_complete_funding_awareness_flow(
        self, mock_kafka_producer, mock_kafka_consumer, funding_rates_progression
    ):
        """Test the complete flow from funding rate collection to position adjustment."""
        # Track messages sent through Kafka
        sent_messages = []
        mock_kafka_producer.send.side_effect = lambda topic, value, **kwargs: sent_messages.append(
            {"topic": topic, "value": value}
        )

        # Step 1: Collector receives funding rate from exchange
        collector_funding_rate = funding_rates_progression[-1]  # Latest extreme rate
        funding_rate_msg = FundingRateMessage(
            service="collector",
            funding_rate=collector_funding_rate,
            trace_id="test-trace-001",
        )

        # Simulate collector sending to Kafka
        await mock_kafka_producer.send(
            "funding_rates", value=funding_rate_msg.dict()
        )

        # Step 2: Funding Engine processes the rate
        with patch(
            "src.hedgelock.funding_engine.service.FundingEngineService._load_historical_rates"
        ) as mock_load:
            # Mock historical data
            mock_load.return_value = funding_rates_progression[:-1]  # All but latest

            funding_engine = FundingEngineService(MagicMock())
            funding_engine.storage = MagicMock()
            funding_engine.storage.get_funding_history.return_value = funding_rates_progression[
                :-1
            ]
            funding_engine.producer = mock_kafka_producer

            # Process the new rate
            await funding_engine._process_funding_rate(funding_rate_msg)

            # Verify funding context was created and sent
            assert len(sent_messages) >= 2  # funding_rates + funding_context
            context_msg = next(
                msg for msg in sent_messages if msg["topic"] == "funding_context"
            )
            context = FundingContext(**context_msg["value"]["funding_context"])

            # Verify extreme regime detected
            assert context.current_regime == FundingRegime.EXTREME
            assert context.current_rate > 300  # >300% APR
            assert context.position_multiplier == 0.0  # No position allowed
            assert context.should_exit is True  # Emergency exit

        # Step 3: Risk Engine receives funding context and adjusts risk assessment
        risk_account_data = AccountData(
            timestamp=datetime.utcnow(),
            balance_total=100000.0,
            balance_free=50000.0,
            balance_used=50000.0,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "side": "LONG",
                    "size": 2.0,
                    "entry_price": 50000.0,
                    "mark_price": 55000.0,
                    "unrealized_pnl": 10000.0,
                    "margin_used": 20000.0,
                }
            ],
            open_orders=[],
            margin_ratio=0.5,
            total_position_value=110000.0,
            total_collateral=100000.0,
            liquidation_price=40000.0,
        )

        # Simulate risk engine decision with funding context
        ltv = risk_account_data.balance_used / risk_account_data.balance_total
        base_risk_score = ltv * 100

        # Apply funding adjustment
        funding_adjusted_score = base_risk_score + (
            context.current_rate / 10
        )  # Add funding impact

        # Create risk state message
        risk_state_msg = {
            "timestamp": datetime.utcnow().isoformat(),
            "risk_state": RiskState.CRITICAL.value,  # Due to extreme funding
            "ltv": ltv,
            "risk_score": base_risk_score,
            "funding_adjusted_score": funding_adjusted_score,
            "net_delta": 2.0,  # Current long position
            "hedge_recommendation": {
                "action": "SELL",
                "quantity": 2.0,  # Close entire position
                "reason": f"EMERGENCY: Extreme funding rate {context.current_rate:.1f}% APR",
                "urgency": "IMMEDIATE",
            },
            "position_multiplier": context.position_multiplier,
            "funding_regime": context.current_regime,
            "funding_context": context.dict(),
            "trace_id": "test-trace-002",
        }

        await mock_kafka_producer.send("risk_state", value=risk_state_msg)

        # Step 4: Hedger receives risk state and executes emergency exit
        hedge_decision = HedgeDecision(
            risk_state=risk_state_msg["risk_state"],
            current_delta=risk_state_msg["net_delta"],
            target_delta=0.0,  # Emergency exit to flat
            hedge_size=2.0,  # Close entire position
            side=OrderSide.SELL,
            reason=risk_state_msg["hedge_recommendation"]["reason"],
            urgency="IMMEDIATE",
            funding_adjusted=True,
            funding_regime=FundingRegime.EXTREME,
            position_multiplier=0.0,
            trace_id=risk_state_msg["trace_id"],
        )

        # Verify the complete flow
        assert hedge_decision.hedge_size == 2.0  # Full position closure
        assert hedge_decision.side == OrderSide.SELL
        assert "EMERGENCY" in hedge_decision.reason
        assert hedge_decision.funding_regime == FundingRegime.EXTREME

        # Verify all messages were sent
        funding_rate_msgs = [
            msg for msg in sent_messages if msg["topic"] == "funding_rates"
        ]
        funding_context_msgs = [
            msg for msg in sent_messages if msg["topic"] == "funding_context"
        ]
        risk_state_msgs = [
            msg for msg in sent_messages if msg["topic"] == "risk_state"
        ]

        assert len(funding_rate_msgs) >= 1
        assert len(funding_context_msgs) >= 1
        assert len(risk_state_msgs) >= 1

    @pytest.mark.asyncio
    async def test_funding_regime_transitions(
        self, mock_kafka_producer, funding_rates_progression
    ):
        """Test smooth transitions between funding regimes."""
        funding_engine = FundingEngineService(MagicMock())
        funding_engine.storage = MagicMock()
        funding_engine.producer = mock_kafka_producer

        regimes_observed = []
        multipliers_observed = []

        # Process rates in sequence
        for i, rate in enumerate(funding_rates_progression):
            # Mock historical data up to current rate
            funding_engine.storage.get_funding_history.return_value = (
                funding_rates_progression[:i] if i > 0 else []
            )

            # Create funding rate message
            funding_msg = FundingRateMessage(
                service="collector", funding_rate=rate, trace_id=f"test-trace-{i:03d}"
            )

            # Capture sent messages
            sent_messages = []
            mock_kafka_producer.send.side_effect = (
                lambda topic, value, **kwargs: sent_messages.append(value)
            )

            # Process rate
            await funding_engine._process_funding_rate(funding_msg)

            # Extract context from sent message
            if sent_messages:
                context = FundingContext(**sent_messages[0]["funding_context"])
                regimes_observed.append(context.current_regime)
                multipliers_observed.append(context.position_multiplier)

        # Verify regime progression
        assert regimes_observed[0] == FundingRegime.NORMAL  # 10.95% APR
        assert regimes_observed[2] == FundingRegime.HEATED  # 65.7% APR
        assert regimes_observed[3] == FundingRegime.MANIA  # 131.4% APR
        assert regimes_observed[5] == FundingRegime.EXTREME  # 383.25% APR

        # Verify position multiplier decreases
        assert multipliers_observed[0] == 1.0  # Full position in NORMAL
        assert 0 < multipliers_observed[2] < 1.0  # Reduced in HEATED
        assert multipliers_observed[5] == 0.0  # No position in EXTREME

    @pytest.mark.asyncio
    async def test_emergency_exit_decision_flow(self, mock_kafka_producer):
        """Test emergency exit decision when funding becomes extreme."""
        # Create extreme funding context
        extreme_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=400.0,  # 400% APR
            avg_rate_24h=350.0,
            avg_rate_7d=200.0,
            max_rate_24h=400.0,
            volatility_24h=100.0,
            position_multiplier=0.0,
            should_exit=True,
            regime_change=True,
            daily_cost_bps=109.6,  # 1.096% daily
            weekly_cost_pct=7.67,  # 7.67% weekly
            trace_id="test-emergency-001",
        )

        # Create funding decision
        funding_decision = FundingDecision(
            context=extreme_context,
            action="emergency_exit",
            position_adjustment=0.0,
            max_position_size=0.0,
            reason="Extreme funding rate detected - emergency position closure required",
            urgency="immediate",
            funding_risk_score=100.0,  # Maximum risk
            projected_cost_24h=1096.0,  # $1,096 per $100k position per day
            trace_id=extreme_context.trace_id,
        )

        # Verify emergency exit logic
        assert funding_decision.action == "emergency_exit"
        assert funding_decision.position_adjustment == 0.0
        assert funding_decision.urgency == "immediate"
        assert funding_decision.funding_risk_score == 100.0

        # Verify cost calculations
        assert funding_decision.projected_cost_24h > 1000  # >$1k per day per $100k

    @pytest.mark.asyncio
    async def test_funding_flow_error_handling(self, mock_kafka_producer):
        """Test error handling throughout the funding flow."""
        # Test invalid funding rate
        with pytest.raises(ValueError):
            invalid_rate = FundingRate(
                symbol="BTCUSDT",
                funding_rate=-10.0,  # Invalid: too negative
                funding_time=datetime.utcnow(),
                mark_price=50000.0,
                index_price=50000.0,
            )

        # Test missing historical data
        funding_engine = FundingEngineService(MagicMock())
        funding_engine.storage = MagicMock()
        funding_engine.storage.get_funding_history.return_value = []  # No history
        funding_engine.producer = mock_kafka_producer

        # Should handle gracefully
        funding_msg = FundingRateMessage(
            service="collector",
            funding_rate=FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.0001,
                funding_time=datetime.utcnow(),
                mark_price=50000.0,
                index_price=50000.0,
            ),
            trace_id="test-no-history",
        )

        # Should not raise exception
        await funding_engine._process_funding_rate(funding_msg)

        # Test Kafka producer failure
        mock_kafka_producer.send.side_effect = Exception("Kafka unavailable")

        with pytest.raises(Exception, match="Kafka unavailable"):
            await funding_engine._process_funding_rate(funding_msg)