"""
Delta-neutral position manager with volatility-based hedging.
"""

import numpy as np
from typing import Optional, Tuple, List
from datetime import datetime, timedelta
from .models import PositionState, HedgeDecision, MarketRegime


class DeltaNeutralManager:
    """Manages delta-neutral positions with volatility-based hedging."""
    
    def __init__(self):
        self.position_state: Optional[PositionState] = None
        self.price_history: List[float] = []
        self.last_hedge_update = datetime.utcnow()
        
    def calculate_delta(self, state: PositionState) -> float:
        """Calculate net delta exposure.
        Δ = Q_B + Q_L - Q_S
        """
        return state.spot_btc + state.long_perp - state.short_perp
    
    def calculate_volatility_24h(self, prices: List[float]) -> float:
        """Calculate 24h realized volatility."""
        if len(prices) < 2:
            return 0.02  # Default 2%
            
        # Filter out NaN values and zeros
        valid_prices = [p for p in prices if not np.isnan(p) and p > 0]
        if len(valid_prices) < 2:
            return 0.02  # Default 2%
            
        # Log returns
        returns = np.diff(np.log(valid_prices))
        
        # Handle NaN returns from log calculation
        returns = returns[~np.isnan(returns)]
        if len(returns) == 0:
            return 0.02  # Default 2%
        
        # For single return, use absolute value as volatility estimate
        if len(returns) == 1:
            vol = abs(returns[0]) * np.sqrt(365)
        else:
            # Annualized volatility
            vol = np.std(returns) * np.sqrt(365)
        
        # Handle edge cases where volatility is 0 or NaN
        if np.isnan(vol) or vol <= 0:
            return 0.02  # Default 2%
            
        return vol
    
    def calculate_hedge_ratio(self, volatility_24h: float) -> float:
        """Determine hedge ratio based on volatility.
        
        h(t) = 0.20 if � < 2%
               0.40 if 2% d � < 4%  
               0.60 if � e 4%
        """
        if volatility_24h < 0.02:
            return 0.20
        elif volatility_24h < 0.04:
            return 0.40
        else:
            return 0.60
    
    def calculate_profit_target(self, volatility_24h: float, 
                               current_price: float) -> float:
        """Calculate profit target price.
        PT = current_price * (1 + k * �_24h)
        """
        k = 1.5  # Empirical multiplier
        return current_price * (1 + k * volatility_24h)
    
    def should_rehedge(self) -> bool:
        """Check if rehedging is needed."""
        # Rehedge every hour
        time_since_last = datetime.utcnow() - self.last_hedge_update
        return time_since_last > timedelta(hours=1)
    
    def apply_funding_multiplier(self, base_position: float,
                                funding_regime: str) -> float:
        """Apply funding-based position scaling."""
        multipliers = {
            "NEUTRAL": 1.0,
            "NORMAL": 1.0,
            "HEATED": 0.5,
            "MANIA": 0.2,
            "EXTREME": 0.0
        }
        return base_position * multipliers.get(funding_regime, 1.0)
    
    def generate_hedge_decision(self, 
                               current_state: PositionState,
                               target_delta: float = 0.0) -> HedgeDecision:
        """Generate hedging decision to achieve target delta."""
        
        current_delta = self.calculate_delta(current_state)
        delta_adjustment = target_delta - current_delta
        
        # Calculate target hedge ratio
        target_hedge = self.calculate_hedge_ratio(current_state.volatility_24h)
        
        # Apply funding multiplier
        target_hedge = self.apply_funding_multiplier(
            target_hedge, 
            current_state.funding_regime
        )
        
        # Calculate position adjustments
        # If we need to reduce delta, increase short or reduce long
        if delta_adjustment < 0:
            adjust_short = abs(delta_adjustment) * target_hedge
            adjust_long = -abs(delta_adjustment) * (1 - target_hedge)
        else:
            adjust_short = -delta_adjustment * target_hedge  
            adjust_long = delta_adjustment * (1 - target_hedge)
        
        return HedgeDecision(
            timestamp=datetime.utcnow(),
            current_hedge_ratio=current_state.hedge_ratio,
            target_hedge_ratio=target_hedge,
            volatility_24h=current_state.volatility_24h,
            reason=f"Rehedge: vol={current_state.volatility_24h:.1%}",
            adjust_short=adjust_short,
            adjust_long=adjust_long
        )
    
    def check_profit_targets(self, state: PositionState) -> bool:
        """Check if profit targets are hit."""
        if state.unrealized_pnl <= 0:
            return False
            
        # Update peak PnL
        if state.unrealized_pnl > state.peak_pnl:
            state.peak_pnl = state.unrealized_pnl
        
        # Check trailing stop (30% drawdown from peak)
        drawdown = (state.peak_pnl - state.unrealized_pnl) / state.peak_pnl
        if drawdown > 0.30:
            return True
            
        # Check profit target based on volatility
        profit_target = self.calculate_profit_target(
            state.volatility_24h,
            116000  # Use initial price as base
        )
        
        # Take profit if current price reaches target
        return state.btc_price >= profit_target