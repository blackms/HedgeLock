"""
Unit tests for collector REST client funding methods.
"""

import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.hedgelock.collector.rest_client import BybitRestClient


class TestFundingRateMethods:
    """Test funding rate collection methods."""
    
    @pytest.fixture
    async def client(self):
        """Create a REST client instance."""
        with patch('src.hedgelock.config.settings.bybit.api_key', 'test-key'), \
             patch('src.hedgelock.config.settings.bybit.api_secret', 'test-secret'), \
             patch('src.hedgelock.config.settings.bybit.rest_url', 'https://api-testnet.bybit.com'):
            client = BybitRestClient()
            yield client
            await client.close()
    
    @pytest.mark.asyncio
    async def test_get_funding_rate_history_success(self, client):
        """Test successful funding rate history retrieval."""
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.0001",
                        "fundingRateTimestamp": "1704067200000"
                    },
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.00015",
                        "fundingRateTimestamp": "1704038400000"
                    }
                ]
            }
        }
        
        # Mock the HTTP response
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            result = await client.get_funding_rate_history("BTCUSDT", limit=2)
            
            assert result is not None
            assert len(result) == 2
            assert result[0]["fundingRate"] == "0.0001"
            
            # Verify API call
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            assert args[0] == "https://api-testnet.bybit.com/v5/market/funding/history"
            assert kwargs['params']['symbol'] == "BTCUSDT"
            assert kwargs['params']['limit'] == "2"
    
    @pytest.mark.asyncio
    async def test_get_funding_rate_history_api_error(self, client):
        """Test funding rate history with API error."""
        mock_response = {
            "retCode": 10001,
            "retMsg": "Invalid parameter"
        }
        
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            result = await client.get_funding_rate_history("INVALID", limit=200)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_funding_rate_history_http_error(self, client):
        """Test funding rate history with HTTP error."""
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPError("Connection error")
            
            result = await client.get_funding_rate_history("BTCUSDT")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_funding_rate_history_exception(self, client):
        """Test funding rate history with unexpected exception."""
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Unexpected error")
            
            result = await client.get_funding_rate_history("BTCUSDT")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rate_success(self, client):
        """Test successful current funding rate retrieval."""
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0001",
                    "nextFundingTime": "1704096000000",
                    "markPrice": "50000.50",
                    "indexPrice": "50000.00"
                }]
            }
        }
        
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            result = await client.get_current_funding_rate("BTCUSDT")
            
            assert result is not None
            assert result["symbol"] == "BTCUSDT"
            assert result["fundingRate"] == 0.0001
            assert result["markPrice"] == 50000.50
            assert result["indexPrice"] == 50000.00
            assert result["nextFundingTime"] == "1704096000000"
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rate_empty_list(self, client):
        """Test current funding rate with empty result."""
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": []
            }
        }
        
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            result = await client.get_current_funding_rate("BTCUSDT")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rate_api_error(self, client):
        """Test current funding rate with API error."""
        mock_response = {
            "retCode": 10001,
            "retMsg": "Symbol not found"
        }
        
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            result = await client.get_current_funding_rate("INVALID")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rate_http_error(self, client):
        """Test current funding rate with HTTP error."""
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPError("Network error")
            
            result = await client.get_current_funding_rate("BTCUSDT")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_current_funding_rate_exception(self, client):
        """Test current funding rate with unexpected exception."""
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ValueError("Invalid response format")
            
            result = await client.get_current_funding_rate("BTCUSDT")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_funding_endpoints_called_correctly(self, client):
        """Test that funding endpoints are called with correct parameters."""
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = {"retCode": 0, "result": {"list": []}}
        mock_http_response.raise_for_status = Mock()
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            # Test funding history
            await client.get_funding_rate_history("ETHUSDT", limit=100)
            
            call_args = mock_get.call_args_list[0]
            assert "/v5/market/funding/history" in call_args[0][0]
            assert call_args[1]['params']['category'] == "linear"
            assert call_args[1]['params']['symbol'] == "ETHUSDT"
            assert call_args[1]['params']['limit'] == "100"
            
            # Reset mock
            mock_get.reset_mock()
            
            # Test current funding
            await client.get_current_funding_rate("ETHUSDT")
            
            call_args = mock_get.call_args_list[0]
            assert "/v5/market/tickers" in call_args[0][0]
            assert call_args[1]['params']['category'] == "linear"
            assert call_args[1]['params']['symbol'] == "ETHUSDT"