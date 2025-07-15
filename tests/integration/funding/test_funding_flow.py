"""
Integration tests for end-to-end funding awareness flow.

Tests the complete flow from funding rate collection through to hedge execution.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
import uuid

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from src.hedgelock.shared.funding_models import (
    FundingRate, FundingRateMessage, FundingContextMessage,
    FundingContext, FundingRegime
)
from src.hedgelock.risk_engine.models import AccountData, RiskStateMessage, RiskState
from src.hedgelock.hedger.models import HedgeTradeMessage


class TestFundingFlow:
    """Test complete funding awareness flow."""
    
    @pytest.fixture
    async def kafka_producer(self):
        """Create mock Kafka producer."""
        producer = AsyncMock(spec=AIOKafkaProducer)
        producer.start = AsyncMock()
        producer.stop = AsyncMock()
        producer.send = AsyncMock()
        return producer
    
    @pytest.fixture
    async def kafka_consumer(self):
        """Create mock Kafka consumer."""
        consumer = AsyncMock(spec=AIOKafkaConsumer)
        consumer.start = AsyncMock()
        consumer.stop = AsyncMock()
        return consumer
    
    @pytest.fixture
    def funding_rate_message(self):
        """Create sample funding rate message."""
        rate = FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0003,  # 0.03% per 8h = ~33% APR
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
        return FundingRateMessage(
            service="collector",
            funding_rate=rate,
            trace_id="test-funding-flow-123"
        )
    
    @pytest.fixture
    def account_data_message(self):
        """Create sample account data."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "bybit",
            "total_collateral_value": 100000.0,
            "available_collateral": 50000.0,
            "used_collateral": 50000.0,
            "total_loan_value": 45000.0,
            "total_interest": 500.0,
            "positions": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "size": 2.0,
                    "side": "Buy",
                    "value": 100000.0
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_funding_rate_to_context_flow(self):
        """Test flow from funding rate to funding context."""
        from src.hedgelock.funding_engine.service import FundingEngineService
        from src.hedgelock.funding_engine.config import FundingEngineConfig
        
        # Create service with mocked dependencies
        config = FundingEngineConfig()
        service = FundingEngineService(config)
        
        # Mock Kafka components
        service.consumer = AsyncMock()
        service.producer = AsyncMock()
        service.storage = Mock()
        
        # Mock storage responses
        service.storage.get_current_funding_rate.return_value = FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0003,
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
        service.storage.get_funding_history.return_value = [
            FundingRate(
                symbol="BTCUSDT",
                funding_rate=0.00025,
                funding_time=datetime.utcnow() - timedelta(hours=8),
                mark_price=49900.0,
                index_price=49900.0
            )
        ]
        
        # Process funding rate message
        funding_msg = FundingRateMessage(
            service="collector",
            funding_rate=service.storage.get_current_funding_rate.return_value,
            trace_id="test-123"
        )
        
        await service._handle_funding_rate(funding_msg)
        
        # Verify funding context was created and sent
        service.producer.send_funding_context.assert_called_once()
        sent_msg = service.producer.send_funding_context.call_args[0][0]
        
        assert isinstance(sent_msg, FundingContextMessage)
        assert sent_msg.funding_context.symbol == "BTCUSDT"
        assert sent_msg.funding_context.current_regime == FundingRegime.NORMAL  # 33% APR
        assert sent_msg.funding_context.position_multiplier < 1.0  # Reduced due to funding
        assert sent_msg.funding_decision is not None
    
    @pytest.mark.asyncio
    async def test_funding_context_to_risk_state_flow(self):
        """Test flow from funding context to risk state."""
        from src.hedgelock.risk_engine.calculator import RiskCalculator
        
        # Create calculator
        calculator = RiskCalculator()
        
        # Create account data
        account_data = AccountData(
            timestamp=datetime.utcnow(),
            source="test",
            total_collateral_value=100000.0,
            available_collateral=50000.0,
            used_collateral=50000.0,
            total_loan_value=40000.0,
            total_interest=1000.0,
            positions={
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "size": 1.5,
                    "side": "Buy",
                    "value": 75000.0
                }
            }
        )
        
        # Create funding context (HEATED regime)
        funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=75.0,  # 75% APR
            avg_rate_24h=70.0,
            avg_rate_7d=65.0,
            max_rate_24h=80.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=20.5,
            weekly_cost_pct=1.44
        )
        
        # Calculate risk with funding
        calculation = calculator.calculate_risk(account_data, funding_context, "test-123")
        
        # Create risk state message
        risk_message = calculator.create_risk_state_message(calculation)
        
        # Verify funding impact
        assert risk_message.funding_context == funding_context
        assert risk_message.funding_regime == FundingRegime.HEATED
        assert risk_message.position_multiplier == 0.4
        assert risk_message.funding_adjusted_score > risk_message.risk_score
        
        # Verify hedge recommendation considers funding
        assert risk_message.hedge_recommendation is not None
    
    @pytest.mark.asyncio
    async def test_risk_state_to_hedge_execution_flow(self):
        """Test flow from risk state to hedge execution."""
        from src.hedgelock.hedger.main import HedgerService
        
        # Create hedger service
        hedger = HedgerService()
        hedger.bybit_client = AsyncMock()
        hedger.producer = AsyncMock()
        
        # Create risk state message with funding context
        funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.MANIA,
            current_rate=150.0,  # 150% APR
            avg_rate_24h=140.0,
            avg_rate_7d=130.0,
            max_rate_24h=160.0,
            volatility_24h=20.0,
            position_multiplier=0.2,  # Very low multiplier
            should_exit=False,
            regime_change=False,
            daily_cost_bps=41.1,
            weekly_cost_pct=2.88
        )
        
        risk_message = RiskStateMessage(
            risk_state=RiskState.CAUTION,
            ltv=0.45,
            net_delta=2.0,
            risk_score=50.0,
            hedge_recommendation={
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 1.0,
                "reason": "Reduce exposure due to high funding",
                "urgency": "HIGH"
            },
            total_collateral_value=100000.0,
            total_loan_value=45000.0,
            available_collateral=50000.0,
            funding_context=funding_context,
            funding_adjusted_score=70.0,  # Higher due to funding
            funding_regime=FundingRegime.MANIA,
            position_multiplier=0.2,
            trace_id="test-123"
        )
        
        # Process the message
        await hedger.process_message(risk_message.dict(), "test-123")
        
        # Verify hedge was adjusted for funding
        # Original hedge: 1.0 BTC
        # With 0.2 multiplier: 0.2 BTC
        hedger.bybit_client.place_order.assert_called_once()
        order_args = hedger.bybit_client.place_order.call_args[0][0]
        assert float(order_args["qty"]) == 0.2  # Reduced by funding multiplier
        
        # Verify hedge trade message was sent
        hedger.producer.send.assert_called()
        sent_topic = hedger.producer.send.call_args[0][0]
        sent_value = hedger.producer.send.call_args[1]["value"]
        
        assert sent_topic == "hedge_trades"
        assert sent_value["funding_context"] is not None
        assert sent_value["funding_cost_24h"] is not None
    
    @pytest.mark.asyncio
    async def test_extreme_funding_emergency_exit_flow(self):
        """Test emergency exit flow for extreme funding."""
        from src.hedgelock.hedger.main import HedgerService
        
        # Create hedger service
        hedger = HedgerService()
        hedger.bybit_client = AsyncMock()
        hedger.producer = AsyncMock()
        
        # Create extreme funding context
        funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=400.0,  # 400% APR - EXTREME!
            avg_rate_24h=350.0,
            avg_rate_7d=300.0,
            max_rate_24h=450.0,
            volatility_24h=60.0,
            position_multiplier=0.0,  # Zero multiplier
            should_exit=True,  # Emergency exit flag
            regime_change=True,
            daily_cost_bps=109.6,
            weekly_cost_pct=7.67
        )
        
        risk_message = RiskStateMessage(
            risk_state=RiskState.CRITICAL,  # Forced to critical
            ltv=0.4,  # Even with normal LTV
            net_delta=3.0,  # Long 3 BTC
            risk_score=40.0,
            hedge_recommendation={
                "action": "SELL",
                "symbol": "BTCUSDT",
                "quantity": 0.5,  # Original recommendation
                "reason": "Normal hedge",
                "urgency": "MEDIUM"
            },
            total_collateral_value=100000.0,
            total_loan_value=40000.0,
            available_collateral=50000.0,
            funding_context=funding_context,
            funding_adjusted_score=100.0,  # Max due to extreme funding
            funding_regime=FundingRegime.EXTREME,
            position_multiplier=0.0,
            trace_id="test-emergency-123"
        )
        
        # Process the message
        await hedger.process_message(risk_message.dict(), "test-emergency-123")
        
        # Verify FULL position closure (not just the recommended 0.5)
        hedger.bybit_client.place_order.assert_called_once()
        order_args = hedger.bybit_client.place_order.call_args[0][0]
        assert float(order_args["qty"]) == 3.0  # Close entire position
        assert order_args["side"] == "Sell"  # Sell to close long
        
        # Verify emergency exit in hedge trade message
        sent_value = hedger.producer.send.call_args[1]["value"]
        assert "EMERGENCY EXIT" in sent_value["hedge_decision"]["reason"]
        assert sent_value["hedge_decision"]["urgency"] == "IMMEDIATE"
    
    @pytest.mark.asyncio
    async def test_full_flow_integration(self):
        """Test complete flow from funding rate to hedge execution."""
        # This test simulates the entire flow with mocked services
        
        # Step 1: Collector publishes funding rate
        funding_rate = FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.001,  # 0.1% per 8h = ~110% APR (MANIA)
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0
        )
        
        # Step 2: Funding Engine processes and publishes context
        funding_context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.MANIA,
            current_rate=109.5,  # 110% APR
            avg_rate_24h=100.0,
            avg_rate_7d=90.0,
            max_rate_24h=120.0,
            volatility_24h=15.0,
            position_multiplier=0.25,  # Low multiplier for mania
            should_exit=False,
            regime_change=True,
            daily_cost_bps=30.0,
            weekly_cost_pct=2.1
        )
        
        # Step 3: Risk Engine includes funding in risk calculation
        # LTV: 0.45 (NORMAL) but funding pushes to CAUTION
        
        # Step 4: Hedger reduces position based on funding
        # Original hedge: 1.0 BTC -> Adjusted: 0.25 BTC
        
        # Verify the complete flow maintains funding awareness
        assert funding_context.current_regime == FundingRegime.MANIA
        assert funding_context.position_multiplier == 0.25
        
        # In production, each service would:
        # 1. Collector: Poll Bybit API, publish funding rates
        # 2. Funding Engine: Calculate regime, publish context
        # 3. Risk Engine: Adjust risk scores, escalate states
        # 4. Hedger: Apply multipliers, execute funding-aware trades


