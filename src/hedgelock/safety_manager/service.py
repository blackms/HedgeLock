"""
Safety Manager service for system protection and monitoring.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .manager import SafetyManager
from .models import (
    SafetyConfig, RiskLevel, EmergencyAction,
    SafetyAlert, SystemHealth
)

logger = logging.getLogger(__name__)


class SafetyManagerService:
    """Service for system safety monitoring and protection."""
    
    def __init__(self, config: Dict[str, Any]):
        # Extract safety config
        safety_config_dict = config.get('safety_config', {})
        self.config = SafetyConfig(**safety_config_dict)
        self.kafka_servers = config.get('kafka_servers', 'localhost:9092')
        
        # Initialize safety manager
        self.safety_manager = SafetyManager(self.config)
        
        # Kafka clients
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        
        # Service state
        self.running = False
        self.emergency_actions_queue: List[EmergencyAction] = []
        
        # Metrics tracking
        self.current_metrics: Dict[str, Any] = {}
    
    async def start(self):
        """Start the safety manager service."""
        logger.info("Starting Safety Manager service...")
        
        # Initialize Kafka
        self.consumer = AIOKafkaConsumer(
            'position_states',     # Position updates
            'pnl_updates',        # P&L updates
            'ltv_updates',        # LTV monitoring
            'service_health',     # Service heartbeats
            'trade_executions',   # Trade activity
            bootstrap_servers=self.kafka_servers,
            group_id='safety-manager-group',
            value_deserializer=lambda v: json.loads(v.decode('utf-8'))
        )
        
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await self.consumer.start()
        await self.producer.start()
        
        self.running = True
        
        # Start monitoring loops
        await asyncio.gather(
            self.process_messages(),
            self.safety_monitoring_loop(),
            self.circuit_breaker_check_loop(),
            self.dead_mans_switch_loop(),
            self.health_check_loop(),
            self.emergency_action_loop()
        )
    
    async def process_messages(self):
        """Process incoming Kafka messages."""
        async for msg in self.consumer:
            if not self.running:
                break
                
            try:
                if msg.topic == 'position_states':
                    await self.handle_position_update(msg.value)
                elif msg.topic == 'pnl_updates':
                    await self.handle_pnl_update(msg.value)
                elif msg.topic == 'ltv_updates':
                    await self.handle_ltv_update(msg.value)
                elif msg.topic == 'service_health':
                    await self.handle_service_health(msg.value)
                elif msg.topic == 'trade_executions':
                    await self.handle_trade_execution(msg.value)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def handle_position_update(self, data: Dict):
        """Handle position state updates."""
        position_state = data.get('position_state', {})
        
        # Update metrics
        self.current_metrics.update({
            'total_position_value': (
                position_state.get('spot_btc', 0) * position_state.get('btc_price', 0) +
                abs(position_state.get('long_perp', 0) - position_state.get('short_perp', 0)) * 
                position_state.get('btc_price', 0)
            ),
            'leverage_ratio': position_state.get('leverage', 0),
            'btc_price': position_state.get('btc_price', 0),
            'volatility_24h': position_state.get('volatility_24h', 0)
        })
        
        # Calculate liquidation risk
        liq_risk = self.safety_manager.calculate_liquidation_risk(
            position_state,
            position_state.get('btc_price', 0)
        )
        
        # Check if emergency action needed
        if liq_risk.risk_level in [RiskLevel.CRITICAL, RiskLevel.EMERGENCY]:
            if liq_risk.recommended_action:
                self.emergency_actions_queue.append(liq_risk.recommended_action)
                await self.publish_liquidation_alert(liq_risk)
    
    async def handle_pnl_update(self, data: Dict):
        """Handle P&L updates."""
        pnl_state = data.get('pnl_breakdown', {})
        metrics = data.get('metrics', {})
        
        # Update daily loss tracking
        net_pnl = pnl_state.get('net_pnl', 0)
        
        # Simple daily loss calculation (would be more sophisticated in practice)
        if 'daily_pnl_start' not in self.current_metrics:
            self.current_metrics['daily_pnl_start'] = net_pnl
        
        daily_loss = net_pnl - self.current_metrics['daily_pnl_start']
        self.current_metrics['daily_loss'] = daily_loss
        
        # Update equity metrics
        if 'peak_equity' not in self.current_metrics:
            self.current_metrics['peak_equity'] = net_pnl
        elif net_pnl > self.current_metrics['peak_equity']:
            self.current_metrics['peak_equity'] = net_pnl
        
        equity_drop = (self.current_metrics['peak_equity'] - net_pnl) / self.current_metrics['peak_equity']
        self.current_metrics['net_equity_drop'] = equity_drop
        
        # Check panic conditions
        if self.safety_manager.check_panic_conditions(self.current_metrics):
            self.emergency_actions_queue.append(EmergencyAction.PANIC_CLOSE)
    
    async def handle_ltv_update(self, data: Dict):
        """Handle LTV updates."""
        ltv_state = data.get('ltv_state', {})
        
        # Update safety state
        self.safety_manager.safety_state.current_risk_level = self._ltv_to_risk_level(
            ltv_state.get('ltv_ratio', 0)
        )
    
    async def handle_service_health(self, data: Dict):
        """Handle service health updates."""
        service_name = data.get('service_name')
        health_data = {
            'healthy': data.get('healthy', False),
            'response_time_ms': data.get('response_time_ms', 0),
            'details': data.get('details', {})
        }
        
        if service_name:
            self.safety_manager.update_system_health(service_name, health_data)
    
    async def handle_trade_execution(self, data: Dict):
        """Handle trade execution events."""
        # Update order rate metrics
        if 'order_rate_window' not in self.current_metrics:
            self.current_metrics['order_rate_window'] = []
        
        # Add timestamp to window
        self.current_metrics['order_rate_window'].append(datetime.utcnow())
        
        # Remove old entries (older than 1 minute)
        cutoff = datetime.utcnow() - timedelta(minutes=1)
        self.current_metrics['order_rate_window'] = [
            ts for ts in self.current_metrics['order_rate_window'] if ts > cutoff
        ]
        
        # Calculate rate
        self.current_metrics['order_rate'] = len(self.current_metrics['order_rate_window'])
    
    async def safety_monitoring_loop(self):
        """Main safety monitoring loop."""
        while self.running:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                # Check circuit breakers
                triggered_breakers = self.safety_manager.check_circuit_breakers(self.current_metrics)
                
                if triggered_breakers and self.config.halt_on_circuit_breaker:
                    self.emergency_actions_queue.append(EmergencyAction.HALT_TRADING)
                    await self.publish_circuit_breaker_alerts(triggered_breakers)
                
                # Check risk limits
                breached_limits = self.safety_manager.check_risk_limits(self.current_metrics)
                
                for limit_name, limit in breached_limits:
                    self.emergency_actions_queue.append(limit.action_on_breach)
                    await self.publish_risk_limit_alert(limit_name, limit)
                
                # Update safety state
                self.safety_manager.safety_state.daily_loss = self.current_metrics.get('daily_loss', 0)
                self.safety_manager.safety_state.leverage_ratio = self.current_metrics.get('leverage_ratio', 0)
                self.safety_manager.safety_state.total_position_value = self.current_metrics.get('total_position_value', 0)
                
                # Publish safety metrics
                await self.publish_safety_metrics()
                
            except Exception as e:
                logger.error(f"Error in safety monitoring: {e}")
    
    async def circuit_breaker_check_loop(self):
        """Check and reset circuit breakers."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Check for circuit breaker resets
                for name, cb in self.safety_manager.circuit_breakers.items():
                    if cb.check_reset():
                        await self.publish_circuit_breaker_reset(name)
                
            except Exception as e:
                logger.error(f"Error in circuit breaker check: {e}")
    
    async def dead_mans_switch_loop(self):
        """Monitor dead man's switch."""
        while self.running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if self.safety_manager.check_dead_mans_switch():
                    # Dead man's switch triggered!
                    logger.critical("Dead man's switch triggered - initiating emergency shutdown")
                    
                    self.emergency_actions_queue.extend([
                        EmergencyAction.CLOSE_ALL,
                        EmergencyAction.HALT_TRADING
                    ])
                    
                    await self.publish_dead_mans_switch_alert()
                
            except Exception as e:
                logger.error(f"Error in dead man's switch check: {e}")
    
    async def health_check_loop(self):
        """Check health of critical services."""
        while self.running:
            try:
                await asyncio.sleep(self.config.service_health_check_interval)
                
                # Get unhealthy services
                unhealthy = self.safety_manager.system_health.get_unhealthy_services()
                
                if unhealthy:
                    logger.warning(f"Unhealthy services detected: {unhealthy}")
                    await self.publish_service_health_alert(unhealthy)
                
            except Exception as e:
                logger.error(f"Error in health check: {e}")
    
    async def emergency_action_loop(self):
        """Process emergency actions."""
        while self.running:
            try:
                if self.emergency_actions_queue:
                    # Get unique actions
                    actions = list(set(self.emergency_actions_queue))
                    self.emergency_actions_queue.clear()
                    
                    for action in actions:
                        await self.execute_emergency_action(action)
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error processing emergency actions: {e}")
    
    async def execute_emergency_action(self, action: EmergencyAction):
        """Execute an emergency action."""
        logger.warning(f"Executing emergency action: {action.value}")
        
        metrics_before = self.current_metrics.copy()
        
        # Publish emergency action request
        await self.producer.send_and_wait(
            'emergency_actions',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'action': action.value,
                'reason': f"Safety system triggered: {action.value}",
                'safety_metrics': self.safety_manager.get_safety_metrics(),
                'risk_level': self.safety_manager.safety_state.current_risk_level.value
            }
        )
        
        # Record the action
        self.safety_manager.record_emergency_action(
            action=action,
            reason="Automatic safety trigger",
            success=True,  # Assume success for now
            metrics_before=metrics_before
        )
    
    def _ltv_to_risk_level(self, ltv_ratio: float) -> RiskLevel:
        """Convert LTV ratio to risk level."""
        if ltv_ratio >= 0.85:
            return RiskLevel.EMERGENCY
        elif ltv_ratio >= 0.75:
            return RiskLevel.CRITICAL
        elif ltv_ratio >= 0.65:
            return RiskLevel.HIGH
        elif ltv_ratio >= 0.50:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    async def publish_safety_metrics(self):
        """Publish current safety metrics."""
        await self.producer.send_and_wait(
            'safety_metrics',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'metrics': self.safety_manager.get_safety_metrics(),
                'current_risk_level': self.safety_manager.safety_state.current_risk_level.value
            }
        )
    
    async def publish_liquidation_alert(self, liq_risk):
        """Publish liquidation risk alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'LIQUIDATION_RISK',
                'severity': liq_risk.risk_level.value,
                'message': f"Liquidation risk: {liq_risk.min_distance_percent:.1%} from liquidation",
                'liquidation_risk': {
                    'distance_percent': liq_risk.min_distance_percent,
                    'risk_level': liq_risk.risk_level.value,
                    'recommended_action': liq_risk.recommended_action.value if liq_risk.recommended_action else None
                }
            }
        )
    
    async def publish_circuit_breaker_alerts(self, triggered: List[str]):
        """Publish circuit breaker alerts."""
        for breaker_name in triggered:
            cb = self.safety_manager.circuit_breakers[breaker_name]
            await self.producer.send_and_wait(
                'risk_alerts',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'alert_type': 'CIRCUIT_BREAKER',
                    'severity': 'HIGH',
                    'breaker_name': breaker_name,
                    'message': f"Circuit breaker {breaker_name} triggered",
                    'details': {
                        'threshold': cb.threshold,
                        'value': cb.last_value,
                        'cooldown_minutes': cb.cooldown_minutes
                    }
                }
            )
    
    async def publish_risk_limit_alert(self, limit_name: str, limit):
        """Publish risk limit alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'RISK_LIMIT',
                'severity': limit.severity.value,
                'limit_name': limit_name,
                'message': f"Risk limit {limit_name} breached",
                'details': {
                    'current_value': limit.current_value,
                    'limit_value': limit.limit_value,
                    'breach_percent': limit.breach_percent(),
                    'action': limit.action_on_breach.value
                }
            }
        )
    
    async def publish_circuit_breaker_reset(self, breaker_name: str):
        """Publish circuit breaker reset notification."""
        await self.producer.send_and_wait(
            'safety_notifications',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'notification_type': 'CIRCUIT_BREAKER_RESET',
                'breaker_name': breaker_name,
                'message': f"Circuit breaker {breaker_name} has been reset"
            }
        )
    
    async def publish_dead_mans_switch_alert(self):
        """Publish dead man's switch alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'DEAD_MANS_SWITCH',
                'severity': 'CRITICAL',
                'message': "Dead man's switch triggered - no activity detected",
                'action': 'EMERGENCY_SHUTDOWN'
            }
        )
    
    async def publish_service_health_alert(self, unhealthy_services: List[str]):
        """Publish service health alert."""
        await self.producer.send_and_wait(
            'risk_alerts',
            value={
                'timestamp': datetime.utcnow().isoformat(),
                'alert_type': 'SERVICE_HEALTH',
                'severity': 'HIGH',
                'message': f"Unhealthy services: {', '.join(unhealthy_services)}",
                'unhealthy_services': unhealthy_services
            }
        )
    
    async def stop(self):
        """Stop the safety manager service."""
        logger.info("Stopping Safety Manager service...")
        self.running = False
        
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current safety state."""
        return {
            'safety_state': self.safety_manager.safety_state.model_dump(),
            'safety_metrics': self.safety_manager.get_safety_metrics(),
            'system_health': self.safety_manager.system_health.model_dump(),
            'pending_actions': [a.value for a in self.emergency_actions_queue],
            'active_alerts': len([
                a for a in self.safety_manager.alert_history 
                if not a.acknowledged
            ])
        }