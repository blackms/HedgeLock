#!/bin/bash

# Run all position manager tests with coverage
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio pytest-cov numpy aiohttp aiokafka fastapi httpx loguru uvicorn && \
    python -m pytest tests/unit/position_manager/ -v \
      --cov=src/hedgelock/position_manager \
      --cov-report=term-missing \
      --cov-report=html:htmlcov/position_manager \
      --cov-fail-under=100
  "