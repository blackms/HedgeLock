"""
Reserve Manager service for USDC reserve management.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .manager import ReserveManager
from .models import (
    ReserveState, DeploymentRequest, DeploymentAction,
    ReserveRebalanceRequest, ReserveManagerConfig
)

logger = logging.getLogger(__name__)


class ReserveManagerService:
    """Service for managing USDC reserves."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = ReserveManagerConfig(**config.get('reserve_config', {}))
        self.kafka_servers = config.get('kafka_servers', 'localhost:9092')
        
        # Initialize reserve manager
        self.reserve_manager = ReserveManager(
            initial_reserves=self.config.initial_reserves
        )
        
        # Kafka clients
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        
        # Service state
        self.running = False
        self.deployment_queue: List[DeploymentRequest] = []
    
    async def start(self):
        """Start the reserve manager service."""
        logger.info("Starting Reserve Manager service...")
        
        # Initialize Kafka
        self.consumer = AIOKafkaConsumer(
            'reserve_deployments',    # Deployment requests
            'profit_taking',          # Profit events for rebalancing
            'ltv_updates',           # LTV updates for deployment decisions
            bootstrap_servers=self.kafka_servers,
            group_id='reserve-manager-group',
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
            self.deployment_processing_loop(),
            self.rebalance_check_loop(),
            self.alert_monitoring_loop()
        )
    
    async def process_messages(self):
        """Process incoming Kafka messages."""
        async for msg in self.consumer:
            if not self.running:
                break
                
            try:
                if msg.topic == 'reserve_deployments':
                    await self.handle_deployment_request(msg.value)
                elif msg.topic == 'profit_taking':
                    await self.handle_profit_event(msg.value)
                elif msg.topic == 'ltv_updates':
                    await self.handle_ltv_update(msg.value)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def handle_deployment_request(self, data: Dict):
        """Handle reserve deployment request."""
        deployment_data = data.get('deployment', {})
        
        # Create deployment request
        request = DeploymentRequest(
            amount=deployment_data.get('deployment_amount', 0),
            action=DeploymentAction.DEPLOY_TO_COLLATERAL,
            reason=deployment_data.get('deployment_reason', 'LTV deployment'),
            ltv_ratio=deployment_data.get('ltv_ratio'),
            emergency=data.get('emergency', False),
            requester='loan_manager'
        )
        
        # Queue for processing
        self.deployment_queue.append(request)
        
        logger.info(f"Queued deployment request: ${request.amount:.2f} for {request.reason}")
    
    async def handle_profit_event(self, data: Dict):
        """Handle profit event for reserve rebalancing."""
        realized_pnl = data.get('realized_pnl', 0)
        
        if realized_pnl <= 0:
            return
        
        # Create rebalance request
        rebalance_request = ReserveRebalanceRequest(
            profit_amount=realized_pnl,
            source='trading_profit',
            target_reserve_ratio=self.config.target_reserve_ratio
        )
        
        # Process rebalancing
        distribution = self.reserve_manager.process_profit_rebalance(rebalance_request)
        
        # Publish distribution event
        await self.publish_profit_distribution(rebalance_request, distribution)
        
        logger.info(f"Processed profit rebalance: ${realized_pnl:.2f} "
                   f"(reserves: ${distribution['to_reserves']:.2f})")
    
    async def handle_ltv_update(self, data: Dict):
        """Handle LTV update for deployment decisions."""
        ltv_state = data.get('ltv_state', {})
        ltv_ratio = ltv_state.get('ltv_ratio', 0)
        
        # Check if automatic deployment is needed
        if ltv_ratio >= 0.65 and self.config.emergency_deployment_enabled:
            # Calculate deployment amount
            deployment_amount = self.reserve_manager.calculate_deployment_for_ltv(ltv_ratio)
            
            if deployment_amount > 0:
                # Create automatic deployment request
                request = DeploymentRequest(
                    amount=deployment_amount,
                    action=DeploymentAction.DEPLOY_TO_COLLATERAL,
                    reason=f"Automatic LTV deployment (LTV: {ltv_ratio:.1%})",
                    ltv_ratio=ltv_ratio,
                    emergency=ltv_ratio >= self.config.emergency_ltv_threshold,
                    requester='reserve_manager_auto'
                )
                
                self.deployment_queue.append(request)
    
    async def deployment_processing_loop(self):
        """Process queued deployment requests."""
        while self.running:
            try:
                if self.deployment_queue:
                    # Process all queued deployments
                    while self.deployment_queue:
                        request = self.deployment_queue.pop(0)
                        
                        # Process deployment
                        record = self.reserve_manager.process_deployment_request(request)
                        
                        # Publish deployment result
                        await self.publish_deployment_result(record)
                        
                        # If successful and to collateral, notify treasury
                        if record.success and request.action == DeploymentAction.DEPLOY_TO_COLLATERAL:
                            await self.publish_collateral_update(record.amount_deployed)
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error processing deployments: {e}")
    
    async def rebalance_check_loop(self):
        """Periodically check if rebalancing is needed."""
        while self.running:
            try:
                await asyncio.sleep(self.config.rebalance_check_interval)
                
                # Check if reserves need rebalancing
                metrics = self.reserve_manager.get_reserve_metrics()
                
                # If too much in trading, consider withdrawal
                if metrics['deployed_to_trading'] > metrics['total_reserves'] * 0.5:
                    withdraw_amount = metrics['deployed_to_trading'] * 0.2  # Withdraw 20%
                    
                    success = self.reserve_manager.withdraw_from_trading(
                        withdraw_amount,
                        "Periodic rebalancing"
                    )
                    
                    if success:
                        await self.publish_withdrawal(withdraw_amount)
                
            except Exception as e:
                logger.error(f"Error in rebalance check: {e}")
    
    async def alert_monitoring_loop(self):
        """Monitor and publish alerts."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Get current metrics
                metrics = self.reserve_manager.get_reserve_metrics()
                
                # Check alert conditions
                if metrics['available_reserves'] < self.config.low_reserve_alert_threshold:
                    await self.publish_low_reserve_alert(metrics)
                
                if metrics['deployment_ratio'] > self.config.high_deployment_alert_percent:
                    await self.publish_high_deployment_alert(metrics)
                
            except Exception as e:
                logger.error(f"Error in alert monitoring: {e}")
    
    async def publish_deployment_result(self, record):
        """Publish deployment result."""
        await self.producer.send_and_wait(
            'reserve_deployment_results',
            value={
                'timestamp': record.timestamp.isoformat(),
                'success': record.success,
                'amount_requested': record.amount_requested,
                'amount_deployed': record.amount_deployed,
                'action': record.action.value,
                'reason': record.reason,
                'reserves_after': record.reserves_after,
                'deployed_after': record.deployed_after
            }
        )
    
    async def publish_collateral_update(self, amount: float):
        """Publish collateral update to treasury."""
        await self.producer.send_and_wait(
            'treasury_updates',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'update_type': 'collateral_addition',
                'amount': amount,
                'source': 'reserve_deployment',
                'available_reserves': self.reserve_manager.reserve_state.available_reserves
            }
        )
    
    async def publish_profit_distribution(self, request, distribution):
        """Publish profit distribution decision."""
        await self.producer.send_and_wait(
            'profit_distribution',
            value={
                'timestamp': request.timestamp.isoformat(),
                'profit_amount': request.profit_amount,
                'distribution': distribution,
                'reserve_metrics': self.reserve_manager.get_reserve_metrics()
            }
        )
    
    async def publish_withdrawal(self, amount: float):
        """Publish trading withdrawal."""
        await self.producer.send_and_wait(
            'trading_withdrawals',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'amount': amount,
                'reason': 'reserve_rebalancing',
                'reserves_after': self.reserve_manager.reserve_state.available_reserves
            }
        )
    
    async def publish_low_reserve_alert(self, metrics: Dict):
        """Publish low reserve alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'LOW_RESERVES',
                'severity': 'HIGH' if metrics['available_reserves'] < 1000 else 'MEDIUM',
                'message': f"Low reserves: ${metrics['available_reserves']:.2f} available",
                'metrics': metrics,
                'action_required': True
            }
        )
    
    async def publish_high_deployment_alert(self, metrics: Dict):
        """Publish high deployment alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'HIGH_DEPLOYMENT',
                'severity': 'MEDIUM',
                'message': f"High deployment ratio: {metrics['deployment_ratio']:.1%}",
                'metrics': metrics,
                'action_required': False
            }
        )
    
    async def stop(self):
        """Stop the reserve manager service."""
        logger.info("Stopping Reserve Manager service...")
        self.running = False
        
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current reserve state."""
        return {
            'reserve_state': self.reserve_manager.reserve_state.model_dump(),
            'reserve_metrics': self.reserve_manager.get_reserve_metrics(),
            'deployment_queue_size': len(self.deployment_queue),
            'recent_deployments': [
                {
                    'timestamp': d.timestamp.isoformat(),
                    'amount': d.amount_deployed,
                    'action': d.action.value,
                    'success': d.success
                }
                for d in self.reserve_manager.get_recent_deployments(1)
            ]
        }