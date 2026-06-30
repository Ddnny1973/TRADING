"""
Binance API client wrapper
Handles all HTTP requests to Binance Futures API
"""

import asyncio
import json
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional
import aiohttp
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
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
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
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params={"symbol": symbol}) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Error fetching mark price: {e}")
        return None

    async def _get_order_by_client_id(self, symbol: str, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Query an order by its clientOrderId to resolve -1007 ambiguity"""
        try:
            params = {
                "symbol": symbol,
                "origClientOrderId": client_order_id,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW
            }
            params["signature"] = self.security.generate_signature(params)
            url = f"{self.base_url}/fapi/v1/order"
            headers = self.security.get_headers()
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Exception checking order status: {e}")
        return None

    async def place_limit_order(self, symbol: str, side: str, quantity: float,
                               price: float, time_in_force: str = "GTC",
                               max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Place a limit order on Binance Futures.

        - 502: order never reached Binance → safe to retry with new clientOrderId.
        - 408/-1007: status unknown → query by clientOrderId before retrying
          to avoid duplicate orders.
        """
        url = f"{self.base_url}/fapi/v1/order"
        headers = self.security.get_headers()

        for attempt in range(1, max_retries + 1):
            client_order_id = str(uuid.uuid4()).replace("-", "")[:32]
            try:
                params = {
                    "symbol": symbol,
                    "side": side,
                    "type": "LIMIT",
                    "timeInForce": time_in_force,
                    "quantity": str(quantity),
                    "price": str(price),
                    "newClientOrderId": client_order_id,
                    "timestamp": self.time_sync.get_adjusted_time(),
                    "recvWindow": settings.BINANCE_RECV_WINDOW
                }
                params["signature"] = self.security.generate_signature(params)

                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, params=params, headers=headers) as response:
                        if response.status in [200, 201]:
                            return await response.json()

                        error_text = await response.text()
                        print(f"Error placing order: {response.status} - {error_text}")

                        if response.status == 502 and attempt < max_retries:
                            await asyncio.sleep(attempt * 1.5)
                            continue

                        if response.status == 408 and attempt < max_retries:
                            await asyncio.sleep(2.0)
                            existing = await self._get_order_by_client_id(symbol, client_order_id)
                            if existing and "orderId" in existing:
                                print(f"Order {client_order_id} confirmed placed after 408")
                                return existing
                            continue

                        return None

            except Exception as e:
                print(f"Exception placing order (attempt {attempt}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 1.5)

        return None

    async def place_batch_orders(self, orders: List[Dict[str, Any]],
                                  max_retries: int = 3) -> List[Optional[Dict[str, Any]]]:
        """
        Place up to 5 LIMIT orders in a single /fapi/v1/batchOrders request.
        Each element of `orders` must have: symbol, side, quantity, price.
        Returns a list aligned with the input (None for items that failed).
        """
        url = f"{self.base_url}/fapi/v1/batchOrders"
        headers = self.security.get_headers()

        for attempt in range(1, max_retries + 1):
            batch_payload = [
                {
                    "symbol": o["symbol"],
                    "side": o["side"],
                    "type": "LIMIT",
                    "timeInForce": "GTC",
                    "quantity": str(o["quantity"]),
                    "price": str(o["price"]),
                    "newClientOrderId": str(uuid.uuid4()).replace("-", "")[:32],
                }
                for o in orders
            ]
            params = {
                "batchOrders": json.dumps(batch_payload, separators=(",", ":")),
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)

            try:
                timeout = aiohttp.ClientTimeout(total=20)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, params=params, headers=headers) as response:
                        if response.status in [200, 201]:
                            results = await response.json()
                            return results if isinstance(results, list) else [None] * len(orders)

                        error_text = await response.text()
                        print(f"batchOrders error {response.status}: {error_text}")

                        if response.status in [429, 418]:
                            retry_after = int(response.headers.get("Retry-After", 60))
                            await asyncio.sleep(retry_after)
                            continue

                        if response.status == 502 and attempt < max_retries:
                            await asyncio.sleep(attempt * 1.5)
                            continue

                        return [None] * len(orders)

            except Exception as e:
                print(f"Exception in batchOrders (attempt {attempt}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 1.5)

        return [None] * len(orders)

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
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
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
            
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Error getting order status: {e}")
        
        return None
