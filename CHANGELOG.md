# Changelog

All notable changes to HedgeLock will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with four-digit versioning (vW.X.Y.Z).

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [0.1.1.0] - 2024-12-30

### Added
- Docker Compose skeleton for local development (HL-00-4)
- Stub implementations for all 5 microservices (Collector, RiskEngine, Hedger, Treasury, Alert)
- PostgreSQL and Redis services in docker-compose.yml
- Comprehensive .env.example with all configuration options
- LOCAL_DEVELOPMENT.md documentation
- Docker Compose commands in Makefile
- CI/CD and Codecov badges in README

### Fixed
- Trivy security scanner configuration to use correct image tags
- Black formatting for all Python files

### Changed
- Updated CI workflow to handle missing Codecov token gracefully
- Set Codecov fail_ci_if_error to false

### Documentation
- Added Codecov setup guide
- Added instructions for using GitHub secrets

## [0.1.0.0] - 2024-12-30

### Added
- Initial project structure with Poetry and dev container
- Comprehensive architect prompts for all microservices (Collector, RiskEngine, Hedger, Treasury, Alert)
- GitHub Actions CI/CD pipeline with Docker support
- Automated release process with four-digit versioning (vW.X.Y.Z)
- Dummy service for testing CI/CD pipeline
- Development tooling (Makefile, black, isort, flake8, mypy)
- Project documentation (README, BRANCHING, COMMITS, RELEASE, SYSTEM_OVERVIEW)
- VS Code dev container configuration with PostgreSQL and Redis
- Python 3.11 and Node.js 20 development environment

### Fixed
- Removed non-existent types-aiokafka dependency
- Corrected git command syntax in release script
- Applied black formatting to all Python files