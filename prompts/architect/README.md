# HedgeLock Architect Prompts

This directory contains detailed prompts for implementing each component of the HedgeLock system.

## Purpose
These prompts serve as comprehensive specifications for developers implementing the HedgeLock MVP. Each prompt provides:
- Clear context and objectives
- Technical requirements and constraints
- Code examples and patterns
- Quality criteria and testing requirements

## Prompts Overview

### System Architecture
- **[overview.md](overview.md)**: Complete system architecture and implementation guide

### Microservices
1. **[collector.md](collector.md)**: Data ingestion service for Bybit WebSocket feeds
2. **[risk_engine.md](risk_engine.md)**: Risk calculation and state management service
3. **[hedger.md](hedger.md)**: Automated trading execution service
4. **[treasury.md](treasury.md)**: Profit allocation and loan management service
5. **[alert.md](alert.md)**: Multi-channel notification service

## How to Use These Prompts

1. **For Developers**: Start with `overview.md` to understand the system, then read the specific prompt for the service you're implementing.

2. **For Architects**: Review all prompts to ensure consistency and completeness of the system design.

3. **For QA**: Use these prompts as the source of truth for expected behavior and testing requirements.

## Implementation Order
1. Start with `collector.md` - establishes data pipeline
2. Then `risk_engine.md` - core business logic
3. Follow with `hedger.md` - trading capabilities
4. Add `treasury.md` - fund management
5. Complete with `alert.md` - user notifications

## Key Principles
- **Reliability First**: Every service must handle failures gracefully
- **Real-time Performance**: Low latency is critical for loan safety
- **Audit Everything**: Complete traceability for all operations
- **User Safety**: Protect funds at all costs

## Updates
These prompts are living documents. Update them as the system evolves to maintain accuracy.