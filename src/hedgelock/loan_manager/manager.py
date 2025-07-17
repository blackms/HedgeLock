"""
Core Loan Manager implementation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

from .models import (
    LoanState, RepaymentRecord, LTVState, ReserveDeployment,
    LoanRepaymentRequest, RepaymentPriority, LTVAction
)

logger = logging.getLogger(__name__)


class LoanManager:
    """Manages loan tracking, repayment, and LTV monitoring."""
    
    def __init__(self, initial_principal: float = 16200.0, apr: float = 0.06):
        """Initialize loan manager with loan parameters."""
        self.loan_state = LoanState(
            principal=initial_principal,
            current_balance=initial_principal,
            apr=apr
        )
        self.repayment_history: List[RepaymentRecord] = []
        self.ltv_history: List[LTVState] = []
        self.deployment_history: List[ReserveDeployment] = []
    
    def calculate_accrued_interest(self) -> float:
        """Calculate interest accrued since last calculation."""
        now = datetime.utcnow()
        time_delta = now - self.loan_state.last_interest_calc
        hours_elapsed = time_delta.total_seconds() / 3600
        
        # Calculate interest
        hourly_rate = self.loan_state.apr / 365 / 24
        interest = self.loan_state.current_balance * hourly_rate * hours_elapsed
        
        return interest
    
    def update_interest(self) -> float:
        """Update accrued interest and return the amount."""
        interest = self.calculate_accrued_interest()
        
        self.loan_state.accrued_interest += interest
        self.loan_state.total_interest_accrued += interest
        self.loan_state.last_interest_calc = datetime.utcnow()
        
        logger.info(f"Updated interest: ${interest:.2f} accrued, "
                   f"total accrued: ${self.loan_state.accrued_interest:.2f}")
        
        return interest
    
    def process_repayment(self, request: LoanRepaymentRequest) -> RepaymentRecord:
        """Process a loan repayment."""
        # Update interest first
        self.update_interest()
        
        # Determine repayment priority
        priority = request.priority or self.loan_state.repayment_priority
        
        # Calculate portions
        principal_portion, interest_portion = self._calculate_payment_portions(
            request.amount, priority
        )
        
        # Apply payment
        self.loan_state.current_balance -= principal_portion
        self.loan_state.principal_paid += principal_portion
        self.loan_state.interest_paid += interest_portion
        self.loan_state.accrued_interest -= interest_portion
        self.loan_state.total_paid += request.amount
        self.loan_state.last_payment_date = datetime.utcnow()
        
        # Create repayment record
        record = RepaymentRecord(
            timestamp=datetime.utcnow(),
            amount=request.amount,
            principal_portion=principal_portion,
            interest_portion=interest_portion,
            remaining_balance=self.loan_state.current_balance,
            notes=request.notes
        )
        
        self.repayment_history.append(record)
        
        logger.info(f"Processed repayment: ${request.amount:.2f} "
                   f"(principal: ${principal_portion:.2f}, interest: ${interest_portion:.2f}), "
                   f"remaining: ${self.loan_state.current_balance:.2f}")
        
        return record
    
    def _calculate_payment_portions(
        self, amount: float, priority: RepaymentPriority
    ) -> Tuple[float, float]:
        """Calculate how to split payment between principal and interest."""
        if priority == RepaymentPriority.INTEREST_FIRST:
            # Pay interest first, remainder to principal
            interest_portion = min(amount, self.loan_state.accrued_interest)
            principal_portion = amount - interest_portion
            principal_portion = min(principal_portion, self.loan_state.current_balance)
            
        elif priority == RepaymentPriority.PRINCIPAL_FIRST:
            # Pay principal first, remainder to interest
            principal_portion = min(amount, self.loan_state.current_balance)
            interest_portion = amount - principal_portion
            interest_portion = min(interest_portion, self.loan_state.accrued_interest)
            
        else:  # PROPORTIONAL
            # Split proportionally based on current balances
            total_owed = self.loan_state.current_balance + self.loan_state.accrued_interest
            if total_owed > 0:
                principal_ratio = self.loan_state.current_balance / total_owed
                principal_portion = min(amount * principal_ratio, self.loan_state.current_balance)
                interest_portion = min(amount - principal_portion, self.loan_state.accrued_interest)
            else:
                principal_portion = interest_portion = 0
        
        return principal_portion, interest_portion
    
    def calculate_ltv(self, collateral_value: float) -> LTVState:
        """Calculate current LTV and determine required actions."""
        # Update interest first
        self.update_interest()
        
        # Calculate total debt (principal + accrued interest)
        total_debt = self.loan_state.current_balance + self.loan_state.accrued_interest
        
        # Calculate LTV
        ltv_ratio = total_debt / collateral_value if collateral_value > 0 else 1.0
        
        # Create LTV state
        ltv_state = LTVState(
            total_collateral_value=collateral_value,
            loan_balance=total_debt,
            ltv_ratio=ltv_ratio,
            current_action=LTVAction.SAFE,  # Will be updated below
            distance_to_liquidation=max(0, (0.95 - ltv_ratio) / 0.95),
            health_score=max(0, min(100, (1 - ltv_ratio) * 100))
        )
        
        # Determine action and deployments
        ltv_state.current_action = ltv_state.get_action_for_ltv(ltv_ratio)
        ltv_state.reserve_deployment = ltv_state.calculate_reserve_deployment()
        ltv_state.position_scaling = ltv_state.calculate_position_scaling()
        
        # Store in history
        self.ltv_history.append(ltv_state)
        
        # Log if concerning
        if ltv_state.current_action != LTVAction.SAFE:
            logger.warning(f"LTV {ltv_ratio:.1%} - Action: {ltv_state.current_action.value}, "
                          f"Deploy reserves: ${ltv_state.reserve_deployment:.0f}, "
                          f"Scale positions: {ltv_state.position_scaling:.0%}")
        
        return ltv_state
    
    def calculate_reserve_deployment(
        self, ltv_state: LTVState, available_reserves: float
    ) -> Optional[ReserveDeployment]:
        """Calculate and create reserve deployment if needed."""
        if ltv_state.reserve_deployment <= 0:
            return None
        
        # Limit deployment to available reserves
        deployment_amount = min(ltv_state.reserve_deployment, available_reserves)
        
        if deployment_amount < 1:  # Minimum $1 deployment
            return None
        
        deployment = ReserveDeployment(
            ltv_ratio=ltv_state.ltv_ratio,
            deployment_amount=deployment_amount,
            deployment_reason=f"LTV {ltv_state.ltv_ratio:.1%} - {ltv_state.current_action.value}",
            from_reserve=available_reserves,
            to_reserve=available_reserves - deployment_amount,
            to_collateral=deployment_amount,
            emergency=ltv_state.current_action in [LTVAction.CRITICAL, LTVAction.EMERGENCY]
        )
        
        self.deployment_history.append(deployment)
        
        logger.info(f"Reserve deployment: ${deployment_amount:.2f} "
                   f"(LTV: {ltv_state.ltv_ratio:.1%}, Action: {ltv_state.current_action.value})")
        
        return deployment
    
    def get_repayment_from_profit(self, profit: float, allocation_percent: float = 0.5) -> float:
        """Calculate loan repayment amount from trading profit."""
        if profit <= 0:
            return 0
        
        # Allocate percentage of profit to loan repayment
        repayment_amount = profit * allocation_percent
        
        # Ensure minimum payment if we have profit
        repayment_amount = max(repayment_amount, self.loan_state.min_payment_amount)
        
        # Don't pay more than we owe
        total_owed = self.loan_state.current_balance + self.loan_state.accrued_interest
        repayment_amount = min(repayment_amount, total_owed)
        
        return repayment_amount
    
    def get_loan_metrics(self) -> Dict[str, float]:
        """Get comprehensive loan metrics."""
        # Update interest
        self.update_interest()
        
        total_debt = self.loan_state.current_balance + self.loan_state.accrued_interest
        
        return {
            'original_principal': self.loan_state.principal,
            'current_balance': self.loan_state.current_balance,
            'accrued_interest': self.loan_state.accrued_interest,
            'total_debt': total_debt,
            'total_paid': self.loan_state.total_paid,
            'principal_paid': self.loan_state.principal_paid,
            'interest_paid': self.loan_state.interest_paid,
            'total_interest_accrued': self.loan_state.total_interest_accrued,
            'apr': self.loan_state.apr,
            'daily_interest': self.loan_state.calculate_daily_interest(),
            'repayment_progress': (self.loan_state.principal_paid / self.loan_state.principal) * 100,
            'days_since_start': (datetime.utcnow() - self.loan_state.loan_start_date).days
        }
    
    def is_loan_paid_off(self) -> bool:
        """Check if loan is fully paid off."""
        return self.loan_state.current_balance <= 0 and self.loan_state.accrued_interest <= 0
    
    def get_recent_ltv_trend(self, hours: int = 24) -> List[float]:
        """Get recent LTV values for trend analysis."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent_ltvs = [
            ltv.ltv_ratio for ltv in self.ltv_history
            if ltv.timestamp >= cutoff
        ]
        return recent_ltvs
    
    def estimate_payoff_time(self, monthly_payment: float) -> Optional[int]:
        """Estimate months to pay off loan at given payment rate."""
        if monthly_payment <= 0 or self.is_loan_paid_off():
            return None
        
        # Simple estimation (doesn't account for compounding)
        monthly_interest = self.loan_state.current_balance * self.loan_state.apr / 12
        
        if monthly_payment <= monthly_interest:
            return None  # Payment doesn't cover interest
        
        # Calculate months to pay off
        principal_payment = monthly_payment - monthly_interest
        months = self.loan_state.current_balance / principal_payment
        
        return int(months + 0.5)  # Round up