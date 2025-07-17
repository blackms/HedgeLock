"""
Kafka integration tests for Loan Manager.
"""

import asyncio
import json
import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from src.hedgelock.loan_manager.service import LoanManagerService
from src.hedgelock.loan_manager.models import LoanRepaymentRequest


class TestLoanManagerKafkaIntegration:
    """Test Loan Manager Kafka integration."""
    
    @pytest.fixture
    def service_config(self):
        """Service configuration for tests."""
        return {
            'kafka_servers': 'localhost:19092',
            'loan_config': {
                'initial_principal': 16200.0,
                'apr': 0.06,
                'auto_repay_enabled': True,
                'profit_allocation_percent': 0.5,
                'ltv_check_interval': 1,
                'reserve_deployment_enabled': True
            }
        }
    
    @pytest.mark.asyncio
    async def test_profit_event_processing(self, service_config):
        """Test that Loan Manager processes profit events correctly."""
        service = LoanManagerService(service_config)
        
        # Test profit event
        profit_event = {
            'timestamp': datetime.utcnow().isoformat(),
            'realized_pnl': 2000.0,
            'position_state': {
                'btc_price': 50000,
                'spot_btc': 0.5
            }
        }
        
        # Process the event
        await service.handle_profit_event(profit_event)
        
        # Verify repayment was queued
        assert len(service.repayment_queue) == 1
        assert service.repayment_queue[0].amount == 1000.0  # 50% of profit
        assert service.repayment_queue[0].source == 'trading_profit'
    
    @pytest.mark.asyncio
    async def test_ltv_update_publishing(self, service_config):
        """Test LTV update publishing to Kafka."""
        service = LoanManagerService(service_config)
        
        # Create mock producer
        producer = AIOKafkaProducer(
            bootstrap_servers=service_config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await producer.start()
            service.producer = producer
            
            # Set collateral value
            service.current_collateral_value = 25000
            
            # Calculate and publish LTV
            ltv_state = service.loan_manager.calculate_ltv(service.current_collateral_value)
            await service.publish_ltv_update(ltv_state)
            
            # Verify message was sent (no errors raised)
            assert True
            
        except Exception as e:
            pytest.fail(f"LTV update publishing failed: {e}")
        finally:
            await producer.stop()
    
    @pytest.mark.asyncio
    async def test_position_scaling_on_high_ltv(self, service_config):
        """Test position scaling messages on high LTV."""
        service = LoanManagerService(service_config)
        
        # Create mock producer
        producer = AIOKafkaProducer(
            bootstrap_servers=service_config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await producer.start()
            service.producer = producer
            
            # Set high LTV conditions
            service.current_collateral_value = 20000  # ~81% LTV
            
            # Calculate LTV (should trigger WARNING/CRITICAL)
            ltv_state = service.loan_manager.calculate_ltv(service.current_collateral_value)
            
            # Publish position scaling
            await service.publish_position_scaling(ltv_state)
            
            # Verify no errors
            assert ltv_state.position_scaling < 1.0  # Should reduce positions
            
        except Exception as e:
            pytest.fail(f"Position scaling publishing failed: {e}")
        finally:
            await producer.stop()
    
    @pytest.mark.asyncio
    async def test_reserve_deployment_flow(self, service_config):
        """Test reserve deployment message flow."""
        service = LoanManagerService(service_config)
        
        # Create mock producer
        producer = AIOKafkaProducer(
            bootstrap_servers=service_config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await producer.start()
            service.producer = producer
            
            # Set LTV that requires deployment (70%)
            service.current_collateral_value = 23000
            service.available_reserves = 10000
            
            # Calculate LTV and check deployment
            ltv_state = service.loan_manager.calculate_ltv(service.current_collateral_value)
            await service.check_reserve_deployment(ltv_state)
            
            # Verify deployment amount
            assert ltv_state.reserve_deployment > 0
            assert service.available_reserves < 10000  # Some reserves deployed
            
        except Exception as e:
            pytest.fail(f"Reserve deployment flow failed: {e}")
        finally:
            await producer.stop()
    
    @pytest.mark.asyncio
    async def test_repayment_processing_flow(self, service_config):
        """Test repayment processing and publishing."""
        service = LoanManagerService(service_config)
        
        # Create mock producer
        producer = AIOKafkaProducer(
            bootstrap_servers=service_config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await producer.start()
            service.producer = producer
            
            # Add manual repayment
            request = LoanRepaymentRequest(
                amount=1000,
                source='manual',
                notes='Test repayment'
            )
            service.repayment_queue.append(request)
            
            # Process repayment
            service.running = True
            task = asyncio.create_task(service.repayment_processing_loop())
            await asyncio.sleep(0.5)  # Let it process
            service.running = False
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Verify repayment was processed
            assert len(service.repayment_queue) == 0
            assert service.loan_manager.loan_state.total_paid == 1000
            
        except Exception as e:
            pytest.fail(f"Repayment processing failed: {e}")
        finally:
            await producer.stop()
    
    @pytest.mark.asyncio
    async def test_emergency_ltv_flow(self, service_config):
        """Test emergency LTV handling."""
        service = LoanManagerService(service_config)
        
        # Create mock producer
        producer = AIOKafkaProducer(
            bootstrap_servers=service_config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await producer.start()
            service.producer = producer
            
            # Set emergency LTV (>85%)
            service.current_collateral_value = 18000
            
            # Calculate LTV
            ltv_state = service.loan_manager.calculate_ltv(service.current_collateral_value)
            
            # Verify emergency actions
            assert ltv_state.current_action.value == 'EMERGENCY'
            assert ltv_state.position_scaling == 0.0  # Close all positions
            assert ltv_state.reserve_deployment == 10000  # Deploy all reserves
            
            # Publish alerts
            await service.publish_ltv_alert(ltv_state)
            await service.publish_position_scaling(ltv_state)
            
        except Exception as e:
            pytest.fail(f"Emergency LTV flow failed: {e}")
        finally:
            await producer.stop()
    
    @pytest.mark.asyncio
    async def test_loan_paid_off_event(self, service_config):
        """Test loan paid off event publishing."""
        service = LoanManagerService(service_config)
        
        # Create mock producer
        producer = AIOKafkaProducer(
            bootstrap_servers=service_config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        try:
            await producer.start()
            service.producer = producer
            
            # Pay off the loan
            service.loan_manager.loan_state.current_balance = 0
            service.loan_manager.loan_state.accrued_interest = 0
            
            # Publish paid off event
            await service.publish_loan_paid_off()
            
            # Verify loan is paid off
            assert service.loan_manager.is_loan_paid_off()
            
        except Exception as e:
            pytest.fail(f"Loan paid off event failed: {e}")
        finally:
            await producer.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])