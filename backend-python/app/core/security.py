"""
Security module for cryptographic operations
Handles HMAC-SHA256 signatures for Binance API authentication
"""

import hmac
import hashlib
import time
from typing import Dict, Any
from urllib.parse import urlencode


class BinanceSecurityManager:
    """
    Manages cryptographic signatures and authentication for Binance Futures API
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize security manager with API credentials
        
        Args:
            api_key: Binance API Key
            api_secret: Binance API Secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
    
    def generate_signature(self, data: Dict[str, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for Binance API requests
        
        Args:
            data: Request parameters as dictionary
        
        Returns:
            Hexadecimal signature string
        """
        # Encode request parameters
        query_string = urlencode(data)
        
        # Generate signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for authenticated Binance API requests
        
        Returns:
            Dictionary of required headers
        """
        return {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    
    @staticmethod
    def get_server_time() -> int:
        """Get current Unix timestamp in milliseconds"""
        return int(time.time() * 1000)
    
    @staticmethod
    def validate_recv_window(recv_window: int = 5000, max_window: int = 60000) -> bool:
        """
        Validate recvWindow parameter
        
        Args:
            recv_window: Requested window in milliseconds
            max_window: Maximum allowed window
        
        Returns:
            True if valid, False otherwise
        """
        return 0 < recv_window <= max_window
