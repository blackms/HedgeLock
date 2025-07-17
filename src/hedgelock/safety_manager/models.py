"""
Safety Manager data models.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class RiskLevel(Enum):
    """System risk levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class EmergencyAction(Enum):
    """Emergency actions that can be taken."""
    REDUCE_POSITIONS = "reduce_positions"
    CLOSE_LOSING = "close_losing_positions"
    CLOSE_ALL = "close_all_positions"
    HALT_TRADING = "halt_trading"
    DEPLOY_RESERVES = "deploy_reserves"
    PANIC_CLOSE = "panic_close"


class SafetyState(BaseModel):
    """Current safety state of the system."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Risk metrics
    current_risk_level: RiskLevel = Field(RiskLevel.LOW)
    distance_to_liquidation: float = Field(1.0, description="Distance to liquidation (0-1)")
    net_equity_drop: float = Field(0.0, description="Drop from peak equity")
    
    # Position metrics
    total_position_value: float = Field(0.0)
    leverage_ratio: float = Field(0.0)
    max_allowed_leverage: float = Field(25.0)
    
    # Loss metrics
    daily_loss: float = Field(0.0)
    max_daily_loss: float = Field(1000.0)
    consecutive_loss_days: int = Field(0)
    
    # System health
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    services_healthy: Dict[str, bool] = Field(default_factory=dict)
    circuit_breakers_active: List[str] = Field(default_factory=list)
    
    # Funding metrics
    funding_cost_24h: float = Field(0.0)
    max_funding_cost: float = Field(100.0)
    
    def is_panic_condition(self) -> bool:
        """Check if panic conditions are met."""
        return (
            self.distance_to_liquidation < 0.05 and 
            self.net_equity_drop > 0.10
        ) or self.current_risk_level == RiskLevel.EMERGENCY


class LiquidationRisk(BaseModel):
    """Liquidation risk assessment."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Liquidation metrics
    liquidation_price_long: float = Field(description="Liquidation price for long positions")
    liquidation_price_short: float = Field(description="Liquidation price for short positions")
    current_price: float = Field(description="Current BTC price")
    
    # Distance calculations
    distance_percent_long: float = Field(description="% distance to long liquidation")
    distance_percent_short: float = Field(description="% distance to short liquidation")
    min_distance_percent: float = Field(description="Minimum distance to any liquidation")
    
    # Risk assessment
    risk_level: RiskLevel
    time_to_liquidation_estimate: Optional[timedelta] = None
    recommended_action: Optional[EmergencyAction] = None
    
    def calculate_distances(self):
        """Calculate distances to liquidation."""
        if self.current_price > 0:
            self.distance_percent_long = abs(
                (self.liquidation_price_long - self.current_price) / self.current_price
            )
            self.distance_percent_short = abs(
                (self.current_price - self.liquidation_price_short) / self.current_price
            )
            self.min_distance_percent = min(
                self.distance_percent_long, 
                self.distance_percent_short
            )


class CircuitBreaker(BaseModel):
    """Circuit breaker configuration and state."""
    name: str
    description: str
    
    # Configuration
    threshold: float = Field(description="Threshold to trigger")
    cooldown_minutes: int = Field(30, description="Cooldown period after trigger")
    auto_reset: bool = Field(True, description="Auto-reset after cooldown")
    
    # State
    is_active: bool = Field(False)
    triggered_at: Optional[datetime] = None
    trigger_count: int = Field(0)
    last_value: float = Field(0.0)
    
    def check_trigger(self, value: float) -> bool:
        """Check if circuit breaker should trigger."""
        if self.is_active:
            return False  # Already triggered
            
        if value >= self.threshold:
            self.is_active = True
            self.triggered_at = datetime.utcnow()
            self.trigger_count += 1
            self.last_value = value
            return True
            
        return False
    
    def check_reset(self) -> bool:
        """Check if circuit breaker should reset."""
        if not self.is_active or not self.auto_reset:
            return False
            
        if self.triggered_at:
            elapsed = datetime.utcnow() - self.triggered_at
            if elapsed >= timedelta(minutes=self.cooldown_minutes):
                self.is_active = False
                return True
                
        return False


