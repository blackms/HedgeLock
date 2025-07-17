#!/bin/bash

echo "🧪 Running Position Manager Kafka Integration Tests"
echo "=================================================="

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install docker-compose."
    exit 1
fi

# Start test infrastructure
echo "🚀 Starting test infrastructure..."
docker-compose -f docker-compose.test.yml up -d test-kafka test-redis

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 15

# Check if Kafka is ready
echo "🔍 Checking Kafka health..."
timeout 30 bash -c '
  while ! nc -z localhost 19092; do
    sleep 1
  done
'

if [ $? -ne 0 ]; then
    echo "❌ Kafka failed to start"
    docker-compose -f docker-compose.test.yml down
    exit 1
fi

echo "✅ Kafka is ready"

# Check if Redis is ready
echo "🔍 Checking Redis health..."
timeout 30 bash -c '
  while ! nc -z localhost 16379; do
    sleep 1
  done
'

if [ $? -ne 0 ]; then
    echo "❌ Redis failed to start"
    docker-compose -f docker-compose.test.yml down
    exit 1
fi

echo "✅ Redis is ready"

# Run the integration tests
echo "🧪 Running Kafka integration tests..."
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  -e KAFKA_BOOTSTRAP_SERVERS=localhost:19092 \
  -e REDIS_HOST=localhost \
  -e REDIS_PORT=16379 \
  --network host \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy redis sqlalchemy aiohttp aiokafka fastapi httpx prometheus-client && \
    python -m pytest tests/integration/position_manager/test_kafka_integration.py -v --tb=short -m 'integration' --override-ini addopts=''
  "

# Store test exit code
TEST_EXIT_CODE=$?

# Clean up test infrastructure
echo "🧹 Cleaning up test infrastructure..."
docker-compose -f docker-compose.test.yml down

# Report results
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All Kafka integration tests passed!"
else
    echo "❌ Some Kafka integration tests failed"
fi

exit $TEST_EXIT_CODE