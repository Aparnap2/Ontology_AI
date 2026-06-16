"""
Redpanda Event Bus for Go→Python interop.

Provides Redpanda consumer/publisher to route events between Go API Gateway
and Python AI Worker through topics:
- trackguard.slack.events       → Python consumes from Go
- trackguard.stripe.events     → Python consumes from Go  
- trackguard.guardian.results → Python publishes to Go
- trackguard.hitl.decisions → Python publishes to Go
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

log = logging.getLogger(__name__)

REDPANDA_URL = os.environ.get("REDPANDA_URL", "localhost:9092")
CONSUMER_GROUP = "trackguard-python-worker"
TIMEOUT_SECONDS = 10


class RedpandaConsumer:
    """Async Redpanda consumer for Go→Python events."""

    def __init__(self, brokers: list[str] = None, group: str = CONSUMER_GROUP):
        self.brokers = brokers or [REDPANDA_URL]
        self.group = group
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    async def connect(self) -> bool:
        """Connect to Redpanda. Returns False if unavailable."""
        try:
            self._consumer = AIOKafkaConsumer(
                "trackguard.slack.events",
                "trackguard.stripe.events",
                bootstrap_servers=self.brokers,
                group_id=self.group,
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )
            await self._consumer.start()
            self._running = True
            log.info(f"Connected to Redpanda at {self.brokers}")
            return True
        except Exception as e:
            log.warning(f"Redpanda unavailable: {e}. Using Redis Streams fallback.")
            return False

    async def consume(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Consume messages and call handler for each."""
        if not self._consumer:
            return

        async for msg in self._consumer:
            if not self._running:
                break

            try:
                envelope = json.loads(msg.value.decode())
                await handler(envelope)
            except Exception as e:
                log.error(f"Error processing message: {e}")

    async def stop(self) -> None:
        """Stop consumer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None


class RedpandaPublisher:
    """Async Redpanda publisher for Python→Go events."""

    def __init__(self, brokers: list[str] = None):
        self.brokers = brokers or [REDPANDA_URL]
        self._producer: AIOKafkaProducer | None = None

    async def connect(self) -> bool:
        """Connect to Redpanda. Returns False if unavailable."""
        try:
            self._producer = AIOKafkaProducer(bootstrap_servers=self.brokers)
            await self._producer.start()
            log.info(f"Redpanda producer connected to {self.brokers}")
            return True
        except Exception as e:
            log.warning(f"Redpanda unavailable for publish: {e}")
            return False

    async def publish(
        self,
        topic: str,
        tenant_id: str,
        event_type: str,
        source: str,
        payload: dict[str, Any],
    ) -> bool:
        """Publish event to topic."""
        if not self._producer:
            log.warning(f"Cannot publish - Redpanda producer not connected")
            return False

        envelope = {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "source": source,
            "payload": payload,
            "occurred_at": datetime.utcnow().isoformat() + "Z",
        }

        try:
            await self._producer.send_and_wait(
                topic,
                json.dumps(envelope).encode(),
                key=tenant_id.encode(),
            )
            log.info(f"Published {event_type} to {topic}")
            return True
        except Exception as e:
            log.error(f"Failed to publish to {topic}: {e}")
            return False

    async def close(self) -> None:
        """Close producer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None


async def publish_guardian_result(
    tenant_id: str,
    alert_id: str,
    decision: str,
    message: str = "",
) -> bool:
    """Publish guardian decision result to Redpanda for Go to consume."""
    publisher = RedpandaPublisher()
    if not await publisher.connect():
        log.warning("Could not connect to Redpanda for guardian result")
        return False

    try:
        return await publisher.publish(
            topic="trackguard.guardian.results",
            tenant_id=tenant_id,
            event_type="GUARDIAN_DECISION",
            source="guardian",
            payload={
                "alert_id": alert_id,
                "decision": decision,
                "message": message,
            },
        )
    finally:
        await publisher.close()


async def consume_topic(
    topic: str,
    tenant_id: str,
    handler: Callable[[dict], Awaitable[None]],
) -> None:
    """Consume from a specific topic."""
    consumer = RedpandaConsumer()
    if not await consumer.connect():
        log.warning(f"Could not connect to Redpanda to consume {topic}")
        return

    try:
        await consumer.consume(handler)
    finally:
        await consumer.stop()


# Singleton instances
_consumer: Optional[RedpandaConsumer] = None
_producer: Optional[RedpandaPublisher] = None


async def get_consumer() -> RedpandaConsumer:
    """Get or create singleton consumer."""
    global _consumer
    if _consumer is None:
        _consumer = RedpandaConsumer()
    if not await _consumer.connect():
        return _consumer
    return _consumer


async def get_producer() -> RedpandaPublisher:
    """Get or create singleton producer."""
    global _producer
    if _producer is None:
        _producer = RedpandaPublisher()
    if not await _producer.connect():
        return _producer
    return _producer


async def close() -> None:
    """Close all connections."""
    global _consumer, _producer
    if _consumer:
        await _consumer.stop()
        _consumer = None
    if _producer:
        await _producer.close()
        _producer = None