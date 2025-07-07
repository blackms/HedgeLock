"""
Health and readiness check utilities for all services.
"""

from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from fastapi import FastAPI, Response
from pydantic import BaseModel
from src.hedgelock.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health check status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    last_check: datetime = None
    metadata: Dict[str, Any] = {}


class ServiceHealth(BaseModel):
    """Overall service health status."""
    service: str
    status: HealthStatus
    timestamp: datetime
    components: List[ComponentHealth]
    version: str = "1.0.0"


class HealthChecker:
    """Manages health checks for a service."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.checks: Dict[str, Callable[[], ComponentHealth]] = {}
        self.last_results: Dict[str, ComponentHealth] = {}
    
    def register_check(self, name: str, check_func: Callable[[], ComponentHealth]):
        """Register a health check function."""
        self.checks[name] = check_func
        logger.info(f"Registered health check: {name}")
    
    def check_health(self) -> ServiceHealth:
        """Run all health checks and return overall status."""
        components = []
        overall_status = HealthStatus.HEALTHY
        
        for name, check_func in self.checks.items():
            try:
                result = check_func()
                result.last_check = datetime.utcnow()
                self.last_results[name] = result
                components.append(result)
                
                # Downgrade overall status if needed
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                    
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                error_result = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                    last_check=datetime.utcnow()
                )
                components.append(error_result)
                overall_status = HealthStatus.UNHEALTHY
        
        return ServiceHealth(
            service=self.service_name,
            status=overall_status,
            timestamp=datetime.utcnow(),
            components=components
        )
    
    def is_ready(self) -> bool:
        """Check if service is ready to handle requests."""
        health = self.check_health()
        return health.status != HealthStatus.UNHEALTHY


def create_health_endpoints(app: FastAPI, health_checker: HealthChecker):
    """Add health and readiness endpoints to FastAPI app."""
    
    @app.get("/healthz")
    async def health_check() -> ServiceHealth:
        """Health check endpoint."""
        return health_checker.check_health()
    
    @app.get("/ready")
    async def readiness_check(response: Response):
        """Readiness check endpoint."""
        if health_checker.is_ready():
            return {"status": "ready"}
        else:
            response.status_code = 503
            return {"status": "not ready"}
    
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint placeholder."""
        # TODO: Integrate with prometheus_client
        return Response(content="# Metrics endpoint\n", media_type="text/plain")


# Common health check functions

def kafka_health_check(bootstrap_servers: str, timeout: float = 5.0) -> ComponentHealth:
    """Check Kafka connectivity."""
    from aiokafka import AIOKafkaProducer
    import asyncio
    
    async def check():
        producer = None
        try:
            producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
            await asyncio.wait_for(producer.start(), timeout=timeout)
            await producer.stop()
            return ComponentHealth(
                name="kafka",
                status=HealthStatus.HEALTHY,
                message="Connected to Kafka",
                metadata={"bootstrap_servers": bootstrap_servers}
            )
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="kafka",
                status=HealthStatus.UNHEALTHY,
                message="Connection timeout",
                metadata={"bootstrap_servers": bootstrap_servers}
            )
        except Exception as e:
            return ComponentHealth(
                name="kafka",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                metadata={"bootstrap_servers": bootstrap_servers}
            )
        finally:
            if producer:
                await producer.stop()
    
    return asyncio.run(check())


def dependency_health_check(url: str, timeout: float = 5.0) -> ComponentHealth:
    """Check external dependency health."""
    import httpx
    
    try:
        response = httpx.get(f"{url}/healthz", timeout=timeout)
        if response.status_code == 200:
            return ComponentHealth(
                name=f"dependency_{url}",
                status=HealthStatus.HEALTHY,
                message="Dependency is healthy",
                metadata={"url": url}
            )
        else:
            return ComponentHealth(
                name=f"dependency_{url}",
                status=HealthStatus.DEGRADED,
                message=f"Unexpected status code: {response.status_code}",
                metadata={"url": url}
            )
    except Exception as e:
        return ComponentHealth(
            name=f"dependency_{url}",
            status=HealthStatus.UNHEALTHY,
            message=str(e),
            metadata={"url": url}
        )