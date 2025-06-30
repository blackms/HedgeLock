# Architect Prompt: hedgelock-collector

You are a senior Python developer implementing the **hedgelock-collector** microservice for the HedgeLock MVP.

## Context
The HedgeLock system monitors cryptocurrency-backed loans on Bybit, maintaining safe LTV ratios through automated hedging. The collector service is the data ingestion layer that feeds real-time information to all other components.

## Your Task
Design and implement a Python microservice that:

1. **Connects to Bybit WebSocket APIs** for:
   - Account updates (balances, positions, orders)
   - Market data (BTCUSDT spot and perpetual prices)
   - Loan status updates

2. **Publishes normalized data to Kafka topics**:
   - `account-updates`: Account balances, loan details
   - `market-data`: Price ticks, order book snapshots
   - `position-changes`: Position updates, PnL changes

3. **Handles reliability concerns**:
   - Automatic reconnection on WebSocket failure
   - Message deduplication
   - Heartbeat monitoring
   - Graceful shutdown

## Technical Requirements

### Stack
- Python 3.12 with asyncio
- FastAPI for health/status endpoints
- pybit for Bybit WebSocket client
- aiokafka for Kafka producer
- Pydantic for data validation

### Data Models
```python
class AccountUpdate(BaseModel):
    timestamp: datetime
    account_id: str
    balances: Dict[str, Decimal]
    loan_amount: Decimal
    collateral_value: Decimal
    positions: List[Position]

class MarketData(BaseModel):
    timestamp: datetime
    symbol: str
    price: Decimal
    volume_24h: Decimal
    bid: Decimal
    ask: Decimal
```

### Configuration
- Environment variables for Bybit API credentials
- Kafka connection settings
- Configurable reconnection delays
- Rate limiting parameters

### Error Handling
- Exponential backoff for reconnections
- Dead letter queue for failed messages
- Structured logging with correlation IDs
- Metrics for monitoring (messages/sec, lag, errors)

## Deliverables

1. **Service Implementation**:
   - `src/collector/main.py`: Service entry point
   - `src/collector/websocket_client.py`: Bybit WebSocket handler
   - `src/collector/kafka_producer.py`: Message publisher
   - `src/collector/models.py`: Pydantic data models

2. **Configuration**:
   - `config/collector.yaml`: Service configuration
   - `docker/Dockerfile.collector`: Container definition

3. **Tests**:
   - Unit tests for message parsing
   - Integration tests with mock WebSocket
   - Load tests for throughput validation

4. **Documentation**:
   - API documentation for health endpoints
   - Message schema documentation
   - Deployment guide

## Quality Criteria
- Zero message loss during normal operation
- < 50ms latency from WebSocket to Kafka
- Handles 1000+ messages/second
- 99.9% uptime with automatic recovery
- Clean, typed, testable code

## Important Notes
- Never log sensitive data (API keys, positions)
- Use structured logging for observability
- Implement circuit breakers for external dependencies
- Design for horizontal scaling

Remember: This service is the foundation of HedgeLock's real-time capabilities. Reliability and performance are critical.