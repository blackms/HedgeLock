"""
Core Reserve Manager implementation.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from .models import (
    ReserveState, DeploymentRequest, DeploymentRecord,
    DeploymentAction, ReserveRebalanceRequest, ReserveAlert
)

logger = logging.getLogger(__name__)


class ReserveManager:
    """Manages USDC reserves and deployments."""
    
    def __init__(self, initial_reserves: float = 10000.0):
        """Initialize reserve manager."""
        self.reserve_state = ReserveState(
            total_reserves=initial_reserves,
            available_reserves=initial_reserves
        )
        self.deployment_history: List[DeploymentRecord] = []
        self.alert_history: List[ReserveAlert] = []
    
    def process_deployment_request(self, request: DeploymentRequest) -> DeploymentRecord:
        """Process a reserve deployment request."""
        # Validate request
        deployable = self.reserve_state.calculate_deployable_amount()
        
        # Determine actual deployment amount
        if request.emergency and request.action == DeploymentAction.EMERGENCY_DEPLOY:
            # Emergency deployment can use more reserves
            amount_to_deploy = min(
                request.amount,
                self.reserve_state.available_reserves - 100  # Keep at least $100
            )
        else:
            # Normal deployment respects limits
            amount_to_deploy = min(request.amount, deployable)
        
        # Create deployment record
        record = DeploymentRecord(
            request=request,
            amount_requested=request.amount,
            amount_deployed=amount_to_deploy,
            action=request.action,
            reserves_before=self.reserve_state.available_reserves,
            deployed_before=self.reserve_state.deployed_reserves,
            reserves_after=0,  # Will be updated
            deployed_after=0,  # Will be updated
            success=False
        )
        
        # Check if deployment is possible
        if amount_to_deploy <= 0:
            record.reason = "Insufficient reserves available"
            logger.warning(f"Deployment rejected: {record.reason}")
            self.deployment_history.append(record)
            return record
        
        # Execute deployment
        try:
            self.reserve_state.update_deployment(amount_to_deploy, request.action)
            
            record.reserves_after = self.reserve_state.available_reserves
            record.deployed_after = self.reserve_state.deployed_reserves
            record.success = True
            record.reason = f"Deployed ${amount_to_deploy:.2f} for {request.reason}"
            
            logger.info(f"Reserve deployment: ${amount_to_deploy:.2f} "
                       f"({request.action.value}) - {request.reason}")
            
            # Check for alerts
            self._check_reserve_alerts()
            
        except Exception as e:
            record.success = False
            record.reason = f"Deployment failed: {str(e)}"
            logger.error(f"Deployment error: {e}")
        
        self.deployment_history.append(record)
        return record
    
    def process_profit_rebalance(self, request: ReserveRebalanceRequest) -> Dict[str, float]:
        """Process profit rebalancing to reserves."""
        # Calculate distribution
        distribution = self._calculate_profit_distribution(request)
        
        # Add to reserves
        if distribution['to_reserves'] > 0:
            self.reserve_state.total_reserves += distribution['to_reserves']
            self.reserve_state.available_reserves += distribution['to_reserves']
            
            # Update health score
            self.reserve_state.reserve_health = min(100, (
                self.reserve_state.available_reserves / self.reserve_state.total_reserves * 100
            ))
            
            logger.info(f"Added ${distribution['to_reserves']:.2f} to reserves from profit")
        
        return distribution
    
    def _calculate_profit_distribution(self, request: ReserveRebalanceRequest) -> Dict[str, float]:
        """Calculate how to distribute profit."""
        profit = request.profit_amount
        
        # Default distribution
        distribution = {
            'to_reserves': 0,
            'to_loan_repayment': 0,
            'to_trading_capital': 0
        }
        
        if profit <= 0:
            return distribution
        
        # Calculate current reserve ratio
        total_capital = self.reserve_state.total_reserves + self.reserve_state.deployed_to_trading
        current_ratio = self.reserve_state.total_reserves / total_capital if total_capital > 0 else 0
        
        # If below target ratio, prioritize reserves
        if current_ratio < request.target_reserve_ratio:
            # Add more to reserves
            reserve_deficit = (request.target_reserve_ratio * total_capital) - self.reserve_state.total_reserves
            distribution['to_reserves'] = min(profit * 0.5, reserve_deficit)
        else:
            # Standard allocation
            distribution['to_reserves'] = max(
                request.min_reserve_addition,
                profit * 0.2  # 20% to reserves
            )
        
        # Remaining profit for loan repayment
        remaining = profit - distribution['to_reserves']
        distribution['to_loan_repayment'] = remaining * 0.5  # 50% of remaining
        distribution['to_trading_capital'] = remaining * 0.5  # 50% of remaining
        
        return distribution
    
    def withdraw_from_trading(self, amount: float, reason: str) -> bool:
        """Withdraw reserves from trading back to available."""
        if amount > self.reserve_state.deployed_to_trading:
            logger.error(f"Cannot withdraw ${amount:.2f} - only ${self.reserve_state.deployed_to_trading:.2f} deployed")
            return False
        
        request = DeploymentRequest(
            amount=amount,
            action=DeploymentAction.WITHDRAW_FROM_TRADING,
            reason=reason,
            requester="reserve_manager"
        )
        
        record = self.process_deployment_request(request)
        return record.success
    
    def get_deployment_capacity(self, emergency: bool = False) -> float:
        """Get current deployment capacity."""
        if emergency:
            # Emergency can use almost all reserves
            return max(0, self.reserve_state.available_reserves - 100)
        else:
            # Normal deployment respects limits
            return self.reserve_state.calculate_deployable_amount()
    
    def _check_reserve_alerts(self):
        """Check and create alerts for reserve conditions."""
        # Low reserves alert
        if self.reserve_state.available_reserves < 2000:
            alert = ReserveAlert(
                alert_type="LOW_RESERVES",
                severity="HIGH" if self.reserve_state.available_reserves < 1000 else "MEDIUM",
                message=f"Low reserves: ${self.reserve_state.available_reserves:.2f} available",
                current_reserves=self.reserve_state.total_reserves,
                available_reserves=self.reserve_state.available_reserves,
                deployment_ratio=self.reserve_state.deployment_ratio,
                action_required=True,
                suggested_action="Consider withdrawing from trading positions"
            )
            self.alert_history.append(alert)
            logger.warning(f"Reserve alert: {alert.message}")
        
        # High deployment alert
        if self.reserve_state.deployment_ratio > 0.8:
            alert = ReserveAlert(
                alert_type="HIGH_DEPLOYMENT",
                severity="MEDIUM",
                message=f"High deployment ratio: {self.reserve_state.deployment_ratio:.1%}",
                current_reserves=self.reserve_state.total_reserves,
                available_reserves=self.reserve_state.available_reserves,
                deployment_ratio=self.reserve_state.deployment_ratio,
                action_required=False
            )
            self.alert_history.append(alert)
    
    def get_reserve_metrics(self) -> Dict[str, float]:
        """Get comprehensive reserve metrics."""
        return {
            'total_reserves': self.reserve_state.total_reserves,
            'available_reserves': self.reserve_state.available_reserves,
            'deployed_reserves': self.reserve_state.deployed_reserves,
            'deployed_to_collateral': self.reserve_state.deployed_to_collateral,
            'deployed_to_trading': self.reserve_state.deployed_to_trading,
            'deployment_ratio': self.reserve_state.deployment_ratio,
            'deployable_amount': self.reserve_state.calculate_deployable_amount(),
            'reserve_health': self.reserve_state.reserve_health,
            'min_reserve_balance': self.reserve_state.min_reserve_balance,
            'total_deployments': len(self.deployment_history),
            'successful_deployments': len([d for d in self.deployment_history if d.success])
        }
    
    def get_recent_deployments(self, hours: int = 24) -> List[DeploymentRecord]:
        """Get recent deployment history."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [d for d in self.deployment_history if d.timestamp >= cutoff]
    
    def calculate_deployment_for_ltv(self, ltv_ratio: float) -> float:
        """Calculate reserve deployment amount based on LTV."""
        if ltv_ratio < 0.65:
            return 0.0
        elif ltv_ratio < 0.75:
            # Deploy proportionally between 0 and 3000
            deployment = 3000 * (ltv_ratio - 0.65) / 0.10
        elif ltv_ratio < 0.85:
            # Deploy proportionally between 3000 and 8000
            deployment = 3000 + 5000 * (ltv_ratio - 0.75) / 0.10
        else:
            # Emergency - deploy maximum available
            deployment = self.get_deployment_capacity(emergency=True)
        
        # Limit to available capacity
        return min(deployment, self.get_deployment_capacity(emergency=ltv_ratio >= 0.85))