class RiskLimit(BaseModel):
    """Risk limit configuration."""
    name: str
    description: str
    
    # Limit configuration
    limit_type: str  # 'position', 'loss', 'funding', 'volatility'
    limit_value: float
    current_value: float = Field(0.0)
    
    # Actions when exceeded
    action_on_breach: EmergencyAction
    severity: RiskLevel
    
    def is_breached(self) -> bool:
        """Check if limit is breached."""
        return self.current_value >= self.limit_value
    
    def breach_percent(self) -> float:
        """Get percentage of limit used."""
        if self.limit_value > 0:
            return (self.current_value / self.limit_value) * 100
        return 0.0


class SystemHealth(BaseModel):
    """System health monitoring."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Service health
    services: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # Format: {
    #   'position_manager': {
    #       'healthy': True,
    #       'last_heartbeat': datetime,
    #       'response_time_ms': 50
    #   }
    # }
    
    # Dead man's switch
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    activity_timeout_minutes: int = Field(60)
    manual_override_active: bool = Field(False)
    
    # Dependency checks
    kafka_healthy: bool = Field(True)
    redis_healthy: bool = Field(True)
    postgres_healthy: bool = Field(True)
    
    def is_dead_mans_switch_triggered(self) -> bool:
        """Check if dead man's switch is triggered."""
        if self.manual_override_active:
            return False
            
        elapsed = datetime.utcnow() - self.last_activity
        return elapsed > timedelta(minutes=self.activity_timeout_minutes)
    
    def get_unhealthy_services(self) -> List[str]:
        """Get list of unhealthy services."""
        unhealthy = []
        for service, status in self.services.items():
            if not status.get('healthy', False):
                unhealthy.append(service)
        return unhealthy


class SafetyAlert(BaseModel):
    """Safety-related alert."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    alert_id: str = Field(description="Unique alert ID")
    
    # Alert details
    alert_type: str  # 'liquidation_risk', 'circuit_breaker', 'dead_mans_switch', etc.
    severity: RiskLevel
    title: str
    message: str
    
    # Context
    metrics: Dict[str, Any] = Field(default_factory=dict)
    recommended_actions: List[EmergencyAction] = Field(default_factory=list)
    
    # Status
    acknowledged: bool = Field(False)
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool = Field(False)
    resolved_at: Optional[datetime] = None


class EmergencyActionRecord(BaseModel):
    """Record of emergency action taken."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: EmergencyAction
    reason: str
    
    # Action details
    triggered_by: str  # 'automatic', 'manual', 'circuit_breaker', etc.
    risk_level_before: RiskLevel
    risk_level_after: Optional[RiskLevel] = None
    
    # Results
    success: bool = Field(False)
    positions_affected: int = Field(0)
    value_affected: float = Field(0.0)
    error_message: Optional[str] = None
    
    # Metrics before/after
    metrics_before: Dict[str, Any] = Field(default_factory=dict)
    metrics_after: Dict[str, Any] = Field(default_factory=dict)


class SafetyConfig(BaseModel):
    """Safety Manager configuration."""
    # Liquidation protection
    min_distance_to_liquidation: float = Field(0.10, description="Minimum 10% distance")
    panic_equity_drop: float = Field(0.10, description="10% equity drop triggers panic")
    deleveraging_steps: List[float] = Field(
        default=[0.8, 0.6, 0.4, 0.2], 
        description="Gradual position reduction steps"
    )
    
    # Circuit breakers
    daily_loss_limit: float = Field(1000.0, description="Max daily loss in USD")
    funding_cost_limit: float = Field(100.0, description="Max daily funding cost")
    volatility_limit: float = Field(0.10, description="Max 24h volatility")
    consecutive_loss_days_limit: int = Field(3, description="Max consecutive loss days")
    
    # Dead man's switch
    heartbeat_timeout_minutes: int = Field(60, description="Max time without activity")
    service_health_check_interval: int = Field(30, description="Seconds between health checks")
    
    # Risk limits
    max_position_value: float = Field(50000.0, description="Max total position value")
    max_leverage: float = Field(25.0, description="Maximum allowed leverage")
    max_order_rate_per_minute: int = Field(10, description="Rate limiting")
    
    # Emergency settings
    auto_deleverage_enabled: bool = Field(True)
    auto_close_on_panic: bool = Field(True)
    halt_on_circuit_breaker: bool = Field(True)