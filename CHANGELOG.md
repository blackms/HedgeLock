# Changelog

All notable changes to HedgeLock will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-07

### Added

#### Core Infrastructure
- Event-driven microservices architecture with Apache Kafka
- Centralized configuration management using pydantic-settings
- Structured logging with Loguru (JSON format, trace IDs)
- Health and readiness probes for all services
- Prometheus metrics integration
- Docker Compose setup for local development

#### Data Collection (Collector Service)
- Bybit exchange integration (WebSocket + REST APIs)
- Real-time position and market data streaming
- Collateral and loan information polling (5s intervals)
- Automatic WebSocket reconnection with exponential backoff
- Message deduplication and reliability guarantees
- Kafka producer integration for account_raw topic

#### Risk Management (Risk Engine v1.0)
- LTV (Loan-to-Value) calculation and monitoring
- Net delta position tracking across portfolios
- Risk state machine: NORMAL → CAUTION → DANGER → CRITICAL
- Configurable risk thresholds
- Hedge recommendation generation
- Processing latency < 150ms requirement
- Kafka consumer/producer for account_raw → risk_state flow

#### Hedge Execution (Hedger v0.9)
- Risk-based automated hedge decisions
- Bybit testnet order execution
- Position sizing based on risk state
- Order tracking and reporting
- Kafka consumer/producer for risk_state → hedge_trades flow
- Support for market orders with IOC time-in-force

#### Testing & Quality
- Integration test suite for complete pipeline
- Collector soak test (WebSocket resilience)
- Unit tests with 90% coverage requirement
- Pre-commit hooks for code quality
- Black, isort, flake8, mypy integration

### Changed
- Migrated from DeFi loan monitoring to trading risk management focus
- Restructured project for event-driven architecture
- Updated all services to use async/await patterns

### Security
- Environment-based configuration for API credentials
- No hardcoded secrets in codebase
- HMAC signature validation for exchange APIs

### Documentation
- Comprehensive project memory system
- Sprint planning documentation
- Integration flow diagrams
- Component status tracking

## [0.1.3.2] - 2024-12-20

### Fixed
- Service naming conventions
- Docker container configurations

## [0.1.0] - 2024-12-15

### Added
- Initial project structure
- Basic service stubs
- Development environment setup