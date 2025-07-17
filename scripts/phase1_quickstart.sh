#!/bin/bash
# Phase 1 Quick Start - Position Manager

echo "🚀 HedgeLock Phase 1 Quick Start - Position Manager"
echo "=================================================="
echo ""

# Check if services are running
echo "1. Checking required services..."
docker ps | grep -E "(kafka|funding-engine)" > /dev/null
if [ $? -ne 0 ]; then
    echo "❌ Required services not running. Please start HedgeLock first:"
    echo "   docker-compose up -d"
    exit 1
fi
echo "✅ Required services are running"
echo ""

# Build position manager
echo "2. Building Position Manager..."
docker-compose build position-manager
if [ $? -ne 0 ]; then
    echo "❌ Build failed"
    exit 1
fi
echo "✅ Position Manager built successfully"
echo ""

# Start position manager
echo "3. Starting Position Manager..."
docker-compose up -d position-manager
if [ $? -ne 0 ]; then
    echo "❌ Failed to start Position Manager"
    exit 1
fi
echo "✅ Position Manager started"
echo ""

# Wait for service to be ready
echo "4. Waiting for Position Manager to be ready..."
sleep 10

# Check health
curl -s http://localhost:8009/health > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ Position Manager is healthy"
else
    echo "⚠️  Position Manager health check failed, checking logs..."
    docker logs hedgelock-position-manager --tail 20
fi
echo ""

# Show service info
echo "📊 Position Manager Service Info:"
echo "   - API: http://localhost:8009"
echo "   - Health: http://localhost:8009/health"
echo "   - Position: http://localhost:8009/position"
echo "   - Hedge Params: http://localhost:8009/hedge-params"
echo "   - Metrics: http://localhost:9096/metrics"
echo ""

echo "🧪 To test the Position Manager:"
echo "   python scripts/test_position_manager.py"
echo ""

echo "📚 Phase 1 Quick Start Complete!"
echo "   Next steps:"
echo "   1. Monitor position state at http://localhost:8009/position"
echo "   2. Send market data updates to 'market_data' Kafka topic"
echo "   3. Watch hedge decisions in 'hedge_trades' topic"
echo ""