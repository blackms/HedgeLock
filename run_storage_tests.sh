#!/bin/bash

echo "🧪 Running Position Manager Storage Tests"
echo "========================================"

# Run storage and volatility tests
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy redis sqlalchemy aiohttp aiokafka fastapi httpx && \
    python -m pytest tests/unit/position_manager/test_storage.py tests/unit/position_manager/test_service_storage.py tests/unit/position_manager/test_volatility_update.py -v --tb=short --override-ini addopts=''
  "