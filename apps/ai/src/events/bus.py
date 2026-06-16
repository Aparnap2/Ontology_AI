"""
Redis Streams Event Bus for TrackGuard.

Provides lightweight ordered event streaming as a replacement for Redpanda.
Uses Redis Streams with consumer groups for ordered, replayable event processing.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import redis.asyncio as redis

log = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
MAX_STREAM_LENGTH = 1000


class EventBus:
    """Redis Streams event bus implementation."""

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis_url = redis_url
        self._client: Optional[redis.Redis] = None

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    def _stream_key(self, topic: str, tenant_id: str) -> str:
        return f"trackguard:{tenant_id}:{topic}"

    async def _get_client(self) -> redis.Redis:
        """Get or create the Redis client."""
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def emit(
        self,
        topic: str,
        tenant_id: str,
        payload: Dict[str, Any],
    ) -> Optional[str]:
        """Emit an event to a stream."""
        client = await self._get_client()
        stream = self._stream_key(topic, tenant_id)

        try:
            msg_id = await client.xadd(
                stream,
                {"payload": json.dumps(payload), "timestamp": datetime.utcnow().isoformat()},
                maxlen=MAX_STREAM_LENGTH,
                approximate=True,
            )
            log.info(f"Emitted to {stream} (msg_id: {msg_id})")
            return msg_id
        except Exception as e:
            log.error(f"Failed to emit: {e}")
            return None

    async def ensure_group(
        self,
        topic: str,
        tenant_id: str,
        group: str,
    ) -> bool:
        """Ensure a consumer group exists for a stream."""
        client = await self._get_client()
        stream = self._stream_key(topic, tenant_id)

        try:
            await client.xgroup_create(stream, group, id="0", mkstream=True)
            log.info(f"Created group {group} for {stream}")
            return True
        except Exception as e:
            if "BUSYGROUP" in str(e):
                return True
            log.warning(f"Failed to create group {group}: {e}")
            return False
        except Exception as e:
            log.warning(f"Failed to ensure group {group}: {e}")
            return False

    async def consume(
        self,
        topic: str,
        tenant_id: str,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> Any:
        """Consume messages from a stream using a consumer group."""
        client = await self._get_client()
        stream = self._stream_key(topic, tenant_id)

        try:
            messages = await client.xreadgroup(
                group,
                consumer,
                {stream: ">"},
                count=count,
                block=block_ms,
            )

            if not messages:
                return {}

            result = {}
            for stream_name, msgs in messages.items():
                stream_key = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                result[stream_key] = []

                for msg_id, fields in msgs:
                    msg = {
                        "id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                    }
                    msg["payload"] = json.loads(fields[b"payload"]) if b"payload" in fields else {}
                    result[stream_key].append(msg)

            return result

        except Exception as e:
            log.error(f"Failed to consume: {e}")
            return {}

    async def read_recent(
        self,
        topic: str,
        tenant_id: str,
        count: int = 100,
    ) -> Any:
        """Read last N messages from a stream (no consumer group)."""
        client = await self._get_client()
        stream = self._stream_key(topic, tenant_id)

        try:
            messages = await client.xrevrange(stream, "+", "-", count=count)

            result = []
            for msg_id, fields in messages:
                msg = {
                    "id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                }
                if b"payload" in fields:
                    msg["payload"] = json.loads(fields[b"payload"])
                if b"timestamp" in fields:
                    msg["timestamp"] = fields[b"timestamp"].decode()
                result.append(msg)

            return result

        except Exception as e:
            log.error(f"Failed to read recent: {e}")
            return []

    async def health_check(self) -> Any:
        """Check Redis connectivity."""
        try:
            client = await self._get_client()
            await client.ping()
            return {"status": "healthy", "redis": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


async def emit(topic: str, tenant_id: str, payload: Dict[str, Any]) -> Any:
    """Emit an event (convenience function)."""
    bus = get_event_bus()
    return await bus.emit(topic, tenant_id, payload)


async def consume(
    topic: str,
    tenant_id: str,
    group: str,
    consumer: str,
    count: int = 10,
    block_ms: int = 5000,
) -> Any:
    """Consume events (convenience function)."""
    bus = get_event_bus()
    return await bus.consume(topic, tenant_id, group, consumer, count, block_ms)


async def acknowledge(
    topic: str,
    tenant_id: str,
    group: str,
    message_ids: List[str],
) -> bool:
    """Acknowledge processed messages."""
    client = await get_event_bus()._get_client()
    stream = get_event_bus()._stream_key(topic, tenant_id)

    try:
        for msg_id in message_ids:
            await client.xack(stream, group, msg_id)
        return True
    except Exception as e:
        log.error(f"Failed to acknowledge: {e}")
        return False