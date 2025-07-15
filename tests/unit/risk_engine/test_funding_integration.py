"""
Unit tests for Risk Engine funding integration.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.hedgelock.risk_engine.calculator import RiskCalculator
from src.hedgelock.risk_engine.models import (
    RiskState, AccountData, RiskCalculation, RiskStateMessage
)
from src.hedgelock.shared.funding_models import FundingContext, FundingRegime


class TestFundingAwareRiskCalculator:
    """Test risk calculator with funding awareness."""
    
    @pytest.fixture
    def calculator(self):
        """Create risk calculator instance."""
        return RiskCalculator()
    
    @pytest.fixture
    def sample_account_data(self):
        """Create sample account data."""
        return AccountData(
            timestamp=datetime.utcnow(),
            source="test",
            total_collateral_value=100000.0,
            available_collateral=50000.0,
            used_collateral=50000.0,
            total_loan_value=40000.0,
            total_interest=1000.0,
            positions={
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "size": 1.5,
                    "side": "Buy",
                    "value": 75000.0
                }
            }
        )
    
    @pytest.fixture
    def neutral_funding_context(self):
        """Create neutral funding context."""
        return FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NEUTRAL,
            current_rate=5.0,
            avg_rate_24h=4.0,
            avg_rate_7d=3.0,
            max_rate_24h=6.0,
            volatility_24h=2.0,
            position_multiplier=1.0,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=1.37,
            weekly_cost_pct=0.096
        )
    
    @pytest.fixture
    def extreme_funding_context(self):
        """Create extreme funding context."""
        return FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.EXTREME,
            current_rate=350.0,
            avg_rate_24h=300.0,
            avg_rate_7d=250.0,
            max_rate_24h=400.0,
            volatility_24h=50.0,
            position_multiplier=0.0,
            should_exit=True,
            regime_change=True,
            daily_cost_bps=95.9,
            weekly_cost_pct=6.71
        )
    
    def test_calculate_risk_without_funding(self, calculator, sample_account_data):
        """Test risk calculation without funding context."""
        calculation = calculator.calculate_risk(sample_account_data)
        
        assert calculation.ltv == 0.41  # (40000 + 1000) / 100000
        assert calculation.risk_state == RiskState.NORMAL  # LTV < 0.5
        assert calculation.risk_score > 0
        assert calculation.funding_context is None
        assert calculation.funding_adjusted_score == calculation.risk_score
    
    def test_calculate_risk_with_neutral_funding(
        self, calculator, sample_account_data, neutral_funding_context
    ):
        """Test risk calculation with neutral funding."""
        calculation = calculator.calculate_risk(
            sample_account_data, 
            neutral_funding_context
        )
        
        assert calculation.ltv == 0.41
        assert calculation.risk_state == RiskState.NORMAL
        assert calculation.funding_context == neutral_funding_context
        
        # Funding adjusted score should be slightly higher
        assert calculation.funding_adjusted_score > calculation.risk_score
        assert calculation.funding_adjusted_score < calculation.risk_score + 10
        
        # Check funding risk factor was added
        assert "funding_risk" in calculation.risk_factors
        assert calculation.risk_factors["funding_risk"] < 2  # 5% / 3
    
    def test_calculate_risk_with_extreme_funding(
        self, calculator, sample_account_data, extreme_funding_context
    ):
        """Test risk calculation with extreme funding."""
        calculation = calculator.calculate_risk(
            sample_account_data,
            extreme_funding_context
        )
        
        # Risk state should be forced to CRITICAL due to extreme funding
        assert calculation.risk_state == RiskState.CRITICAL
        assert calculation.funding_context == extreme_funding_context
        
        # Funding adjusted score should be much higher
        assert calculation.funding_adjusted_score >= calculation.risk_score + 30
        
        # Check funding risk factor
        assert calculation.risk_factors["funding_risk"] > 100  # 350% / 3
    
    def test_risk_state_escalation_with_funding(self, calculator, sample_account_data):
        """Test that funding can escalate risk state."""
        # Create mania funding context
        mania_funding = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.MANIA,
            current_rate=150.0,
            avg_rate_24h=140.0,
            avg_rate_7d=130.0,
            max_rate_24h=160.0,
            volatility_24h=20.0,
            position_multiplier=0.2,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=41.1,
            weekly_cost_pct=2.88
        )
        
        # Without funding - should be NORMAL
        calc_no_funding = calculator.calculate_risk(sample_account_data)
        assert calc_no_funding.risk_state == RiskState.NORMAL
        
        # With mania funding - should escalate to CAUTION
        calc_with_funding = calculator.calculate_risk(sample_account_data, mania_funding)
        assert calc_with_funding.risk_state == RiskState.CAUTION
    
    def test_funding_impact_on_risk_score(self, calculator, sample_account_data):
        """Test funding impact on risk score calculation."""
        base_calc = calculator.calculate_risk(sample_account_data)
        base_score = base_calc.risk_score
        
        # Test different funding regimes
        regimes_and_impacts = [
            (FundingRegime.NEUTRAL, 0),     # No additional impact
            (FundingRegime.NORMAL, 5),      # +5 points
            (FundingRegime.HEATED, 10),     # +10 points
            (FundingRegime.MANIA, 20),      # +20 points
            (FundingRegime.EXTREME, 30),    # +30 points
        ]
        
        for regime, expected_impact in regimes_and_impacts:
            funding_context = FundingContext(
                symbol="BTCUSDT",
                current_regime=regime,
                current_rate=50.0,  # Dummy rate
                avg_rate_24h=50.0,
                avg_rate_7d=50.0,
                max_rate_24h=50.0,
                volatility_24h=10.0,  # Low volatility
                position_multiplier=0.5,
                should_exit=False,
                regime_change=False,
                daily_cost_bps=13.7,
                weekly_cost_pct=0.96
            )
            
            calc = calculator.calculate_risk(sample_account_data, funding_context)
            
            # Check that funding adjusted score reflects the expected impact
            expected_score = base_score + expected_impact
            assert abs(calc.funding_adjusted_score - expected_score) < 1
    
    def test_high_volatility_adds_risk(self, calculator, sample_account_data):
        """Test that high funding volatility adds risk."""
        # Create funding context with high volatility
        high_vol_funding = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=25.0,
            avg_rate_7d=25.0,
            max_rate_24h=30.0,
            volatility_24h=60.0,  # High volatility
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=6.85,
            weekly_cost_pct=0.48
        )
        
        # Create same context with low volatility
        low_vol_funding = FundingContext(
            symbol="BTCUSDT",
            current_regime=FundingRegime.NORMAL,
            current_rate=25.0,
            avg_rate_24h=25.0,
            avg_rate_7d=25.0,
            max_rate_24h=30.0,
            volatility_24h=10.0,  # Low volatility
            position_multiplier=0.75,
            should_exit=False,
            regime_change=False,
            daily_cost_bps=6.85,
            weekly_cost_pct=0.48
        )
        
        calc_high_vol = calculator.calculate_risk(sample_account_data, high_vol_funding)
        calc_low_vol = calculator.calculate_risk(sample_account_data, low_vol_funding)
        
        # High volatility should result in higher risk score
        assert calc_high_vol.funding_adjusted_score > calc_low_vol.funding_adjusted_score
    
    def test_risk_state_message_includes_funding(
        self, calculator, sample_account_data, neutral_funding_context
    ):
        """Test that risk state message includes funding information."""
        calculation = calculator.calculate_risk(
            sample_account_data,
            neutral_funding_context
        )
        
        message = calculator.create_risk_state_message(calculation)
        
        assert message.funding_context == neutral_funding_context
        assert message.funding_adjusted_score == calculation.funding_adjusted_score
        assert message.funding_regime == FundingRegime.NEUTRAL
        assert message.position_multiplier == 1.0
    
    def test_risk_state_message_without_funding(self, calculator, sample_account_data):
        """Test risk state message when no funding context."""
        calculation = calculator.calculate_risk(sample_account_data)
        message = calculator.create_risk_state_message(calculation)
        
        assert message.funding_context is None
        assert message.funding_regime is None
        assert message.position_multiplier == 1.0  # Default multiplier