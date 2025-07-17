"""
Unit tests for P&L Calculator.
"""

import pytest
from datetime import datetime
from src.hedgelock.position_manager.pnl_calculator import PnLCalculator, PnLBreakdown
from src.hedgelock.position_manager.models import PositionState, MarketRegime


class TestPnLCalculator:
    """Test P&L calculation functionality."""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return PnLCalculator()
    
    @pytest.fixture
    def position_state(self):
        """Create test position state."""
        return PositionState(
            timestamp=datetime.utcnow(),
            spot_btc=0.27,
            long_perp=0.213,
            short_perp=0.213,
            net_delta=0.27,
            hedge_ratio=1.0,
            btc_price=116000,
            volatility_24h=0.02,
            funding_rate=0.0001,
            market_regime=MarketRegime.NEUTRAL
        )
    
    def test_initialization(self, calculator):
        """Test calculator initialization."""
        assert calculator.entry_prices['spot'] == 116000
        assert calculator.entry_prices['long_perp'] == 116000
        assert calculator.entry_prices['short_perp'] == 116000
        assert calculator.cumulative_funding_paid == 0.0
        assert calculator.cumulative_funding_received == 0.0
        assert calculator.cumulative_realized_pnl == 0.0
    
    def test_calculate_spot_pnl(self, calculator, position_state):
        """Test spot P&L calculation."""
        # Price increases to 120000
        position_state.btc_price = 120000
        pnl = calculator._calculate_spot_pnl(position_state)
        
        # P&L = (120000 - 116000) * 0.27 = 1080
        assert pnl == pytest.approx(1080.0)
        
        # Price decreases
        position_state.btc_price = 110000
        pnl = calculator._calculate_spot_pnl(position_state)
        
        # P&L = (110000 - 116000) * 0.27 = -1620
        assert pnl == pytest.approx(-1620.0)
    
    def test_calculate_long_perp_pnl(self, calculator, position_state):
        """Test long perpetual P&L calculation."""
        # Price increases - long profits
        position_state.btc_price = 120000
        pnl = calculator._calculate_perp_pnl(
            position_state.long_perp, 
            position_state.btc_price, 
            'long'
        )
        
        # P&L = (120000 - 116000) * 0.213 = 852
        assert pnl == pytest.approx(852.0)
        
        # Price decreases - long loses
        position_state.btc_price = 110000
        pnl = calculator._calculate_perp_pnl(
            position_state.long_perp,
            position_state.btc_price,
            'long'
        )
        
        # P&L = (110000 - 116000) * 0.213 = -1278
        assert pnl == pytest.approx(-1278.0)
    
    def test_calculate_short_perp_pnl(self, calculator, position_state):
        """Test short perpetual P&L calculation."""
        # Price increases - short loses
        position_state.btc_price = 120000
        pnl = calculator._calculate_perp_pnl(
            position_state.short_perp,
            position_state.btc_price,
            'short'
        )
        
        # P&L = (116000 - 120000) * 0.213 = -852
        assert pnl == pytest.approx(-852.0)
        
        # Price decreases - short profits
        position_state.btc_price = 110000
        pnl = calculator._calculate_perp_pnl(
            position_state.short_perp,
            position_state.btc_price,
            'short'
        )
        
        # P&L = (116000 - 110000) * 0.213 = 1278
        assert pnl == pytest.approx(1278.0)
    
    def test_funding_pnl_net_long(self, calculator, position_state):
        """Test funding P&L for net long position."""
        # Make position net long
        position_state.long_perp = 0.5
        position_state.short_perp = 0.2
        position_state.funding_rate = 0.0001  # 0.01% per 8h
        
        funding_pnl = calculator._calculate_funding_pnl(position_state)
        
        # Net long = 0.5 - 0.2 = 0.3
        # Position value = 0.3 * 116000 = 34800
        # Funding = -0.0001 * 34800 * 1 = -3.48
        assert funding_pnl < 0  # Longs pay funding
        assert calculator.cumulative_funding_paid > 0
    
    def test_funding_pnl_net_short(self, calculator, position_state):
        """Test funding P&L for net short position."""
        # Make position net short
        position_state.long_perp = 0.2
        position_state.short_perp = 0.5
        position_state.funding_rate = 0.0001
        
        funding_pnl = calculator._calculate_funding_pnl(position_state)
        
        # Net short = 0.2 - 0.5 = -0.3
        # Position value = 0.3 * 116000 = 34800
        # Funding = 0.0001 * 34800 * 1 = 3.48
        assert funding_pnl > 0  # Shorts receive funding
        assert calculator.cumulative_funding_received > 0
    
    def test_funding_pnl_delta_neutral(self, calculator, position_state):
        """Test funding P&L for delta-neutral position."""
        # Perfectly balanced
        position_state.long_perp = 0.213
        position_state.short_perp = 0.213
        
        funding_pnl = calculator._calculate_funding_pnl(position_state)
        
        # Net position = 0, no funding P&L
        assert funding_pnl == 0.0
    
    def test_calculate_pnl_comprehensive(self, calculator, position_state):
        """Test comprehensive P&L calculation."""
        # Price increase scenario
        position_state.btc_price = 120000
        position_state.long_perp = 0.3
        position_state.short_perp = 0.2
        
        breakdown = calculator.calculate_pnl(position_state)
        
        assert isinstance(breakdown, PnLBreakdown)
        assert breakdown.spot_pnl > 0  # Spot gains
        assert breakdown.long_perp_pnl > 0  # Long gains
        assert breakdown.short_perp_pnl < 0  # Short loses
        assert breakdown.funding_pnl < 0  # Net long pays funding
        
        # Total unrealized should be sum of components
        expected_total = (
            breakdown.spot_pnl + 
            breakdown.long_perp_pnl + 
            breakdown.short_perp_pnl + 
            breakdown.funding_pnl
        )
        assert breakdown.total_unrealized_pnl == pytest.approx(expected_total)
    
    def test_realize_pnl(self, calculator):
        """Test P&L realization on position close."""
        # Close a profitable long position
        closed_positions = {
            'long_perp': 0.5,
            'short_perp': 0.0
        }
        
        # Assume price moved from 116000 to 120000
        realized = calculator.realize_pnl(closed_positions, 120000)
        
        # Realized = (120000 - 116000) * 0.5 = 2000
        assert realized == 2000.0
        assert calculator.cumulative_realized_pnl == 2000.0
        
        # Close a losing short position
        closed_positions = {
            'long_perp': 0.0,
            'short_perp': 0.3
        }
        
        realized = calculator.realize_pnl(closed_positions, 120000)
        
        # Realized = (116000 - 120000) * 0.3 = -1200
        assert realized == -1200.0
        assert calculator.cumulative_realized_pnl == 800.0  # 2000 - 1200
    
    def test_update_entry_prices_new_position(self, calculator):
        """Test entry price updates for new positions."""
        # New long position
        calculator.update_entry_prices('long_perp', 118000, 0, 0.5)
        assert calculator.entry_prices['long_perp'] == 118000
        
        # New short position
        calculator.update_entry_prices('short_perp', 119000, 0, 0.3)
        assert calculator.entry_prices['short_perp'] == 119000
    
    def test_update_entry_prices_add_to_position(self, calculator):
        """Test weighted average entry price calculation."""
        # Initial position: 0.5 BTC at 116000
        calculator.entry_prices['long_perp'] = 116000
        
        # Add 0.3 BTC at 120000
        calculator.update_entry_prices('long_perp', 120000, 0.5, 0.8)
        
        # Weighted average = (116000*0.5 + 120000*0.3) / 0.8 = 117500
        assert calculator.entry_prices['long_perp'] == 117500
    
    def test_update_entry_prices_close_position(self, calculator):
        """Test entry price reset on position close."""
        calculator.entry_prices['long_perp'] = 116000
        
        # Close position (quantity = 0)
        calculator.update_entry_prices('long_perp', 120000, 0.5, 0)
        
        # Entry price should reset to current price
        assert calculator.entry_prices['long_perp'] == 120000
    
    def test_get_pnl_metrics(self, calculator, position_state):
        """Test comprehensive P&L metrics."""
        position_state.btc_price = 120000
        position_state.long_perp = 0.3
        position_state.short_perp = 0.2
        
        metrics = calculator.get_pnl_metrics(position_state)
        
        assert 'spot_pnl' in metrics
        assert 'long_perp_pnl' in metrics
        assert 'short_perp_pnl' in metrics
        assert 'funding_pnl' in metrics
        assert 'unrealized_pnl' in metrics
        assert 'realized_pnl' in metrics
        assert 'net_pnl' in metrics
        assert 'roi_percent' in metrics
        assert 'position_value' in metrics
        assert 'cumulative_funding_paid' in metrics
        assert 'cumulative_funding_received' in metrics
        
        # ROI should be calculated
        assert metrics['roi_percent'] != 0
        
        # Position value should include all components
        assert metrics['position_value'] > 0
    
    def test_zero_positions(self, calculator, position_state):
        """Test P&L calculation with zero positions."""
        position_state.spot_btc = 0
        position_state.long_perp = 0
        position_state.short_perp = 0
        
        breakdown = calculator.calculate_pnl(position_state)
        
        assert breakdown.spot_pnl == 0
        assert breakdown.long_perp_pnl == 0
        assert breakdown.short_perp_pnl == 0
        assert breakdown.funding_pnl == 0
        assert breakdown.total_unrealized_pnl == 0
    
    def test_reset(self, calculator):
        """Test P&L reset functionality."""
        # Accumulate some P&L
        calculator.cumulative_realized_pnl = 1000
        calculator.cumulative_funding_paid = 50
        calculator.cumulative_funding_received = 30
        
        calculator.reset()
        
        assert calculator.cumulative_realized_pnl == 0
        assert calculator.cumulative_funding_paid == 0
        assert calculator.cumulative_funding_received == 0
        
        # Entry prices should remain
        assert calculator.entry_prices['spot'] == 116000