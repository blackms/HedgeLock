# HedgeLock Collector Service

The collector service is responsible for ingesting real-time data from Bybit exchange and publishing it to Kafka topics for downstream processing.

## Overview

The collector service connects to Bybit's WebSocket and REST APIs to gather:
- Account balances and updates
- Position information
- Market data (prices, order book)
- Collateral and loan information
- Order updates

All data is normalized and published to the `account_raw` Kafka topic for consumption by other services.

## Architecture

### Components

1. **WebSocket Client** (`websocket_client.py`)
   - Connects to Bybit's public and private WebSocket streams
   - Handles real-time updates for market data, positions, and orders
   - Implements automatic reconnection with exponential backoff
   - Maintains persistent connections with heartbeat monitoring

2. **REST Client** (`rest_client.py`)
   - Polls for collateral and loan information
   - Fetches account balances when WebSocket data is unavailable
   - Implements HMAC signature authentication

3. **Kafka Producer** (`kafka_producer.py`)
   - Publishes normalized data to Kafka topics
   - Ensures exactly-once delivery with idempotent producer
   - Handles message serialization with Decimal support
   - Implements trace ID propagation for observability

4. **Data Models** (`models.py`)
   - Pydantic models for type safety and validation
   - Supports all required data types: positions, balances, orders, etc.

## Configuration

The service uses environment variables for configuration:

### Bybit Settings
- `BYBIT_API_KEY`: Your Bybit API key
- `BYBIT_API_SECRET`: Your Bybit API secret
- `BYBIT_TESTNET`: Use testnet (default: true)
- `BYBIT_COLLATERAL_POLL_INTERVAL`: Polling interval in seconds (default: 5)
- `BYBIT_LOAN_POLL_INTERVAL`: Loan info polling interval (default: 5)

### Kafka Settings
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka bootstrap servers (default: localhost:9092)
- `KAFKA_TOPIC_ACCOUNT_RAW`: Topic for account updates (default: account_raw)

### Monitoring Settings
- `MONITORING_LOG_LEVEL`: Log level (default: INFO)
- `MONITORING_LOG_FORMAT`: Log format - json or text (default: json)

## API Endpoints

- `GET /health`: Health check endpoint
- `GET /stats`: Service statistics

## Data Flow

1. **WebSocket Streams**:
   - Public: Market data, order book updates
   - Private: Wallet updates, position changes, order updates

2. **REST Polling**:
   - Collateral information (LTV, collateral value)
   - Active loan details
   - Account balances (fallback)

3. **Kafka Publishing**:
   - All data published to `account_raw` topic
   - Messages include trace IDs for distributed tracing
   - Key-based partitioning for account updates

## Message Schema

### Account Update
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "account_id": "default_account",
  "balances": {
    "BTC": {
      "coin": "BTC",
      "wallet_balance": "2.5",
      "available_balance": "2.0"
    }
  },
  "positions": [...],
  "collateral_info": {
    "ltv": "0.65",
    "collateral_value": "100000.00",
    "borrowed_amount": "65000.00",
    "collateral_ratio": "1.54",
    "free_collateral": "35000.00"
  },
  "loan_info": {...},
  "source": "collector",
  "trace_id": "uuid-v4"
}
```

## Running the Service

### Local Development
```bash
python -m hedgelock.collector.main
```

### Docker
```bash
docker build -f docker/Dockerfile.collector -t hedgelock-collector .
docker run -p 8000:8000 hedgelock-collector
```

### Docker Compose
```bash
docker-compose up collector
```

## Monitoring

The service provides comprehensive logging with structured JSON output:
- All WebSocket connection events
- Message processing metrics
- Error tracking with stack traces
- Trace ID propagation for request correlation

## Error Handling

- Automatic WebSocket reconnection with exponential backoff
- Dead letter queue for failed Kafka messages
- Circuit breaker pattern for external dependencies
- Graceful shutdown on SIGTERM/SIGINT

## Performance

- Designed to handle 1000+ messages/second
- < 50ms latency from WebSocket to Kafka
- Efficient message batching and compression
- Horizontal scaling ready