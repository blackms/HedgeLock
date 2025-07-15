# HedgeLock AI Assistant Rules

This file contains critical rules for AI assistants working on the HedgeLock codebase.

## Project Context
- **Project**: HedgeLock - Event-driven trading risk management system
- **Stack**: Python FastAPI microservices with Apache Kafka
- **Version**: 1.0.0

## CRITICAL RULES (MUST FOLLOW)

### 1. Code Organization
- **File Size Limits**: Soft limit 300 lines, hard limit 500 lines
- **Refactoring Threshold**: If file exceeds 600 lines (20% over hard limit), STOP and refactor immediately
- **Single Responsibility**: Each file manages ONE distinct aspect (API endpoints, Kafka handlers, business logic, models)

### 2. Python Standards
- Use type hints for ALL function parameters and returns
- Follow PEP 8 (enforced by Black formatter)
- Use async/await for ALL I/O operations
- Pydantic models for ALL data validation
- Include trace_id in ALL log messages for distributed tracing

### 3. Git Workflow
- **Branch naming**: `[type]/[sprint-id]-[short-summary]` (e.g., `feat/HL-07-1-trade-executor`)
- **Commit format**: `[type]([sprint-id]): [description]` (e.g., `feat(HL-07-1): implement trade executor`)
- **Commit types**: feat, fix, docs, test, refactor, perf, chore
- **Always test before commit**: Run `make test` and `make lint`

### 4. Development Process
1. Create branch for task
2. Update todo list with task breakdown
3. For Kafka tasks: Test connectivity FIRST (`make kafka-topics`)
4. Write integration tests BEFORE unit tests
5. Include health checks and monitoring
6. Add Prometheus metrics for new features
7. Commit frequently with clear messages
8. Push to remote after each commit

### 5. Testing Requirements
- Integration tests for ALL Kafka data flows
- Soak tests for 5+ minute continuous operation
- Performance validation: <150ms latency
- 60% minimum code coverage
- Commands: `make test`, `make test-integration`, `make test-cov`

### 6. Error Handling
- **File size exceeded**: Stop, create refactoring task, split file, test, then resume
- **Test failures**: Fix before proceeding, never commit broken code
- **Kafka errors**: Check Docker (`make compose-ps`), verify topics (`make kafka-topics`)

## QUICK COMMANDS

### Essential Make Commands
```bash
make compose-ps          # Check Docker services
make test               # Run unit tests
make lint               # Check code style
make test-integration   # Run integration tests
make kafka-topics       # List Kafka topics
make logs-{service}     # View service logs
```

### Verification Checklist
- [ ] All tests pass: `make test && make lint`
- [ ] Services healthy: `curl http://localhost:800{1-5}/health`
- [ ] No errors in logs: `make compose-logs | grep ERROR`
- [ ] Kafka topics active: `make kafka-topics`

## PROJECT STRUCTURE
```
src/hedgelock/
├── collector/     # Market data collection
├── monitor/       # Risk monitoring
├── executor/      # Trade execution
├── api_gateway/   # API gateway
└── shared/        # Shared utilities
```

## REMEMBER
- Always use structured logging with trace_id
- Test Kafka integration BEFORE business logic
- Update PROJECT_MEMORY.yaml after significant changes
- Follow existing patterns in src/hedgelock/
- Never commit without running tests