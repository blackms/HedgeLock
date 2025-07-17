"""
Loan Manager service for automatic loan tracking and repayment.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .manager import LoanManager
from .models import (
    LoanState, LTVState, LoanRepaymentRequest, 
    RepaymentPriority, LTVAction, LoanManagerConfig
)

logger = logging.getLogger(__name__)


class LoanManagerService:
    """Service for managing loan operations and monitoring."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = LoanManagerConfig(**config.get('loan_config', {}))
        self.kafka_servers = config.get('kafka_servers', 'localhost:9092')
        
        # Initialize loan manager
        self.loan_manager = LoanManager(
            initial_principal=self.config.initial_principal,
            apr=self.config.apr
        )
        
        # Kafka clients
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        
        # Service state
        self.running = False
        self.last_ltv_check = datetime.utcnow()
        self.current_collateral_value = 0.0
        self.available_reserves = 10000.0  # Initial reserves
        
        # Repayment queue
        self.repayment_queue: List[LoanRepaymentRequest] = []
    
    async def start(self):
        """Start the loan manager service."""
        logger.info("Starting Loan Manager service...")
        
        # Initialize Kafka
        self.consumer = AIOKafkaConsumer(
            'profit_taking',      # Listen to profit events
            'position_states',    # Listen to position updates for collateral value
            'treasury_updates',   # Listen to treasury for reserve updates
            bootstrap_servers=self.kafka_servers,
            group_id='loan-manager-group',
            value_deserializer=lambda v: json.loads(v.decode('utf-8'))
        )
        
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await self.consumer.start()
        await self.producer.start()
        
        self.running = True
        
        # Start processing loops
        await asyncio.gather(
            self.process_messages(),
            self.ltv_monitoring_loop(),
            self.repayment_processing_loop(),
            self.interest_update_loop()
        )
    
    async def process_messages(self):
        """Process incoming Kafka messages."""
        async for msg in self.consumer:
            if not self.running:
                break
                
            try:
                if msg.topic == 'profit_taking':
                    await self.handle_profit_event(msg.value)
                elif msg.topic == 'position_states':
                    await self.handle_position_update(msg.value)
                elif msg.topic == 'treasury_updates':
                    await self.handle_treasury_update(msg.value)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def handle_profit_event(self, data: Dict):
        """Handle profit taking events for auto-repayment."""
        if not self.config.auto_repay_enabled:
            return
        
        # Extract profit amount
        realized_pnl = data.get('realized_pnl', 0)
        
        if realized_pnl <= 0:
            return
        
        # Calculate repayment amount
        repayment_amount = self.loan_manager.get_repayment_from_profit(
            realized_pnl,
            self.config.profit_allocation_percent
        )
        
        if repayment_amount >= self.config.min_payment_amount:
            # Queue repayment
            request = LoanRepaymentRequest(
                amount=repayment_amount,
                source='trading_profit',
                priority=self.config.repayment_priority,
                notes=f"Auto-repayment from profit: ${realized_pnl:.2f}"
            )
            
            self.repayment_queue.append(request)
            
            logger.info(f"Queued auto-repayment: ${repayment_amount:.2f} from profit ${realized_pnl:.2f}")
    
    async def handle_position_update(self, data: Dict):
        """Handle position updates to track collateral value."""
        position_state = data.get('position_state', {})
        
        # Calculate collateral value (spot BTC + any USDC reserves)
        btc_price = position_state.get('btc_price', 0)
        spot_btc = position_state.get('spot_btc', 0)
        
        # Collateral = BTC value + available reserves
        btc_value = spot_btc * btc_price
        self.current_collateral_value = btc_value + self.available_reserves
        
        logger.debug(f"Updated collateral value: ${self.current_collateral_value:.2f} "
                    f"(BTC: ${btc_value:.2f}, Reserves: ${self.available_reserves:.2f})")
    
    async def handle_treasury_update(self, data: Dict):
        """Handle treasury updates for reserve tracking."""
        self.available_reserves = data.get('available_reserves', self.available_reserves)
        logger.debug(f"Updated available reserves: ${self.available_reserves:.2f}")
    
    async def ltv_monitoring_loop(self):
        """Monitor LTV and trigger actions as needed."""
        while self.running:
            try:
                # Check LTV at configured interval
                await asyncio.sleep(self.config.ltv_check_interval)
                
                if self.current_collateral_value <= 0:
                    logger.warning("No collateral value available for LTV calculation")
                    continue
                
                # Calculate current LTV
                ltv_state = self.loan_manager.calculate_ltv(self.current_collateral_value)
                
                # Publish LTV update
                await self.publish_ltv_update(ltv_state)
                
                # Check if reserve deployment needed
                if self.config.reserve_deployment_enabled:
                    await self.check_reserve_deployment(ltv_state)
                
                # Check if position scaling needed
                if ltv_state.current_action in [LTVAction.WARNING, LTVAction.CRITICAL, LTVAction.EMERGENCY]:
                    await self.publish_position_scaling(ltv_state)
                
                # Send alerts if needed
                if self.config.alert_on_high_ltv and ltv_state.ltv_ratio >= self.config.alert_ltv_threshold:
                    await self.publish_ltv_alert(ltv_state)
                
            except Exception as e:
                logger.error(f"Error in LTV monitoring: {e}")
    
    async def repayment_processing_loop(self):
        """Process queued repayments."""
        while self.running:
            try:
                if self.repayment_queue:
                    # Process all queued repayments
                    while self.repayment_queue:
                        request = self.repayment_queue.pop(0)
                        
                        # Process repayment
                        record = self.loan_manager.process_repayment(request)
                        
                        # Publish repayment event
                        await self.publish_repayment(record, request)
                        
                        # Check if loan is paid off
                        if self.loan_manager.is_loan_paid_off():
                            await self.publish_loan_paid_off()
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error processing repayments: {e}")
    
    async def interest_update_loop(self):
        """Periodically update accrued interest."""
        while self.running:
            try:
                # Update interest every hour
                await asyncio.sleep(3600)
                
                # Update interest
                interest = self.loan_manager.update_interest()
                
                # Publish interest update
                await self.publish_interest_update(interest)
                
            except Exception as e:
                logger.error(f"Error updating interest: {e}")
    
    async def check_reserve_deployment(self, ltv_state: LTVState):
        """Check and execute reserve deployment if needed."""
        deployment = self.loan_manager.calculate_reserve_deployment(
            ltv_state,
            self.available_reserves
        )
        
        if deployment:
            # Publish reserve deployment request
            await self.producer.send_and_wait(
                'reserve_deployments',
                value={
                    'timestamp': deployment.timestamp.isoformat(),
                    'deployment': deployment.model_dump(),
                    'ltv_state': ltv_state.model_dump(),
                    'emergency': deployment.emergency
                }
            )
            
            # Update local reserve tracking
            self.available_reserves = deployment.to_reserve
            
            logger.info(f"Requested reserve deployment: ${deployment.deployment_amount:.2f}")
    
    async def publish_ltv_update(self, ltv_state: LTVState):
        """Publish LTV update to Kafka."""
        await self.producer.send_and_wait(
            'ltv_updates',
            value={
                'timestamp': ltv_state.timestamp.isoformat(),
                'ltv_state': ltv_state.model_dump(),
                'loan_metrics': self.loan_manager.get_loan_metrics(),
                'recent_trend': self.loan_manager.get_recent_ltv_trend(24)
            }
        )
    
    async def publish_position_scaling(self, ltv_state: LTVState):
        """Publish position scaling request based on LTV."""
        await self.producer.send_and_wait(
            'position_scaling',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'ltv_ratio': ltv_state.ltv_ratio,
                'current_action': ltv_state.current_action.value,
                'scaling_factor': ltv_state.position_scaling,
                'reason': f"LTV {ltv_state.ltv_ratio:.1%} - {ltv_state.current_action.value}"
            }
        )
    
    async def publish_ltv_alert(self, ltv_state: LTVState):
        """Publish LTV alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'HIGH_LTV',
                'severity': ltv_state.current_action.value,
                'ltv_ratio': ltv_state.ltv_ratio,
                'message': f"LTV at {ltv_state.ltv_ratio:.1%} - Action: {ltv_state.current_action.value}",
                'ltv_state': ltv_state.model_dump()
            }
        )
    
    async def publish_repayment(self, record, request):
        """Publish loan repayment event."""
        await self.producer.send_and_wait(
            'loan_repayments',
            value={
                'timestamp': record.timestamp.isoformat(),
                'repayment': record.model_dump(),
                'source': request.source,
                'loan_metrics': self.loan_manager.get_loan_metrics()
            }
        )
    
    async def publish_loan_paid_off(self):
        """Publish loan paid off event."""
        await self.producer.send_and_wait(
            'loan_events',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'event': 'LOAN_PAID_OFF',
                'final_metrics': self.loan_manager.get_loan_metrics(),
                'total_days': (datetime.utcnow() - self.loan_manager.loan_state.loan_start_date).days
            }
        )
        
        logger.info("🎉 Loan fully paid off!")
    
    async def publish_interest_update(self, interest: float):
        """Publish interest accrual update."""
        await self.producer.send_and_wait(
            'loan_updates',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'update_type': 'interest_accrual',
                'interest_amount': interest,
                'total_accrued': self.loan_manager.loan_state.accrued_interest,
                'loan_metrics': self.loan_manager.get_loan_metrics()
            }
        )
    
    async def stop(self):
        """Stop the loan manager service."""
        logger.info("Stopping Loan Manager service...")
        self.running = False
        
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current loan and LTV state."""
        return {
            'loan_state': self.loan_manager.loan_state.model_dump(),
            'loan_metrics': self.loan_manager.get_loan_metrics(),
            'current_collateral': self.current_collateral_value,
            'available_reserves': self.available_reserves,
            'repayment_queue_size': len(self.repayment_queue),
            'latest_ltv': self.loan_manager.ltv_history[-1].model_dump() if self.loan_manager.ltv_history else None
        }