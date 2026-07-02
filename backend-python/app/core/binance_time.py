"""
Binance time synchronization module
Ensures accurate timestamp synchronization with Binance servers
"""

import asyncio
import aiohttp
import time
from typing import Optional


class BinanceTimeSync:
    """
    Manages time synchronization with Binance servers
    to avoid authentication errors due to clock skew.

    sync_if_stale() re-syncs automatically when the last sync is older than
    max_age_seconds (default 30 min). Call it before any signed request that
    runs in a long-lived container.
    """

    def __init__(self, testnet_url: str):
        self.testnet_url = testnet_url
        self.time_offset = 0          # milliseconds
        self._last_sync_at: Optional[float] = None  # local time.time() of last sync

    async def sync_time(self) -> Optional[int]:
        """
        Synchronize local time with Binance server.

        Returns:
            Server time in milliseconds or None if sync fails.
        """
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.testnet_url}/fapi/v1/time"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        server_time = data.get('serverTime')
                        local_time = int(time.time() * 1000)
                        self.time_offset = server_time - local_time
                        self._last_sync_at = time.time()
                        return server_time
        except Exception as e:
            print(f"Error syncing with Binance: {e}")
        return None

    async def sync_if_stale(self, max_age_seconds: int = 1800) -> None:
        """
        Re-sync only if last sync was more than max_age_seconds ago (default 30 min).
        Safe to call before every signed request - cheap no-op when fresh.
        """
        if (
            self._last_sync_at is None
            or (time.time() - self._last_sync_at) > max_age_seconds
        ):
            await self.sync_time()

    def get_adjusted_time(self) -> int:
        """
        Get current time adjusted for Binance server offset.

        Returns:
            Adjusted Unix timestamp in milliseconds.
        """
        return int(time.time() * 1000) + self.time_offset