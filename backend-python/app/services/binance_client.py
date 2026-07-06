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
from urllib.parse import urlencode
from app.core.security import BinanceSecurityManager
from app.core.binance_time import BinanceTimeSync
from app.core.config import settings


class BinanceClient:
    """
    Async HTTP client for Binance Futures API
    Handles authentication and request management

    Uses a single aiohttp.ClientSession (lazy-initialized) to avoid:
    - Excessive socket overhead (new session = new sockets)
    - Connection pool waste
    - Time sync on every request (cached with sync_if_stale())
    """

    def __init__(self):
        """Initialize Binance client"""
        self.security = BinanceSecurityManager(
            settings.BINANCE_API_KEY,
            settings.BINANCE_API_SECRET
        )
        self.time_sync = BinanceTimeSync(settings.BINANCE_TESTNET_URL)
        self.base_url = settings.BINANCE_TESTNET_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-initialize and return the session"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close_session(self) -> None:
        """Close the session (call on shutdown)"""
        if self._session:
            await self._session.close()
            self._session = None

    async def _signed_request(self, method: str, endpoint: str, params: Dict[str, Any],
                             max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Execute a signed request with time sync, 429/418 handling, and retries.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: Binance endpoint (e.g., /fapi/v1/order)
            params: Request parameters (will be signed)
            max_retries: Retry attempts on 429/418

        Returns:
            Parsed JSON response, or None if all retries failed
        """
        await self.time_sync.sync_if_stale()
        params["timestamp"] = self.time_sync.get_adjusted_time()
        params["recvWindow"] = settings.BINANCE_RECV_WINDOW
        params["signature"] = self.security.generate_signature(params)

        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = self.security.get_headers()
        timeout = aiohttp.ClientTimeout(total=15)

        for attempt in range(1, max_retries + 1):
            try:
                async with session.request(method, url, params=params, headers=headers, timeout=timeout) as r:
                    if r.status in (200, 201):
                        return await r.json()

                    if r.status in (429, 418):  # Rate limit or IP banned
                        retry_after = int(r.headers.get("Retry-After", 60))
                        if attempt < max_retries:
                            print(f"Rate limited (HTTP {r.status}), retry after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            print(f"Rate limited, max retries exceeded")
                            return None

                    # Other errors - don't retry
                    error_text = await r.text()
                    print(f"{method} {endpoint} error {r.status}: {error_text}")
                    return None

            except asyncio.TimeoutError:
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 1.5)
                    continue
                return None
            except Exception as e:
                print(f"Exception in _signed_request (attempt {attempt}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 1.5)
                    continue
                return None

        return None

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
            session = await self._get_session()
            async with session.get(url, params={"symbol": symbol}) as response:
                if response.status == 200:
                    return await response.json()
                print(f"Error fetching exchange info: HTTP {response.status}")
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

    async def get_last_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get last traded price for a symbol (from /fapi/v1/ticker/price).

        Use this for calculating grid bounds (reflects actual market level).

        Args:
            symbol: Trading pair (e.g., BTCUSDT)

        Returns:
            Dict with 'symbol' and 'price' keys, or None if request fails
        """
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            timeout = aiohttp.ClientTimeout(total=15)
            session = await self._get_session()
            async with session.get(url, params={"symbol": symbol}, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            print(f"Error fetching last price: {e}")
        return None

    async def get_mark_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real mark price for a symbol (from /fapi/v1/premiumIndex).

        Mark price = index price (reference price) + funding basis.
        This is the price Binance uses to value your position and trigger liquidations.
        Use this for PnL calculations.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)

        Returns:
            Dict with 'markPrice' key, or None if request fails
        """
        try:
            url = f"{self.base_url}/fapi/v1/premiumIndex"
            timeout = aiohttp.ClientTimeout(total=15)
            session = await self._get_session()
            async with session.get(url, params={"symbol": symbol}, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    # Binance returns markPrice as string, return as dict with 'price' for compatibility
                    return {"symbol": symbol, "price": data.get("markPrice")}
        except Exception as e:
            print(f"Error fetching mark price: {e}")
        return None

    async def get_klines(self, symbol: str, interval: str = "4h",
                          limit: int = 15) -> Optional[List[Dict[str, Any]]]:
        """
        Get historical candlestick (kline) data for a symbol.
        Public endpoint - no signature required.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Kline interval (1m, 5m, 1h, 4h, 1d, etc.)
            limit: Number of candles to fetch (max 1500 per Binance docs).
                   Default 15 covers an ATR(14) calculation
                   (14 true-range periods + 1 reference close).

        Returns:
            List of candles ordered oldest -> newest, each parsed into a
            dict with Decimal values, or None if the request fails.
        """
        try:
            url = f"{self.base_url}/fapi/v1/klines"
            params = {"symbol": symbol, "interval": interval, "limit": limit}
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        raw_klines = await response.json()
                        return [self._parse_kline(k) for k in raw_klines]
                    error_text = await response.text()
                    print(f"Error fetching klines: {response.status} - {error_text}")
        except Exception as e:
            print(f"Error fetching klines: {e}")
        return None

    @staticmethod
    def _parse_kline(raw: List[Any]) -> Dict[str, Any]:
        """Convert a raw Binance kline array into a dict with Decimal values"""
        return {
            "open_time": raw[0],
            "open": Decimal(raw[1]),
            "high": Decimal(raw[2]),
            "low": Decimal(raw[3]),
            "close": Decimal(raw[4]),
            "volume": Decimal(raw[5]),
            "close_time": raw[6],
            "quote_volume": Decimal(raw[7]),
            "num_trades": raw[8],
        }

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

        Binance's batchOrders can return HTTP 200 while individual entries in
        the response array are error objects (e.g. {"code": -1007, "msg":
        "Timeout waiting for response..."}). Those per-order ambiguous
        timeouts are resolved by querying the order's clientOrderId before
        deciding whether to retry, to avoid duplicate order placement.
        """
        url = f"{self.base_url}/fapi/v1/batchOrders"
        headers = self.security.get_headers()

        # Re-sync clock if stale (avoids -1022 in long-running containers)
        await self.time_sync.sync_if_stale()

        # Ambiguous per-order Binance error codes: the order MAY have been
        # placed despite the error — must be confirmed via clientOrderId
        # before retrying, never assumed to have failed outright.
        _AMBIGUOUS_CODES = {-1007, -1021}

        results: List[Optional[Dict[str, Any]]] = [None] * len(orders)
        pending_indices = list(range(len(orders)))

        for attempt in range(1, max_retries + 1):
            if not pending_indices:
                break

            client_order_ids = {i: str(uuid.uuid4()).replace("-", "")[:32] for i in pending_indices}
            batch_payload = [
                {
                    "symbol": orders[i]["symbol"],
                    "side": orders[i]["side"],
                    "type": "LIMIT",
                    "timeInForce": "GTC",
                    "quantity": str(orders[i]["quantity"]),
                    "price": str(orders[i]["price"]),
                    "newClientOrderId": client_order_ids[i],
                }
                for i in pending_indices
            ]
            raw_params = {
                "batchOrders": json.dumps(batch_payload, separators=(",", ":")),
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            # urlencode encodes ':' as %3A inside the JSON string; aiohttp's
            # yarl leaves ':' raw in query-param values, producing a different
            # string than what we signed -> -1022.  Sending the pre-encoded
            # string as form body (data=) guarantees signed == sent.
            body = urlencode(raw_params) + "&signature=" + self.security.generate_signature(raw_params)

            try:
                timeout = aiohttp.ClientTimeout(total=20)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, data=body, headers=headers) as response:
                        if response.status in [200, 201]:
                            batch_results = await response.json()
                            if not isinstance(batch_results, list):
                                batch_results = [None] * len(pending_indices)

                            still_pending = []
                            for pos, orig_index in enumerate(pending_indices):
                                item = batch_results[pos] if pos < len(batch_results) else None

                                if isinstance(item, dict) and "orderId" in item:
                                    results[orig_index] = item
                                    continue

                                code = item.get("code") if isinstance(item, dict) else None
                                if code in _AMBIGUOUS_CODES:
                                    print(f"Ambiguous order response ({code}) for index {orig_index}, "
                                          f"checking status via clientOrderId before retry")
                                    await asyncio.sleep(2.0)
                                    confirmed = await self._get_order_by_client_id(
                                        orders[orig_index]["symbol"], client_order_ids[orig_index]
                                    )
                                    if confirmed and "orderId" in confirmed:
                                        print(f"Order {client_order_ids[orig_index]} confirmed placed after {code}")
                                        results[orig_index] = confirmed
                                        continue
                                    if attempt < max_retries:
                                        still_pending.append(orig_index)
                                        continue
                                    print(f"Order at index {orig_index} still unresolved after {max_retries} attempts")
                                    continue

                                # Non-ambiguous error (margin, filters, etc.) — terminal failure, do not retry.
                                print(f"batchOrders item error for index {orig_index}: {item}")

                            pending_indices = still_pending
                            continue

                        error_text = await response.text()
                        print(f"batchOrders error {response.status}: {error_text}")

                        if response.status in [429, 418]:
                            retry_after = int(response.headers.get("Retry-After", 60))
                            await asyncio.sleep(retry_after)
                            continue

                        if response.status == 502 and attempt < max_retries:
                            await asyncio.sleep(attempt * 1.5)
                            continue

                        # Whole batch failed with a non-retryable HTTP status — leave remaining as None.
                        break

            except Exception as e:
                print(f"Exception in batchOrders (attempt {attempt}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 1.5)

        return results

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

    async def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """
        Get account balance information from Binance Futures.

        Calls /fapi/v2/balance to retrieve wallet balance per asset.
        For sizing calculations, focus on USDT balance (collateral).

        Returns:
            Dict with balance data, or None if failed.
            Example:
            {
              "balances": [
                {"asset": "USDT", "balance": "10000.50", "availableBalance": "9500.00"},
                {"asset": "BTC", "balance": "0.5", "availableBalance": "0.5"},
                ...
              ]
            }
        """
        try:
            params = {
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW
            }
            params["signature"] = self.security.generate_signature(params)

            url = f"{self.base_url}/fapi/v2/balance"
            headers = self.security.get_headers()

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        raw_balances = await response.json()
                        return {"balances": raw_balances}
                    error_text = await response.text()
                    print(f"Error fetching account balance: {response.status} - {error_text}")
        except Exception as e:
            print(f"Error fetching account balance: {e}")

        return None

    async def cancel_all_open_orders(self, symbol: str) -> bool:
        """
        Cancel all open orders for a symbol in a single atomic call.

        Uses DELETE /fapi/v1/allOpenOrders which is safer than canceling
        individual orders (avoids race conditions with fills).

        Args:
            symbol: Trading pair

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.time_sync.sync_if_stale()
            params = {
                "symbol": symbol,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)
            url = f"{self.base_url}/fapi/v1/allOpenOrders"
            headers = self.security.get_headers()
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.delete(url, params=params, headers=headers) as r:
                    return r.status == 200
        except Exception as e:
            print(f"Error canceling all open orders: {e}")
        return False

    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current position (net positionAmt) for a symbol.

        Uses GET /fapi/v2/positionRisk to fetch the position with current
        unrealized PnL and other metadata.

        Args:
            symbol: Trading pair

        Returns:
            Dict with position data (positionAmt, unrealizedProfit, etc.) or None if failed
        """
        try:
            await self.time_sync.sync_if_stale()
            params = {
                "symbol": symbol,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)
            url = f"{self.base_url}/fapi/v2/positionRisk"
            headers = self.security.get_headers()
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data[0] if data else None
        except Exception as e:
            print(f"Error fetching position: {e}")
        return None

    async def place_market_close(self, symbol: str, position_amt: Decimal) -> Optional[Dict[str, Any]]:
        """
        Close (reduce) a position with a MARKET order and reduceOnly flag.

        This ensures we cannot accidentally open a position in the opposite
        direction if the net positionAmt is already zero.

        Args:
            symbol: Trading pair
            position_amt: Signed quantity (positive = long to sell, negative = short to buy)

        Returns:
            Order response if successful, None otherwise
        """
        side = "SELL" if position_amt > 0 else "BUY"
        try:
            await self.time_sync.sync_if_stale()
            params = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": str(abs(position_amt)),
                "reduceOnly": "true",
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)
            url = f"{self.base_url}/fapi/v1/order"
            headers = self.security.get_headers()
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, params=params, headers=headers) as r:
                    if r.status in (200, 201):
                        return await r.json()
                    error_text = await r.text()
                    print(f"Error closing position: {r.status} - {error_text}")
        except Exception as e:
            print(f"Exception closing position: {e}")
        return None

    async def ensure_symbol_settings(self, symbol: str, leverage: int = 1,
                                     margin_type: str = "ISOLATED") -> bool:
        """
        Set leverage and margin type for a symbol. Idempotent.

        Tolerates -4046 (no need to change) which indicates the setting
        is already correct.

        Args:
            symbol: Trading pair
            leverage: Leverage multiplier (1 = no leverage)
            margin_type: "ISOLATED" or "CROSS"

        Returns:
            True if successfully set or already at the desired value, False otherwise
        """
        ok = True
        for endpoint, params in [
            ("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}),
            ("/fapi/v1/marginType", {"symbol": symbol, "marginType": margin_type}),
        ]:
            try:
                await self.time_sync.sync_if_stale()
                p = {
                    **params,
                    "timestamp": self.time_sync.get_adjusted_time(),
                    "recvWindow": settings.BINANCE_RECV_WINDOW,
                }
                p["signature"] = self.security.generate_signature(p)
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{self.base_url}{endpoint}", params=p,
                        headers=self.security.get_headers()
                    ) as r:
                        if r.status == 200:
                            continue
                        body = await r.json()
                        if body.get("code") == -4046:
                            continue
                        print(f"ensure_symbol_settings {endpoint}: {r.status} {body}")
                        ok = False
            except Exception as e:
                print(f"ensure_symbol_settings error: {e}")
                ok = False
        return ok

    async def is_one_way_mode(self) -> Optional[bool]:
        """
        Check if account is in one-way position mode (not hedge/dual mode).

        GET /fapi/v1/positionSide/dual returns dualSidePosition flag.
        Returns True if one-way (dualSidePosition=False), False if hedge mode.

        Returns:
            True if one-way, False if hedge, None if request failed
        """
        try:
            await self.time_sync.sync_if_stale()
            params = {
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/fapi/v1/positionSide/dual",
                    params=params,
                    headers=self.security.get_headers()
                ) as r:
                    if r.status == 200:
                        return not (await r.json()).get("dualSidePosition", False)
        except Exception as e:
            print(f"Error checking position mode: {e}")
        return None

    async def get_commission_rate(self, symbol: str) -> Optional[Dict[str, Decimal]]:
        """
        Get actual commission rates for a symbol (respects VIP level, BNB discount).

        GET /fapi/v1/commissionRate returns the account's maker/taker fees
        for the symbol, already accounting for VIP tier and fee discounts.

        Args:
            symbol: Trading pair

        Returns:
            Dict with 'maker' and 'taker' as Decimal, or None if request failed
        """
        try:
            await self.time_sync.sync_if_stale()
            params = {
                "symbol": symbol,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/fapi/v1/commissionRate",
                    params=params,
                    headers=self.security.get_headers()
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        return {
                            "maker": Decimal(data.get("makerCommissionRate", "0.0002")),
                            "taker": Decimal(data.get("takerCommissionRate", "0.0004")),
                        }
        except Exception as e:
            print(f"Error fetching commission rate: {e}")
        return None

    async def get_open_orders(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get all open orders for a symbol in a single request.

        GET /fapi/v1/openOrders?symbol= is more efficient than querying
        each order individually. Returns all non-terminal orders.

        Args:
            symbol: Trading pair

        Returns:
            List of order dicts, or None if request failed
        """
        try:
            await self.time_sync.sync_if_stale()
            params = {
                "symbol": symbol,
                "timestamp": self.time_sync.get_adjusted_time(),
                "recvWindow": settings.BINANCE_RECV_WINDOW,
            }
            params["signature"] = self.security.generate_signature(params)
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/fapi/v1/openOrders",
                    params=params,
                    headers=self.security.get_headers()
                ) as r:
                    if r.status == 200:
                        return await r.json()
        except Exception as e:
            print(f"Error fetching open orders: {e}")
        return None