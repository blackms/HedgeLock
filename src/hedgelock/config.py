"""
Centralized configuration management using pydantic-settings.
All services should import Settings from this module.
"""

from typing import Optional
from enum import Enum
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTNET = "testnet"


class KafkaSettings(BaseSettings):
    """Kafka-specific settings."""
    bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers")
    consumer_group_prefix: str = Field(default="hedgelock", description="Prefix for consumer groups")
    producer_timeout_ms: int = Field(default=10000, description="Producer timeout in milliseconds")
    consumer_timeout_ms: int = Field(default=10000, description="Consumer timeout in milliseconds")
    max_poll_records: int = Field(default=500, description="Max records per poll")
    enable_auto_commit: bool = Field(default=False, description="Enable auto commit for consumers")
    
    # Topic names
    topic_account_raw: str = Field(default="account_raw", description="Raw account data topic")
    topic_risk_state: str = Field(default="risk_state", description="Risk state topic")
    topic_hedge_trades: str = Field(default="hedge_trades", description="Hedge trades topic")
    topic_treasury_actions: str = Field(default="treasury_actions", description="Treasury actions topic")
    
    model_config = SettingsConfigDict(env_prefix="KAFKA_")


class BybitSettings(BaseSettings):
    """Bybit exchange settings."""
    api_key: Optional[str] = Field(default=None, description="Bybit API key")
    api_secret: Optional[str] = Field(default=None, description="Bybit API secret")
    testnet: bool = Field(default=True, description="Use testnet")
    
    # API endpoints
    rest_url: str = Field(default="https://api-testnet.bybit.com", description="REST API URL")
    ws_public_url: str = Field(default="wss://stream-testnet.bybit.com/v5/public/linear", description="Public WebSocket URL")
    ws_private_url: str = Field(default="wss://stream-testnet.bybit.com/v5/private", description="Private WebSocket URL")
    
    # Rate limits
    rest_rate_limit: int = Field(default=10, description="REST API rate limit per second")
    ws_ping_interval: int = Field(default=20, description="WebSocket ping interval in seconds")
    
    # Polling intervals
    collateral_poll_interval: int = Field(default=5, description="Collateral info polling interval in seconds")
    loan_poll_interval: int = Field(default=5, description="Loan info polling interval in seconds")
    
    model_config = SettingsConfigDict(env_prefix="BYBIT_")
    
    def __init__(self, **data):
        super().__init__(**data)
        # Update URLs based on testnet setting
        if not self.testnet:
            self.rest_url = "https://api.bybit.com"
            self.ws_public_url = "wss://stream.bybit.com/v5/public/linear"
            self.ws_private_url = "wss://stream.bybit.com/v5/private"


class RiskSettings(BaseSettings):
    """Risk engine settings."""
    # Risk thresholds
    ltv_normal_threshold: float = Field(default=0.5, description="LTV threshold for NORMAL state")
    ltv_caution_threshold: float = Field(default=0.65, description="LTV threshold for CAUTION state")
    ltv_danger_threshold: float = Field(default=0.8, description="LTV threshold for DANGER state")
    ltv_critical_threshold: float = Field(default=0.9, description="LTV threshold for CRITICAL state")
    
    # Delta targets
    net_delta_normal: float = Field(default=0.0, description="Target net delta for NORMAL state")
    net_delta_caution: float = Field(default=0.02, description="Target net delta for CAUTION state")
    net_delta_danger: float = Field(default=0.0, description="Target net delta for DANGER state")
    net_delta_critical: float = Field(default=-0.1, description="Target net delta for CRITICAL state")
    
    # Performance
    max_processing_latency_ms: int = Field(default=150, description="Max processing latency in milliseconds")
    
    model_config = SettingsConfigDict(env_prefix="RISK_")


class HedgerSettings(BaseSettings):
    """Hedger service settings."""
    # Order settings
    order_type: str = Field(default="Market", description="Order type for hedge trades")
    time_in_force: str = Field(default="IOC", description="Time in force for orders")
    
    # Position limits
    max_position_size_btc: float = Field(default=10.0, description="Maximum position size in BTC")
    min_order_size_btc: float = Field(default=0.001, description="Minimum order size in BTC")
    
    # Risk response
    caution_hedge_size_btc: float = Field(default=0.02, description="Hedge size for CAUTION state")
    danger_hedge_size_btc: float = Field(default=0.05, description="Hedge size for DANGER state")
    critical_hedge_size_btc: float = Field(default=0.1, description="Hedge size for CRITICAL state")
    
    model_config = SettingsConfigDict(env_prefix="HEDGER_")


class MonitoringSettings(BaseSettings):
    """Monitoring and observability settings."""
    # Prometheus
    metrics_port: int = Field(default=9090, description="Prometheus metrics port")
    metrics_path: str = Field(default="/metrics", description="Prometheus metrics path")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json or text)")
    log_file: Optional[str] = Field(default=None, description="Log file path")
    
    # Health checks
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    readiness_timeout: int = Field(default=5, description="Readiness check timeout in seconds")
    
    model_config = SettingsConfigDict(env_prefix="MONITORING_")


class Settings(BaseSettings):
    """Main settings class combining all service settings."""
    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT, description="Environment")
    service_name: str = Field(default="hedgelock", description="Service name")
    
    # Sub-settings
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    bybit: BybitSettings = Field(default_factory=BybitSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    hedger: HedgerSettings = Field(default_factory=HedgerSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False
    )


# Global settings instance
settings = Settings()