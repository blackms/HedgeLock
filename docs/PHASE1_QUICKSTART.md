# Phase 1 Quick Start: Core Trading Engine

## 🚀 Getting Started with Position Manager

### Step 1: Create Position Manager Service Structure

```bash
# Create service directories
mkdir -p src/hedgelock/position_manager
mkdir -p docker

# Create service files
touch src/hedgelock/position_manager/__init__.py
touch src/hedgelock/position_manager/models.py
touch src/hedgelock/position_manager/manager.py
touch src/hedgelock/position_manager/service.py
touch src/hedgelock/position_manager/api.py
touch docker/Dockerfile.position-manager
```

### Step 2: Position Models

```python
# src/hedgelock/position_manager/models.py

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

class MarketRegime(str, Enum):
    NEUTRAL = "NEUTRAL"
    LONG_BIASED = "LONG_BIASED"  
    SHORT_BIASED = "SHORT_BIASED"
    TAKING_PROFIT = "TAKING_PROFIT"

class PositionState(BaseModel):
    """Current position state snapshot."""
    timestamp: datetime
    
    # Core positions
    spot_btc: float = Field(default=0.27, description="BTC held as collateral")
    long_perp: float = Field(default=0.0, description="Long perpetual position")
    short_perp: float = Field(default=0.0, description="Short perpetual position")
    
    # Calculated fields
    net_delta: float = Field(description="Net BTC exposure")
    hedge_ratio: float = Field(default=1.0, description="Current hedge ratio")
    
    # Market data
    btc_price: float
    volatility_24h: float
    funding_rate: float
    
    # P&L tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    peak_pnl: float = 0.0
    
    # State
    market_regime: MarketRegime = MarketRegime.NEUTRAL
    funding_regime: str = "NORMAL"  # From funding engine
    
    @property
    def total_long(self) -> float:
        return self.spot_btc + self.long_perp
    
    @property
    def delta_neutral(self) -> bool:
        return abs(self.net_delta) < 0.01  # Within 1% of neutral

class HedgeDecision(BaseModel):
    """Hedge adjustment decision."""
    timestamp: datetime
    current_hedge_ratio: float
    target_hedge_ratio: float
    volatility_24h: float
    reason: str
    
    # Actions
    adjust_short: float  # BTC to add/remove from short
    adjust_long: float   # BTC to add/remove from long
    
class ProfitTarget(BaseModel):
    """Profit taking parameters."""
    timestamp: datetime
    target_price: float
    target_pnl: float
    trailing_stop_pct: float = 0.30  # 30% of peak
    volatility_multiplier: float = 1.5  # k in PT = k*σ
```

### Step 3: Core Delta-Neutral Manager

```python
# src/hedgelock/position_manager/manager.py

import numpy as np
from typing import Optional, Tuple
from datetime import datetime, timedelta
from .models import PositionState, HedgeDecision, MarketRegime

class DeltaNeutralManager:
    """Manages delta-neutral positions with volatility-based hedging."""
    
    def __init__(self):
        self.position_state: Optional[PositionState] = None
        self.price_history: list[float] = []
        self.last_hedge_update = datetime.utcnow()
        
    def calculate_delta(self, state: PositionState) -> float:
        """Calculate net delta exposure.
        Δ = Q_B + Q_L - Q_S
        """
        return state.spot_btc + state.long_perp - state.short_perp
    
    def calculate_volatility_24h(self, prices: list[float]) -> float:
        """Calculate 24h realized volatility."""
        if len(prices) < 2:
            return 0.02  # Default 2%
            
        # Log returns
        returns = np.diff(np.log(prices))
        
        # Annualized volatility
        return np.std(returns) * np.sqrt(365)
    
    def calculate_hedge_ratio(self, volatility_24h: float) -> float:
        """Determine hedge ratio based on volatility.
        
        h(t) = 0.20 if σ < 2%
               0.40 if 2% ≤ σ < 4%  
               0.60 if σ ≥ 4%
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
        PT = current_price * (1 + k * σ_24h)
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
            state.btc_price
        )
        
        # Simplified: take profit if price moved by target %
        price_move = abs(state.btc_price - 116000) / 116000  # From initial
        target_move = profit_target / state.btc_price - 1
        
        return price_move >= target_move
```

### Step 4: Service Implementation

```python
# src/hedgelock/position_manager/service.py

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from .manager import DeltaNeutralManager
from .models import PositionState, MarketRegime

logger = logging.getLogger(__name__)

class PositionManagerService:
    """Service for managing delta-neutral positions."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.manager = DeltaNeutralManager()
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.running = False
        
        # Track positions
        self.current_position = PositionState(
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
    
    async def start(self):
        """Start the service."""
        logger.info("Starting Position Manager service...")
        
        # Initialize Kafka
        self.consumer = AIOKafkaConsumer(
            'funding_context',  # Listen to funding updates
            'market_data',      # Listen to price updates
            bootstrap_servers=self.config['kafka_servers'],
            group_id='position-manager-group'
        )
        
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.config['kafka_servers']
        )
        
        await self.consumer.start()
        await self.producer.start()
        
        self.running = True
        
        # Start processing loops
        await asyncio.gather(
            self.process_messages(),
            self.periodic_rehedge()
        )
    
    async def process_messages(self):
        """Process incoming messages."""
        async for msg in self.consumer:
            if not self.running:
                break
                
            try:
                if msg.topic == 'funding_context':
                    await self.handle_funding_update(msg.value)
                elif msg.topic == 'market_data':
                    await self.handle_price_update(msg.value)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def handle_funding_update(self, data: Dict):
        """Handle funding context updates."""
        funding_context = data.get('funding_context', {})
        
        # Update position state with funding info
        self.current_position.funding_regime = funding_context.get(
            'current_regime', 'NORMAL'
        )
        self.current_position.funding_rate = funding_context.get(
            'current_rate', 0) / 100 / 365 / 3  # Convert to 8h rate
        
        # Check if we need to adjust positions due to funding
        if funding_context.get('should_exit', False):
            logger.warning("Emergency exit triggered by funding!")
            await self.emergency_close_positions()
    
    async def periodic_rehedge(self):
        """Periodically check and adjust hedges."""
        while self.running:
            try:
                if self.manager.should_rehedge():
                    await self.rehedge_positions()
                
                # Check profit targets
                if self.manager.check_profit_targets(self.current_position):
                    await self.take_profit()
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in rehedge loop: {e}")
    
    async def rehedge_positions(self):
        """Rehedge positions based on current market conditions."""
        logger.info("Rehedging positions...")
        
        # Generate hedge decision
        decision = self.manager.generate_hedge_decision(
            self.current_position,
            target_delta=0.0  # Target delta-neutral
        )
        
        # Send orders via trade executor
        orders = []
        
        if abs(decision.adjust_long) > 0.001:
            orders.append({
                'symbol': 'BTCUSDT',
                'side': 'BUY' if decision.adjust_long > 0 else 'SELL',
                'quantity': abs(decision.adjust_long),
                'order_type': 'MARKET'
            })
        
        if abs(decision.adjust_short) > 0.001:
            orders.append({
                'symbol': 'BTCUSDT',
                'side': 'SELL' if decision.adjust_short > 0 else 'BUY',
                'quantity': abs(decision.adjust_short),
                'order_type': 'MARKET',
                'position_side': 'SHORT'
            })
        
        # Publish orders
        for order in orders:
            await self.producer.send_and_wait(
                'hedge_trades',
                value={
                    'timestamp': datetime.utcnow().isoformat(),
                    'order_request': order,
                    'hedge_decision': decision.dict()
                }
            )
        
        # Update state
        self.current_position.hedge_ratio = decision.target_hedge_ratio
        self.manager.last_hedge_update = datetime.utcnow()
```

### Step 5: Docker Configuration

```dockerfile
# docker/Dockerfile.position-manager
FROM hedgelock-base:latest

EXPOSE 8009

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8009/health || exit 1

CMD ["python", "-m", "uvicorn", "src.hedgelock.position_manager.api:app", \
     "--host", "0.0.0.0", "--port", "8009"]
```

### Step 6: Add to Docker Compose

```yaml
# Add to docker-compose.yml

  position-manager:
    build:
      context: .
      dockerfile: docker/Dockerfile.position-manager
    container_name: hedgelock-position-manager
    environment:
      - SERVICE_NAME=position-manager
      - LOG_LEVEL=INFO
      - KAFKA__BOOTSTRAP_SERVERS=kafka:29092
      - MONITORING__METRICS_PORT=9096
    ports:
      - "8009:8009"
      - "9096:9096"
    networks:
      - hedgelock-network
    depends_on:
      kafka:
        condition: service_healthy
      funding-engine:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8009/health"]
      interval: 30s
      timeout: 3s
      retries: 3
```

### Step 7: Integration Tests

```python
# tests/integration/test_position_manager.py

import pytest
from src.hedgelock.position_manager.manager import DeltaNeutralManager
from src.hedgelock.position_manager.models import PositionState

def test_delta_calculation():
    """Test delta calculation."""
    manager = DeltaNeutralManager()
    
    state = PositionState(
        timestamp=datetime.utcnow(),
        spot_btc=0.27,
        long_perp=0.213,
        short_perp=0.213,
        net_delta=0.27,
        hedge_ratio=1.0,
        btc_price=116000,
        volatility_24h=0.02,
        funding_rate=0.0001
    )
    
    delta = manager.calculate_delta(state)
    assert abs(delta - 0.27) < 0.001  # Should equal spot position

def test_hedge_ratio_calculation():
    """Test volatility-based hedge ratio."""
    manager = DeltaNeutralManager()
    
    assert manager.calculate_hedge_ratio(0.01) == 0.20  # Low vol
    assert manager.calculate_hedge_ratio(0.03) == 0.40  # Med vol
    assert manager.calculate_hedge_ratio(0.05) == 0.60  # High vol

def test_funding_multiplier():
    """Test funding-based position scaling."""
    manager = DeltaNeutralManager()
    
    assert manager.apply_funding_multiplier(1.0, "NORMAL") == 1.0
    assert manager.apply_funding_multiplier(1.0, "HEATED") == 0.5
    assert manager.apply_funding_multiplier(1.0, "EXTREME") == 0.0
```

## 🚀 Next Steps

1. **Implement Profit Taking Logic**
   - Track peak PnL
   - Implement trailing stop
   - Auto-repay loan from profits

2. **Add Volatility Calculation**
   - Store price history
   - Calculate rolling 24h volatility
   - Update hedge ratios hourly

3. **Connect to Trade Executor**
   - Send properly formatted orders
   - Handle order confirmations
   - Update position state

4. **Create Monitoring Dashboard**
   - Real-time position display
   - Delta tracking
   - P&L visualization

This gives you a working foundation for the core trading engine. Each component can be tested independently before full integration.