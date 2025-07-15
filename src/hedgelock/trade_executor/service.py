"""
Trade Executor service implementation.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.hedgelock.trade_executor.config import Config
from src.hedgelock.trade_executor.kafka_config import KafkaManager
from src.hedgelock.trade_executor.bybit_client import BybitOrderClient
from src.hedgelock.trade_executor.models import (
    TradeExecution, TradeConfirmation, ExecutionStatus,
    ExecutionError, ExecutorState
)

logger = logging.getLogger(__name__)


class TradeExecutorService:
    """Service for executing trades from hedge decisions."""
    
    def __init__(self, config: Config):
        self.config = config
        self.kafka = KafkaManager(config)
        self.bybit = BybitOrderClient(config.bybit)
        
        # Service state
        self.state = ExecutorState()
        self.is_running = False
        self._consumer_task = None
        self._health_check_task = None
        
        # Execution tracking
        self.pending_executions: Dict[str, TradeExecution] = {}
        self.daily_volume = 0.0
        self.daily_volume_reset = datetime.utcnow()
        
    async def start(self) -> None:
        """Start the trade executor service."""
        logger.info("Starting Trade Executor service...")
        
        try:
            # Start Kafka connections
            await self.kafka.start()
            self.state.kafka_connected = True
            
            # Test Bybit connection
            if await self.bybit.test_connection():
                self.state.bybit_connected = True
            else:
                raise Exception("Failed to connect to Bybit API")
                
            # Start background tasks
            self.is_running = True
            self.state.is_running = True
            self._consumer_task = asyncio.create_task(self._consume_loop())
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info("Trade Executor service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Trade Executor: {e}")
            await self.stop()
            raise
            
    async def stop(self) -> None:
        """Stop the trade executor service."""
        logger.info("Stopping Trade Executor service...")
        
        self.is_running = False
        self.state.is_running = False
        
        # Cancel background tasks
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
                
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
                
        # Stop connections
        await self.kafka.stop()
        await self.bybit.close()
        
        logger.info("Trade Executor service stopped")
        
    async def _consume_loop(self) -> None:
        """Main consumer loop for processing hedge trades."""
        while self.is_running:
            try:
                # Consume message from Kafka
                message = await self.kafka.consume_message()
                
                if message:
                    await self._process_hedge_trade(
                        message['value'],
                        message.get('trace_id')
                    )
                    
                    # Commit offset after successful processing
                    await self.kafka.commit_offset()
                    
                else:
                    # No message, short sleep
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(1)  # Backoff on error
                
    async def _process_hedge_trade(
        self,
        hedge_trade: Dict[str, Any],
        trace_id: Optional[str] = None
    ) -> None:
        """Process a hedge trade message."""
        start_time = datetime.utcnow()
        
        # Create execution record
        execution = TradeExecution(
            execution_id=str(uuid.uuid4()),
            hedge_trade_id=hedge_trade.get('timestamp', ''),
            order_link_id=f"HL-{uuid.uuid4().hex[:8]}",
            symbol=hedge_trade['order_request']['symbol'],
            side=hedge_trade['order_request']['side'],
            order_type=hedge_trade['order_request']['orderType'],
            quantity=float(hedge_trade['order_request']['qty']),
            status=ExecutionStatus.PENDING,
            trace_id=trace_id
        )
        
        # Store pending execution
        self.pending_executions[execution.order_link_id] = execution
        
        try:
            # Check safety limits
            await self._check_safety_limits(execution)
            
            # Submit order to Bybit
            execution.status = ExecutionStatus.SUBMITTED
            execution.submitted_at = datetime.utcnow()
            
            order_result = await self.bybit.place_order(
                symbol=execution.symbol,
                side=execution.side,
                order_type=execution.order_type,
                qty=str(execution.quantity),
                order_link_id=execution.order_link_id
            )
            
            # Update execution with order details
            execution.order_id = order_result.get('orderId')
            submission_latency = (
                execution.submitted_at - start_time
            ).total_seconds() * 1000
            
            # Track order status
            await self._track_order_status(execution)
            
            # Calculate metrics
            fill_latency = None
            if execution.filled_at:
                fill_latency = (
                    execution.filled_at - execution.submitted_at
                ).total_seconds() * 1000
                
            total_latency = (
                datetime.utcnow() - start_time
            ).total_seconds() * 1000
            
            # Create confirmation
            confirmation = TradeConfirmation(
                hedge_trade_id=execution.hedge_trade_id,
                hedge_decision_id=hedge_trade['hedge_decision']['timestamp'],
                execution=execution,
                submission_latency_ms=submission_latency,
                fill_latency_ms=fill_latency,
                total_latency_ms=total_latency,
                risk_state=hedge_trade['risk_state'],
                ltv=hedge_trade['ltv'],
                hedge_size=hedge_trade['hedge_decision']['hedge_size'],
                success=execution.status in [
                    ExecutionStatus.FILLED,
                    ExecutionStatus.PARTIALLY_FILLED
                ],
                filled_quantity=execution.filled_quantity or 0,
                avg_price=execution.avg_fill_price,
                commission=execution.commission,
                trace_id=trace_id,
                testnet=self.config.bybit.testnet
            )
            
            # Update statistics
            self._update_statistics(execution, confirmation)
            
            # Publish confirmation
            await self.kafka.publish_confirmation(
                confirmation.dict(),
                trace_id
            )
            
            logger.info(
                f"Trade executed successfully: {execution.order_link_id} "
                f"({execution.filled_quantity} @ {execution.avg_fill_price})"
            )
            
        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")
            
            # Update execution with error
            execution.status = ExecutionStatus.FAILED
            execution.error = ExecutionError(
                code="EXECUTION_FAILED",
                message=str(e),
                retry_count=execution.retry_count
            )
            
            # Create error confirmation
            confirmation = TradeConfirmation(
                hedge_trade_id=execution.hedge_trade_id,
                hedge_decision_id=hedge_trade['hedge_decision']['timestamp'],
                execution=execution,
                submission_latency_ms=0,
                total_latency_ms=(
                    datetime.utcnow() - start_time
                ).total_seconds() * 1000,
                risk_state=hedge_trade['risk_state'],
                ltv=hedge_trade['ltv'],
                hedge_size=hedge_trade['hedge_decision']['hedge_size'],
                success=False,
                filled_quantity=0,
                error_message=str(e),
                error_details={"execution_error": execution.error.dict()},
                trace_id=trace_id,
                testnet=self.config.bybit.testnet
            )
            
            # Publish error confirmation
            await self.kafka.publish_confirmation(
                confirmation.dict(),
                trace_id
            )
            
            # Update failure statistics
            self.state.trades_failed += 1
            
        finally:
            # Clean up pending execution
            self.pending_executions.pop(execution.order_link_id, None)
            
    async def _check_safety_limits(self, execution: TradeExecution) -> None:
        """Check if order meets safety limits."""
        # Check max order size
        if execution.quantity > self.config.executor.max_order_size_btc:
            raise ValueError(
                f"Order size {execution.quantity} exceeds max "
                f"{self.config.executor.max_order_size_btc} BTC"
            )
            
        # Check daily volume
        self._reset_daily_volume_if_needed()
        
        if self.daily_volume + execution.quantity > self.config.executor.max_daily_volume_btc:
            raise ValueError(
                f"Daily volume would exceed limit of "
                f"{self.config.executor.max_daily_volume_btc} BTC"
            )
            
    async def _track_order_status(self, execution: TradeExecution) -> None:
        """Track order status until filled or timeout."""
        timeout = self.config.executor.order_timeout_ms / 1000
        start_time = datetime.utcnow()
        
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            # Get order status
            order_update = await self.bybit.get_order_status(
                symbol=execution.symbol,
                order_link_id=execution.order_link_id
            )
            
            if not order_update:
                await asyncio.sleep(
                    self.config.executor.status_poll_interval_ms / 1000
                )
                continue
                
            # Update execution with latest status
            if order_update.order_status == "Filled":
                execution.status = ExecutionStatus.FILLED
                execution.filled_at = datetime.utcnow()
                execution.avg_fill_price = order_update.avg_price
                execution.filled_quantity = order_update.cum_exec_qty
                execution.commission = order_update.cum_exec_fee
                break
                
            elif order_update.order_status == "PartiallyFilled":
                execution.status = ExecutionStatus.PARTIALLY_FILLED
                execution.avg_fill_price = order_update.avg_price
                execution.filled_quantity = order_update.cum_exec_qty
                execution.commission = order_update.cum_exec_fee
                
            elif order_update.order_status in ["Cancelled", "Rejected"]:
                execution.status = (
                    ExecutionStatus.CANCELLED 
                    if order_update.order_status == "Cancelled"
                    else ExecutionStatus.REJECTED
                )
                break
                
            # Continue polling
            await asyncio.sleep(
                self.config.executor.status_poll_interval_ms / 1000
            )
            
        # If timeout, mark as partially filled or failed
        if execution.status == ExecutionStatus.SUBMITTED:
            execution.status = ExecutionStatus.FAILED
            execution.error = ExecutionError(
                code="ORDER_TIMEOUT",
                message="Order tracking timeout"
            )
            
    def _update_statistics(
        self,
        execution: TradeExecution,
        confirmation: TradeConfirmation
    ) -> None:
        """Update service statistics."""
        self.state.trades_submitted += 1
        
        if execution.status == ExecutionStatus.FILLED:
            self.state.trades_filled += 1
            self.daily_volume += execution.filled_quantity or 0
        elif execution.status == ExecutionStatus.REJECTED:
            self.state.trades_rejected += 1
        elif execution.status == ExecutionStatus.FAILED:
            self.state.trades_failed += 1
            
        # Update latencies (moving average)
        if confirmation.submission_latency_ms > 0:
            self.state.avg_submission_latency_ms = (
                (self.state.avg_submission_latency_ms * 0.9) +
                (confirmation.submission_latency_ms * 0.1)
            )
            
        if confirmation.fill_latency_ms:
            self.state.avg_fill_latency_ms = (
                (self.state.avg_fill_latency_ms * 0.9) +
                (confirmation.fill_latency_ms * 0.1)
            )
            
        # Keep recent executions
        self.state.recent_executions.append(execution)
        self.state.recent_executions = self.state.recent_executions[-10:]
        
        self.state.last_update = datetime.utcnow()
        
    def _reset_daily_volume_if_needed(self) -> None:
        """Reset daily volume counter if new day."""
        now = datetime.utcnow()
        if now.date() > self.daily_volume_reset.date():
            self.daily_volume = 0.0
            self.daily_volume_reset = now
            logger.info("Daily volume counter reset")
            
    async def _health_check_loop(self) -> None:
        """Periodic health check."""
        while self.is_running:
            try:
                # Check Kafka connection
                self.state.kafka_connected = self.kafka.is_connected()
                
                # Check Bybit connection
                self.state.bybit_connected = await self.bybit.test_connection()
                
                # Overall health
                self.state.is_healthy = (
                    self.state.kafka_connected and
                    self.state.bybit_connected
                )
                
                await asyncio.sleep(self.config.executor.health_check_interval_s)
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
                self.state.is_healthy = False
                await asyncio.sleep(5)
                
    def get_state(self) -> ExecutorState:
        """Get current service state."""
        return self.state