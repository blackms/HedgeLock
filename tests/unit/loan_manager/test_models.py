"""
Unit tests for Loan Manager models.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.hedgelock.loan_manager.models import (
    LoanState, RepaymentRecord, LTVState, ReserveDeployment,
    LoanRepaymentRequest, RepaymentPriority, LTVAction,
    LoanManagerConfig
)


class TestLoanState:
    """Test LoanState model."""
    
    def test_default_initialization(self):
        """Test default loan state initialization."""
        state = LoanState()
        
        assert state.principal == 16200.0
        assert state.current_balance == 16200.0
        assert state.apr == 0.06
        assert state.total_paid == 0.0
        assert state.repayment_priority == RepaymentPriority.INTEREST_FIRST
    
    def test_calculate_daily_interest(self):
        """Test daily interest calculation."""
        state = LoanState(principal=10000, current_balance=10000, apr=0.06)
        
        daily_interest = state.calculate_daily_interest()
        expected = 10000 * 0.06 / 365
        
        assert abs(daily_interest - expected) < 0.01
    
    def test_calculate_hourly_interest(self):
        """Test hourly interest calculation."""
        state = LoanState(principal=10000, current_balance=10000, apr=0.06)
        
        hourly_interest = state.calculate_hourly_interest()
        expected = 10000 * 0.06 / 365 / 24
        
        assert abs(hourly_interest - expected) < 0.001
    
    def test_model_dump_enum_handling(self):
        """Test that model_dump properly handles enums."""
        state = LoanState()
        data = state.model_dump()
        
        assert data['repayment_priority'] == 'interest_first'
        assert isinstance(data['repayment_priority'], str)


class TestLTVState:
    """Test LTVState model."""
    
    def test_get_action_for_ltv(self):
        """Test LTV action determination."""
        state = LTVState(
            total_collateral_value=20000,
            loan_balance=10000,
            ltv_ratio=0.5,
            current_action=LTVAction.SAFE,
            distance_to_liquidation=0.45,
            health_score=50
        )
        
        assert state.get_action_for_ltv(0.4) == LTVAction.SAFE
        assert state.get_action_for_ltv(0.6) == LTVAction.MONITOR
        assert state.get_action_for_ltv(0.7) == LTVAction.WARNING
        assert state.get_action_for_ltv(0.8) == LTVAction.CRITICAL
        assert state.get_action_for_ltv(0.9) == LTVAction.EMERGENCY
    
    def test_calculate_reserve_deployment(self):
        """Test reserve deployment calculation."""
        # Safe zone - no deployment
        state = LTVState(
            total_collateral_value=20000,
            loan_balance=10000,
            ltv_ratio=0.5,
            current_action=LTVAction.SAFE,
            distance_to_liquidation=0.45,
            health_score=50
        )
        assert state.calculate_reserve_deployment() == 0.0
        
        # Warning zone - proportional deployment
        state.ltv_ratio = 0.70
        deployment = state.calculate_reserve_deployment()
        expected = 3000 * (0.70 - 0.65) / 0.10  # 1500
        assert abs(deployment - expected) < 0.01
        
        # Critical zone - higher deployment
        state.ltv_ratio = 0.80
        deployment = state.calculate_reserve_deployment()
        expected = 3000 + 5000 * (0.80 - 0.75) / 0.10  # 5500
        assert abs(deployment - expected) < 0.01
        
        # Emergency zone - full deployment
        state.ltv_ratio = 0.90
        assert state.calculate_reserve_deployment() == 10000.0
    
    def test_calculate_position_scaling(self):
        """Test position scaling calculation."""
        state = LTVState(
            total_collateral_value=20000,
            loan_balance=10000,
            ltv_ratio=0.5,
            current_action=LTVAction.SAFE,
            distance_to_liquidation=0.45,
            health_score=50
        )
        
        # Safe/Monitor - full size
        state.ltv_ratio = 0.5
        assert state.calculate_position_scaling() == 1.0
        
        # Warning - 50% reduction
        state.ltv_ratio = 0.70
        assert state.calculate_position_scaling() == 0.5
        
        # Critical - 80% reduction
        state.ltv_ratio = 0.80
        assert state.calculate_position_scaling() == 0.2
        
        # Emergency - close all
        state.ltv_ratio = 0.90
        assert state.calculate_position_scaling() == 0.0


class TestRepaymentRecord:
    """Test RepaymentRecord model."""
    
    def test_repayment_record_creation(self):
        """Test creating repayment record."""
        record = RepaymentRecord(
            timestamp=datetime.utcnow(),
            amount=1000,
            principal_portion=800,
            interest_portion=200,
            remaining_balance=15200
        )
        
        assert record.amount == 1000
        assert record.principal_portion == 800
        assert record.interest_portion == 200
        assert record.remaining_balance == 15200
        assert record.transaction_id is None


class TestLoanRepaymentRequest:
    """Test LoanRepaymentRequest model."""
    
    def test_valid_request(self):
        """Test valid repayment request."""
        request = LoanRepaymentRequest(
            amount=500,
            source="trading_profit"
        )
        
        assert request.amount == 500
        assert request.source == "trading_profit"
        assert request.priority is None
    
    def test_invalid_amount(self):
        """Test invalid repayment amount."""
        with pytest.raises(ValidationError):
            LoanRepaymentRequest(
                amount=0,  # Must be > 0
                source="test"
            )
        
        with pytest.raises(ValidationError):
            LoanRepaymentRequest(
                amount=-100,  # Must be > 0
                source="test"
            )


class TestLoanManagerConfig:
    """Test LoanManagerConfig model."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = LoanManagerConfig()
        
        assert config.initial_principal == 16200.0
        assert config.apr == 0.06
        assert config.auto_repay_enabled == True
        assert config.repayment_priority == RepaymentPriority.INTEREST_FIRST
        assert config.profit_allocation_percent == 0.5
        assert config.ltv_check_interval == 60
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = LoanManagerConfig(
            initial_principal=20000,
            apr=0.08,
            auto_repay_enabled=False,
            profit_allocation_percent=0.7
        )
        
        assert config.initial_principal == 20000
        assert config.apr == 0.08
        assert config.auto_repay_enabled == False
        assert config.profit_allocation_percent == 0.7


class TestReserveDeployment:
    """Test ReserveDeployment model."""
    
    def test_deployment_creation(self):
        """Test reserve deployment creation."""
        deployment = ReserveDeployment(
            ltv_ratio=0.75,
            deployment_amount=3000,
            deployment_reason="LTV 75.0% - WARNING",
            from_reserve=10000,
            to_reserve=7000,
            to_collateral=3000,
            emergency=False
        )
        
        assert deployment.deployment_amount == 3000
        assert deployment.from_reserve == 10000
        assert deployment.to_reserve == 7000
        assert deployment.to_collateral == 3000
        assert not deployment.emergency
    
    def test_emergency_deployment(self):
        """Test emergency deployment."""
        deployment = ReserveDeployment(
            ltv_ratio=0.90,
            deployment_amount=10000,
            deployment_reason="LTV 90.0% - EMERGENCY",
            from_reserve=10000,
            to_reserve=0,
            to_collateral=10000,
            emergency=True
        )
        
        assert deployment.emergency
        assert deployment.to_reserve == 0  # All reserves deployed