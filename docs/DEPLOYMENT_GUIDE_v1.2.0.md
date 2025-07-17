# HedgeLock v1.2.0 Deployment Guide

## Overview

This guide documents the deployment process for HedgeLock v1.2.0 with Funding Awareness feature. It includes all fixes and configurations discovered during deployment.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Known Issues & Fixes](#known-issues--fixes)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)
7. [Production Checklist](#production-checklist)

## Prerequisites

- Docker & Docker Compose installed
- Python 3.11+ (for local testing)
- 8GB+ RAM recommended
- Ports available: 8001-8008, 8080, 9090-9095, 5432, 6379, 9092, 29092, 2181

## Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/hedgelock.git
cd hedgelock

# Build base image
docker build -t hedgelock-base:latest -f docker/Dockerfile.base .

# Start all services
docker-compose up -d

# Wait for services to stabilize (30-60 seconds)
sleep 30

# Check service health
docker ps --format "table {{.Names}}\t{{.Status}}"

# View funding engine logs
docker logs hedgelock-funding-engine --tail 50
```

## Configuration

### Critical Configuration Changes

#### 1. Kafka Internal Port Configuration

**Issue**: Services must use Kafka's internal port (29092) not the external port (9092)

**Fix Applied**: Update all service configurations:

```yaml
# docker-compose.yml
environment:
  - KAFKA__BOOTSTRAP_SERVERS=kafka:29092  # NOT kafka:9092
```

**Files Updated**:
- `/src/hedgelock/config.py`
- `/src/hedgelock/funding_engine/config.py`
- `/src/hedgelock/trade_executor/config.py`

#### 2. Funding Rate Validation Fix

**Issue**: Validation was double-converting APR rates causing false EXTREME detections

**Fix Applied**: Update validation to handle annualized rates correctly:

```python
# src/hedgelock/shared/funding_errors.py
def validate_funding_rate(symbol: str, rate: float, is_annualized: bool = True) -> None:
    if is_annualized:
        apr = rate  # Already in annualized percentage
    else:
        apr = rate * 3 * 365 * 100  # Convert 8h rate to APR
```

### Environment Variables

Create `.env` file for production:

```bash
# API Keys (Required for real trading)
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=false  # Set to true for testnet

# Optional: Alerting
TELEGRAM_BOT_TOKEN=your_bot_token
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### Funding Regime Thresholds

Default thresholds (% APR):
- **NEUTRAL**: < 10%
- **NORMAL**: 10-50%
- **HEATED**: 50-100%
- **MANIA**: 100-300%
- **EXTREME**: > 300%

Customize via environment variables:

```bash
FUNDING_ENGINE_REGIME_NEUTRAL_THRESHOLD=10.0
FUNDING_ENGINE_REGIME_NORMAL_THRESHOLD=50.0
FUNDING_ENGINE_REGIME_HEATED_THRESHOLD=100.0
FUNDING_ENGINE_REGIME_MANIA_THRESHOLD=300.0
FUNDING_ENGINE_EMERGENCY_EXIT_THRESHOLD=300.0
```

## Known Issues & Fixes

### 1. Service Health Check Failures

**Symptoms**: Alert, Treasury, Hedger services show as unhealthy

**Cause**: Services running in stub mode without API credentials

**Solution**: 
- For testing: Ignore these health check failures
- For production: Add proper API credentials in `.env`

### 2. JSON Parsing Errors in Logs

**Symptoms**: "Expecting property name enclosed in double quotes" errors

**Cause**: Old/malformed messages in Kafka topics

**Solution**: These can be ignored as they're from previous test messages

### 3. No Hedge Trades Generated

**Symptoms**: No messages in `hedge_trades` topic

**Cause**: Risk engine expects lending/collateral data format, not futures positions

**Solution**: This is by design - the funding engine publishes contexts for other services to consume

## Monitoring

### 1. Web Dashboard

Access the monitoring dashboard:

```bash
# Start web server
cd monitoring
python3 -m http.server 8888 &

# Open browser
open http://localhost:8888/funding_dashboard.html
```

Features:
- Real-time funding rates
- Regime visualization
- Position multipliers
- Emergency alerts

### 2. Kafka UI

Access Kafka UI: http://localhost:8080

Monitor topics:
- `funding_rates`: Raw funding rate data
- `funding_context`: Processed funding contexts with regimes
- `account_raw`: Account/position data
- `risk_state`: Risk assessments
- `hedge_trades`: Hedge decisions

### 3. Service Status APIs

- Funding Engine: http://localhost:8005/status
- Risk Engine: http://localhost:8002/status
- Collector: http://localhost:8001/status

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker logs hedgelock-funding-engine --tail 100

# Common issues:
# 1. Port already in use
lsof -i :8005  # Check if port is occupied

# 2. Kafka connection issues
docker exec hedgelock-funding-engine ping kafka  # Should resolve

# 3. Rebuild if code changes aren't applied
docker-compose build funding-engine --no-cache
docker-compose up -d funding-engine
```

### Kafka Connection Errors

```bash
# Test Kafka connectivity
docker exec hedgelock-kafka kafka-topics --bootstrap-server localhost:29092 --list

# Reset Kafka if needed
docker-compose down
docker volume rm hedgelock_kafka-data
docker-compose up -d
```

### Funding Engine Not Processing Messages

```bash
# Send test message
docker exec hedgelock-collector python /tmp/test_funding_e2e.py

# Check consumer group lag
docker exec hedgelock-kafka kafka-consumer-groups \
  --bootstrap-server localhost:29092 \
  --group funding-engine-group \
  --describe
```

## Testing

### 1. Send Test Funding Rates

```bash
# Copy test script
docker cp scripts/test_funding_e2e.py hedgelock-collector:/tmp/

# Run test
docker exec hedgelock-collector python /tmp/test_funding_e2e.py
```

### 2. Simulate Extreme Funding

```python
# Test extreme funding (350% APR)
curl -X POST http://localhost:8005/funding/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "current_rate": 350.0,
    "rates_24h": [300.0, 310.0, 320.0],
    "rates_7d": [250.0, 260.0, 270.0, 280.0, 290.0, 300.0, 310.0]
  }'
```

Expected response:
```json
{
  "regime": "extreme",
  "position_multiplier": 0.0,
  "should_exit": true
}
```

## Production Checklist

- [ ] Set `BYBIT_TESTNET=false` in `.env`
- [ ] Add real Bybit API credentials
- [ ] Configure alerting (Telegram/Email)
- [ ] Adjust funding thresholds for your risk tolerance
- [ ] Set up monitoring dashboards
- [ ] Configure automatic restarts: `restart: unless-stopped` in docker-compose
- [ ] Set up log rotation
- [ ] Configure backup strategy for PostgreSQL
- [ ] Test emergency exit functionality
- [ ] Document emergency procedures

## Funding Awareness Feature

### How It Works

1. **Collector** receives funding rates from exchange
2. **Funding Engine** processes rates and detects regimes:
   - Calculates annualized rates
   - Determines funding regime
   - Sets position multipliers
   - Triggers emergency exits if needed
3. **Risk Engine** consumes funding contexts
4. **Hedger** adjusts positions based on multipliers

### Position Multipliers by Regime

| Regime | APR Range | Multiplier | Action |
|--------|-----------|------------|--------|
| NEUTRAL | < 10% | 1.0 | Full position |
| NORMAL | 10-50% | 0.7-1.0 | Slight reduction |
| HEATED | 50-100% | 0.4-0.7 | Moderate reduction |
| MANIA | 100-300% | 0.0-0.4 | Heavy reduction |
| EXTREME | > 300% | 0.0 | EXIT ALL |

### Emergency Exit

When funding exceeds 300% APR:
- Position multiplier set to 0.0
- `should_exit` flag set to true
- Emergency alerts triggered
- All positions should be closed immediately

## Version History

### v1.2.0 (Current)
- Added funding awareness feature
- Automatic position sizing based on funding rates
- Emergency exit for extreme funding
- Real-time monitoring dashboard

### Fixes Applied During Deployment
1. Kafka internal port configuration (29092)
2. Funding rate validation logic
3. Pydantic v2 import updates
4. Health check endpoint corrections
5. Service startup timing improvements

## Support

For issues or questions:
- Check logs: `docker logs <service-name>`
- Review this guide's troubleshooting section
- Check service status endpoints
- Monitor Kafka topics for message flow

---

*Last Updated: January 2025*
*Version: 1.2.0*