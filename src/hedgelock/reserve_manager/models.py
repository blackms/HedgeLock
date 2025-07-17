"""
Reserve Manager data models.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class DeploymentAction(Enum):
    """Types of reserve deployment actions."""
    DEPLOY_TO_COLLATERAL = "deploy_to_collateral"  # Add to collateral
    DEPLOY_TO_TRADING = "deploy_to_trading"  # Add to trading capital
    WITHDRAW_FROM_TRADING = "withdraw_from_trading"  # Pull back from trading
    REBALANCE = "rebalance"  # Rebalance after profits
    EMERGENCY_DEPLOY = "emergency_deploy"  # Emergency deployment


class ReserveState(BaseModel):
    """Current state of reserves."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Reserve balances
    total_reserves: float = Field(10000.0, description="Total USDC reserves")
    available_reserves: float = Field(10000.0, description="Available for deployment")
    deployed_reserves: float = Field(0.0, description="Currently deployed")
    
    # Deployment breakdown
    deployed_to_collateral: float = Field(0.0, description="Deployed as collateral")
    deployed_to_trading: float = Field(0.0, description="Deployed for trading")
    
    # Limits and thresholds
    min_reserve_balance: float = Field(1000.0, description="Minimum reserve to maintain")
    max_deployment_percent: float = Field(0.9, description="Max percent deployable")
    
    # Current metrics
    deployment_ratio: float = Field(0.0, description="Deployed / Total")
    reserve_health: float = Field(100.0, description="Reserve health score")
    
    def calculate_deployable_amount(self) -> float:
        """Calculate maximum deployable amount."""
        max_deployable = self.total_reserves * self.max_deployment_percent
        current_deployable = max_deployable - self.deployed_reserves
        available_deployable = self.available_reserves - self.min_reserve_balance
        return max(0, min(current_deployable, available_deployable))
    
    def update_deployment(self, amount: float, action: DeploymentAction):
        """Update reserve state after deployment."""
        if action == DeploymentAction.DEPLOY_TO_COLLATERAL:
            self.deployed_to_collateral += amount
            self.deployed_reserves += amount
            self.available_reserves -= amount
        elif action == DeploymentAction.DEPLOY_TO_TRADING:
            self.deployed_to_trading += amount
            self.deployed_reserves += amount
            self.available_reserves -= amount
        elif action == DeploymentAction.WITHDRAW_FROM_TRADING:
            self.deployed_to_trading -= amount
            self.deployed_reserves -= amount
            self.available_reserves += amount
        
        # Update metrics
        self.deployment_ratio = self.deployed_reserves / self.total_reserves if self.total_reserves > 0 else 0
        self.reserve_health = (self.available_reserves / self.total_reserves) * 100 if self.total_reserves > 0 else 0


class DeploymentRequest(BaseModel):
    """Request for reserve deployment."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    amount: float = Field(gt=0, description="Amount to deploy")
    action: DeploymentAction
    reason: str
    ltv_ratio: Optional[float] = None
    emergency: bool = Field(False)
    requester: str = Field(description="Service requesting deployment")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeploymentRecord(BaseModel):
    """Record of a reserve deployment."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request: DeploymentRequest
    
    # Deployment details
    amount_requested: float
    amount_deployed: float
    action: DeploymentAction
    
    # State before and after
    reserves_before: float
    reserves_after: float
    deployed_before: float
    deployed_after: float
    
    # Result
    success: bool
    reason: Optional[str] = None
    transaction_id: Optional[str] = None


class ReserveRebalanceRequest(BaseModel):
    """Request to rebalance reserves after profit."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    profit_amount: float = Field(description="Profit to add to reserves")
    source: str = Field(description="Source of profit")
    
    # Rebalancing parameters
    target_reserve_ratio: float = Field(0.2, description="Target reserve/capital ratio")
    min_reserve_addition: float = Field(100.0, description="Minimum to add to reserves")
    
    # Distribution
    to_reserves: Optional[float] = None
    to_loan_repayment: Optional[float] = None
    to_trading_capital: Optional[float] = None


class ReserveAlert(BaseModel):
    """Reserve-related alert."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    alert_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    message: str
    
    # Alert details
    current_reserves: float
    available_reserves: float
    deployment_ratio: float
    
    # Action required
    action_required: bool = Field(False)
    suggested_action: Optional[str] = None


class ReserveManagerConfig(BaseModel):
    """Configuration for Reserve Manager."""
    # Initial reserves
    initial_reserves: float = Field(10000.0)
    
    # Deployment limits
    min_reserve_balance: float = Field(1000.0)
    max_deployment_percent: float = Field(0.9)
    max_single_deployment: float = Field(5000.0)
    
    # Rebalancing settings
    profit_to_reserve_percent: float = Field(0.2, description="Percent of profit to reserves")
    target_reserve_ratio: float = Field(0.2, description="Target reserve/capital ratio")
    rebalance_check_interval: int = Field(300, description="Seconds between rebalance checks")
    
    # Emergency settings
    emergency_deployment_enabled: bool = Field(True)
    emergency_ltv_threshold: float = Field(0.85)
    
    # Alert settings
    low_reserve_alert_threshold: float = Field(2000.0)
    high_deployment_alert_percent: float = Field(0.8)