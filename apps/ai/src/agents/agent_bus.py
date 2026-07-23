"""AgentBus — typed peer-to-peer message bus for agent mesh (V5.1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional


class AgentMessage:
    """A typed message sent between agents via the AgentBus."""

    def __init__(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        payload: dict[str, Any],
        thread_id: Optional[str] = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.sender = sender
        self.recipient = recipient
        self.message_type = message_type
        self.payload = payload
        self.thread_id = thread_id or self.id
        self.ts = datetime.now(timezone.utc).isoformat()
        self.read = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": self.sender,
            "to": self.recipient,
            "type": self.message_type,
            "payload": self.payload,
            "thread_id": self.thread_id,
            "ts": self.ts,
            "read": self.read,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentMessage":
        msg = cls(
            sender=d["from"],
            recipient=d["to"],
            message_type=d["type"],
            payload=d.get("payload", {}),
            thread_id=d.get("thread_id"),
        )
        msg.id = d.get("id", msg.id)
        msg.ts = d.get("ts", msg.ts)
        msg.read = d.get("read", False)
        return msg


MessageHandler = Callable[[AgentMessage], None]


class AgentBus:
    """Simple typed message bus for agent-to-agent communication.

    Messages are stored as serialized dicts in EngagementState.agent_inbox.
    Agents subscribe to message types they want to handle.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[MessageHandler]] = {}

    def register(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for a given message type."""
        self._handlers.setdefault(message_type, []).append(handler)

    def publish(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        payload: dict[str, Any],
        thread_id: Optional[str] = None,
    ) -> AgentMessage:
        """Create a message and route it to the recipient's inbox.

        Returns the created AgentMessage (which can be appended to agent_inbox).
        """
        msg = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            thread_id=thread_id,
        )
        return msg

    def deliver(self, msg: AgentMessage) -> None:
        """Deliver a message to registered handlers (in-process dispatch)."""
        handlers = self._handlers.get(msg.message_type, [])
        for handler in handlers:
            handler(msg)

    @staticmethod
    def drain(inbox: list[dict]) -> list[AgentMessage]:
        """Drain unread messages from an inbox list.

        Returns unread AgentMessage objects and marks them as read in-place.
        """
        unread: list[AgentMessage] = []
        for entry in inbox:
            if not entry.get("read"):
                entry["read"] = True
                unread.append(AgentMessage.from_dict(entry))
        return unread


# Module-level singleton
_BUS: AgentBus = AgentBus()


def get_bus() -> AgentBus:
    """Return the module-level AgentBus singleton."""
    return _BUS