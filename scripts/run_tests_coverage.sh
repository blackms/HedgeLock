#!/bin/bash
# Run tests with coverage for Position Manager

echo "🧪 Running Position Manager Tests with Coverage"
echo "=============================================="

# Use base image to run tests
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  hedgelock-base:latest \
  python -m pytest tests/unit/position_manager/ -v \
    --cov=src/hedgelock/position_manager \
    --cov-report=term-missing \
    --cov-report=html:htmlcov/position_manager \
    --cov-fail-under=100

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed with 100% coverage!"
    echo ""
    echo "📊 Coverage report available at: htmlcov/position_manager/index.html"
else
    echo ""
    echo "❌ Tests failed or coverage below 100%"
    exit 1
fi