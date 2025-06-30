# HedgeLock MVP - Loan Control Loop

A decentralized loan monitoring and management system with automated liquidation protection.

## Project Overview

HedgeLock implements a control loop for cryptocurrency-backed loans, providing:
- Real-time loan health monitoring
- Automated margin calls
- Liquidation prevention through hedging strategies
- Multi-chain collateral support

## Development Setup

### Prerequisites

- Docker Desktop or Docker Engine
- VS Code with Dev Containers extension (recommended)
- Git

### Using Dev Container

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd HedgeLock
   ```

2. Open in VS Code:
   ```bash
   code .
   ```

3. When prompted, click "Reopen in Container" or use Command Palette:
   - Press `F1` or `Ctrl+Shift+P`
   - Type "Dev Containers: Reopen in Container"
   - Press Enter

The dev container includes:
- Node.js 20 LTS
- Python 3.11
- PostgreSQL 15
- Redis
- All required development tools

### Manual Setup

If not using dev containers:

```bash
# Install dependencies
npm install

# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install Python dependencies with Poetry
poetry install

# Configure environment
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
npm run db:migrate

# Start development server
npm run dev
```

### Poetry Commands

```bash
# Add a new dependency
poetry add <package>

# Add a dev dependency
poetry add --group dev <package>

# Update dependencies
poetry update

# Show installed packages
poetry show

# Run commands in the virtual environment
poetry run python script.py

# Activate the virtual environment
poetry shell
```

## Project Structure

```
HedgeLock/
├── docs/              # Documentation
│   ├── BRANCHING.md   # Git branching model
│   └── COMMITS.md     # Commit conventions
├── src/               # Source code
│   ├── api/           # REST API endpoints
│   ├── core/          # Core business logic
│   ├── monitoring/    # Loan monitoring services
│   └── strategies/    # Hedging strategies
├── tests/             # Test suites
├── scripts/           # Utility scripts
└── .devcontainer/     # Dev container configuration
```

## Development Workflow

1. Create feature branch following naming convention in `docs/BRANCHING.md`
2. Make changes with atomic commits following `docs/COMMITS.md`
3. Write tests for new functionality
4. Create pull request to `develop` branch
5. Ensure all CI checks pass

## Sprint Planning

Currently in **Sprint 0** - Project Bootstrap

See `docs/SPRINT_PLAN.md` for complete sprint roadmap.

## Contributing

Please read our contributing guidelines and code of conduct before submitting PRs.

## License

[License Type] - See LICENSE file for details