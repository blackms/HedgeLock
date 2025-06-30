# Local Development Guide

This guide explains how to run the HedgeLock system locally using Docker Compose.

## Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose (included with Docker Desktop)
- Git
- Make (optional, for convenience commands)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/blackms/HedgeLock.git
   cd HedgeLock
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start all services**
   ```bash
   docker compose up -d
   # Or using Make:
   make compose-up
   ```

4. **Check service status**
   ```bash
   docker compose ps
   # Or using Make:
   make compose-ps
   ```

## Services Overview

The Docker Compose setup includes all five HedgeLock microservices plus supporting infrastructure:

### Core Services

| Service | Port | Health Check | Description |
|---------|------|-------------|-------------|
| collector | 8001 | http://localhost:8001/health | Data ingestion from Bybit |
| risk-engine | 8002 | http://localhost:8002/health | LTV calculation and risk assessment |
| hedger | 8003 | http://localhost:8003/health | Automated trading execution |
| treasury | 8004 | http://localhost:8004/health | Fund management and allocation |
| alert | 8005 | http://localhost:8005/health | Multi-channel notifications |

### Infrastructure

| Service | Port | Description |
|---------|------|-------------|
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis cache and state store |
| kafka | 9092 | Apache Kafka message broker |
| zookeeper | 2181 | Kafka coordination service |
| kafka-ui | 8080 | Web UI for Kafka monitoring |

## Service Endpoints

Each service provides the following endpoints:

- `GET /health` - Health check endpoint
- `GET /stats` - Service statistics
- `GET /docs` - FastAPI automatic documentation

### Service-Specific Endpoints

#### Collector (port 8001)
- No additional endpoints (data flows to Kafka in production)

#### Risk Engine (port 8002)
- `GET /risk-state` - Current risk state and LTV

#### Hedger (port 8003)
- `GET /orders` - Recent orders (last 10)

#### Treasury (port 8004)
- `GET /actions` - Recent treasury actions (last 10)

#### Alert (port 8005)
- `GET /alerts` - Recent alerts (last 20)
- `POST /test-alert` - Send a test alert

## Viewing Logs

### All services
```bash
docker compose logs -f
# Or using Make:
make compose-logs
```

### Specific service
```bash
docker compose logs -f collector
# Or using Make:
make logs-collector
```

Available log commands:
- `make logs-collector`
- `make logs-risk`
- `make logs-hedger`
- `make logs-treasury`
- `make logs-alert`

## Environment Variables

Key environment variables (see `.env.example` for full list):

### General
- `LOG_LEVEL` - Logging level (INFO, DEBUG, WARNING, ERROR)
- `DEBUG` - Enable debug mode

### Bybit API
- `BYBIT_API_KEY` - Your Bybit API key
- `BYBIT_API_SECRET` - Your Bybit API secret
- `BYBIT_TESTNET` - Use testnet (true/false)

### Risk Parameters
- `LTV_TARGET_RATIO` - Target LTV ratio (default: 40)
- `LTV_MAX_RATIO` - Maximum LTV ratio (default: 50)

### Trading Limits
- `MAX_ORDER_SIZE_BTC` - Maximum order size in BTC
- `MAX_POSITION_SIZE_BTC` - Maximum position size in BTC

### Notifications
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `SMTP_HOST` - Email server host
- `SMTP_USER` - Email username
- `SMTP_PASSWORD` - Email password

## Development Workflow

1. **Make changes to service code**
   - Services are in `src/hedgelock/<service_name>/`
   - Each service has a `main.py` file

2. **Rebuild and restart services**
   ```bash
   docker compose build
   docker compose up -d
   # Or using Make:
   make compose-build
   make compose-restart
   ```

3. **Check service health**
   ```bash
   curl http://localhost:8001/health
   curl http://localhost:8002/health
   # ... etc
   ```

## Stub Mode

All services run in "stub mode" by default, which means:
- No real API connections are made
- Services generate simulated data
- All operations are safe for testing

To see stub activity:
1. Watch the logs: `make compose-logs`
2. Check stats endpoints: `curl http://localhost:8001/stats`
3. View generated data via service-specific endpoints

## Stopping Services

```bash
docker compose down
# Or using Make:
make compose-down
```

To remove volumes (database data):
```bash
docker compose down -v
```

## Troubleshooting

### Services not starting
- Check logs: `docker compose logs <service-name>`
- Verify ports are not in use: `lsof -i :8001` (etc.)
- Ensure Docker is running

### Database connection issues
- Wait for postgres to be healthy: `docker compose ps`
- Check database logs: `docker compose logs postgres`

### Cannot access service endpoints
- Verify service is running: `docker compose ps`
- Check health endpoint: `curl http://localhost:<port>/health`
- Review service logs for errors

## Kafka Management

### Viewing Kafka Topics

The system automatically creates four topics on startup:
- `account_raw` - Raw account data from Bybit
- `risk_state` - Calculated risk states and LTV
- `hedge_trades` - Hedge trade commands
- `treasury_actions` - Treasury fund movements

To list all topics:
```bash
docker exec hedgelock-kafka kafka-topics --bootstrap-server localhost:29092 --list
# Or using Make:
make kafka-topics
```

### Kafka UI

Access the Kafka UI at http://localhost:8080 to:
- Browse topics and messages
- Monitor consumer groups
- View broker health
- Inspect message content

### Testing Kafka

To produce a test message:
```bash
docker exec -it hedgelock-kafka kafka-console-producer --bootstrap-server localhost:29092 --topic account_raw
# Type your message and press Ctrl+D
```

To consume messages:
```bash
docker exec -it hedgelock-kafka kafka-console-consumer --bootstrap-server localhost:29092 --topic account_raw --from-beginning
```

## Next Steps

1. Implement real Bybit WebSocket connections in collector
2. Connect services to Kafka for inter-service communication
3. Implement actual trading logic in hedger
4. Connect real notification channels in alert
5. Add comprehensive monitoring with Prometheus/Grafana