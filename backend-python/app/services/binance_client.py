"""
Binance API client wrapper
Handles all HTTP requests to Binance Futures API
"""

import aiohttp
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional
from app.core.security import BinanceSecurityManager
from app.core.binance_time import BinanceTimeSync
from app.core.config import settings


class BinanceClient:
    """
    Async HTTP client for Binance Futures API
    Handles authentication and request management
    """
    
    def __init__(self):
        """Initialize Binance client"""
        self.security = BinanceSecurityManager(
            settings.BINANCE_API_KEY,
            settings.BINANCE_API_SECRET
        )
        self.time_sync = BinanceTimeSync(settings.BINANCE_TESTNET_URL)
        self.base_url = settings.BINANCE_TESTNET_URL
    
    async def get_exchange_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get exchange info for a symbol
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
        
        Returns:
            Symbol info or None if request fails
        """
        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params={"symbol": symbol}) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Error fetching exchange info: {e}")
        return None

    async def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, Decimal]]:
        """
        Get price/quantity/notional filters for a symbol (tickSize, stepSize, minNotional)

        Args:
            symbol: Trading pair (e.g., BTCUSDT)

        Returns:
            Dict with 'tick_size', 'step_size', 'min_notional' as Decimal, or None if not found
        """
        info = await self.get_exchange_info(symbol)
        if not info:
            return None

        for symbol_info in info.get("symbols", []):
            if symbol_info.get("symbol") != symbol:
                continue

            filters = {f["filterType"]: f for f in symbol_info.get("filters", [])}
            price_filter = filters.get("PRICE_FILTER", {})
            lot_size = filters.get("LOT_SIZE", {})
            min_notional = filters.get("MIN_NOTIONAL", {})

            return {
                "tick_size": Decimal(price_filter.get("tickSize", "0.00000001")),
                "step_size": Decimal(lot_size.get("stepSize", "0.00000001")),
                "min_notional": Decimal(min_notional.get("notional", min_notional.get("minNotional", "0")))
            }

        return None

    async def get_mark_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current mark price for a symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)

        Returns:
            Dict with 'price' key or None if request fails
        """
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params={"symbol": symbol}) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Error fetching mark price: {e}")
        return None

    async def place_limit_order(self, symbol: str, side: str, quantity: float,
                               price: float, time_in_force: str = "GTC") -> Optional[Dict[str, Any]]:
        """
        Place a limit order on Binance Futures
        
        Args:
            symbol: Trading pair
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price
            time_in_force: Time in force (GTC, IOC, FOK)
        
        Returns:
            Order response or None if failed
        """
        try:
            params = {
                "symbol": symbol,
                "side": side,
                "type": "LIMIT",
                "timeInForce": time_in_force,
                "quantity": str(quantity),
                "price": str(price),
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW
            }
            
            params["signature"] = self.security.generate_signature(params)
            
            url = f"{self.base_url}/fapi/v1/order"
            headers = self.security.get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, headers=headers) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        print(f"Error placing order: {response.status} - {error_text}")
        except Exception as e:
            print(f"Exception placing order: {e}")
        
        return None
    
    async def cancel_order(self, symbol: str, order_id: int) -> Optional[Dict[str, Any]]:
        """
        Cancel an order on Binance Futures
        
        Args:
            symbol: Trading pair
            order_id: Order ID to cancel
        
        Returns:
            Cancellation response or None if failed
        """
        try:
            params = {
                "symbol": symbol,
                "orderId": order_id,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW
            }
            
            params["signature"] = self.security.generate_signature(params)
            
            url = f"{self.base_url}/fapi/v1/order"
            headers = self.security.get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Error canceling order: {e}")
        
        return None
    
    async def get_order_status(self, symbol: str, order_id: int) -> Optional[Dict[str, Any]]:
        """
        Get order status from Binance Futures
        
        Args:
            symbol: Trading pair
            order_id: Order ID
        
        Returns:
            Order status or None if failed
        """
        try:
            params = {
                "symbol": symbol,
                "orderId": order_id,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW
            }
            
            params["signature"] = self.security.generate_signature(params)
            
            url = f"{self.base_url}/fapi/v1/order"
            headers = self.security.get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Error getting order status: {e}")
        
        return None
