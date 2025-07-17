"""
P&L Calculator for Position Manager.
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from .models import PositionState

logger = logging.getLogger(__name__)


@dataclass
class PnLBreakdown:
    """Detailed P&L breakdown by component."""
    spot_pnl: float
    long_perp_pnl: float
    short_perp_pnl: float
    funding_pnl: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    net_pnl: float
    timestamp: datetime


class PnLCalculator:
    """Calculates P&L for delta-neutral positions."""
    
    def __init__(self):
        # Track entry prices for P&L calculation
        self.entry_prices: Dict[str, float] = {
            'spot': 116000,  # Initial BTC price
            'long_perp': 116000,
            'short_perp': 116000
        }
        
        # Track cumulative values
        self.cumulative_funding_paid: float = 0.0
        self.cumulative_funding_received: float = 0.0
        self.cumulative_realized_pnl: float = 0.0
        
        # Track position entry times for funding calculation
        self.position_entry_times: Dict[str, datetime] = {}
        
    def calculate_pnl(self, state: PositionState) -> PnLBreakdown:
        """Calculate comprehensive P&L breakdown."""
        
        # Calculate individual components
        spot_pnl = self._calculate_spot_pnl(state)
        long_perp_pnl = self._calculate_perp_pnl(state.long_perp, state.btc_price, 'long')
        short_perp_pnl = self._calculate_perp_pnl(state.short_perp, state.btc_price, 'short')
        funding_pnl = self._calculate_funding_pnl(state)
        
        # Total unrealized P&L
        total_unrealized = spot_pnl + long_perp_pnl + short_perp_pnl + funding_pnl
        
        # Net P&L includes both realized and unrealized
        net_pnl = total_unrealized + self.cumulative_realized_pnl
        
        return PnLBreakdown(
            spot_pnl=spot_pnl,
            long_perp_pnl=long_perp_pnl,
            short_perp_pnl=short_perp_pnl,
            funding_pnl=funding_pnl,
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=self.cumulative_realized_pnl,
            net_pnl=net_pnl,
            timestamp=datetime.utcnow()
        )
    
    def _calculate_spot_pnl(self, state: PositionState) -> float:
        """Calculate P&L from spot BTC holdings."""
        if state.spot_btc <= 0:
            return 0.0
            
        # P&L = (current_price - entry_price) * quantity
        price_diff = state.btc_price - self.entry_prices['spot']
        return price_diff * state.spot_btc
    
    def _calculate_perp_pnl(self, quantity: float, current_price: float, 
                           position_type: str) -> float:
        """Calculate P&L for perpetual positions."""
        if quantity <= 0:
            return 0.0
            
        entry_key = f'{position_type}_perp'
        entry_price = self.entry_prices.get(entry_key, current_price)
        
        if position_type == 'long':
            # Long P&L = (current_price - entry_price) * quantity
            return (current_price - entry_price) * quantity
        else:  # short
            # Short P&L = (entry_price - current_price) * quantity
            return (entry_price - current_price) * quantity
    
    def _calculate_funding_pnl(self, state: PositionState) -> float:
        """Calculate P&L from funding rates.
        
        In perpetual futures:
        - Longs pay shorts when funding is positive
        - Shorts pay longs when funding is negative
        """
        # Net perpetual position
        net_perp_position = state.long_perp - state.short_perp
        
        if abs(net_perp_position) < 0.0001:
            return 0.0
            
        # Funding P&L = -funding_rate * position_value * time_held
        # Negative because positive funding means longs pay
        position_value = abs(net_perp_position) * state.btc_price
        
        # Assume 8-hour funding intervals
        hours_held = 8  # This should be tracked more precisely in production
        funding_periods = hours_held / 8
        
        if net_perp_position > 0:  # Net long pays funding
            funding_pnl = -state.funding_rate * position_value * funding_periods
            self.cumulative_funding_paid += abs(funding_pnl)
        else:  # Net short receives funding
            funding_pnl = state.funding_rate * position_value * funding_periods
            self.cumulative_funding_received += funding_pnl
            
        return funding_pnl
    
    def realize_pnl(self, closed_position: Dict[str, float], 
                   closing_price: float) -> float:
        """Calculate and record realized P&L when closing positions."""
        realized = 0.0
        
        # Calculate P&L for each closed component
        if 'long_perp' in closed_position and closed_position['long_perp'] > 0:
            entry_price = self.entry_prices.get('long_perp', closing_price)
            realized += (closing_price - entry_price) * closed_position['long_perp']
            
        if 'short_perp' in closed_position and closed_position['short_perp'] > 0:
            entry_price = self.entry_prices.get('short_perp', closing_price)
            realized += (entry_price - closing_price) * closed_position['short_perp']
            
        self.cumulative_realized_pnl += realized
        logger.info(f"Realized P&L: ${realized:.2f}, Total realized: ${self.cumulative_realized_pnl:.2f}")
        
        return realized
    
    def update_entry_prices(self, position_type: str, new_price: float, 
                          old_quantity: float, new_quantity: float):
        """Update weighted average entry prices when positions change."""
        if new_quantity <= 0:
            # Position closed, reset entry price
            self.entry_prices[position_type] = new_price
            return
            
        if old_quantity <= 0:
            # New position, set entry price
            self.entry_prices[position_type] = new_price
            self.position_entry_times[position_type] = datetime.utcnow()
            return
            
        # Adding to existing position - calculate weighted average
        added_quantity = new_quantity - old_quantity
        if added_quantity > 0:
            old_value = self.entry_prices[position_type] * old_quantity
            new_value = new_price * added_quantity
            self.entry_prices[position_type] = (old_value + new_value) / new_quantity
    
    def get_pnl_metrics(self, state: PositionState) -> Dict[str, float]:
        """Get comprehensive P&L metrics."""
        breakdown = self.calculate_pnl(state)
        
        # Calculate additional metrics
        total_position_value = abs(state.spot_btc * state.btc_price)
        if state.long_perp > 0:
            total_position_value += state.long_perp * state.btc_price
        if state.short_perp > 0:
            total_position_value += state.short_perp * state.btc_price
            
        roi = 0.0
        if total_position_value > 0:
            roi = (breakdown.net_pnl / total_position_value) * 100
            
        return {
            'spot_pnl': breakdown.spot_pnl,
            'long_perp_pnl': breakdown.long_perp_pnl,
            'short_perp_pnl': breakdown.short_perp_pnl,
            'funding_pnl': breakdown.funding_pnl,
            'unrealized_pnl': breakdown.total_unrealized_pnl,
            'realized_pnl': breakdown.total_realized_pnl,
            'net_pnl': breakdown.net_pnl,
            'roi_percent': roi,
            'cumulative_funding_paid': self.cumulative_funding_paid,
            'cumulative_funding_received': self.cumulative_funding_received,
            'position_value': total_position_value
        }
    
    def reset(self):
        """Reset P&L tracking for new trading session."""
        self.cumulative_realized_pnl = 0.0
        self.cumulative_funding_paid = 0.0
        self.cumulative_funding_received = 0.0
        # Keep entry prices as they represent current positions