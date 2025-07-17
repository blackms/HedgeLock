"""
Configuration for Funding Engine service.
"""

from typing import Optional

from pydantic_settings import BaseSettings


class FundingEngineConfig(BaseSettings):
    """Configuration for Funding Engine service."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import os
        print(f"DEBUG: Environment FUNDING_ENGINE_KAFKA_BOOTSTRAP_SERVERS = {os.getenv('FUNDING_ENGINE_KAFKA_BOOTSTRAP_SERVERS')}")
        print(f"DEBUG: Config kafka_bootstrap_servers = {self.kafka_bootstrap_servers}")

    # Service identification
    service_name: str = "funding-engine"
    service_port: int = 8005

    # Kafka configuration
    kafka_bootstrap_servers: str = "kafka:29092"
    consumer_group_id: str = "funding-engine-group"
    funding_rates_topic: str = "funding_rates"
    funding_context_topic: str = "funding_context"

    # Processing configuration
    history_window_hours: int = 168  # 7 days
    regime_update_interval_seconds: int = 60  # Update regime every minute

    # Regime thresholds (annualized rates)
    regime_neutral_threshold: float = 10.0  # < 10% APR
    regime_normal_threshold: float = 50.0  # 10-50% APR
    regime_heated_threshold: float = 100.0  # 50-100% APR
    regime_mania_threshold: float = 300.0  # 100-300% APR
    # > 300% APR = EXTREME

    # Position multiplier bounds
    min_position_multiplier: float = 0.0
    max_position_multiplier: float = 1.0

    # Emergency thresholds
    emergency_exit_threshold: float = 300.0  # Exit all at > 300% APR

    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9095

    model_config = {
        "env_prefix": "FUNDING_ENGINE_",
        "env_file": ".env",
        "extra": "ignore"
    }
