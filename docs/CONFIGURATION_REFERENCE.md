# HedgeLock Configuration Reference

## Environment Variables

### Global Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `SERVICE_NAME` | Service-specific | Name of the service for logging |
| `ENVIRONMENT` | `development` | Environment (development, staging, production) |

### Kafka Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA__BOOTSTRAP_SERVERS` | `kafka:29092` | Kafka broker addresses |
| `KAFKA__CONSUMER_GROUP_PREFIX` | `hedgelock` | Prefix for consumer groups |
| `KAFKA__MAX_POLL_RECORDS` | `500` | Max records per poll |
| `KAFKA__ENABLE_AUTO_COMMIT` | `false` | Auto-commit offsets |

### Funding Engine Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNDING_ENGINE_KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092` | Kafka brokers |
| `FUNDING_ENGINE_CONSUMER_GROUP_ID` | `funding-engine-group` | Consumer group |
| `FUNDING_ENGINE_FUNDING_RATES_TOPIC` | `funding_rates` | Input topic |
| `FUNDING_ENGINE_FUNDING_CONTEXT_TOPIC` | `funding_context` | Output topic |
| `FUNDING_ENGINE_REDIS_HOST` | `redis` | Redis hostname |
| `FUNDING_ENGINE_REDIS_PORT` | `6379` | Redis port |
| `FUNDING_ENGINE_HISTORY_WINDOW_HOURS` | `168` | History window (7 days) |
| `FUNDING_ENGINE_REGIME_UPDATE_INTERVAL_SECONDS` | `60` | Update interval |

### Funding Regime Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNDING_ENGINE_REGIME_NEUTRAL_THRESHOLD` | `10.0` | < 10% APR |
| `FUNDING_ENGINE_REGIME_NORMAL_THRESHOLD` | `50.0` | 10-50% APR |
| `FUNDING_ENGINE_REGIME_HEATED_THRESHOLD` | `100.0` | 50-100% APR |
| `FUNDING_ENGINE_REGIME_MANIA_THRESHOLD` | `300.0` | 100-300% APR |
| `FUNDING_ENGINE_EMERGENCY_EXIT_THRESHOLD` | `300.0` | > 300% APR triggers exit |

### Exchange Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BYBIT_API_KEY` | None | Bybit API key |
| `BYBIT_API_SECRET` | None | Bybit API secret |
| `BYBIT_TESTNET` | `true` | Use testnet |

### Risk Engine Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `RISK__LTV_NORMAL_THRESHOLD` | `0.5` | Normal LTV threshold |
| `RISK__LTV_CAUTION_THRESHOLD` | `0.65` | Caution LTV threshold |
| `RISK__LTV_DANGER_THRESHOLD` | `0.8` | Danger LTV threshold |
| `RISK__LTV_CRITICAL_THRESHOLD` | `0.9` | Critical LTV threshold |

### Trade Executor Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EXECUTOR_MAX_ORDER_SIZE_BTC` | `1.0` | Max order size in BTC |
| `EXECUTOR_MAX_DAILY_VOLUME_BTC` | `10.0` | Max daily volume |
| `EXECUTOR_ORDER_TIMEOUT_MS` | `120000` | Order timeout (2 min) |
| `EXECUTOR_STATUS_POLL_INTERVAL_MS` | `1000` | Status check interval |

### Alert Service Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | None | Telegram bot token |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | None | SMTP username |
| `SMTP_PASSWORD` | None | SMTP password |

### Monitoring Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITORING__METRICS_PORT` | `9090` | Prometheus metrics port |
| `MONITORING__ENABLE_METRICS` | `true` | Enable metrics collection |

## Service Ports

| Service | API Port | Metrics Port | Description |
|---------|----------|--------------|-------------|
| Collector | 8001 | 9091 | Data ingestion |
| Risk Engine | 8002 | 9192 | Risk calculation |
| Hedger | 8003 | 9093 | Hedge execution |
| Trade Executor | 8004 | 9094 | Trade execution |
| Funding Engine | 8005 | 9095 | Funding awareness |
| Treasury | 8007 | - | Fund management |
| Alert | 8008 | - | Notifications |
| Kafka UI | 8080 | - | Kafka monitoring |

## Kafka Topics

| Topic | Description | Producers | Consumers |
|-------|-------------|-----------|-----------|
| `account_raw` | Raw account data | Collector | Risk Engine |
| `funding_rates` | Exchange funding rates | Collector | Funding Engine |
| `funding_context` | Processed funding context | Funding Engine | Risk Engine, Hedger |
| `risk_state` | Risk assessments | Risk Engine | Hedger |
| `hedge_trades` | Hedge decisions | Hedger | Trade Executor |
| `trade_confirmations` | Trade results | Trade Executor | Risk Engine |
| `treasury_actions` | Fund movements | Treasury | Alert |

## Position Multiplier Formula

The position multiplier determines how much to reduce positions based on funding:

```python
# Simplified formula
if regime == EXTREME:
    multiplier = 0.0  # Exit all
elif regime == MANIA:
    multiplier = 0.0 to 0.4  # Heavy reduction
elif regime == HEATED:
    multiplier = 0.4 to 0.7  # Moderate reduction
elif regime == NORMAL:
    multiplier = 0.7 to 1.0  # Slight reduction
else:  # NEUTRAL
    multiplier = 1.0  # Full position
```

## Docker Compose Override

Create `docker-compose.override.yml` for local customization:

```yaml
version: '3.8'

services:
  funding-engine:
    environment:
      - LOG_LEVEL=DEBUG
      - FUNDING_ENGINE_REGIME_UPDATE_INTERVAL_SECONDS=30
    volumes:
      - ./src:/app/src  # Mount source for development

  collector:
    environment:
      - BYBIT_API_KEY=your_test_key
      - BYBIT_API_SECRET=your_test_secret
```

## Production Configuration

### Recommended Production Settings

```bash
# .env.production
ENVIRONMENT=production
LOG_LEVEL=INFO
BYBIT_TESTNET=false

# Increase thresholds for production
FUNDING_ENGINE_EMERGENCY_EXIT_THRESHOLD=500.0
EXECUTOR_MAX_ORDER_SIZE_BTC=5.0
EXECUTOR_MAX_DAILY_VOLUME_BTC=50.0

# Enable monitoring
MONITORING__ENABLE_METRICS=true

# Configure alerts
TELEGRAM_BOT_TOKEN=your_production_bot
ALERT_CRITICAL_ONLY=true
```

### Security Considerations

1. **Never commit secrets** to version control
2. Use **environment variables** for sensitive data
3. Enable **SSL/TLS** for external connections
4. Set up **firewall rules** for service ports
5. Use **read-only** database users where possible
6. Enable **API rate limiting**
7. Configure **log rotation** to prevent disk fill

---

*Last Updated: January 2025*