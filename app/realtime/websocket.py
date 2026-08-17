import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

from app.realtime.redis_bus import CHANNELS, redis_bus

logger = logging.getLogger("waterwatch.ws")


class ConnectionManager:
    """Keeps track of connected WebSocket clients per user, and forwards
    events published on Redis to the right connected clients."""

    def __init__(self) -> None:
        self.user_connections: dict[str, set[WebSocket]] = {}
        self.role_connections: dict[str, set[WebSocket]] = {}
        self._listener_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket, user_id: str, role: str) -> None:
        await websocket.accept()
        self.user_connections.setdefault(user_id, set()).add(websocket)
        self.role_connections.setdefault(role, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str, role: str) -> None:
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        if role in self.role_connections:
            self.role_connections[role].discard(websocket)
            if not self.role_connections[role]:
                del self.role_connections[role]

    async def _send(self, websocket: WebSocket, message: dict) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            logger.warning("Failed to send websocket message; dropping connection")

    async def send_to_user(self, user_id: str, message: dict) -> None:
        for ws in list(self.user_connections.get(user_id, set())):
            await self._send(ws, message)

    async def send_to_role(self, role: str, message: dict) -> None:
        for ws in list(self.role_connections.get(role, set())):
            await self._send(ws, message)

    async def broadcast(self, message: dict) -> None:
        seen: set[int] = set()
        for conns in list(self.user_connections.values()):
            for ws in conns:
                if id(ws) not in seen:
                    seen.add(id(ws))
                    await self._send(ws, message)

    async def dispatch(self, envelope: dict) -> None:
        """Dispatch a redis-delivered event to the right local connections."""
        target = envelope.get("target", {})
        message = envelope.get("message")
        if not message:
            return
        if target.get("broadcast"):
            await self.broadcast(message)
            return
        for uid in target.get("user_ids", []) or []:
            await self.send_to_user(uid, message)
        for role in target.get("roles", []) or []:
            await self.send_to_role(role, message)

    async def start_redis_listener(self) -> None:
        await redis_bus.connect()
        pubsub = redis_bus.pubsub()
        await pubsub.subscribe(*CHANNELS.values())

        async def _listen():
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(raw["data"])
                except (TypeError, ValueError):
                    continue
                await self.dispatch(envelope)

        self._listener_task = asyncio.create_task(_listen())

    async def stop_redis_listener(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None


manager = ConnectionManager()


def make_ws_event(event_type: str, data: dict) -> dict:
    return {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


async def publish_event(
    channel_key: str,
    event_type: str,
    data: dict,
    user_ids: list[str] | None = None,
    roles: list[str] | None = None,
    broadcast: bool = False,
) -> None:
    """Publish an event to Redis so any process (including this one) forwards it
    to the right connected WebSocket clients."""
    message = make_ws_event(event_type, data)
    envelope = {
        "target": {
            "user_ids": user_ids or [],
            "roles": roles or [],
            "broadcast": broadcast,
        },
        "message": message,
    }
    await redis_bus.publish(CHANNELS[channel_key], envelope)
