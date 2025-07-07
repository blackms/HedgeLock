#!/bin/bash

# Collector Soak Test Runner
# Tests WebSocket reconnection and ensures no data gaps > 15 seconds

set -e

echo "Starting Collector Soak Test..."
echo "================================"

# Check if docker-compose is running
if ! docker-compose ps | grep -q "kafka.*Up"; then
    echo "ERROR: Kafka is not running. Please start docker-compose first:"
    echo "  docker-compose up -d"
    exit 1
fi

# Ensure all services are healthy
echo "Checking service health..."
for service in collector risk_engine hedger; do
    port=$((8000 + $(echo $service | wc -c)))
    if ! curl -s "http://localhost:${port}/healthz" > /dev/null 2>&1; then
        echo "WARNING: ${service} service is not responding on port ${port}"
    fi
done

# Run the soak test
echo "Running soak test (5 minutes)..."
python -m pytest tests/integration/test_collector_soak.py::main -v

# Check exit code
if [ $? -eq 0 ]; then
    echo "✅ Soak test PASSED - No data gaps exceeding 15 seconds"
    exit 0
else
    echo "❌ Soak test FAILED - Data gaps detected"
    exit 1
fi