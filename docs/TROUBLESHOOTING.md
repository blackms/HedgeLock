# HedgeLock Troubleshooting Guide

## Common Issues and Solutions

### 1. Funding Engine Issues

#### Problem: Funding rates detected as EXTREME when they shouldn't be

**Symptom**: 
```
Funding rate exceeds limits: Funding rate exceeds absolute limit (Symbol: BTCUSDT, Rate: 2737500.0% APR, Max: 1000.0% APR)
```

**Cause**: Double conversion of APR rates in validation

**Solution**: 
1. Ensure you have the latest code with validation fix
2. Rebuild base image: `docker build -t hedgelock-base:latest -f docker/Dockerfile.base .`
3. Rebuild and restart funding engine

#### Problem: "NoneType object has no attribute 'check_errors'"

**Symptom**: Repeated errors in funding engine logs

**Cause**: Kafka consumer not properly initialized

**Solution**:
1. Check Kafka bootstrap servers configuration
2. Ensure using `kafka:29092` not `kafka:9092`
3. Restart funding engine

#### Problem: No funding contexts being published

**Symptom**: Empty `funding_context` topic

**Solution**:
```bash
# Check if funding rates are being received
docker exec hedgelock-kafka kafka-console-consumer \
  --bootstrap-server localhost:29092 \
  --topic funding_rates \
  --from-beginning \
  --max-messages 5

# Send test funding rate
docker exec hedgelock-collector python /tmp/test_funding_e2e.py
```

### 2. Kafka Connection Issues

#### Problem: "No connection to node with id 1"

**Cause**: Services trying to connect to wrong Kafka port

**Solution**:
1. Update all services to use `kafka:29092`
2. Check docker-compose.yml environment variables
3. Rebuild affected services

#### Problem: "Multiple exceptions: [Errno 111] Connect call failed"

**Cause**: Service trying to connect to localhost instead of kafka hostname

**Solution**:
```yaml
# Correct configuration
KAFKA__BOOTSTRAP_SERVERS=kafka:29092

# Wrong configuration
KAFKA__BOOTSTRAP_SERVERS=localhost:9092
```

### 3. Service Health Check Failures

#### Problem: Services showing as unhealthy

**Check health status**:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

**Common causes**:
1. Wrong health check endpoint (e.g., `/healthz` vs `/health`)
2. Service not fully started
3. Missing dependencies (Redis, Kafka, PostgreSQL)

**Solutions**:
```yaml
# Correct health check
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
  interval: 30s
  timeout: 3s
  retries: 3
```

### 4. Docker Issues

#### Problem: Services won't start after code changes

**Solution**:
```bash
# Rebuild without cache
docker-compose build --no-cache funding-engine

# Force recreate
docker-compose up -d --force-recreate funding-engine
```

#### Problem: Port already in use

**Solution**:
```bash
# Find process using port
lsof -i :8005

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

### 5. Monitoring Issues

#### Problem: Web dashboard shows "Unable to connect to Funding Engine"

**Causes**:
1. CORS issues with browser
2. Funding engine not running
3. Wrong port configuration

**Solutions**:
```bash
# Check if funding engine is running
curl http://localhost:8005/status

# Check CORS headers (if needed, use proxy)
# Or access directly: http://localhost:8005/status
```

### 6. Testing Issues

#### Problem: Test scripts fail with import errors

**Solution**: Run tests inside Docker containers
```bash
docker cp scripts/test_funding_e2e.py hedgelock-collector:/tmp/
docker exec hedgelock-collector python /tmp/test_funding_e2e.py
```

### 7. Data Flow Issues

#### Problem: Messages not flowing between services

**Debug steps**:
```bash
# List all topics
docker exec hedgelock-kafka kafka-topics \
  --bootstrap-server localhost:29092 --list

# Check consumer groups
docker exec hedgelock-kafka kafka-consumer-groups \
  --bootstrap-server localhost:29092 --list

# Check consumer lag
docker exec hedgelock-kafka kafka-consumer-groups \
  --bootstrap-server localhost:29092 \
  --group funding-engine-group --describe
```

## Debug Commands

### View Service Logs
```bash
# All logs
docker logs hedgelock-funding-engine

# Last 50 lines
docker logs hedgelock-funding-engine --tail 50

# Follow logs
docker logs hedgelock-funding-engine -f
```

### Check Service Configuration
```bash
# View environment variables
docker exec hedgelock-funding-engine env | grep -E "(KAFKA|FUNDING)"

# Check service status
curl http://localhost:8005/status | jq .
```

### Reset Services
```bash
# Restart single service
docker-compose restart funding-engine

# Recreate service
docker-compose up -d --force-recreate funding-engine

# Full reset
docker-compose down
docker-compose up -d
```

### Kafka Debugging
```bash
# View messages in topic
docker exec hedgelock-kafka kafka-console-consumer \
  --bootstrap-server localhost:29092 \
  --topic funding_context \
  --from-beginning \
  --max-messages 10

# Delete topic (careful!)
docker exec hedgelock-kafka kafka-topics \
  --bootstrap-server localhost:29092 \
  --delete --topic funding_rates
```

## Emergency Procedures

### System Unresponsive
```bash
# Stop all services
docker-compose down

# Clean up volumes (WARNING: Deletes all data)
docker-compose down -v

# Restart fresh
docker-compose up -d
```

### Extreme Funding Detected
1. Check monitoring dashboard for affected symbols
2. Verify positions are being reduced/closed
3. Check alerts are being sent
4. Manual intervention if automatic exit fails

## Getting Help

1. Check service logs first
2. Verify configuration matches deployment guide
3. Test with minimal example
4. Isolate the problem to specific service
5. Check Kafka message flow

---

*Last Updated: January 2025*