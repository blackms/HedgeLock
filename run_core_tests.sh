#!/bin/bash

echo "🧪 Running Core Position Manager Tests"
echo "======================================"

# Run core tests (models, manager, service)
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio pytest-cov numpy aiohttp aiokafka fastapi httpx && \
    python -m pytest tests/unit/position_manager/test_models.py tests/unit/position_manager/test_manager.py tests/unit/position_manager/test_service.py tests/unit/position_manager/test_edge_cases.py -v \
      --cov=src/hedgelock/position_manager/models.py \
      --cov=src/hedgelock/position_manager/manager.py \
      --cov=src/hedgelock/position_manager/service.py \
      --cov-report=term-missing \
      --cov-report=html:htmlcov/position_manager \
      --cov-fail-under=95
  "