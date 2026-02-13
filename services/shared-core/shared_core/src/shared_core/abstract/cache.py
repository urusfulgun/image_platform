import asyncio
import logging
from collections import OrderedDict
from typing import Any
import httpx

logger = logging.getLogger(__name__)


class AsyncLRUCache:
    def __init__(self, maxsize: int = 500):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: Any):
        if key in self.cache:
            self.cache.move_to_end(key)

        self.cache[key] = value

        if len(self.cache) > self.maxsize:
            # Pop the oldest (least recently used)
            old_key, old_value = self.cache.popitem(last=False)
            # Schedule the cleanup in the background
            self._schedule_cleanup(old_key, old_value)

    def _schedule_cleanup(self, key: str, client: httpx.AsyncClient):
        """Safely close the client without blocking the main thread."""

        async def close_task():
            try:
                if hasattr(client, "aclose"):
                    await client.aclose()
                    logger.debug(
                        f"Successfully evicted and closed client for session: {key}"
                    )
            except Exception as e:
                logger.error(f"Error closing evicted DPoP client {key}: {e}")

        # Create a background task
        asyncio.create_task(close_task())
