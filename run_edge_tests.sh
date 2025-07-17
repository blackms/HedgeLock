#!/bin/bash

echo "🧪 Running Edge Case Tests"
echo "========================="

# Run just edge case tests
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy aiohttp aiokafka fastapi httpx && \
    python -m pytest tests/unit/position_manager/test_edge_cases.py -v --tb=short --override-ini addopts=''
  "