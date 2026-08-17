import json
from typing import Any

import redis.asyncio as redis

from app.config import settings

CHANNELS = {
    "cases": "waterwatch:cases",
    "surveillance": "waterwatch:surveillance",
    "appointments": "waterwatch:appointments",
    "alerts": "waterwatch:alerts",
    "notifications": "waterwatch:notifications",
}


class RedisBus:
    """Thin wrapper around a single reusable async Redis client for pub/sub."""

    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            try:
                await self._client.connection_pool.disconnect()
            except Exception:
                pass
            self._client = None

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        if self._client is None:
            await self.connect()
        await self._client.publish(channel, json.dumps(payload, default=str))

    async def ping(self) -> bool:
        try:
            if self._client is None:
                await self.connect()
            return await self._client.ping()
        except Exception:
            return False

    def pubsub(self):
        return self._client.pubsub()

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client not connected")
        return self._client


redis_bus = RedisBus()
