"""
Redpanda Event Bus for Go→Python interop.

Provides Redpanda consumer/publisher to route events between Go API Gateway
and Python AI Worker through topics:
- ontology_ai.slack.events       → Python consumes from Go
- ontology_ai.stripe.events     → Python consumes from Go  
- ontology_ai.guardian.results → Python publishes to Go
- ontology_ai.hitl.decisions → Python publishes to Go
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
CONSUMER_GROUP = "ontology_ai-python-worker"
TIMEOUT_SECONDS = 10

# Bound on a single publish acknowledgement. Publication is best-effort and must
# never block the caller indefinitely when the broker is unhealthy.
PUBLISH_TIMEOUT_SECONDS = float(
    os.environ.get("REDPANDA_PUBLISH_TIMEOUT_SECONDS", "10")
)


DLQ_TOPIC = "ontology_ai.dlq.events"


async def _safe_stop(producer: AIOKafkaProducer) -> None:
    """Stop a producer without raising.

    Cleanup runs on success, on failure, and on cancellation. A producer that was
    never started, or one that is already stopping, can raise here; that must not
    mask the original exception. ``CancelledError`` is deliberately NOT swallowed
    (it derives from BaseException), so cancellation still propagates.
    """
    try:
        await producer.stop()
    except Exception as e:
        log.warning("Error stopping Kafka producer: %s", e)


class RedpandaConsumer:
    """Async Redpanda consumer for Go→Python events."""

    def __init__(self, brokers: list[str] = None, group: str = CONSUMER_GROUP):
        self.brokers = brokers or [REDPANDA_URL]
        self.group = group
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: AIOKafkaProducer | None = None
        self._running = False

    async def _ensure_dlq_producer(self) -> AIOKafkaProducer | None:
        """Lazy-init the DLQ producer. Returns None if unavailable."""
        if self._dlq_producer is not None:
            return self._dlq_producer
        producer = AIOKafkaProducer(
            bootstrap_servers=self.brokers,
            client_id="ontology_ai_dlq",
        )
        try:
            await producer.start()
        except Exception as e:
            log.warning("DLQ producer unavailable: %s", e)
            # Drop the half-started producer only after stopping it, otherwise it
            # is garbage-collected unclosed.
            await _safe_stop(producer)
            self._dlq_producer = None
            return None

        self._dlq_producer = producer
        log.info("DLQ producer connected to %s", self.brokers)
        return self._dlq_producer

    async def _publish_dlq(
        self,
        original_topic: str,
        original_key: bytes | None,
        error: str,
        payload: dict,
    ) -> None:
        """Publish a failed message envelope to the DLQ topic."""
        producer = await self._ensure_dlq_producer()
        if producer is None:
            log.warning("Cannot publish to DLQ — no producer available")
            return

        dlq_envelope = {
            "original_topic": original_topic,
            "original_key": original_key.decode() if original_key else None,
            "error": error,
            "failed_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }

        try:
            await producer.send_and_wait(
                DLQ_TOPIC,
                json.dumps(dlq_envelope).encode(),
                key=original_key,
            )
            log.info("Published failed message to DLQ topic %s", DLQ_TOPIC)
        except Exception as dlq_err:
            log.error("Failed to publish to DLQ topic: %s", dlq_err)

    async def connect(self) -> bool:
        """Connect to Redpanda. Returns False if unavailable."""
        try:
            self._consumer = AIOKafkaConsumer(
                "ontology_ai.slack.events",
                "ontology_ai.stripe.events",
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
            log.warning(f"Redpanda unavailable: {e}. Events will not be published.")
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
                error_msg = f"{type(e).__name__}: {e}"
                log.error(f"Error processing message: {error_msg}")

                # Publish to DLQ so the message is not lost
                try:
                    raw_payload = json.loads(msg.value.decode())
                except Exception:
                    raw_payload = {"raw": msg.value.decode(errors="replace")}

                await self._publish_dlq(
                    original_topic=msg.topic,
                    original_key=msg.key,
                    error=error_msg,
                    payload=raw_payload,
                )

    async def stop(self) -> None:
        """Stop consumer and DLQ producer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        if self._dlq_producer:
            await self._dlq_producer.stop()
            self._dlq_producer = None


class RedpandaPublisher:
    """Async Redpanda publisher for Python→Go events."""

    def __init__(self, brokers: list[str] = None):
        self.brokers = brokers or [REDPANDA_URL]
        self._producer: AIOKafkaProducer | None = None

    async def connect(self) -> bool:
        """Connect to Redpanda. Returns False if unavailable."""
        # Release any previously connected producer first: connect() may be called
        # more than once (e.g. get_producer()), and replacing self._producer
        # without stopping the old one leaks a live producer.
        await self.close()

        producer = AIOKafkaProducer(bootstrap_servers=self.brokers)
        try:
            await producer.start()
        except Exception as e:
            log.warning(f"Redpanda unavailable for publish: {e}")
            # Never leave a half-started producer referenced or unclosed.
            await _safe_stop(producer)
            return False

        self._producer = producer
        log.info(f"Redpanda producer connected to {self.brokers}")
        return True

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
            # send_and_wait blocks until the broker acknowledges. If the broker
            # is reachable but wedged (e.g. it advertises a metadata node with
            # an unresolvable host), the await never returns and the caller --
            # including run_startup_guardian -- hangs indefinitely. Bound it so
            # event publication degrades fail-closed instead of blocking.
            await asyncio.wait_for(
                self._producer.send_and_wait(
                    topic,
                    json.dumps(envelope).encode(),
                    key=tenant_id.encode(),
                ),
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
            log.info(f"Published {event_type} to {topic}")
            return True
        except Exception as e:
            log.error(f"Failed to publish to {topic}: {e}")
            return False

    async def close(self) -> None:
        """Close producer. Idempotent, and never raises.

        The reference is cleared *before* awaiting stop() so that concurrent or
        repeated cleanup paths cannot stop the same producer twice, and a cleanup
        error can never replace an in-flight publish/cancellation exception.
        """
        producer, self._producer = self._producer, None
        if producer is None:
            return
        await _safe_stop(producer)


async def publish_guardian_result(
    tenant_id: str,
    alert_id: str,
    decision: str,
    message: str = "",
) -> bool:
    """Publish guardian decision result to Redpanda for Go to consume."""
    publisher = RedpandaPublisher()
    try:
        if not await publisher.connect():
            log.warning("Could not connect to Redpanda for guardian result")
            return False
        return await publisher.publish(
            topic="ontology_ai.guardian.results",
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
        # Covers the connect-failure path too: connect() may have created a
        # producer that still needs stopping.
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