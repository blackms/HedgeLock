"""
Bybit REST API client for polling account information.
"""

import time
import hmac
import hashlib
import httpx
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from src.hedgelock.config import settings
from src.hedgelock.logging import get_logger
from .models import CollateralInfo, LoanInfo, Balance

logger = get_logger(__name__)


class BybitRestClient:
    """REST API client for Bybit."""
    
    def __init__(self):
        self.config = settings.bybit
        self.api_key = self.config.api_key
        self.api_secret = self.config.api_secret
        self.base_url = self.config.rest_url
        self.recv_window = 5000
        self.client = httpx.AsyncClient(timeout=10.0)
        
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC signature for request."""
        param_str = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get common headers for requests."""
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(int(time.time() * 1000)),
            "X-BAPI-RECV-WINDOW": str(self.recv_window),
            "Content-Type": "application/json"
        }
    
    async def get_collateral_info(self) -> Optional[CollateralInfo]:
        """Get collateral information from unified margin account."""
        endpoint = "/v5/account/collateral-info"
        url = f"{self.base_url}{endpoint}"
        
        params = {
            "timestamp": str(int(time.time() * 1000)),
            "recv_window": self.recv_window
        }
        
        params["sign"] = self._generate_signature(params)
        headers = self._get_headers()
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("retCode") != 0:
                logger.error(f"Failed to get collateral info: {result.get('retMsg')}")
                return None
            
            data = result.get("result", {})
            
            # Extract collateral information
            collateral_info = CollateralInfo(
                ltv=Decimal(str(data.get("ltv", 0))),
                collateral_value=Decimal(str(data.get("collateralValue", 0))),
                borrowed_amount=Decimal(str(data.get("borrowAmount", 0))),
                collateral_ratio=Decimal(str(data.get("collateralRatio", 0))),
                free_collateral=Decimal(str(data.get("freeCollateral", 0)))
            )
            
            return collateral_info
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting collateral info: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting collateral info: {e}", exc_info=True)
            return None
    
    async def get_loan_info(self) -> Optional[LoanInfo]:
        """Get active loan information."""
        endpoint = "/v5/lending/info"
        url = f"{self.base_url}{endpoint}"
        
        params = {
            "timestamp": str(int(time.time() * 1000)),
            "recv_window": self.recv_window
        }
        
        params["sign"] = self._generate_signature(params)
        headers = self._get_headers()
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("retCode") != 0:
                logger.error(f"Failed to get loan info: {result.get('retMsg')}")
                return None
            
            loans = result.get("result", {}).get("list", [])
            
            if not loans:
                logger.info("No active loans found")
                return None
            
            # Get the first active loan (for MVP)
            loan_data = loans[0]
            
            loan_info = LoanInfo(
                loan_currency=loan_data.get("loanCurrency"),
                loan_amount=Decimal(str(loan_data.get("loanAmount", 0))),
                collateral_currency=loan_data.get("collateralCurrency"),
                collateral_amount=Decimal(str(loan_data.get("collateralAmount", 0))),
                hourly_interest_rate=Decimal(str(loan_data.get("hourlyInterestRate", 0))),
                loan_term=loan_data.get("loanTerm"),
                loan_order_id=loan_data.get("loanOrderId")
            )
            
            return loan_info
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting loan info: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting loan info: {e}", exc_info=True)
            return None
    
    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Balance]:
        """Get wallet balance."""
        endpoint = "/v5/account/wallet-balance"
        url = f"{self.base_url}{endpoint}"
        
        params = {
            "accountType": account_type,
            "timestamp": str(int(time.time() * 1000)),
            "recv_window": self.recv_window
        }
        
        params["sign"] = self._generate_signature(params)
        headers = self._get_headers()
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("retCode") != 0:
                logger.error(f"Failed to get wallet balance: {result.get('retMsg')}")
                return {}
            
            balances = {}
            accounts = result.get("result", {}).get("list", [])
            
            for account in accounts:
                for coin_data in account.get("coin", []):
                    coin = coin_data.get("coin")
                    balance = Balance(
                        coin=coin,
                        wallet_balance=Decimal(str(coin_data.get("walletBalance", 0))),
                        available_balance=Decimal(str(coin_data.get("availableToWithdraw", 0)))
                    )
                    balances[coin] = balance
            
            return balances
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting wallet balance: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting wallet balance: {e}", exc_info=True)
            return {}
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()