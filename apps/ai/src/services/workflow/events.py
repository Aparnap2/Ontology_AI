"""
Workflow Events — Redpanda event wiring for cross-agent communication.

Provides event publishing and consuming for:
- Memory service events
- Decision engine events  
- Agent-to-agent events
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from src.events.redpanda import RedpandaPublisher, RedpandaConsumer, get_producer

log = logging.getLogger(__name__)

# =============================================================================
# Topic Definitions
# =============================================================================

# Memory service topics
MEMORY_QUERY_TOPIC = "sarthi.memory.query"
MEMORY_STORE_TOPIC = "sarthi.memory.store"
MEMORY_RETRIEVE_TOPIC = "sarthi.memory.retrieve"
MEMORY_COMPRESS_TOPIC = "sarthi.memory.compress"
MEMORY_DECAY_TOPIC = "sarthi.memory.decay"

# Decision engine topics
DECISION_REQUEST_TOPIC = "sarthi.decision.request"
DECISION_RESULT_TOPIC = "sarthi.decision.result"

# Agent-to-agent topics
AGENT_EVENT_TOPIC = "sarthi.agent.events"
WORKFLOW_COMPLETE_TOPIC = "sarthi.workflow.complete"
WORKFLOW_FAILED_TOPIC = "sarthi.workflow.failed"


# =============================================================================
# Event Publishers
# =============================================================================


class WorkflowEventPublisher:
    """Publisher for workflow-related events."""

    def __init__(self):
        self._publisher: RedpandaPublisher | None = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Redpanda."""
        try:
            self._publisher = await get_producer()
            self._connected = True
            log.info("WorkflowEventPublisher connected to Redpanda")
            return True
        except Exception as e:
            log.error(f"Failed to connect WorkflowEventPublisher: {e}")
            return False

    async def publish_memory_query(
        self,
        tenant_id: str,
        query: str,
        context: dict[str, Any],
    ) -> bool:
        """Publish a memory query event."""
        if not self._connected:
            log.warning("Publisher not connected, attempting reconnect")
            await self.connect()

        if not self._publisher:
            log.error("Cannot publish - no publisher available")
            return False

        return await self._publisher.publish(
            topic=MEMORY_QUERY_TOPIC,
            tenant_id=tenant_id,
            event_type="MEMORY_QUERY",
            source="workflow",
            payload={
                "query": query,
                "context": context,
            },
        )

    async def publish_decision_request(
        self,
        tenant_id: str,
        request_id: str,
        decision_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """Publish a decision request event."""
        if not self._connected:
            await self.connect()

        if not self._publisher:
            return False

        return await self._publisher.publish(
            topic=DECISION_REQUEST_TOPIC,
            tenant_id=tenant_id,
            event_type="DECISION_REQUEST",
            source="workflow",
            payload={
                "request_id": request_id,
                "decision_type": decision_type,
                "payload": payload,
            },
        )

    async def publish_workflow_complete(
        self,
        tenant_id: str,
        workflow_name: str,
        run_id: str,
        result: dict[str, Any],
    ) -> bool:
        """Publish workflow completion event."""
        if not self._connected:
            await self.connect()

        if not self._publisher:
            return False

        return await self._publisher.publish(
            topic=WORKFLOW_COMPLETE_TOPIC,
            tenant_id=tenant_id,
            event_type="WORKFLOW_COMPLETE",
            source="workflow",
            payload={
                "workflow_name": workflow_name,
                "run_id": run_id,
                "result": result,
            },
        )

    async def publish_workflow_failed(
        self,
        tenant_id: str,
        workflow_name: str,
        run_id: str,
        error: str,
    ) -> bool:
        """Publish workflow failure event."""
        if not self._connected:
            await self.connect()

        if not self._publisher:
            return False

        return await self._publisher.publish(
            topic=WORKFLOW_FAILED_TOPIC,
            tenant_id=tenant_id,
            event_type="WORKFLOW_FAILED",
            source="workflow",
            payload={
                "workflow_name": workflow_name,
                "run_id": run_id,
                "error": error,
            },
        )

    async def publish_agent_event(
        self,
        tenant_id: str,
        from_agent: str,
        to_agent: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """Publish an agent-to-agent event."""
        if not self._connected:
            await self.connect()

        if not self._publisher:
            return False

        return await self._publisher.publish(
            topic=AGENT_EVENT_TOPIC,
            tenant_id=tenant_id,
            event_type=event_type,
            source=from_agent,
            payload={
                "to_agent": to_agent,
                "event_type": event_type,
                "payload": payload,
            },
        )

    async def close(self) -> None:
        """Close the publisher."""
        self._connected = False


# =============================================================================
# Event Consumers
# =============================================================================


class WorkflowEventConsumer:
    """Consumer for workflow-related events."""

    def __init__(self):
        self._consumer: RedpandaConsumer | None = None

    async def connect(self) -> bool:
        """Connect to Redpanda."""
        try:
            self._consumer = RedpandaConsumer()
            return await self._consumer.connect()
        except Exception as e:
            log.error(f"Failed to connect WorkflowEventConsumer: {e}")
            return False

    async def consume_memory_results(
        self,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        """Consume memory query results."""
        if not self._consumer:
            log.warning("Consumer not connected")
            return

        # Start consuming from memory retrieve topic
        # Note: In production, would need separate consumer for results
        log.info("Starting memory results consumption")

    async def consume_decision_results(
        self,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        """Consume decision results."""
        if not self._consumer:
            log.warning("Consumer not connected")
            return

        log.info("Starting decision results consumption")

    async def stop(self) -> None:
        """Stop the consumer."""
        if self._consumer:
            await self._consumer.stop()


# =============================================================================
# Singleton instances
# =============================================================================

_publisher: WorkflowEventPublisher | None = None
_consumer: WorkflowEventConsumer | None = None


async def get_workflow_publisher() -> WorkflowEventPublisher:
    """Get or create singleton workflow publisher."""
    global _publisher
    if _publisher is None:
        _publisher = WorkflowEventPublisher()
        await _publisher.connect()
    return _publisher


async def get_workflow_consumer() -> WorkflowEventConsumer:
    """Get or create singleton workflow consumer."""
    global _consumer
    if _consumer is None:
        _consumer = WorkflowEventConsumer()
        await _consumer.connect()
    return _consumer


async def close_workflow_events() -> None:
    """Close all workflow event connections."""
    global _publisher, _consumer
    if _publisher:
        await _publisher.close()
        _publisher = None
    if _consumer:
        await _consumer.stop()
        _consumer = None