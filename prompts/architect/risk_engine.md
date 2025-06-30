# Architect Prompt: hedgelock-risk

You are a senior Python developer implementing the **hedgelock-risk** microservice for the HedgeLock MVP.

## Context
The HedgeLock system protects cryptocurrency loans from liquidation. The risk engine is the brain that continuously calculates loan health metrics and determines when hedging actions are needed.

## Your Task
Design and implement a Python microservice that:

1. **Consumes real-time data from Kafka**:
   - Account updates (loan amount, collateral value)
   - Market data (BTC spot/perp prices)
   - Position changes (current hedge positions)

2. **Calculates risk metrics**:
   - LTV ratio: (Loan Amount / Collateral Value) × 100
   - Net Delta: BTC Spot Holdings - BTC Perp Short
   - Liquidation distance: Buffer until critical LTV
   - Hedge effectiveness: PnL offset ratio

3. **Emits risk states to Kafka**:
   - SAFE: LTV < 40%
   - CAUTION: 40% ≤ LTV < 45%
   - DANGER: 45% ≤ LTV < 48%
   - CRITICAL: LTV ≥ 48%

## Technical Requirements

### Stack
- Python 3.12 with asyncio
- FastAPI for metrics API
- aiokafka for stream processing
- NumPy/Pandas for calculations
- Redis for state persistence

### Core Algorithms
```python
class RiskCalculator:
    def calculate_ltv(self, loan_amount: Decimal, collateral_value: Decimal) -> Decimal:
        """Calculate Loan-to-Value ratio"""
        return (loan_amount / collateral_value) * 100
    
    def calculate_net_delta(self, spot_btc: Decimal, perp_btc: Decimal) -> Decimal:
        """Calculate net BTC exposure"""
        return spot_btc - abs(perp_btc)
    
    def calculate_hedge_ratio(self, net_delta: Decimal, ltv: Decimal) -> Decimal:
        """Determine required hedge size based on risk"""
        risk_multiplier = self._get_risk_multiplier(ltv)
        return net_delta * risk_multiplier
```

### Data Models
```python
class RiskState(BaseModel):
    timestamp: datetime
    account_id: str
    ltv_ratio: Decimal
    net_delta: Decimal
    risk_level: RiskLevel  # SAFE/CAUTION/DANGER/CRITICAL
    required_hedge: Decimal
    liquidation_price: Decimal
    metrics: RiskMetrics

class RiskMetrics(BaseModel):
    collateral_value_usd: Decimal
    loan_amount_usd: Decimal
    spot_exposure_btc: Decimal
    perp_exposure_btc: Decimal
    unrealized_pnl: Decimal
    margin_usage: Decimal
```

### State Management
- Maintain running calculations in Redis
- Store last 1000 risk states for analysis
- Implement state recovery on restart
- Track state transitions for alerting

### Performance Requirements
- Process updates within 100ms
- Support 100+ accounts simultaneously
- Calculate rolling statistics (1m, 5m, 1h)
- Emit states immediately on level change

## Deliverables

1. **Service Implementation**:
   - `src/risk/main.py`: Service orchestrator
   - `src/risk/calculator.py`: Risk calculation engine
   - `src/risk/stream_processor.py`: Kafka consumer/producer
   - `src/risk/state_manager.py`: Redis state handling

2. **Configuration**:
   - `config/risk.yaml`: Thresholds and parameters
   - Risk level definitions and triggers
   - Calculation intervals and windows

3. **Tests**:
   - Unit tests for all calculations
   - Scenario tests (market crash, recovery)
   - Performance benchmarks

4. **Monitoring**:
   - Prometheus metrics for risk levels
   - Grafana dashboards for LTV trends
   - Alerting rules for anomalies

## Risk Management Logic

### LTV Bands
- **0-35%**: Ultra-safe, no action needed
- **35-40%**: Safe, monitor closely
- **40-45%**: Caution, prepare hedging
- **45-48%**: Danger, aggressive hedging
- **48-50%**: Critical, maximum hedging
- **>50%**: Emergency, alert immediately

### Hedge Sizing
```python
def _get_risk_multiplier(self, ltv: Decimal) -> Decimal:
    if ltv < 40:
        return 0.0  # No hedge needed
    elif ltv < 45:
        return 0.5  # Partial hedge
    elif ltv < 48:
        return 0.8  # Strong hedge
    else:
        return 1.0  # Full hedge
```

### Special Considerations
- Hysteresis to prevent flip-flopping
- Smoothing for volatile markets
- Emergency overrides for black swan events
- Integration with circuit breakers

## Quality Criteria
- Accurate calculations (6 decimal precision)
- No missed risk state transitions
- Complete audit trail of decisions
- Explainable risk metrics
- Testable, maintainable code

## Important Notes
- This service determines financial safety - accuracy is paramount
- All calculations must be deterministic and reproducible
- Implement comprehensive logging for post-mortem analysis
- Design for regulatory compliance and auditing

Remember: The risk engine protects users' funds. Every calculation matters.