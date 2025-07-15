# GitHub Copilot Instructions for HedgeLock

You are working on HedgeLock, an event-driven trading risk management system built with Python FastAPI microservices and Apache Kafka.

## Code Standards

- Maximum file length: 500 lines (split if exceeds by 20%)
- Follow Single Responsibility Principle - one file, one purpose
- Use Python type hints for all functions
- Use async/await for all I/O operations
- Use Pydantic models for data validation
- Include trace_id in all log messages

## Architecture Patterns

When writing code for HedgeLock:
- Follow the existing service structure in src/hedgelock/
- Implement Kafka integration before business logic
- Include health checks and Prometheus metrics
- Handle errors with automatic reconnection
- Use structured JSON logging

## Git Conventions

Format commits as: `type(sprint-id): description`
Examples:
- `feat(HL-07-1): implement trade executor consumer`
- `fix(HL-07-2): handle WebSocket reconnection`

## Testing Requirements

- Write integration tests for all Kafka flows
- Maintain 60% minimum code coverage
- Ensure <150ms end-to-end latency
- Run `make test` and `make lint` before commits

## Essential Commands

Always use these make commands:
- `make compose-up` - Start services
- `make test` - Run tests
- `make lint` - Check code quality
- `make logs-{service}` - View service logs

## Current Priorities

Focus on implementing:
1. Trade Executor service (consume from hedge_trades topic)
2. API authentication and authorization
3. Production monitoring with Prometheus/Grafana
4. Treasury module for P&L tracking