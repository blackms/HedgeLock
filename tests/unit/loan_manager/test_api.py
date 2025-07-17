"""
Unit tests for Loan Manager API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import Mock, patch

from src.hedgelock.loan_manager.api import app, loan_service
from src.hedgelock.loan_manager.models import (
    LoanState, LTVState, LTVAction, RepaymentRecord,
    ReserveDeployment
)


class TestLoanManagerAPI:
    """Test Loan Manager API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_service(self):
        """Create mock loan service."""
        mock = Mock()
        mock.running = True
        mock.loan_manager = Mock()
        mock.loan_manager.loan_state = LoanState()
        mock.loan_manager.ltv_history = []
        mock.loan_manager.repayment_history = []
        mock.loan_manager.deployment_history = []
        mock.repayment_queue = []
        mock.current_collateral_value = 25000
        mock.available_reserves = 10000
        return mock
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Loan Manager"
        assert data["version"] == "1.0.0"
    
    def test_status_no_service(self, client):
        """Test status endpoint without service."""
        with patch('src.hedgelock.loan_manager.api.loan_service', None):
            response = client.get("/status")
            assert response.status_code == 503
    
    def test_status_with_service(self, client, mock_service):
        """Test status endpoint with service."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            mock_service.get_current_state.return_value = {
                'loan_state': {},
                'loan_metrics': {},
                'current_collateral': 25000,
                'available_reserves': 10000
            }
            
            response = client.get("/status")
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "loan-manager"
            assert data["status"] == "active"
    
    def test_loan_state_endpoint(self, client, mock_service):
        """Test loan state endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            mock_service.loan_manager.get_loan_metrics.return_value = {
                'current_balance': 16200,
                'accrued_interest': 50,
                'total_paid': 1000
            }
            mock_service.loan_manager.is_loan_paid_off.return_value = False
            
            response = client.get("/loan/state")
            assert response.status_code == 200
            data = response.json()
            assert "loan_state" in data
            assert "metrics" in data
            assert data["is_paid_off"] == False
    
    def test_loan_metrics_endpoint(self, client, mock_service):
        """Test loan metrics endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            mock_service.loan_manager.get_loan_metrics.return_value = {
                'current_balance': 16200,
                'apr': 0.06,
                'daily_interest': 2.66
            }
            mock_service.loan_manager.estimate_payoff_time.side_effect = [
                6,   # $100/month = 6 months
                35,  # $500/month = 35 months
                18,  # $1000/month = 18 months
                9    # $2000/month = 9 months
            ]
            
            response = client.get("/loan/metrics")
            assert response.status_code == 200
            data = response.json()
            assert "metrics" in data
            assert "payoff_estimates" in data
            assert "$500/month" in data["payoff_estimates"]
    
    def test_current_ltv_endpoint(self, client, mock_service):
        """Test current LTV endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            # Create test LTV state
            ltv_state = LTVState(
                total_collateral_value=25000,
                loan_balance=16200,
                ltv_ratio=0.648,
                current_action=LTVAction.MONITOR,
                distance_to_liquidation=0.302,
                health_score=35.2
            )
            mock_service.loan_manager.ltv_history = [ltv_state]
            
            response = client.get("/ltv/current")
            assert response.status_code == 200
            data = response.json()
            assert data["ltv_ratio"] == 0.648
            assert data["ltv_percent"] == "64.8%"
            assert data["current_action"] == "MONITOR"
    
    def test_ltv_history_endpoint(self, client, mock_service):
        """Test LTV history endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            # Create test history
            mock_service.loan_manager.get_recent_ltv_trend.return_value = [0.65, 0.66, 0.64]
            mock_service.loan_manager.ltv_history = [
                LTVState(
                    total_collateral_value=25000,
                    loan_balance=16200,
                    ltv_ratio=0.65,
                    current_action=LTVAction.MONITOR,
                    distance_to_liquidation=0.3,
                    health_score=35
                )
            ]
            
            response = client.get("/ltv/history?hours=24")
            assert response.status_code == 200
            data = response.json()
            assert data["hours"] == 24
            assert len(data["ltv_values"]) == 3
            assert data["average_ltv"] == pytest.approx(0.65, rel=0.01)
    
    def test_repayment_history_endpoint(self, client, mock_service):
        """Test repayment history endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            # Create test repayment history
            record = RepaymentRecord(
                timestamp=datetime.utcnow(),
                amount=500,
                principal_portion=400,
                interest_portion=100,
                remaining_balance=15800,
                notes="Test payment"
            )
            mock_service.loan_manager.repayment_history = [record]
            
            response = client.get("/repayments/history")
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert len(data["repayments"]) == 1
            assert data["repayments"][0]["amount"] == 500
    
    def test_manual_repayment_endpoint(self, client, mock_service):
        """Test manual repayment endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            repayment_data = {
                "amount": 1000,
                "source": "manual_payment",
                "notes": "Extra payment"
            }
            
            response = client.post("/repayment/manual", json=repayment_data)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert "1000.00" in data["message"]
            
            # Check that repayment was queued
            assert len(mock_service.repayment_queue) == 1
            assert mock_service.repayment_queue[0].amount == 1000
    
    def test_reserve_deployment_history(self, client, mock_service):
        """Test reserve deployment history endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            # Create test deployment
            deployment = ReserveDeployment(
                ltv_ratio=0.75,
                deployment_amount=3000,
                deployment_reason="LTV 75% - WARNING",
                from_reserve=10000,
                to_reserve=7000,
                to_collateral=3000,
                emergency=False
            )
            mock_service.loan_manager.deployment_history = [deployment]
            
            response = client.get("/reserves/deployment")
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["total_deployed"] == 3000
            assert len(data["deployments"]) == 1
    
    def test_configuration_endpoint(self, client, mock_service):
        """Test configuration endpoint."""
        with patch('src.hedgelock.loan_manager.api.loan_service', mock_service):
            from src.hedgelock.loan_manager.models import LoanManagerConfig, RepaymentPriority
            mock_service.config = LoanManagerConfig()
            
            response = client.get("/config")
            assert response.status_code == 200
            data = response.json()
            config = data["configuration"]
            assert config["initial_principal"] == 16200.0
            assert config["apr"] == 0.06
            assert config["auto_repay_enabled"] == True
    
    def test_health_check_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"