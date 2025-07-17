"""
Core Safety Manager implementation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from .models import (
    SafetyState, LiquidationRisk, CircuitBreaker, RiskLimit,
    SystemHealth, SafetyAlert, EmergencyActionRecord,
    RiskLevel, EmergencyAction, SafetyConfig
)

logger = logging.getLogger(__name__)


class SafetyManager:
    """Manages system safety, liquidation protection, and risk limits."""
    
    def __init__(self, config: SafetyConfig):
        self.config = config
        self.safety_state = SafetyState()
        self.system_health = SystemHealth()
        
        # Initialize circuit breakers
        self.circuit_breakers = self._init_circuit_breakers()
        
        # Initialize risk limits
        self.risk_limits = self._init_risk_limits()
        
        # History tracking
        self.alert_history: List[SafetyAlert] = []
        self.action_history: List[EmergencyActionRecord] = []
        self.liquidation_history: List[LiquidationRisk] = []
    
    def _init_circuit_breakers(self) -> Dict[str, CircuitBreaker]:
        """Initialize circuit breakers."""
        return {
            'daily_loss': CircuitBreaker(
                name='daily_loss',
                description='Daily loss limit circuit breaker',
                threshold=self.config.daily_loss_limit,
                cooldown_minutes=60
            ),
            'funding_cost': CircuitBreaker(
                name='funding_cost',
                description='Funding cost limit circuit breaker',
                threshold=self.config.funding_cost_limit,
                cooldown_minutes=30
            ),
            'volatility': CircuitBreaker(
                name='volatility',
                description='Volatility limit circuit breaker',
                threshold=self.config.volatility_limit,
                cooldown_minutes=120
            ),
            'consecutive_losses': CircuitBreaker(
                name='consecutive_losses',
                description='Consecutive loss days circuit breaker',
                threshold=self.config.consecutive_loss_days_limit,
                cooldown_minutes=1440  # 24 hours
            )
        }
    
    def _init_risk_limits(self) -> Dict[str, RiskLimit]:
        """Initialize risk limits."""
        return {
            'position_value': RiskLimit(
                name='position_value',
                description='Maximum total position value',
                limit_type='position',
                limit_value=self.config.max_position_value,
                action_on_breach=EmergencyAction.REDUCE_POSITIONS,
                severity=RiskLevel.HIGH
            ),
            'leverage': RiskLimit(
                name='leverage',
                description='Maximum leverage ratio',
                limit_type='position',
                limit_value=self.config.max_leverage,
                action_on_breach=EmergencyAction.REDUCE_POSITIONS,
                severity=RiskLevel.CRITICAL
            ),
            'order_rate': RiskLimit(
                name='order_rate',
                description='Order rate per minute',
                limit_type='rate',
                limit_value=self.config.max_order_rate_per_minute,
                action_on_breach=EmergencyAction.HALT_TRADING,
                severity=RiskLevel.MEDIUM
            )
        }
    
    def calculate_liquidation_risk(
        self, 
        position_state: Dict[str, Any],
        current_price: float
    ) -> LiquidationRisk:
        """Calculate current liquidation risk."""
        # Extract position data
        spot_btc = position_state.get('spot_btc', 0)
        long_perp = position_state.get('long_perp', 0)
        short_perp = position_state.get('short_perp', 0)
        leverage = position_state.get('leverage', 25)
        
        # Calculate liquidation prices
        # Simplified calculation - in practice would use exchange formulas
        maintenance_margin = 0.5  # 0.5% for 25x leverage
        
        if long_perp > 0:
            liq_price_long = current_price * (1 - 1/leverage + maintenance_margin/100)
        else:
            liq_price_long = 0
            
        if short_perp > 0:
            liq_price_short = current_price * (1 + 1/leverage - maintenance_margin/100)
        else:
            liq_price_short = float('inf')
        
        # Create liquidation risk assessment
        liq_risk = LiquidationRisk(
            liquidation_price_long=liq_price_long,
            liquidation_price_short=liq_price_short,
            current_price=current_price,
            distance_percent_long=0,
            distance_percent_short=0,
            min_distance_percent=0,
            risk_level=RiskLevel.LOW
        )
        
        # Calculate distances
        liq_risk.calculate_distances()
        
        # Determine risk level
        if liq_risk.min_distance_percent < 0.05:
            liq_risk.risk_level = RiskLevel.EMERGENCY
            liq_risk.recommended_action = EmergencyAction.PANIC_CLOSE
        elif liq_risk.min_distance_percent < 0.10:
            liq_risk.risk_level = RiskLevel.CRITICAL
            liq_risk.recommended_action = EmergencyAction.CLOSE_ALL
        elif liq_risk.min_distance_percent < 0.15:
            liq_risk.risk_level = RiskLevel.HIGH
            liq_risk.recommended_action = EmergencyAction.CLOSE_LOSING
        elif liq_risk.min_distance_percent < 0.25:
            liq_risk.risk_level = RiskLevel.MEDIUM
            liq_risk.recommended_action = EmergencyAction.REDUCE_POSITIONS
        else:
            liq_risk.risk_level = RiskLevel.LOW
        
        # Update safety state
        self.safety_state.distance_to_liquidation = liq_risk.min_distance_percent
        
        # Store in history
        self.liquidation_history.append(liq_risk)
        
        return liq_risk
    
    def check_circuit_breakers(self, metrics: Dict[str, float]) -> List[str]:
        """Check all circuit breakers and return triggered ones."""
        triggered = []
        
        # Daily loss
        if 'daily_loss' in metrics:
            if self.circuit_breakers['daily_loss'].check_trigger(abs(metrics['daily_loss'])):
                triggered.append('daily_loss')
                self._create_circuit_breaker_alert('daily_loss', metrics['daily_loss'])
        
        # Funding cost
        if 'funding_cost_24h' in metrics:
            if self.circuit_breakers['funding_cost'].check_trigger(metrics['funding_cost_24h']):
                triggered.append('funding_cost')
                self._create_circuit_breaker_alert('funding_cost', metrics['funding_cost_24h'])
        
        # Volatility
        if 'volatility_24h' in metrics:
            if self.circuit_breakers['volatility'].check_trigger(metrics['volatility_24h']):
                triggered.append('volatility')
                self._create_circuit_breaker_alert('volatility', metrics['volatility_24h'])
        
        # Consecutive losses
        if 'consecutive_loss_days' in metrics:
            if self.circuit_breakers['consecutive_losses'].check_trigger(metrics['consecutive_loss_days']):
                triggered.append('consecutive_losses')
                self._create_circuit_breaker_alert('consecutive_losses', metrics['consecutive_loss_days'])
        
        # Update safety state
        self.safety_state.circuit_breakers_active = [
            name for name, cb in self.circuit_breakers.items() if cb.is_active
        ]
        
        # Check for resets
        for name, cb in self.circuit_breakers.items():
            if cb.check_reset():
                logger.info(f"Circuit breaker {name} reset after cooldown")
        
        return triggered
    
    def check_risk_limits(self, metrics: Dict[str, float]) -> List[Tuple[str, RiskLimit]]:
        """Check risk limits and return breached ones."""
        breached = []
        
        # Update current values
        if 'total_position_value' in metrics:
            self.risk_limits['position_value'].current_value = metrics['total_position_value']
            
        if 'leverage_ratio' in metrics:
            self.risk_limits['leverage'].current_value = metrics['leverage_ratio']
            
        if 'order_rate' in metrics:
            self.risk_limits['order_rate'].current_value = metrics['order_rate']
        
        # Check limits
        for name, limit in self.risk_limits.items():
            if limit.is_breached():
                breached.append((name, limit))
                self._create_risk_limit_alert(name, limit)
        
        return breached
    
    def check_panic_conditions(self, equity_metrics: Dict[str, float]) -> bool:
        """Check if panic conditions are met."""
        # Update equity drop
        if 'net_equity_drop' in equity_metrics:
            self.safety_state.net_equity_drop = equity_metrics['net_equity_drop']
        
        # Check panic conditions
        is_panic = self.safety_state.is_panic_condition()
        
        if is_panic:
            self._create_panic_alert()
        
        return is_panic
    
    def update_system_health(self, service_name: str, health_data: Dict[str, Any]):
        """Update system health for a service."""
        self.system_health.services[service_name] = {
            'healthy': health_data.get('healthy', False),
            'last_heartbeat': datetime.utcnow(),
            'response_time_ms': health_data.get('response_time_ms', 0),
            'details': health_data.get('details', {})
        }
        
        # Update last activity
        self.system_health.last_activity = datetime.utcnow()
        
        # Check if all critical services are healthy
        critical_services = ['position_manager', 'risk_engine', 'trade_executor']
        all_healthy = all(
            self.system_health.services.get(svc, {}).get('healthy', False)
            for svc in critical_services
        )
        
        self.safety_state.services_healthy = {
            svc: self.system_health.services.get(svc, {}).get('healthy', False)
            for svc in critical_services
        }
    
    def check_dead_mans_switch(self) -> bool:
        """Check if dead man's switch is triggered."""
        if self.system_health.is_dead_mans_switch_triggered():
            self._create_dead_mans_switch_alert()
            return True
        return False
    
    def record_emergency_action(
        self, 
        action: EmergencyAction,
        reason: str,
        success: bool,
        metrics_before: Dict[str, Any],
        metrics_after: Optional[Dict[str, Any]] = None
    ) -> EmergencyActionRecord:
        """Record an emergency action taken."""
        record = EmergencyActionRecord(
            action=action,
            reason=reason,
            triggered_by='automatic',
            risk_level_before=self.safety_state.current_risk_level,
            success=success,
            metrics_before=metrics_before,
            metrics_after=metrics_after or {}
        )
        
        if metrics_after:
            # Update risk level after action
            if action in [EmergencyAction.CLOSE_ALL, EmergencyAction.PANIC_CLOSE]:
                record.risk_level_after = RiskLevel.LOW
            elif action == EmergencyAction.REDUCE_POSITIONS:
                record.risk_level_after = RiskLevel.MEDIUM
        
        self.action_history.append(record)
        return record
    
    def get_deleveraging_schedule(self) -> List[float]:
        """Get gradual deleveraging schedule."""
        return self.config.deleveraging_steps
    
    def _create_circuit_breaker_alert(self, breaker_name: str, value: float):
        """Create alert for triggered circuit breaker."""
        cb = self.circuit_breakers[breaker_name]
        alert = SafetyAlert(
            alert_id=f"cb_{breaker_name}_{datetime.utcnow().timestamp()}",
            alert_type='circuit_breaker',
            severity=RiskLevel.HIGH,
            title=f"Circuit Breaker Triggered: {breaker_name}",
            message=f"{cb.description} triggered. Value: {value:.2f}, Threshold: {cb.threshold:.2f}",
            metrics={'breaker_name': breaker_name, 'value': value, 'threshold': cb.threshold},
            recommended_actions=[EmergencyAction.HALT_TRADING]
        )
        self.alert_history.append(alert)
    
    def _create_risk_limit_alert(self, limit_name: str, limit: RiskLimit):
        """Create alert for breached risk limit."""
        alert = SafetyAlert(
            alert_id=f"rl_{limit_name}_{datetime.utcnow().timestamp()}",
            alert_type='risk_limit',
            severity=limit.severity,
            title=f"Risk Limit Breached: {limit_name}",
            message=f"{limit.description} breached. Current: {limit.current_value:.2f}, Limit: {limit.limit_value:.2f}",
            metrics={
                'limit_name': limit_name,
                'current_value': limit.current_value,
                'limit_value': limit.limit_value,
                'breach_percent': limit.breach_percent()
            },
            recommended_actions=[limit.action_on_breach]
        )
        self.alert_history.append(alert)
    
    def _create_panic_alert(self):
        """Create panic condition alert."""
        alert = SafetyAlert(
            alert_id=f"panic_{datetime.utcnow().timestamp()}",
            alert_type='panic_condition',
            severity=RiskLevel.EMERGENCY,
            title="PANIC CONDITIONS DETECTED",
            message=f"Distance to liquidation: {self.safety_state.distance_to_liquidation:.1%}, "
                   f"Equity drop: {self.safety_state.net_equity_drop:.1%}",
            metrics={
                'distance_to_liquidation': self.safety_state.distance_to_liquidation,
                'net_equity_drop': self.safety_state.net_equity_drop
            },
            recommended_actions=[EmergencyAction.PANIC_CLOSE]
        )
        self.alert_history.append(alert)
    
    def _create_dead_mans_switch_alert(self):
        """Create dead man's switch alert."""
        alert = SafetyAlert(
            alert_id=f"dms_{datetime.utcnow().timestamp()}",
            alert_type='dead_mans_switch',
            severity=RiskLevel.CRITICAL,
            title="Dead Man's Switch Triggered",
            message=f"No activity for {self.system_health.activity_timeout_minutes} minutes",
            metrics={
                'last_activity': self.system_health.last_activity.isoformat(),
                'timeout_minutes': self.system_health.activity_timeout_minutes
            },
            recommended_actions=[EmergencyAction.CLOSE_ALL, EmergencyAction.HALT_TRADING]
        )
        self.alert_history.append(alert)
    
    def get_safety_metrics(self) -> Dict[str, Any]:
        """Get comprehensive safety metrics."""
        return {
            'current_risk_level': self.safety_state.current_risk_level.value,
            'distance_to_liquidation': self.safety_state.distance_to_liquidation,
            'net_equity_drop': self.safety_state.net_equity_drop,
            'daily_loss': self.safety_state.daily_loss,
            'leverage_ratio': self.safety_state.leverage_ratio,
            'circuit_breakers_active': len(self.safety_state.circuit_breakers_active),
            'active_breakers': self.safety_state.circuit_breakers_active,
            'unhealthy_services': self.system_health.get_unhealthy_services(),
            'dead_mans_switch_active': self.system_health.is_dead_mans_switch_triggered(),
            'recent_alerts': len([a for a in self.alert_history if not a.acknowledged]),
            'emergency_actions_today': len([
                a for a in self.action_history 
                if a.timestamp.date() == datetime.utcnow().date()
            ])
        }