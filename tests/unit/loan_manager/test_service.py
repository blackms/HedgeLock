"""
Unit tests for Loan Manager Service.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from src.hedgelock.loan_manager.service import LoanManagerService
from src.hedgelock.loan_manager.models import (
    LoanRepaymentRequest, RepaymentPriority, LTVAction
)


class TestLoanManagerService:
    """Test LoanManagerService functionality."""
    
    @pytest.fixture
    def service_config(self):
        """Create test service configuration."""
        return {
            'kafka_servers': 'localhost:9092',
            'loan_config': {
                'initial_principal': 16200.0,
                'apr': 0.06,
                'auto_repay_enabled': True,
                'profit_allocation_percent': 0.5,
                'ltv_check_interval': 1,  # Short for testing
                'reserve_deployment_enabled': True
            }
        }
    
    @pytest.fixture
    def service(self, service_config):
        """Create LoanManagerService instance."""
        return LoanManagerService(service_config)
    
    def test_initialization(self, service):
        """Test service initialization."""
        assert service.config.initial_principal == 16200.0
        assert service.config.apr == 0.06
        assert service.loan_manager is not None
        assert service.available_reserves == 10000.0
        assert len(service.repayment_queue) == 0
    
    @pytest.mark.asyncio
    async def test_handle_profit_event(self, service):
        """Test handling profit taking events."""
        # Test with profit
        profit_data = {
            'realized_pnl': 1000.0,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await service.handle_profit_event(profit_data)
        
        # Should queue repayment (50% of profit)
        assert len(service.repayment_queue) == 1
        assert service.repayment_queue[0].amount == 500.0
        assert service.repayment_queue[0].source == 'trading_profit'
    
    @pytest.mark.asyncio
    async def test_handle_profit_event_no_profit(self, service):
        """Test handling profit event with no profit."""
        profit_data = {
            'realized_pnl': 0.0,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await service.handle_profit_event(profit_data)
        
        # Should not queue repayment
        assert len(service.repayment_queue) == 0
    
    @pytest.mark.asyncio
    async def test_handle_profit_event_disabled(self, service):
        """Test handling profit event when auto-repay is disabled."""
        service.config.auto_repay_enabled = False
        
        profit_data = {
            'realized_pnl': 1000.0,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await service.handle_profit_event(profit_data)
        
        # Should not queue repayment
        assert len(service.repayment_queue) == 0
    
    @pytest.mark.asyncio
    async def test_handle_position_update(self, service):
        """Test handling position updates."""
        position_data = {
            'position_state': {
                'btc_price': 50000,
                'spot_btc': 0.5
            }
        }
        
        await service.handle_position_update(position_data)
        
        # Should update collateral value
        expected_collateral = 0.5 * 50000 + 10000  # BTC value + reserves
        assert service.current_collateral_value == expected_collateral
    
    @pytest.mark.asyncio
    async def test_handle_treasury_update(self, service):
        """Test handling treasury updates."""
        treasury_data = {
            'available_reserves': 8000.0
        }
        
        await service.handle_treasury_update(treasury_data)
        
        assert service.available_reserves == 8000.0
    
    @pytest.mark.asyncio
    async def test_check_reserve_deployment(self, service):
        """Test reserve deployment check."""
        # Create mock producer
        service.producer = AsyncMock()
        
        # Create LTV state that needs deployment
        ltv_state = service.loan_manager.calculate_ltv(23000)  # ~70% LTV
        
        await service.check_reserve_deployment(ltv_state)
        
        # Should publish deployment request
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'reserve_deployments'
        assert 'deployment' in call_args[1]['value']
    
    @pytest.mark.asyncio
    async def test_publish_ltv_update(self, service):
        """Test LTV update publishing."""
        service.producer = AsyncMock()
        
        ltv_state = service.loan_manager.calculate_ltv(30000)
        
        await service.publish_ltv_update(ltv_state)
        
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'ltv_updates'
        assert 'ltv_state' in call_args[1]['value']
        assert 'loan_metrics' in call_args[1]['value']
    
    @pytest.mark.asyncio
    async def test_publish_position_scaling(self, service):
        """Test position scaling publishing."""
        service.producer = AsyncMock()
        
        # Create LTV state that needs scaling
        ltv_state = service.loan_manager.calculate_ltv(23000)  # ~70% LTV
        ltv_state.current_action = LTVAction.WARNING
        
        await service.publish_position_scaling(ltv_state)
        
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'position_scaling'
        assert call_args[1]['value']['scaling_factor'] == 0.5  # 50% reduction
    
    @pytest.mark.asyncio
    async def test_publish_ltv_alert(self, service):
        """Test LTV alert publishing."""
        service.producer = AsyncMock()
        
        ltv_state = service.loan_manager.calculate_ltv(20000)  # High LTV
        
        await service.publish_ltv_alert(ltv_state)
        
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'risk_alerts'
        assert call_args[1]['value']['alert_type'] == 'HIGH_LTV'
    
    @pytest.mark.asyncio
    async def test_repayment_processing(self, service):
        """Test repayment queue processing."""
        service.producer = AsyncMock()
        
        # Add repayment to queue
        request = LoanRepaymentRequest(
            amount=500,
            source='test',
            priority=RepaymentPriority.INTEREST_FIRST
        )
        service.repayment_queue.append(request)
        
        # Process one iteration
        service.running = True
        
        # Run processing loop for a short time
        task = asyncio.create_task(service.repayment_processing_loop())
        await asyncio.sleep(0.1)
        service.running = False
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Queue should be empty
        assert len(service.repayment_queue) == 0
        
        # Should publish repayment
        service.producer.send_and_wait.assert_called()
    
    @pytest.mark.asyncio
    async def test_loan_paid_off_publishing(self, service):
        """Test loan paid off event publishing."""
        service.producer = AsyncMock()
        
        # Make loan paid off
        service.loan_manager.loan_state.current_balance = 0
        service.loan_manager.loan_state.accrued_interest = 0
        
        await service.publish_loan_paid_off()
        
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'loan_events'
        assert call_args[1]['value']['event'] == 'LOAN_PAID_OFF'
    
    def test_get_current_state(self, service):
        """Test getting current service state."""
        # Add some data
        service.current_collateral_value = 25000
        service.available_reserves = 8000
        
        state = service.get_current_state()
        
        assert 'loan_state' in state
        assert 'loan_metrics' in state
        assert state['current_collateral'] == 25000
        assert state['available_reserves'] == 8000
        assert state['repayment_queue_size'] == 0
    
    @pytest.mark.asyncio
    async def test_ltv_monitoring_high_ltv(self, service):
        """Test LTV monitoring with high LTV."""
        service.producer = AsyncMock()
        service.current_collateral_value = 20000  # High LTV ~81%
        service.config.alert_on_high_ltv = True
        service.config.alert_ltv_threshold = 0.70
        
        # Run one iteration of monitoring
        service.running = True
        task = asyncio.create_task(service.ltv_monitoring_loop())
        await asyncio.sleep(1.5)  # Wait for one check
        service.running = False
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Should have published multiple messages
        assert service.producer.send_and_wait.call_count >= 3  # LTV update, scaling, alert
        
        # Check for alert
        alert_calls = [
            call for call in service.producer.send_and_wait.call_args_list
            if call[0][0] == 'risk_alerts'
        ]
        assert len(alert_calls) > 0
    
    @pytest.mark.asyncio
    async def test_interest_update_publishing(self, service):
        """Test interest update publishing."""
        service.producer = AsyncMock()
        
        interest = 10.5
        await service.publish_interest_update(interest)
        
        service.producer.send_and_wait.assert_called_once()
        call_args = service.producer.send_and_wait.call_args
        assert call_args[0][0] == 'loan_updates'
        assert call_args[1]['value']['update_type'] == 'interest_accrual'
        assert call_args[1]['value']['interest_amount'] == 10.5