"""Unit tests for configuration module."""

import pytest
from src.hedgelock.config import Settings, Environment, KafkaSettings, BybitSettings


def test_settings_defaults():
    """Test default settings initialization."""
    settings = Settings()
    
    assert settings.environment == Environment.DEVELOPMENT
    assert settings.service_name == "hedgelock"
    assert isinstance(settings.kafka, KafkaSettings)
    assert isinstance(settings.bybit, BybitSettings)


def test_kafka_settings():
    """Test Kafka settings."""
    kafka_settings = KafkaSettings()
    
    assert kafka_settings.bootstrap_servers == "localhost:9092"
    assert kafka_settings.consumer_group_prefix == "hedgelock"
    assert kafka_settings.topic_account_raw == "account_raw"
    assert kafka_settings.topic_risk_state == "risk_state"
    assert kafka_settings.topic_hedge_trades == "hedge_trades"


def test_bybit_settings_testnet():
    """Test Bybit settings for testnet."""
    bybit_settings = BybitSettings(testnet=True)
    
    assert bybit_settings.testnet is True
    assert "testnet" in bybit_settings.rest_url
    assert "testnet" in bybit_settings.ws_public_url
    assert bybit_settings.collateral_poll_interval == 5


def test_bybit_settings_mainnet():
    """Test Bybit settings for mainnet."""
    bybit_settings = BybitSettings(testnet=False)
    
    assert bybit_settings.testnet is False
    assert "testnet" not in bybit_settings.rest_url
    assert bybit_settings.rest_url == "https://api.bybit.com"