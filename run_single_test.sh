#!/bin/bash

# Run a single test file using Python base image
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio pytest-cov numpy aiohttp aiokafka fastapi httpx && \
    python -m pytest tests/unit/position_manager/test_models.py -v
  "