"""
Risk calculation engine.
"""

import time
from typing import Optional, Dict, Tuple
from src.hedgelock.config import settings
from src.hedgelock.logging import get_logger
from src.hedgelock.risk_engine.models import (
    RiskState, AccountData, RiskCalculation, RiskStateMessage
)

logger = get_logger(__name__)


class RiskCalculator:
    """Calculates risk metrics and determines risk state."""
    
    def __init__(self):
        self.config = settings.risk
        self.previous_state: Optional[RiskState] = None
        self.state_history: list = []
        
    def calculate_risk(self, account_data: AccountData, trace_id: Optional[str] = None) -> RiskCalculation:
        """Calculate risk metrics from account data."""
        start_time = time.time()
        
        # Calculate core metrics
        ltv = account_data.ltv
        net_delta = account_data.net_delta
        
        # Determine risk state
        risk_state = self._determine_risk_state(ltv)
        
        # Calculate risk score (0-100)
        risk_score = self._calculate_risk_score(ltv, net_delta)
        
        # Calculate individual risk factors
        risk_factors = {
            "ltv_risk": min(ltv * 100, 100),
            "delta_risk": abs(net_delta) * 10,  # Scale delta to 0-100
            "collateral_usage": (account_data.used_collateral / account_data.total_collateral_value * 100) if account_data.total_collateral_value > 0 else 0
        }
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        calculation = RiskCalculation(
            account_data=account_data,
            ltv=ltv,
            net_delta=net_delta,
            risk_state=risk_state,
            risk_score=risk_score,
            risk_factors=risk_factors,
            processing_time_ms=processing_time_ms,
            trace_id=trace_id
        )
        
        logger.info(
            "Risk calculation completed",
            ltv=ltv,
            net_delta=net_delta,
            risk_state=risk_state.value,
            risk_score=risk_score,
            processing_time_ms=processing_time_ms,
            trace_id=trace_id
        )
        
        return calculation
    
    def _determine_risk_state(self, ltv: float) -> RiskState:
        """Determine risk state based on LTV."""
        if ltv >= self.config.ltv_critical_threshold:
            return RiskState.CRITICAL
        elif ltv >= self.config.ltv_danger_threshold:
            return RiskState.DANGER
        elif ltv >= self.config.ltv_caution_threshold:
            return RiskState.CAUTION
        else:
            return RiskState.NORMAL
    
    def _calculate_risk_score(self, ltv: float, net_delta: float) -> float:
        """Calculate overall risk score from 0-100."""
        # LTV contributes 70% of risk score
        ltv_score = min(ltv * 100, 100) * 0.7
        
        # Delta risk contributes 30% of risk score
        # Higher absolute delta = higher risk
        delta_score = min(abs(net_delta) * 10, 100) * 0.3
        
        return round(ltv_score + delta_score, 2)
    
    def create_risk_state_message(self, calculation: RiskCalculation) -> RiskStateMessage:
        """Create message for risk_state topic."""
        state_changed = calculation.risk_state != self.previous_state
        
        # Generate hedge recommendation
        hedge_recommendation = self._generate_hedge_recommendation(
            calculation.risk_state,
            calculation.net_delta
        )
        
        message = RiskStateMessage(
            risk_state=calculation.risk_state,
            previous_state=self.previous_state,
            state_changed=state_changed,
            ltv=calculation.ltv,
            net_delta=calculation.net_delta,
            risk_score=calculation.risk_score,
            hedge_recommendation=hedge_recommendation,
            total_collateral_value=calculation.account_data.total_collateral_value,
            total_loan_value=calculation.account_data.total_loan_value,
            available_collateral=calculation.account_data.available_collateral,
            trace_id=calculation.trace_id,
            processing_time_ms=calculation.processing_time_ms
        )
        
        # Update state tracking
        self.previous_state = calculation.risk_state
        self.state_history.append({
            "timestamp": message.timestamp,
            "state": calculation.risk_state,
            "ltv": calculation.ltv
        })
        
        # Keep only last 100 state changes
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]
        
        return message
    
    def _generate_hedge_recommendation(self, risk_state: RiskState, current_delta: float) -> Optional[Dict]:
        """Generate hedge recommendation based on risk state."""
        target_delta = self._get_target_delta(risk_state)
        delta_difference = target_delta - current_delta
        
        if abs(delta_difference) < 0.001:  # Less than 0.001 BTC difference
            return None
        
        return {
            "action": "BUY" if delta_difference > 0 else "SELL",
            "symbol": "BTCUSDT",
            "quantity": abs(delta_difference),
            "reason": f"Adjust delta from {current_delta:.4f} to {target_delta:.4f} for {risk_state.value} state",
            "urgency": self._get_urgency(risk_state)
        }
    
    def _get_target_delta(self, risk_state: RiskState) -> float:
        """Get target delta for given risk state."""
        if risk_state == RiskState.NORMAL:
            return self.config.net_delta_normal
        elif risk_state == RiskState.CAUTION:
            return self.config.net_delta_caution
        elif risk_state == RiskState.DANGER:
            return self.config.net_delta_danger
        else:  # CRITICAL
            return self.config.net_delta_critical
    
    def _get_urgency(self, risk_state: RiskState) -> str:
        """Get urgency level for hedge recommendation."""
        if risk_state == RiskState.CRITICAL:
            return "IMMEDIATE"
        elif risk_state == RiskState.DANGER:
            return "HIGH"
        elif risk_state == RiskState.CAUTION:
            return "MEDIUM"
        else:
            return "LOW"