#!/bin/bash

echo "🧪 Checking Position Manager Metrics Tests"
echo "=========================================="

# Check if tests exist and are runnable
if [ ! -f "tests/unit/position_manager/test_metrics.py" ]; then
    echo "❌ test_metrics.py not found"
    exit 1
fi

echo "✅ test_metrics.py exists"

# Check if prometheus-client is available
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  -e PYTHONPATH=/app/src \
  python:3.11-slim \
  bash -c "
    pip install --quiet pydantic pytest pytest-asyncio numpy redis sqlalchemy aiohttp aiokafka fastapi httpx prometheus-client && \
    python -c 'import prometheus_client; print(\"✅ prometheus-client imported successfully\")' && \
    python -c 'from src.hedgelock.position_manager.metrics import MetricsCollector; print(\"✅ MetricsCollector imported successfully\")' && \
    python -m pytest tests/unit/position_manager/test_metrics.py::TestMetricsCollector::test_update_position_metrics -v --tb=short --override-ini addopts=''
  "