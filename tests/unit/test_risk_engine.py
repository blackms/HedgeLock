"""Unit tests for risk engine."""

from datetime import datetime

import pytest

from src.hedgelock.risk_engine.calculator import RiskCalculator
from src.hedgelock.risk_engine.models import AccountData, RiskState


def test_account_data_ltv_calculation():
    """Test LTV calculation in AccountData."""
    account = AccountData(
        timestamp=datetime.utcnow(),
        source="test",
        total_collateral_value=100000.0,
        available_collateral=50000.0,
        used_collateral=50000.0,
        total_loan_value=65000.0,
        total_interest=0.0,
        positions={},
    )

    assert account.ltv == 0.65  # 65% LTV


def test_account_data_net_delta():
    """Test net delta calculation."""
    account = AccountData(
        timestamp=datetime.utcnow(),
        source="test",
        total_collateral_value=100000.0,
        available_collateral=50000.0,
        used_collateral=50000.0,
        total_loan_value=50000.0,
        total_interest=0.0,
        positions={
            "BTCUSDT": {"symbol": "BTCUSDT", "side": "Buy", "size": 0.5},
            "BTCUSD": {"symbol": "BTCUSD", "side": "Sell", "size": 0.2},
        },
    )

    assert account.net_delta == 0.3  # 0.5 - 0.2


def test_risk_calculator_state_determination():
    """Test risk state determination."""
    calculator = RiskCalculator()

    # Test different LTV levels
    assert calculator._determine_risk_state(0.4) == RiskState.NORMAL
    assert calculator._determine_risk_state(0.65) == RiskState.CAUTION
    assert calculator._determine_risk_state(0.8) == RiskState.DANGER
    assert calculator._determine_risk_state(0.9) == RiskState.CRITICAL


def test_risk_calculator_risk_score():
    """Test risk score calculation."""
    calculator = RiskCalculator()

    # Low risk
    score = calculator._calculate_risk_score(0.3, 0.1)
    assert 0 <= score <= 100
    assert score < 30

    # High risk
    score = calculator._calculate_risk_score(0.9, 1.0)
    assert score > 70


def test_risk_calculator_target_delta():
    """Test target delta for different risk states."""
    calculator = RiskCalculator()

    assert calculator._get_target_delta(RiskState.NORMAL) == 0.0
    assert calculator._get_target_delta(RiskState.CAUTION) == 0.02
    assert calculator._get_target_delta(RiskState.DANGER) == 0.0
    assert calculator._get_target_delta(RiskState.CRITICAL) == -0.1
