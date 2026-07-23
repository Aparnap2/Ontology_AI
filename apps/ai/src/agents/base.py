"""OntologyAI V5.1 — Base Agent with agent mesh primitives.

Provides common agent facilities:
- AgentResult dataclass (simplified, no legacy copilot fields)
- BaseAgent class with send()/receive() for peer-to-peer messaging
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.agents.agent_bus import AgentBus, get_bus


@dataclass
class AgentResult:
    """Standard result structure for OntologyAI V5.1 agents."""

    tenant_id: str
    agent_name: str = "unknown"
    summary: str = ""
    output_json: dict[str, Any] = field(default_factory=dict)
    agent_output_id: Optional[str] = None
    qdrant_point_id: Optional[str] = None


class BaseAgent:
    """Base class for all OntologyAI V5.1 agents.

    Provides:
    - send() — publish a typed message to another agent's inbox
    - receive() — drain and return unread inbox messages
    - Qdrant memory writing
    - Agent output persistence
    """

    agent_name: str = "base_agent"

    def __init__(self) -> None:
        self._bus: AgentBus = get_bus()

    def run(self, state: dict, event: dict) -> dict:
        raise NotImplementedError("Subclasses must implement run()")

    # ── Agent mesh primitives ──────────────────────────────────────────

    def send(
        self,
        recipient: str,
        message_type: str,
        payload: dict[str, Any],
        thread_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send a typed message to another agent.

        The message is returned as a dict ready to append to engagement_state.agent_inbox.
        """
        msg = self._bus.publish(
            sender=self.agent_name,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            thread_id=thread_id,
        )
        return msg.to_dict()

    def receive(self, inbox: list[dict]) -> list[dict[str, Any]]:
        """Drain unread messages from the agent's inbox.

        Returns list of message dicts (marked as read in-place).
        """
        return [m.to_dict() for m in AgentBus.drain(inbox)]

    # ── Persistence helpers ────────────────────────────────────────────

    def _write_qdrant_memory(
        self, tenant_id: str, text: str, category: str = "general"
    ) -> str:
        from src.memory.qdrant_ops import upsert_memory

        memory_type_map = {
            "anomaly": "anomaly",
            "briefing": "briefing",
            "revenue_event": "revenue_event",
            "general": "general",
        }
        memory_type = memory_type_map.get(category, category)
        return upsert_memory(
            tenant_id=tenant_id,
            content=text,
            memory_type=memory_type,
            agent=self.agent_name,
        )

    def _write_agent_output(
        self, tenant_id: str, result: AgentResult
    ) -> str:
        from src.db.agent_outputs import insert_agent_output

        record_id = insert_agent_output(
            tenant_id=tenant_id,
            agent_name=result.agent_name,
            headline=result.summary,
            urgency="low",
            hitl_sent=False,
            output_json=result.output_json,
            output_type=None,
        )
        return record_id