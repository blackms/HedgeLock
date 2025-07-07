"""Unit tests for health check module."""

import pytest
from datetime import datetime
from src.hedgelock.health import HealthStatus, ComponentHealth, ServiceHealth, HealthChecker


def test_component_health():
    """Test ComponentHealth model."""
    health = ComponentHealth(
        name="test_component",
        status=HealthStatus.HEALTHY,
        message="All good",
        metadata={"version": "1.0"}
    )
    
    assert health.name == "test_component"
    assert health.status == HealthStatus.HEALTHY
    assert health.message == "All good"
    assert health.metadata["version"] == "1.0"


def test_health_checker():
    """Test HealthChecker functionality."""
    checker = HealthChecker("test_service")
    
    # Register a healthy check
    def healthy_check():
        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Connected"
        )
    
    checker.register_check("database", healthy_check)
    
    # Check overall health
    result = checker.check_health()
    assert result.service == "test_service"
    assert result.status == HealthStatus.HEALTHY
    assert len(result.components) == 1
    assert result.components[0].name == "database"


def test_health_checker_degraded():
    """Test degraded health state."""
    checker = HealthChecker("test_service")
    
    # Register checks
    def healthy_check():
        return ComponentHealth(name="db", status=HealthStatus.HEALTHY)
    
    def degraded_check():
        return ComponentHealth(name="cache", status=HealthStatus.DEGRADED)
    
    checker.register_check("db", healthy_check)
    checker.register_check("cache", degraded_check)
    
    result = checker.check_health()
    assert result.status == HealthStatus.DEGRADED


def test_health_checker_unhealthy():
    """Test unhealthy state takes precedence."""
    checker = HealthChecker("test_service")
    
    # Register checks
    def healthy_check():
        return ComponentHealth(name="db", status=HealthStatus.HEALTHY)
    
    def unhealthy_check():
        return ComponentHealth(name="kafka", status=HealthStatus.UNHEALTHY)
    
    checker.register_check("db", healthy_check)
    checker.register_check("kafka", unhealthy_check)
    
    result = checker.check_health()
    assert result.status == HealthStatus.UNHEALTHY
    assert not checker.is_ready()


def test_health_checker_exception_handling():
    """Test exception handling in health checks."""
    checker = HealthChecker("test_service")
    
    def failing_check():
        raise Exception("Connection failed")
    
    checker.register_check("failing", failing_check)
    
    result = checker.check_health()
    assert result.status == HealthStatus.UNHEALTHY
    assert len(result.components) == 1
    assert "Check failed" in result.components[0].message