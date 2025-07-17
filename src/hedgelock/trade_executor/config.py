"""
Configuration for Trade Executor service.
"""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class KafkaConfig(BaseSettings):
    """Kafka configuration."""

    bootstrap_servers: str = Field(
        default="kafka:29092", env="KAFKA_BOOTSTRAP_SERVERS"
    )
    consumer_group: str = Field(
        default="trade-executor-group", env="KAFKA_CONSUMER_GROUP"
    )
    topic_hedge_trades: str = Field(
        default="hedge_trades", env="KAFKA_TOPIC_HEDGE_TRADES"
    )
    topic_trade_confirmations: str = Field(
        default="trade_confirmations", env="KAFKA_TOPIC_TRADE_CONFIRMATIONS"
    )
    max_poll_records: int = Field(default=10, env="KAFKA_MAX_POLL_RECORDS")
    session_timeout_ms: int = Field(default=30000, env="KAFKA_SESSION_TIMEOUT_MS")
    heartbeat_interval_ms: int = Field(default=10000, env="KAFKA_HEARTBEAT_INTERVAL_MS")

    class Config:
        env_prefix = "KAFKA_"


class BybitConfig(BaseSettings):
    """Bybit API configuration."""

    api_key: str = Field(env="BYBIT_API_KEY")
    api_secret: str = Field(env="BYBIT_API_SECRET")
    testnet: bool = Field(default=True, env="BYBIT_TESTNET")

    # API endpoints
    rest_url: str = Field(default="https://api-testnet.bybit.com", env="BYBIT_REST_URL")

    # Rate limiting
    max_orders_per_second: int = Field(default=10, env="BYBIT_MAX_ORDERS_PER_SECOND")

    # Order defaults
    time_in_force: str = Field(default="IOC", env="BYBIT_TIME_IN_FORCE")
    position_idx: int = Field(default=0, env="BYBIT_POSITION_IDX")

    class Config:
        env_prefix = "BYBIT_"


class ExecutorConfig(BaseSettings):
    """Trade executor configuration."""

    # Execution settings
    max_retries: int = Field(default=3, env="EXECUTOR_MAX_RETRIES")
    retry_delay_ms: int = Field(default=1000, env="EXECUTOR_RETRY_DELAY_MS")

    # Safety limits
    max_order_size_btc: float = Field(default=1.0, env="EXECUTOR_MAX_ORDER_SIZE_BTC")
    max_daily_volume_btc: float = Field(
        default=10.0, env="EXECUTOR_MAX_DAILY_VOLUME_BTC"
    )

    # Performance
    order_timeout_ms: int = Field(default=5000, env="EXECUTOR_ORDER_TIMEOUT_MS")
    status_poll_interval_ms: int = Field(
        default=500, env="EXECUTOR_STATUS_POLL_INTERVAL_MS"
    )

    # Monitoring
    metrics_port: int = Field(default=9094, env="EXECUTOR_METRICS_PORT")
    health_check_interval_s: int = Field(
        default=30, env="EXECUTOR_HEALTH_CHECK_INTERVAL_S"
    )

    class Config:
        env_prefix = "EXECUTOR_"


class Config(BaseSettings):
    """Main configuration."""

    # Service info
    service_name: str = Field(default="trade-executor", env="SERVICE_NAME")
    environment: str = Field(default="development", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # Sub-configurations
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    bybit: BybitConfig = Field(default_factory=BybitConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_config() -> Config:
    """Get configuration instance."""
    return Config()
