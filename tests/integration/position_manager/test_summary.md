# Position Manager Kafka Integration Tests

## Overview
This directory contains comprehensive Kafka integration tests for the Position Manager service, covering end-to-end message flow and service interactions.

## Test Files

### 1. `test_kafka_core.py`
Core Kafka integration tests focusing on essential functionality:
- **Kafka Connection Tests**: Verify producer/consumer connections
- **Service Initialization**: Test Position Manager Kafka setup
- **Message Handling**: Test funding context and market data processing
- **Message Publishing**: Test hedge decisions and emergency actions

### 2. `test_kafka_integration.py`
Comprehensive integration tests with full message flow:
- **Full Message Flow**: End-to-end testing with real Kafka brokers
- **Position State Publishing**: Test position state updates
- **P&L Updates**: Test P&L message publishing
- **Emergency Actions**: Test emergency close scenarios
- **Profit Taking**: Test profit taking flow
- **Message Sequencing**: Test complete message sequences

## Test Infrastructure

### Docker Compose Setup
The tests use `docker-compose.test.yml` to provide:
- **Kafka**: Test broker on port 19092
- **Redis**: Test storage on port 16379
- **Zookeeper**: Required for Kafka

### Test Topics
The integration tests cover all Position Manager topics:
- `funding_context` - Funding rate updates
- `market_data` - Price and volume updates
- `position_states` - Position state changes
- `hedge_trades` - Hedge execution requests
- `pnl_updates` - P&L calculations
- `profit_taking` - Profit taking actions
- `emergency_actions` - Emergency position closures

## Running the Tests

### Core Tests (Quick)
```bash
./run_kafka_core_tests.sh
```

### Full Integration Tests (Requires Docker)
```bash
./run_kafka_integration_tests.sh
```

### Manual Test Execution
```bash
# Start test infrastructure
docker-compose -f docker-compose.test.yml up -d

# Run tests
python -m pytest tests/integration/position_manager/ -v

# Clean up
docker-compose -f docker-compose.test.yml down
```

## Test Coverage

### Message Processing
- ✅ Funding context updates
- ✅ Market data price updates
- ✅ Volatility calculations
- ✅ Position state persistence

### Message Publishing
- ✅ Hedge trade requests
- ✅ Position state updates
- ✅ P&L calculations
- ✅ Emergency actions
- ✅ Profit taking events

### Service Integration
- ✅ Kafka producer/consumer setup
- ✅ Message serialization/deserialization
- ✅ Error handling and recovery
- ✅ Performance metrics collection

### Error Scenarios
- ✅ Emergency position closure
- ✅ Extreme funding conditions
- ✅ Connection failures
- ✅ Message processing errors

## Key Test Scenarios

1. **Normal Operation Flow**
   - Receive funding context → Update position → Publish state
   - Receive market data → Update P&L → Publish updates
   - Periodic rehedge → Generate trade → Publish hedge request

2. **Emergency Scenarios**
   - Extreme funding rates → Emergency close → Publish emergency action
   - Position imbalance → Rehedge → Publish trade request

3. **Profit Taking**
   - Profit target reached → Close positions → Publish profit taking
   - Trailing stop triggered → Partial close → Update state

4. **Message Sequencing**
   - Multiple message types → Proper processing order
   - State consistency across messages
   - Error recovery and retry logic

## Benefits

- **Confidence**: Ensures Position Manager works correctly in production
- **Integration**: Validates service interactions through Kafka
- **Reliability**: Tests error conditions and recovery scenarios
- **Performance**: Validates message throughput and latency
- **Maintainability**: Provides regression testing for changes

## Next Steps

After completing these integration tests, the Position Manager Phase 1 implementation is complete and ready for production deployment.