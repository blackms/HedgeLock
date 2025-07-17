#!/bin/bash

echo "🧪 Running All Position Manager Tests"
echo "====================================="

# Run all tests with a simpler approach
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy aiohttp aiokafka fastapi httpx prometheus-client && \
    python -m pytest tests/unit/position_manager/ -v --tb=short --override-ini addopts=''
  "