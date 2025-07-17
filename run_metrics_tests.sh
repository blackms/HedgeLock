#!/bin/bash

echo "🧪 Running Position Manager Metrics Tests"
echo "========================================"

# Run metrics tests
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy redis sqlalchemy aiohttp aiokafka fastapi httpx prometheus-client && \
    python -m pytest tests/unit/position_manager/test_metrics.py -v --tb=short --override-ini addopts=''
  "