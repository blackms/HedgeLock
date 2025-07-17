"""
Loan Manager data models.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class RepaymentPriority(Enum):
    """Priority levels for loan repayment."""
    INTEREST_FIRST = "interest_first"  # Pay interest before principal
    PRINCIPAL_FIRST = "principal_first"  # Pay principal before interest
    PROPORTIONAL = "proportional"  # Split between interest and principal


class LTVAction(Enum):
    """Actions based on LTV levels."""
    SAFE = "SAFE"  # LTV < 50%
    MONITOR = "MONITOR"  # 50% <= LTV < 65%
    WARNING = "WARNING"  # 65% <= LTV < 75% - Reduce positions by 50%
    CRITICAL = "CRITICAL"  # 75% <= LTV < 85% - Close losing positions
    EMERGENCY = "EMERGENCY"  # LTV >= 85% - Close all positions


class LoanState(BaseModel):
    """Current state of the loan."""
    # Loan details
    principal: float = Field(16200.0, description="Initial loan amount L(0)")
    current_balance: float = Field(16200.0, description="Current loan balance L(t)")
    apr: float = Field(0.06, description="Annual percentage rate")
    
    # Payment tracking
    total_paid: float = Field(0.0, description="Total amount paid to date")
    principal_paid: float = Field(0.0, description="Principal paid to date")
    interest_paid: float = Field(0.0, description="Interest paid to date")
    
    # Timing
    loan_start_date: datetime = Field(default_factory=datetime.utcnow)
    last_interest_calc: datetime = Field(default_factory=datetime.utcnow)
    last_payment_date: Optional[datetime] = None
    
    # Current state
    accrued_interest: float = Field(0.0, description="Interest accrued since last payment")
    total_interest_accrued: float = Field(0.0, description="Total interest accrued over loan lifetime")
    
    # Configuration
    repayment_priority: RepaymentPriority = RepaymentPriority.INTEREST_FIRST
    min_payment_amount: float = Field(10.0, description="Minimum payment amount in USD")
    
    def calculate_daily_interest(self) -> float:
        """Calculate daily interest amount."""
        return self.current_balance * self.apr / 365
    
    def calculate_hourly_interest(self) -> float:
        """Calculate hourly interest amount."""
        return self.current_balance * self.apr / 365 / 24
    
    def model_dump(self) -> dict:
        """Serialize to dict with enum handling."""
        data = super().model_dump()
        data['repayment_priority'] = self.repayment_priority.value
        return data


class RepaymentRecord(BaseModel):
    """Record of a loan repayment."""
    timestamp: datetime
    amount: float
    principal_portion: float
    interest_portion: float
    remaining_balance: float
    transaction_id: Optional[str] = None
    notes: Optional[str] = None


class LTVState(BaseModel):
    """Loan-to-Value state and metrics."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Values
    total_collateral_value: float = Field(description="Total value of collateral (spot BTC + USDC)")
    loan_balance: float = Field(description="Current loan balance")
    ltv_ratio: float = Field(description="Current LTV ratio (0-1)")
    
    # Thresholds
    safe_ltv: float = Field(0.50, description="Safe LTV threshold")
    warning_ltv: float = Field(0.65, description="Warning LTV threshold")
    critical_ltv: float = Field(0.75, description="Critical LTV threshold")
    emergency_ltv: float = Field(0.85, description="Emergency LTV threshold")
    liquidation_ltv: float = Field(0.95, description="Liquidation LTV threshold")
    
    # Current state
    current_action: LTVAction = Field(description="Current action based on LTV")
    reserve_deployment: float = Field(0.0, description="Amount of reserves to deploy")
    position_scaling: float = Field(1.0, description="Position size multiplier (0-1)")
    
    # Risk metrics
    distance_to_liquidation: float = Field(description="Distance to liquidation (0-1)")
    health_score: float = Field(description="Overall health score (0-100)")
    
    def get_action_for_ltv(self, ltv: float) -> LTVAction:
        """Determine action based on LTV ratio."""
        if ltv < self.safe_ltv:
            return LTVAction.SAFE
        elif ltv < self.warning_ltv:
            return LTVAction.MONITOR
        elif ltv < self.critical_ltv:
            return LTVAction.WARNING
        elif ltv < self.emergency_ltv:
            return LTVAction.CRITICAL
        else:
            return LTVAction.EMERGENCY
    
    def calculate_reserve_deployment(self) -> float:
        """Calculate how much reserve to deploy based on LTV."""
        if self.ltv_ratio < 0.65:
            return 0.0
        elif self.ltv_ratio < 0.75:
            # Deploy proportionally between 0 and 3000
            return 3000 * (self.ltv_ratio - 0.65) / 0.10
        elif self.ltv_ratio < 0.85:
            # Deploy proportionally between 3000 and 8000
            return 3000 + 5000 * (self.ltv_ratio - 0.75) / 0.10
        else:
            # Deploy all reserves
            return 10000.0
    
    def calculate_position_scaling(self) -> float:
        """Calculate position size multiplier based on LTV."""
        if self.ltv_ratio < self.warning_ltv:
            return 1.0  # Full size
        elif self.ltv_ratio < self.critical_ltv:
            return 0.5  # Reduce by 50%
        elif self.ltv_ratio < self.emergency_ltv:
            return 0.2  # Reduce to 20%
        else:
            return 0.0  # Close all


class ReserveDeployment(BaseModel):
    """Reserve deployment decision."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ltv_ratio: float
    deployment_amount: float
    deployment_reason: str
    from_reserve: float = Field(10000.0, description="Reserve before deployment")
    to_reserve: float = Field(description="Reserve after deployment")
    to_collateral: float = Field(description="Amount added to collateral")
    emergency: bool = Field(False, description="Is this an emergency deployment")


class LoanRepaymentRequest(BaseModel):
    """Request to repay loan."""
    amount: float = Field(gt=0, description="Amount to repay")
    source: str = Field(description="Source of funds (e.g., 'trading_profit', 'manual')")
    priority: Optional[RepaymentPriority] = None
    notes: Optional[str] = None


class LoanManagerConfig(BaseModel):
    """Configuration for Loan Manager."""
    # Loan parameters
    initial_principal: float = Field(16200.0)
    apr: float = Field(0.06)
    
    # Repayment settings
    auto_repay_enabled: bool = Field(True)
    repayment_priority: RepaymentPriority = Field(RepaymentPriority.INTEREST_FIRST)
    min_payment_amount: float = Field(10.0)
    profit_allocation_percent: float = Field(0.5, description="Percent of profits to allocate to loan repayment")
    
    # LTV settings
    ltv_check_interval: int = Field(60, description="Seconds between LTV checks")
    reserve_deployment_enabled: bool = Field(True)
    emergency_deployment_threshold: float = Field(0.85)
    
    # Alert settings
    alert_on_high_ltv: bool = Field(True)
    alert_ltv_threshold: float = Field(0.70)