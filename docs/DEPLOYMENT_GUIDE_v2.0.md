# HedgeLock v2.0 Deployment Guide

## 🚀 Overview

HedgeLock v2.0 introduces autonomous delta-neutral trading with comprehensive risk management. This guide covers deployment from development to production.

## 📋 Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Bybit API credentials
- Minimum 8GB RAM, 20GB disk space

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│   Market    │────▶│   Position   │────▶│     Trade      │
│  Collector  │     │   Manager    │     │   Executor     │
└─────────────┘     └──────────────┘     └────────────────┘
       │                    │                      │
       ▼                    ▼                      ▼
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│   Funding   │     │     Loan     │     │    Reserve     │
│   Engine    │     │   Manager    │     │    Manager     │
└─────────────┘     └──────────────┘     └────────────────┘
       │                    │                      │
       ▼                    ▼                      ▼
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│    Risk     │     │    Safety    │     │   Monitoring   │
│   Engine    │     │   Manager    │     │  (Prometheus)  │
└─────────────┘     └──────────────┘     └────────────────┘
```

## 🛠️ Deployment Steps

### 1. Environment Setup

Create `.env` file:
```bash
# API Credentials
BYBIT_API_KEY=your_api_key
BYBIT_API_SECRET=your_api_secret
BYBIT_TESTNET=true  # Set to false for mainnet

# Database
POSTGRES_DB=hedgelock
POSTGRES_USER=hedgelock
POSTGRES_PASSWORD=secure_password

# Initial Configuration
INITIAL_LOAN_PRINCIPAL=16200
INITIAL_RESERVES=10000
```

### 2. Create Kafka Topics

```bash
# Make script executable
chmod +x scripts/kafka-topics-v2.sh

# Start infrastructure
docker-compose -f docker-compose.v2.yml up -d zookeeper kafka

# Wait for Kafka to be ready
sleep 30

# Create topics
./scripts/kafka-topics-v2.sh
```

### 3. Initialize Database

```bash
# Start PostgreSQL
docker-compose -f docker-compose.v2.yml up -d postgres

# Apply schemas
docker exec -i hedgelock-postgres psql -U hedgelock -d hedgelock < src/hedgelock/loan_manager/schema.sql
```

### 4. Start Core Services

```bash
# Start all services
docker-compose -f docker-compose.v2.yml up -d

# Verify all services are running
docker-compose -f docker-compose.v2.yml ps
```

### 5. Health Verification

```bash
# Check service health
for port in 8001 8002 8003 8004 8005 8006 8009 8010 8011 8012; do
  echo "Service on port $port:"
  curl -s http://localhost:$port/health | jq .
done
```

## 🔧 Configuration

### Position Manager Settings
- Delta threshold: 0.01 BTC
- Rehedge interval: 300 seconds
- Profit target: 1.5 * volatility

### Loan Manager Settings
- APR: 6%
- Auto-repay: 50% of profits
- Min payment: $10

### Safety Manager Limits
- Daily loss: $1000
- Min liquidation distance: 10%
- Dead man's switch: 60 minutes

## 📊 Monitoring

### Access Dashboards
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

### Key Metrics to Monitor
1. **Position Delta**: Should stay near 0
2. **LTV Ratio**: Keep below 65%
3. **Daily P&L**: Monitor for circuit breakers
4. **Service Health**: All should be "healthy"

## 🚨 Production Checklist

### Before Going Live
- [ ] Set BYBIT_TESTNET=false
- [ ] Update API credentials for mainnet
- [ ] Increase resource limits in docker-compose
- [ ] Configure external monitoring/alerting
- [ ] Test emergency procedures
- [ ] Backup database configuration
- [ ] Set up log aggregation

### Resource Requirements
- **CPU**: 4+ cores recommended
- **RAM**: 16GB minimum for production
- **Disk**: 100GB+ for logs and data
- **Network**: Stable, low-latency connection

### Security Hardening
1. Use secrets management for API keys
2. Enable PostgreSQL SSL
3. Restrict network access
4. Set up firewall rules
5. Enable audit logging

## 🔄 Upgrade Procedure

From v1.x to v2.0:
```bash
# 1. Backup existing data
docker exec hedgelock-postgres pg_dump -U hedgelock hedgelock > backup.sql

# 2. Stop v1.x services
docker-compose down

# 3. Deploy v2.0
docker-compose -f docker-compose.v2.yml up -d

# 4. Verify services
./scripts/health-check.sh
```

## 🛑 Rollback Procedure

If issues occur:
```bash
# 1. Stop v2.0
docker-compose -f docker-compose.v2.yml down

# 2. Restore v1.x
docker-compose up -d

# 3. Restore database if needed
docker exec -i hedgelock-postgres psql -U hedgelock -d hedgelock < backup.sql
```

## 📞 Support

- Documentation: `/docs` directory
- Emergency procedures: `docs/EMERGENCY_PROCEDURES.md`
- Logs: `docker-compose -f docker-compose.v2.yml logs -f [service]`

## ✅ Post-Deployment

1. Monitor closely for first 24 hours
2. Check all circuit breakers are functioning
3. Verify loan repayments are processing
4. Confirm position rebalancing is active
5. Test emergency shutdown procedure