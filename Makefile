.PHONY: help install test lint format typecheck build run clean docker-build docker-run

# Default target
help:
	@echo "Available commands:"
	@echo "  install       Install dependencies with Poetry"
	@echo "  test          Run tests with coverage"
	@echo "  lint          Run linting (black, isort, flake8)"
	@echo "  format        Format code with black and isort"
	@echo "  typecheck     Run type checking with mypy"
	@echo "  build         Build all Docker images"
	@echo "  run           Run dummy service locally"
	@echo "  clean         Clean up generated files"
	@echo "  docker-build  Build Docker image for dummy service"
	@echo "  docker-run    Run dummy service in Docker"
	@echo ""
	@echo "Docker Compose commands:"
	@echo "  compose-up    Start all services"
	@echo "  compose-down  Stop all services"
	@echo "  compose-logs  View logs for all services"
	@echo "  compose-ps    Show service status"
	@echo ""
	@echo "Kafka commands:"
	@echo "  kafka-topics  List all Kafka topics"
	@echo "  kafka-describe-topics  Describe all topics"
	@echo "  kafka-consumer-groups  List consumer groups"
	@echo "  kafka-produce-test     Send test message"
	@echo "  kafka-consume-test     Read test messages"

# Install dependencies
install:
	poetry install

# Run tests
test:
	poetry run pytest -v

# Run tests with coverage
test-cov:
	poetry run pytest -v --cov=src --cov-report=html --cov-report=term

# Lint code
lint:
	poetry run black --check src/ tests/
	poetry run isort --check-only src/ tests/
	poetry run flake8 src/ tests/
	poetry run mypy src/

# Format code
format:
	poetry run black src/ tests/
	poetry run isort src/ tests/

# Type checking
typecheck:
	poetry run mypy src/

# Build Docker images
build: docker-build

# Run dummy service locally
run:
	poetry run python -m hedgelock.dummy.main

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# Docker commands
docker-build:
	docker build -f docker/Dockerfile.dummy -t hedgelock-dummy:latest .

docker-run:
	docker run -p 8000:8000 hedgelock-dummy:latest

# Development workflow
dev-setup: install
	pre-commit install

# CI simulation
ci: lint test

# Generate Poetry lock file
lock:
	poetry lock --no-update

# Release commands
release:
	@if [ -z "$(BRANCH)" ]; then \
		echo "Usage: make release BRANCH=feature/branch-name"; \
		exit 1; \
	fi
	./scripts/release.sh $(BRANCH)

# Docker Compose commands
compose-up:
	docker compose up -d

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

compose-build:
	docker compose build

compose-ps:
	docker compose ps

compose-restart:
	docker compose restart

# Service-specific logs
logs-collector:
	docker compose logs -f collector

logs-risk:
	docker compose logs -f risk-engine

logs-hedger:
	docker compose logs -f hedger

logs-trade-executor:
	docker compose logs -f trade-executor

logs-treasury:
	docker compose logs -f treasury

logs-alert:
	docker compose logs -f alert

logs-kafka:
	docker compose logs -f kafka

logs-zookeeper:
	docker compose logs -f zookeeper

# Kafka commands
kafka-topics:
	docker exec hedgelock-kafka kafka-topics --bootstrap-server localhost:29092 --list

kafka-describe-topics:
	docker exec hedgelock-kafka kafka-topics --bootstrap-server localhost:29092 --describe

kafka-consumer-groups:
	docker exec hedgelock-kafka kafka-consumer-groups --bootstrap-server localhost:29092 --list

kafka-produce-test:
	@echo "Enter your message and press Ctrl+D when done:"
	@docker exec -it hedgelock-kafka kafka-console-producer --bootstrap-server localhost:29092 --topic account_raw

kafka-consume-test:
	docker exec -it hedgelock-kafka kafka-console-consumer --bootstrap-server localhost:29092 --topic account_raw --from-beginning --max-messages 10