"""
Unit tests for LoanManager class.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.hedgelock.loan_manager.manager import LoanManager
from src.hedgelock.loan_manager.models import (
    LoanState, LoanRepaymentRequest, RepaymentPriority, LTVAction
)


class TestLoanManager:
    """Test LoanManager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create LoanManager instance."""
        return LoanManager(initial_principal=16200.0, apr=0.06)
    
    def test_initialization(self, manager):
        """Test loan manager initialization."""
        assert manager.loan_state.principal == 16200.0
        assert manager.loan_state.current_balance == 16200.0
        assert manager.loan_state.apr == 0.06
        assert manager.loan_state.total_paid == 0.0
        assert len(manager.repayment_history) == 0
    
    def test_calculate_accrued_interest(self, manager):
        """Test interest calculation."""
        # Set last interest calc to 1 day ago
        manager.loan_state.last_interest_calc = datetime.utcnow() - timedelta(days=1)
        
        interest = manager.calculate_accrued_interest()
        
        # Daily interest = 16200 * 0.06 / 365 = ~2.66
        expected_daily = 16200 * 0.06 / 365
        assert abs(interest - expected_daily) < 0.01
    
    def test_update_interest(self, manager):
        """Test interest update."""
        # Set last interest calc to 1 hour ago
        manager.loan_state.last_interest_calc = datetime.utcnow() - timedelta(hours=1)
        
        interest = manager.update_interest()
        
        # Hourly interest = 16200 * 0.06 / 365 / 24 = ~0.11
        expected_hourly = 16200 * 0.06 / 365 / 24
        assert abs(interest - expected_hourly) < 0.01
        assert manager.loan_state.accrued_interest > 0
        assert manager.loan_state.total_interest_accrued > 0
    
    def test_process_repayment_interest_first(self, manager):
        """Test repayment with interest-first priority."""
        # Add some accrued interest
        manager.loan_state.accrued_interest = 50.0
        
        # Make a payment
        request = LoanRepaymentRequest(
            amount=100.0,
            source="test",
            priority=RepaymentPriority.INTEREST_FIRST
        )
        
        record = manager.process_repayment(request)
        
        assert record.amount == 100.0
        assert record.interest_portion == 50.0  # Pay all interest first
        assert record.principal_portion == 50.0  # Remainder to principal
        assert manager.loan_state.current_balance == 16150.0  # 16200 - 50
        assert manager.loan_state.accrued_interest == 0.0  # All interest paid
    
    def test_process_repayment_principal_first(self, manager):
        """Test repayment with principal-first priority."""
        # Add some accrued interest
        manager.loan_state.accrued_interest = 50.0
        
        # Make a payment
        request = LoanRepaymentRequest(
            amount=100.0,
            source="test",
            priority=RepaymentPriority.PRINCIPAL_FIRST
        )
        
        record = manager.process_repayment(request)
        
        assert record.amount == 100.0
        assert record.principal_portion == 100.0  # All to principal
        assert record.interest_portion == 0.0  # None to interest
        assert manager.loan_state.current_balance == 16100.0  # 16200 - 100
        assert manager.loan_state.accrued_interest == 50.0  # Interest unchanged
    
    def test_process_repayment_proportional(self, manager):
        """Test repayment with proportional split."""
        # Add some accrued interest
        manager.loan_state.accrued_interest = 100.0  # Total debt = 16300
        
        # Make a payment
        request = LoanRepaymentRequest(
            amount=163.0,  # 1% of total debt
            source="test",
            priority=RepaymentPriority.PROPORTIONAL
        )
        
        record = manager.process_repayment(request)
        
        # Should split proportionally: ~99.4% to principal, ~0.6% to interest
        assert abs(record.principal_portion - 162.0) < 1.0
        assert abs(record.interest_portion - 1.0) < 1.0
    
    def test_calculate_ltv_safe(self, manager):
        """Test LTV calculation in safe zone."""
        # Collateral value > 2x loan
        ltv_state = manager.calculate_ltv(collateral_value=40000)
        
        assert ltv_state.ltv_ratio < 0.5  # Should be ~0.405
        assert ltv_state.current_action == LTVAction.SAFE
        assert ltv_state.reserve_deployment == 0.0
        assert ltv_state.position_scaling == 1.0
        assert ltv_state.health_score > 50
    
    def test_calculate_ltv_warning(self, manager):
        """Test LTV calculation in warning zone."""
        # LTV around 70%
        ltv_state = manager.calculate_ltv(collateral_value=23000)
        
        assert 0.65 < ltv_state.ltv_ratio < 0.75
        assert ltv_state.current_action == LTVAction.WARNING
        assert ltv_state.reserve_deployment > 0  # Should deploy reserves
        assert ltv_state.position_scaling == 0.5  # Reduce positions by 50%
    
    def test_calculate_ltv_critical(self, manager):
        """Test LTV calculation in critical zone."""
        # LTV around 80%
        ltv_state = manager.calculate_ltv(collateral_value=20000)
        
        assert 0.75 < ltv_state.ltv_ratio < 0.85
        assert ltv_state.current_action == LTVAction.CRITICAL
        assert ltv_state.reserve_deployment > 3000  # Should deploy more reserves
        assert ltv_state.position_scaling == 0.2  # Reduce to 20%
    
    def test_calculate_ltv_emergency(self, manager):
        """Test LTV calculation in emergency zone."""
        # LTV > 85%
        ltv_state = manager.calculate_ltv(collateral_value=18000)
        
        assert ltv_state.ltv_ratio > 0.85
        assert ltv_state.current_action == LTVAction.EMERGENCY
        assert ltv_state.reserve_deployment == 10000  # Deploy all reserves
        assert ltv_state.position_scaling == 0.0  # Close all positions
    
    def test_calculate_reserve_deployment(self, manager):
        """Test reserve deployment calculation."""
        # Create LTV state that needs deployment
        ltv_state = manager.calculate_ltv(collateral_value=23000)  # ~70% LTV
        
        # Test deployment with sufficient reserves
        deployment = manager.calculate_reserve_deployment(ltv_state, available_reserves=10000)
        
        assert deployment is not None
        assert deployment.deployment_amount > 0
        assert deployment.deployment_amount <= ltv_state.reserve_deployment
        assert deployment.to_reserve == 10000 - deployment.deployment_amount
        assert not deployment.emergency  # WARNING is not emergency
    
    def test_get_repayment_from_profit(self, manager):
        """Test profit-based repayment calculation."""
        # Test with $1000 profit
        repayment = manager.get_repayment_from_profit(1000, allocation_percent=0.5)
        
        assert repayment == 500  # 50% of profit
        
        # Test with small profit
        repayment = manager.get_repayment_from_profit(10, allocation_percent=0.5)
        
        assert repayment == 10  # Minimum payment
        
        # Test with no profit
        repayment = manager.get_repayment_from_profit(0, allocation_percent=0.5)
        
        assert repayment == 0
    
    def test_is_loan_paid_off(self, manager):
        """Test loan paid off check."""
        assert not manager.is_loan_paid_off()
        
        # Pay off the loan
        manager.loan_state.current_balance = 0
        manager.loan_state.accrued_interest = 0
        
        assert manager.is_loan_paid_off()
    
    def test_get_loan_metrics(self, manager):
        """Test loan metrics calculation."""
        # Make a payment
        manager.loan_state.principal_paid = 1000
        manager.loan_state.interest_paid = 50
        manager.loan_state.total_paid = 1050
        manager.loan_state.current_balance = 15200
        
        metrics = manager.get_loan_metrics()
        
        assert metrics['original_principal'] == 16200
        assert metrics['current_balance'] == 15200
        assert metrics['total_paid'] == 1050
        assert metrics['principal_paid'] == 1000
        assert metrics['interest_paid'] == 50
        assert metrics['repayment_progress'] == pytest.approx(6.17, rel=0.1)
    
    def test_estimate_payoff_time(self, manager):
        """Test payoff time estimation."""
        # Test with $500/month payment
        months = manager.estimate_payoff_time(500)
        
        # With 6% APR, should take ~35-36 months
        assert 34 < months < 37
        
        # Test with payment too low (doesn't cover interest)
        months = manager.estimate_payoff_time(50)
        
        assert months is None  # Can't pay off
        
        # Test with paid off loan
        manager.loan_state.current_balance = 0
        months = manager.estimate_payoff_time(500)
        
        assert months is None
    
    def test_get_recent_ltv_trend(self, manager):
        """Test recent LTV trend retrieval."""
        # Add some LTV history
        now = datetime.utcnow()
        
        # Add old entry (should not be included)
        old_ltv = manager.calculate_ltv(30000)
        manager.ltv_history[0].timestamp = now - timedelta(hours=25)
        
        # Add recent entries
        manager.calculate_ltv(28000)
        manager.calculate_ltv(26000)
        manager.calculate_ltv(24000)
        
        # Get 24h trend
        trend = manager.get_recent_ltv_trend(24)
        
        assert len(trend) == 3  # Should exclude the old one
        assert all(0 < ltv < 1 for ltv in trend)
    
    def test_payment_portions_edge_cases(self, manager):
        """Test payment portion calculation edge cases."""
        # Test payment larger than total debt
        manager.loan_state.accrued_interest = 50
        
        request = LoanRepaymentRequest(
            amount=20000,  # More than we owe
            source="test",
            priority=RepaymentPriority.INTEREST_FIRST
        )
        
        record = manager.process_repayment(request)
        
        # Should only pay what we owe
        assert record.principal_portion == 16200
        assert record.interest_portion == 50
        assert manager.loan_state.current_balance == 0
        assert manager.loan_state.accrued_interest == 0