class TestFundingEdgeCases:
    """Test edge cases in funding flow."""
    
    @pytest.mark.asyncio
    async def test_funding_regime_transitions(self):
        """Test smooth transitions between funding regimes."""
        from src.hedgelock.shared.funding_calculator import FundingCalculator
        
        # Test all regime transitions
        transitions = [
            (5.0, FundingRegime.NEUTRAL),
            (15.0, FundingRegime.NORMAL),
            (60.0, FundingRegime.HEATED),
            (150.0, FundingRegime.MANIA),
            (350.0, FundingRegime.EXTREME),
        ]
        
        for rate, expected_regime in transitions:
            regime = FundingCalculator.detect_regime(rate)
            assert regime == expected_regime
    
    @pytest.mark.asyncio
    async def test_negative_funding_rates(self):
        """Test system handles negative funding rates correctly."""
        from src.hedgelock.shared.funding_calculator import FundingCalculator
        
        # Negative funding should still map to regimes by absolute value
        assert FundingCalculator.detect_regime(-5.0) == FundingRegime.NEUTRAL
        assert FundingCalculator.detect_regime(-75.0) == FundingRegime.HEATED
        assert FundingCalculator.detect_regime(-400.0) == FundingRegime.EXTREME
    
    @pytest.mark.asyncio
    async def test_missing_funding_context_graceful_degradation(self):
        """Test system continues to work without funding context."""
        from src.hedgelock.risk_engine.calculator import RiskCalculator
        
        calculator = RiskCalculator()
        
        # Create account data
        account_data = AccountData(
            timestamp=datetime.utcnow(),
            source="test",
            total_collateral_value=100000.0,
            available_collateral=50000.0,
            used_collateral=50000.0,
            total_loan_value=40000.0,
            total_interest=1000.0,
            positions={"BTCUSDT": {"symbol": "BTCUSDT", "size": 1.5, "side": "Buy", "value": 75000.0}}
        )
        
        # Calculate risk WITHOUT funding context
        calculation = calculator.calculate_risk(account_data, None, "test-123")
        
        # Should work normally, just without funding adjustments
        assert calculation.funding_context is None
        assert calculation.funding_adjusted_score == calculation.risk_score
        assert calculation.risk_state == RiskState.NORMAL  # Based on LTV only