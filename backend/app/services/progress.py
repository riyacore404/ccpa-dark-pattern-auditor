"""Live progress events for running audits, carried over Redis pub/sub.

The worker publishes small events (step numbers and counts only, never page
content, URLs or findings text). The WebSocket endpoint subscribes and
forwards them. Pub/sub does not replay, so the endpoint also sends a database
snapshot when a client connects; a late joiner is never left guessing.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import redis
import redis.asyncio as redis_async

CHANNEL_PREFIX = "audit-progress:"


def channel_for(session_id: UUID | str) -> str:
    return f"{CHANNEL_PREFIX}{session_id}"


class RedisProgressPublisher:
    """Used by the worker as the AuditRunner progress sink."""

    def __init__(self, url: str, client: Any | None = None) -> None:
        self._client = client or redis.Redis.from_url(
            url, socket_timeout=2, socket_connect_timeout=2
        )

    def __call__(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, separators=(",", ":"))
        self._client.publish(channel_for(event["session_id"]), payload)


class EventReader:
    def __init__(self, pubsub: Any) -> None:
        self._pubsub = pubsub

    async def next(self, timeout: float) -> dict[str, Any] | None:
        """The next event, or None when nothing arrived within `timeout`.

        redis-py returns None early when it only consumed a subscribe
        confirmation, so keep polling until the deadline passes.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = max(deadline - loop.time(), 0.0)
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=remaining
            )
            if message is not None:
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    event = None
                return event if isinstance(event, dict) else None
            if remaining <= 0.0:
                return None


class RedisProgressSource:
    """Used by the WebSocket endpoint."""

    def __init__(self, url: str, client: Any | None = None) -> None:
        self._url = url
        self._client = client

    @asynccontextmanager
    async def subscribe(self, session_id: UUID | str) -> AsyncIterator[EventReader]:
        client = self._client or redis_async.Redis.from_url(
            self._url, socket_connect_timeout=2
        )
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(channel_for(session_id))
            yield EventReader(pubsub)
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            finally:
                if self._client is None:
                    await client.aclose()
