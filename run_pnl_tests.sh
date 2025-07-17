#!/bin/bash

echo "🧪 Running Position Manager P&L Tests"
echo "===================================="

# Run P&L tests
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy redis sqlalchemy aiohttp aiokafka fastapi httpx && \
    python -m pytest tests/unit/position_manager/test_pnl_calculator.py tests/unit/position_manager/test_service_pnl.py tests/unit/position_manager/test_api_pnl.py -v --tb=short --override-ini addopts=''
  "