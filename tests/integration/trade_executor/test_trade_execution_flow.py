"""
Integration tests for trade execution flow.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from src.hedgelock.hedger.models import (
    HedgeDecision,
    HedgeTradeMessage,
    OrderRequest,
    OrderSide,
    OrderType,
)


class TestTradeExecutionFlow:
    """Test complete trade execution flow."""

    @pytest.fixture
    async def kafka_producer(self):
        """Create Kafka producer for testing."""
        producer = AIOKafkaProducer(
            bootstrap_servers="localhost:9092",
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await producer.start()
        yield producer
        await producer.stop()

    @pytest.fixture
    async def kafka_consumer(self):
        """Create Kafka consumer for testing."""
        consumer = AIOKafkaConsumer(
            "trade_confirmations",
            bootstrap_servers="localhost:9092",
            group_id=f"test-consumer-{uuid.uuid4()}",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest",
        )
        await consumer.start()
        yield consumer
        await consumer.stop()

    @pytest.mark.asyncio
    async def test_successful_trade_execution(self, kafka_producer, kafka_consumer):
        """Test successful trade execution flow."""
        # Create test hedge trade message
        trace_id = str(uuid.uuid4())

        hedge_decision = HedgeDecision(
            timestamp=datetime.utcnow(),
            risk_state="danger",
            current_delta=0.8,
            target_delta=0.5,
            hedge_size=0.3,
            side=OrderSide.SELL,
            reason="LTV exceeded danger threshold",
            urgency="high",
            trace_id=trace_id,
        )

        order_request = OrderRequest(
            symbol="BTCUSDT", side=OrderSide.SELL, orderType=OrderType.MARKET, qty="0.3"
        )

        hedge_trade = HedgeTradeMessage(
            hedge_decision=hedge_decision,
            order_request=order_request,
            risk_state="danger",
            ltv=0.8,
            risk_score=85.0,
            trace_id=trace_id,
        )

        # Send hedge trade to Kafka
        await kafka_producer.send(
            "hedge_trades",
            value=hedge_trade.dict(),
            headers=[("trace_id", trace_id.encode())],
        )

        # Wait for trade confirmation
        confirmation = None
        start_time = asyncio.get_event_loop().time()
        timeout = 10  # 10 seconds timeout

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # Poll for messages
                records = await asyncio.wait_for(
                    kafka_consumer.getmany(timeout_ms=1000), timeout=2
                )

                for topic_partition, messages in records.items():
                    for message in messages:
                        msg_trace_id = None
                        if message.headers:
                            for key, value in message.headers:
                                if key == "trace_id":
                                    msg_trace_id = value.decode("utf-8")

                        if msg_trace_id == trace_id:
                            confirmation = message.value
                            break

                if confirmation:
                    break

            except asyncio.TimeoutError:
                continue

        # Verify confirmation received
        assert confirmation is not None, "No trade confirmation received"

        # Verify confirmation details
        assert confirmation["trace_id"] == trace_id
        assert confirmation["success"] is True or confirmation["success"] is False
        assert "execution" in confirmation
        assert confirmation["execution"]["symbol"] == "BTCUSDT"
        assert confirmation["execution"]["side"] == "Sell"
        assert confirmation["execution"]["quantity"] == 0.3

        # Verify latency metrics
        assert "total_latency_ms" in confirmation
        assert confirmation["total_latency_ms"] < 5000  # Less than 5 seconds

        print(f"Trade execution confirmed: {confirmation['execution']['status']}")

    @pytest.mark.asyncio
    async def test_trade_execution_with_invalid_size(
        self, kafka_producer, kafka_consumer
    ):
        """Test trade execution with order size exceeding limit."""
        trace_id = str(uuid.uuid4())

        # Create order exceeding max size (>1.0 BTC)
        hedge_decision = HedgeDecision(
            timestamp=datetime.utcnow(),
            risk_state="critical",
            current_delta=0.95,
            target_delta=0.5,
            hedge_size=2.0,  # Exceeds max order size
            side=OrderSide.SELL,
            reason="Critical LTV",
            urgency="critical",
            trace_id=trace_id,
        )

        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            orderType=OrderType.MARKET,
            qty="2.0",  # Exceeds max order size
        )

        hedge_trade = HedgeTradeMessage(
            hedge_decision=hedge_decision,
            order_request=order_request,
            risk_state="critical",
            ltv=0.95,
            risk_score=95.0,
            trace_id=trace_id,
        )

        # Send hedge trade
        await kafka_producer.send(
            "hedge_trades",
            value=hedge_trade.dict(),
            headers=[("trace_id", trace_id.encode())],
        )

        # Wait for error confirmation
        confirmation = None
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < 5:
            try:
                records = await asyncio.wait_for(
                    kafka_consumer.getmany(timeout_ms=1000), timeout=2
                )

                for topic_partition, messages in records.items():
                    for message in messages:
                        msg_trace_id = None
                        if message.headers:
                            for key, value in message.headers:
                                if key == "trace_id":
                                    msg_trace_id = value.decode("utf-8")

                        if msg_trace_id == trace_id:
                            confirmation = message.value
                            break

                if confirmation:
                    break

            except asyncio.TimeoutError:
                continue

        # Verify error confirmation
        assert confirmation is not None
        assert confirmation["success"] is False
        assert "error_message" in confirmation
        assert "exceeds max" in confirmation["error_message"].lower()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_trades(self, kafka_producer, kafka_consumer):
        """Test multiple concurrent trade executions."""
        num_trades = 5
        trace_ids = []

        # Send multiple trades
        for i in range(num_trades):
            trace_id = str(uuid.uuid4())
            trace_ids.append(trace_id)

            hedge_decision = HedgeDecision(
                timestamp=datetime.utcnow(),
                risk_state="caution",
                current_delta=0.65,
                target_delta=0.5,
                hedge_size=0.1,
                side=OrderSide.SELL if i % 2 == 0 else OrderSide.BUY,
                reason=f"Test trade {i}",
                urgency="medium",
                trace_id=trace_id,
            )

            order_request = OrderRequest(
                symbol="BTCUSDT",
                side=hedge_decision.side,
                orderType=OrderType.MARKET,
                qty="0.1",
            )

            hedge_trade = HedgeTradeMessage(
                hedge_decision=hedge_decision,
                order_request=order_request,
                risk_state="caution",
                ltv=0.65,
                risk_score=65.0,
                trace_id=trace_id,
            )

            await kafka_producer.send(
                "hedge_trades",
                value=hedge_trade.dict(),
                headers=[("trace_id", trace_id.encode())],
            )

        # Collect confirmations
        confirmations = {}
        start_time = asyncio.get_event_loop().time()

        while (
            len(confirmations) < num_trades
            and asyncio.get_event_loop().time() - start_time < 15
        ):
            try:
                records = await asyncio.wait_for(
                    kafka_consumer.getmany(timeout_ms=1000), timeout=2
                )

                for topic_partition, messages in records.items():
                    for message in messages:
                        msg_trace_id = None
                        if message.headers:
                            for key, value in message.headers:
                                if key == "trace_id":
                                    msg_trace_id = value.decode("utf-8")

                        if msg_trace_id in trace_ids:
                            confirmations[msg_trace_id] = message.value

            except asyncio.TimeoutError:
                continue

        # Verify all trades were processed
        assert len(confirmations) == num_trades

        # Verify each confirmation
        for trace_id, confirmation in confirmations.items():
            assert confirmation["trace_id"] == trace_id
            assert "execution" in confirmation
            assert confirmation["execution"]["quantity"] == 0.1

        print(f"Successfully processed {len(confirmations)} concurrent trades")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
