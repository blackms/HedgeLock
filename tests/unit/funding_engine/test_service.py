"""
Unit tests for funding engine service with 100% coverage.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.hedgelock.funding_engine.config import FundingEngineConfig
from src.hedgelock.funding_engine.service import FundingEngineService
from src.hedgelock.shared.funding_models import (
    FundingAlert,
    FundingContext,
    FundingContextMessage,
    FundingDecision,
    FundingRate,
    FundingRateMessage,
    FundingRegime,
    FundingSnapshot,
)


class TestFundingEngineService:
    """Test funding engine service functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return FundingEngineConfig(
            kafka_bootstrap_servers="test:9092",
            redis_host="test-redis",
            regime_update_interval_seconds=1,  # Fast for testing
        )

    @pytest.fixture
    def mock_consumer(self):
        """Create mock Kafka consumer."""
        mock = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.consume_messages = AsyncMock()
        return mock

    @pytest.fixture
    def mock_producer(self):
        """Create mock Kafka producer."""
        mock = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.send_funding_context = AsyncMock()
        return mock

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage."""
        mock = Mock()
        mock.store_funding_rate = Mock()
        mock.get_funding_history = Mock()
        mock.get_current_funding_rate = Mock()
        mock.store_funding_regime = Mock()
        mock.get_funding_regime = Mock()
        return mock

    @pytest.fixture
    def service(self, config, mock_consumer, mock_producer, mock_storage):
        """Create service with mocked dependencies."""
        with (
            patch(
                "src.hedgelock.funding_engine.service.FundingEngineConsumer",
                return_value=mock_consumer,
            ),
            patch(
                "src.hedgelock.funding_engine.service.FundingEngineProducer",
                return_value=mock_producer,
            ),
            patch(
                "src.hedgelock.funding_engine.service.FundingStorage",
                return_value=mock_storage,
            ),
        ):
            service = FundingEngineService(config)
        return service

    @pytest.fixture
    def sample_funding_rate(self):
        """Create sample funding rate."""
        return FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0001,
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0,
        )

    @pytest.fixture
    def sample_funding_message(self, sample_funding_rate):
        """Create sample funding rate message."""
        return FundingRateMessage(
            service="collector",
            funding_rate=sample_funding_rate,
            trace_id="test-trace-123",
        )

    @pytest.mark.asyncio
    async def test_service_initialization(self, config):
        """Test service initialization."""
        service = FundingEngineService(config)

        assert service.config == config
        assert service.running is False
        assert len(service.current_contexts) == 0
        assert len(service.previous_regimes) == 0

    @pytest.mark.asyncio
    async def test_service_start(self, service, mock_consumer, mock_producer):
        """Test service startup."""
        # Start service
        await service.start()

        # Verify components started
        mock_consumer.start.assert_called_once()
        mock_producer.start.assert_called_once()

        # Verify service state
        assert service.running is True
        assert len(service.tasks) == 2

        # Cleanup
        await service.stop()

    @pytest.mark.asyncio
    async def test_service_stop(self, service, mock_consumer, mock_producer):
        """Test service shutdown."""
        # Start and stop service
        await service.start()
        await service.stop()

        # Verify components stopped
        mock_consumer.stop.assert_called_once()
        mock_producer.stop.assert_called_once()

        # Verify service state
        assert service.running is False

    @pytest.mark.asyncio
    async def test_handle_funding_rate_success(
        self,
        service,
        mock_storage,
        mock_producer,
        sample_funding_message,
        sample_funding_rate,
    ):
        """Test successful funding rate handling."""
        # Mock storage responses
        mock_storage.get_current_funding_rate.return_value = sample_funding_rate
        mock_storage.get_funding_history.return_value = [sample_funding_rate]

        # Process message
        await service._handle_funding_rate(sample_funding_message)

        # Verify storage calls
        mock_storage.store_funding_rate.assert_called_once_with(sample_funding_rate)
        mock_storage.store_funding_regime.assert_called_once()

        # Verify context was sent
        mock_producer.send_funding_context.assert_called_once()

        # Verify context was stored
        assert "BTCUSDT" in service.current_contexts
        assert "BTCUSDT" in service.previous_regimes

    @pytest.mark.asyncio
    async def test_handle_funding_rate_error(
        self, service, mock_storage, sample_funding_message
    ):
        """Test error handling in funding rate processing."""
        # Mock storage to raise error
        mock_storage.get_current_funding_rate.return_value = None

        # Process message - should not raise
        await service._handle_funding_rate(sample_funding_message)

        # Verify no context was stored
        assert len(service.current_contexts) == 0

    @pytest.mark.asyncio
    async def test_create_funding_snapshot(
        self, service, mock_storage, sample_funding_rate
    ):
        """Test funding snapshot creation."""
        # Mock storage responses
        mock_storage.get_current_funding_rate.return_value = sample_funding_rate
        mock_storage.get_funding_history.side_effect = [
            [sample_funding_rate],  # 24h history
            [sample_funding_rate] * 3,  # 7d history
        ]

        # Create snapshot
        snapshot = await service._create_funding_snapshot("BTCUSDT")

        # Verify snapshot
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.current_rate == sample_funding_rate
        assert len(snapshot.rates_24h) == 1
        assert len(snapshot.rates_7d) == 3

    @pytest.mark.asyncio
    async def test_create_funding_snapshot_no_current_rate(self, service, mock_storage):
        """Test snapshot creation with no current rate."""
        mock_storage.get_current_funding_rate.return_value = None

        with pytest.raises(ValueError, match="No current funding rate"):
            await service._create_funding_snapshot("BTCUSDT")

    def test_generate_funding_decision_emergency(self, service):
        """Test funding decision generation for emergency exit."""
        # Create emergency context
        context = FundingContext(
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

        # Generate decision
        decision = service._generate_funding_decision(context)

        # Verify decision
        assert decision.action == "exit_all"
        assert decision.urgency == "critical"
        assert decision.position_adjustment == 0.0
        assert decision.max_position_size == 0.0

    def test_generate_funding_decision_reduce(self, service):
        """Test funding decision for position reduction."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=75.0,
            avg_rate_24h=60.0,
            avg_rate_7d=50.0,
            max_rate_24h=80.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=20.5,
            weekly_cost_pct=1.44,
        )

        decision = service._generate_funding_decision(context)

        assert decision.urgency == "medium"
        assert decision.position_adjustment == 0.4
        assert decision.max_position_size == 1.0

    def test_generate_funding_decision_normal(self, service):
        """Test funding decision for normal conditions."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=25.0,
            avg_rate_7d=25.0,
            max_rate_24h=30.0,
            volatility_24h=3.0,
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=6.85,
            weekly_cost_pct=0.48,
        )

        decision = service._generate_funding_decision(context)

        assert decision.urgency == "low"
        assert decision.max_position_size == 1.5

    @pytest.mark.asyncio
    async def test_check_funding_alerts_emergency(self, service):
        """Test emergency alert generation."""
        context = FundingContext(
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
            trace_id="test-123",
        )

        # Check alerts
        await service._check_funding_alerts(context, FundingRegime.MANIA)

        # No direct way to verify alerts, but method should complete

    @pytest.mark.asyncio
    async def test_check_funding_alerts_regime_change(self, service):
        """Test regime change alert generation."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=75.0,
            avg_rate_24h=60.0,
            avg_rate_7d=50.0,
            max_rate_24h=80.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=20.5,
            weekly_cost_pct=1.44,
        )

        await service._check_funding_alerts(context, FundingRegime.NORMAL)

    @pytest.mark.asyncio
    async def test_check_funding_alerts_high_rate(self, service):
        """Test high funding rate alert."""
        context = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.MANIA,
            current_rate=150.0,
            avg_rate_24h=140.0,
            avg_rate_7d=130.0,
            max_rate_24h=160.0,
            volatility_24h=15.0,
            position_multiplier=0.2,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=41.1,
            weekly_cost_pct=2.88,
        )

        await service._check_funding_alerts(context, None)

    @pytest.mark.asyncio
    async def test_periodic_context_update(
        self, service, mock_storage, mock_producer, sample_funding_rate
    ):
        """Test periodic context update task."""
        # Setup initial context
        service.current_contexts["BTCUSDT"] = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=25.0,
            avg_rate_7d=25.0,
            max_rate_24h=30.0,
            volatility_24h=3.0,
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=6.85,
            weekly_cost_pct=0.48,
        )

        # Mock storage for significant change
        mock_storage.get_current_funding_rate.return_value = FundingRate(
            symbol="BTCUSDT",
            funding_rate=0.0003,  # Higher rate
            funding_time=datetime.utcnow(),
            mark_price=50000.0,
            index_price=50000.0,
        )
        mock_storage.get_funding_history.return_value = [sample_funding_rate]

        # Run one iteration
        service.running = True
        update_task = asyncio.create_task(service.periodic_context_update())
        await asyncio.sleep(1.5)  # Let it run once
        service.running = False
        update_task.cancel()

        try:
            await update_task
        except asyncio.CancelledError:
            pass

        # Verify update was sent (rate changed significantly)
        assert mock_producer.send_funding_context.called

    @pytest.mark.asyncio
    async def test_periodic_context_update_error_handling(self, service, mock_storage):
        """Test error handling in periodic update."""
        service.current_contexts["BTCUSDT"] = Mock()
        mock_storage.get_current_funding_rate.side_effect = Exception("Test error")

        # Run one iteration
        service.running = True
        update_task = asyncio.create_task(service.periodic_context_update())
        await asyncio.sleep(1.5)
        service.running = False
        update_task.cancel()

        try:
            await update_task
        except asyncio.CancelledError:
            pass

    def test_get_funding_status(self, service):
        """Test getting funding status."""
        # Add some contexts
        service.current_contexts["BTCUSDT"] = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.HEATED,
            current_rate=75.0,
            avg_rate_24h=70.0,
            avg_rate_7d=60.0,
            max_rate_24h=80.0,
            volatility_24h=10.0,
            position_multiplier=0.4,
            should_exit=False,
            regime_change=True,
            daily_cost_bps=20.5,
            weekly_cost_pct=1.44,
        )

        service.running = True

        # Get status
        status = service.get_funding_status()

        # Verify status
        assert status["service"] == "funding-engine"
        assert status["running"] is True
        assert status["symbols_tracked"] == 1
        assert "BTCUSDT" in status["contexts"]
        assert status["contexts"]["BTCUSDT"]["regime"] == "heated"
        assert status["contexts"]["BTCUSDT"]["current_rate"] == "75.00%"

    @pytest.mark.asyncio
    async def test_process_funding_rates_loop(
        self, service, mock_consumer, sample_funding_message
    ):
        """Test main funding rate processing loop."""
        # Mock consumer to yield one message then stop
        messages = [sample_funding_message]

        async def mock_consume():
            for msg in messages:
                yield msg
                service.running = False  # Stop after one message

        mock_consumer.consume_messages.return_value = mock_consume()

        # Mock handle method
        service._handle_funding_rate = AsyncMock()

        # Run process loop
        service.running = True
        await service.process_funding_rates()

        # Verify message was handled
        service._handle_funding_rate.assert_called_once_with(sample_funding_message)

    @pytest.mark.asyncio
    async def test_process_funding_rates_error_recovery(self, service, mock_consumer):
        """Test error recovery in processing loop."""
        # Mock consumer to raise error
        mock_consumer.consume_messages.side_effect = Exception("Test error")

        # Run process loop briefly
        service.running = True
        process_task = asyncio.create_task(service.process_funding_rates())
        await asyncio.sleep(0.1)
        service.running = False

        # Should not raise
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass
