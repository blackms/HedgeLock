# Architect Prompt: hedgelock-hedger

You are a senior Python developer implementing the **hedgelock-hedger** microservice for the HedgeLock MVP.

## Context
The HedgeLock system protects loans by automatically hedging BTC exposure with perpetual futures. The hedger service executes trading strategies based on risk signals, managing positions to maintain safe LTV ratios.

## Your Task
Design and implement a Python microservice that:

1. **Responds to risk states from Kafka**:
   - Monitors `risk-states` topic for hedging signals
   - Reacts to risk level changes (CAUTION/DANGER/CRITICAL)
   - Processes required hedge sizes

2. **Executes intelligent trading strategies**:
   - Places BTCUSDT perpetual short orders
   - Manages order lifecycle (place, modify, cancel)
   - Optimizes execution for minimal slippage
   - Handles partial fills and rejections

3. **Publishes execution results**:
   - Emits to `hedge-executions` topic
   - Reports fills, costs, and position changes
   - Tracks strategy performance metrics

## Technical Requirements

### Stack
- Python 3.12 with asyncio
- FastAPI for control API
- pybit for Bybit trading
- aiokafka for event streaming
- Redis for order state

### Trading Engine
```python
class HedgingEngine:
    async def execute_hedge(self, risk_state: RiskState) -> HedgeExecution:
        """Execute hedging based on risk state"""
        # 1. Calculate order parameters
        size = self._calculate_position_size(risk_state)
        price = await self._get_execution_price(risk_state)
        
        # 2. Risk checks
        if not self._validate_order_params(size, price):
            return HedgeExecution(status="rejected", reason="risk_limits")
        
        # 3. Execute with smart order routing
        order = await self._place_limit_order(size, price)
        
        # 4. Monitor and manage execution
        fill = await self._monitor_fill(order, timeout=30)
        
        return HedgeExecution(
            order_id=order.id,
            size=fill.size,
            price=fill.price,
            status="completed"
        )
```

### Order Management
```python
class OrderManager:
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: Decimal,
        price: Decimal,
        time_in_force: str = "IOC"
    ) -> Order:
        """Place limit order with optimal parameters"""
        
    async def modify_order(self, order_id: str, new_price: Decimal) -> Order:
        """Modify existing order price"""
        
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel unfilled order"""
```

### Execution Strategies

#### 1. Aggressive Hedging (CRITICAL state)
```python
def aggressive_strategy(self, risk_state: RiskState) -> OrderParams:
    # Take liquidity immediately
    return OrderParams(
        size=risk_state.required_hedge,
        price_offset=-10,  # 10 bps through mid
        time_in_force="IOC",
        post_only=False
    )
```

#### 2. Passive Hedging (CAUTION state)
```python
def passive_strategy(self, risk_state: RiskState) -> OrderParams:
    # Provide liquidity for better pricing
    return OrderParams(
        size=risk_state.required_hedge * 0.5,  # Scale in
        price_offset=5,  # 5 bps better than mid
        time_in_force="GTC",
        post_only=True
    )
```

#### 3. TWAP Execution (Large positions)
```python
async def twap_strategy(self, total_size: Decimal, duration: int) -> List[Order]:
    # Split large orders over time
    slice_size = total_size / (duration / 30)  # 30-second slices
    orders = []
    
    for i in range(duration // 30):
        order = await self.place_limit_order(size=slice_size)
        orders.append(order)
        await asyncio.sleep(30)
    
    return orders
```

### Position Management
- Track current hedge position vs. target
- Calculate position deltas in real-time
- Implement position limits and checks
- Handle cross-margin requirements

### Risk Controls
```python
class RiskLimits:
    max_order_size_btc = Decimal("10.0")
    max_position_size_btc = Decimal("50.0")
    max_orders_per_minute = 20
    min_order_size_btc = Decimal("0.001")
    max_slippage_bps = 50
```

## Deliverables

1. **Service Implementation**:
   - `src/hedger/main.py`: Service orchestrator
   - `src/hedger/engine.py`: Core hedging logic
   - `src/hedger/strategies.py`: Execution strategies
   - `src/hedger/order_manager.py`: Order lifecycle

2. **Configuration**:
   - `config/hedger.yaml`: Strategy parameters
   - Risk limits and controls
   - Execution algorithm selection

3. **Tests**:
   - Unit tests for strategies
   - Integration tests with exchange simulator
   - Backtest framework for optimization

4. **Monitoring**:
   - Real-time PnL tracking
   - Slippage analysis
   - Fill rate metrics
   - Strategy performance analytics

## Performance Requirements
- < 100ms from signal to order
- Handle 50+ orders/second
- 99%+ fill rate in normal markets
- Graceful degradation in volatility

## Important Considerations

### Market Impact
- Minimize order book impact
- Use iceberg orders for large sizes
- Implement anti-gaming measures
- Monitor for adverse selection

### Execution Quality
- Track implementation shortfall
- Measure price improvement
- Optimize for total cost (fees + slippage)
- A/B test strategy parameters

### Error Handling
- Retry failed orders with backoff
- Handle exchange maintenance windows
- Implement circuit breakers
- Failover to backup strategies

### Compliance
- Maintain full audit trail
- Record all order decisions
- Implement kill switches
- Support manual overrides

## Quality Criteria
- Consistent hedge maintenance
- Minimal execution costs
- Robust error handling
- Clear strategy logic
- Comprehensive testing

Remember: This service manages real money in volatile markets. Precision, reliability, and risk management are essential.