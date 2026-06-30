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
    to avoid authentication errors due to clock skew
    """
    
    def __init__(self, testnet_url: str):
        """
        Initialize time synchronizer
        
        Args:
            testnet_url: Binance Testnet API base URL
        """
        self.testnet_url = testnet_url
        self.time_offset = 0  # Time difference in milliseconds
    
    async def sync_time(self) -> Optional[int]:
        """
        Synchronize local time with Binance server
        
        Returns:
            Server time in milliseconds or None if sync fails
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
                        
                        # Calculate time offset
                        self.time_offset = server_time - local_time
                        return server_time
        except Exception as e:
            print(f"Error syncing with Binance: {e}")
        
        return None
    
    def get_adjusted_time(self) -> int:
        """
        Get current time adjusted for Binance server offset
        
        Returns:
            Adjusted Unix timestamp in milliseconds
        """
        return int(time.time() * 1000) + self.time_offset
