#!/bin/bash

echo "🧪 Running Position Manager Kafka Core Tests"
echo "============================================"

# Simple test runner that just runs the core Kafka tests
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy redis sqlalchemy aiohttp aiokafka fastapi httpx prometheus-client && \
    python -m pytest tests/integration/position_manager/test_kafka_core.py::test_position_manager_kafka_initialization -v --tb=short --override-ini addopts=''
  "

echo "🏁 Core Kafka tests completed!"