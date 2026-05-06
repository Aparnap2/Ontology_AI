"""
Delivery Service — Coordinates decision delivery across channels.

Delivers decision results from sarthi.decision.results topic to
Slack/Telegram and manages the pending approval review queue.

Key Features:
- Consumes decision results from Redpanda (not HTTP calls to decision-engine)
- Publishes delivery status events back to Redpanda
- Telegram fallback stays behind interface (not in Redpanda contract)
- Review queue for pending HITL items
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .formatter import format_plain_text
from .queue import ReviewQueue, get_queue
from .schemas import (
    DeliveryChannel,
    DeliveryResult,
    DeliveryStatus,
    DeliveryStatusEvent,
    DecisionResultInput,
    PendingApproval,
)

log = logging.getLogger(__name__)

# OTel tracing - initialize at module load
_TRACER = None


def _init_tracing():
    """Initialize tracing once at module load."""
    global _TRACER
    if _TRACER is None:
        try:
            from apps.ai.src.services.tracing import init_tracing, get_service_name
            init_tracing(service_name=get_service_name("delivery-service"))
            from apps.ai.src.services.tracing import get_tracer
            _TRACER = get_tracer("delivery-service")
            log.info("Delivery service tracing initialized")
        except Exception as e:
            log.warning(f"Tracing init failed: {e}")


# Initialize on import
try:
    _init_tracing()
except Exception:
    pass

# Redpanda configuration
REDPANDA_URL = os.environ.get("REDPANDA_URL", "localhost:9092")
CONSUMER_GROUP = "sarthi-delivery-service"
DECISION_TOPIC = "sarthi.decision.results"
DELIVERY_STATUS_TOPIC = "sarthi.delivery.status"


class DeliveryService:
    """
    Main delivery service coordinating decision result delivery.

    Flow:
    1. Subscribe to sarthi.decision.results Redpanda topic
    2. For each decision result:
       a. Try Slack delivery first
       b. Fall back to Telegram if Slack fails
       c. Publish delivery status event to Redpanda
       d. Add to review queue if HITL required
    3. Provide review queue methods for pending approvals
    """

    def __init__(self):
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._producer: Optional[AIOKafkaProducer] = None
        self._running = False
        self._queue: ReviewQueue = get_queue()
        self._handlers: list[Callable[[DecisionResultInput], Awaitable[None]]] = []

    @property
    def queue(self) -> ReviewQueue:
        """Access the review queue."""
        return self._queue

    async def connect(self) -> bool:
        """Connect to Redpanda for consuming and publishing."""
        try:
            # Set up consumer for decision results
            self._consumer = AIOKafkaConsumer(
                DECISION_TOPIC,
                bootstrap_servers=[REDPANDA_URL],
                group_id=CONSUMER_GROUP,
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )
            await self._consumer.start()
            log.info(f"Delivery service connected to Redpanda: {REDPANDA_URL}")

            # Set up producer for delivery status events
            self._producer = AIOKafkaProducer(bootstrap_servers=[REDPANDA_URL])
            await self._producer.start()
            log.info("Delivery service producer connected")

            return True
        except Exception as e:
            log.error(f"Failed to connect to Redpanda: {e}")
            return False

    async def close(self) -> None:
        """Close all Redpanda connections."""
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        if self._producer:
            await self._producer.stop()
            self._producer = None
        log.info("Delivery service connections closed")

    async def deliver(self, decision_result: dict[str, Any]) -> bool:
        """
        Deliver a decision result to configured channels.

        Tries Slack first, falls back to Telegram if Slack fails.
        Publishes delivery status to Redpanda.

        Args:
            decision_result: Raw decision result dict (from Redpanda)

        Returns:
            True if delivered successfully to at least one channel
        """
        import json
        from datetime import datetime

        # Parse into schema
        try:
            decision = DecisionResultInput(**decision_result)
        except Exception as e:
            log.error(f"Failed to parse decision result: {e}")
            return False

        log.info(f"Delivering decision {decision.decision_id} to channels")

        # Try Slack first
        from . import slack
        result = await slack.deliver(decision)

        if not result.ok:
            # Fall back to Telegram (behind interface - not in contract)
            from . import telegram
            result = await telegram.deliver(decision)
            if result.ok:
                result.status = DeliveryStatus.FALLBACK_USED

        # Publish delivery status event to Redpanda
        await self._publish_status(decision, result)

        # Add to review queue if HITL required
        if decision.hitl_required:
            await self._queue.add(
                tenant_id=decision.tenant_id,
                decision_id=decision.decision_id,
                pattern_name=decision.pattern_name,
                severity=decision.severity,
                insight=decision.insight,
                signals=decision.signals,
            )

        return result.ok

    async def _publish_status(
        self,
        decision: DecisionResultInput,
        result: DeliveryResult
    ) -> None:
        """Publish delivery status event to Redpanda."""
        import json

        if not self._producer:
            log.warning("Cannot publish status - producer not connected")
            return

        event = DeliveryStatusEvent(
            tenant_id=decision.tenant_id,
            decision_id=decision.decision_id,
            status=result.status,
            channel=result.channel,
            error=result.error,
        )

        try:
            await self._producer.send_and_wait(
                DELIVERY_STATUS_TOPIC,
                json.dumps(event.model_dump()).encode(),
                key=decision.tenant_id.encode(),
            )
            log.info(f"Published delivery status for {decision.decision_id}")
        except Exception as e:
            log.error(f"Failed to publish delivery status: {e}")

    async def get_pending_approvals(self, tenant_id: str) -> list[dict[str, Any]]:
        """
        Get pending HITL items for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of pending approval items as dicts
        """
        pending = await self._queue.get_pending(tenant_id)
        return [item.model_dump() for item in pending]

    async def approve(
        self,
        item_id: str,
        reason: Optional[str] = None,
        acted_by: Optional[str] = None,
    ) -> bool:
        """
        Approve a pending HITL item.

        Args:
            item_id: Item to approve
            reason: Optional reason for approval
            acted_by: User who performed the action

        Returns:
            True if approved successfully
        """
        return await self._queue.approve(item_id, reason, acted_by)

    async def reject(
        self,
        item_id: str,
        reason: Optional[str] = None,
        acted_by: Optional[str] = None,
    ) -> bool:
        """
        Reject a pending HITL item.

        Args:
            item_id: Item to reject
            reason: Optional reason for rejection
            acted_by: User who performed the action

        Returns:
            True if rejected successfully
        """
        return await self._queue.reject(item_id, reason, acted_by)

    async def consume(self) -> None:
        """Start consuming decision results from Redpanda."""
        if not self._consumer:
            log.warning("Consumer not connected - call connect() first")
            return

        self._running = True
        log.info(f"Starting to consume from {DECISION_TOPIC}")

        async for msg in self._consumer:
            if not self._running:
                break

            try:
                import json
                decision_result = json.loads(msg.value.decode())
                await self.deliver(decision_result)
            except Exception as e:
                log.error(f"Error processing decision result: {e}")

    async def stop_consuming(self) -> None:
        """Stop consuming from Redpanda."""
        self._running = False

    def on_decision(self, handler: Callable[[DecisionResultInput], Awaitable[None]]) -> None:
        """
        Register a callback for decision results.

        Use this to hook into the delivery flow without consuming from Redpanda.

        Args:
            handler: Async function to call with each DecisionResultInput
        """
        self._handlers.append(handler)


# Singleton instance
_service: Optional[DeliveryService] = None


def get_delivery_service() -> DeliveryService:
    """Get or create singleton DeliveryService instance."""
    global _service
    if _service is None:
        _service = DeliveryService()
    return _service


async def create_delivery_service() -> DeliveryService:
    """Create and connect a new delivery service."""
    service = DeliveryService()
    await service.connect()
    return service