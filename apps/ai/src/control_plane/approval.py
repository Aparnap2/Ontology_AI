"""Control Plane approval — thin wrapper over the HITL signal handler.

Emits ``hitl-approval`` and suspends on ``await_decision`` via the
injected ``InMemorySignalHandler``. In production Temporal binds the
same ``SignalHandler`` protocol to a real workflow signal; this module
holds no approval logic of its own. No connector imports. No LLM calls.
"""

from __future__ import annotations

from typing import Any

from src.control_plane.contracts import AuthorizedAction
from src.mission.signal_handler import InMemorySignalHandler


def request_approval(
    authorized: AuthorizedAction,
    handler: InMemorySignalHandler,
) -> None:
    """Emit the ``hitl-approval`` signal for a human decision."""
    handler.emit(
        "hitl-approval",
        {
            "action_id": authorized.action_id,
            "tenant_id": authorized.tenant_id,
            "mission_id": authorized.mission_id,
            "action_type": authorized.operation,
            "target": authorized.target_reference,
            "risk_tier": authorized.risk_tier,
            "idempotency_key": authorized.idempotency_key,
        },
    )


async def await_approval(
    handler: InMemorySignalHandler,
) -> dict[str, Any]:
    """Suspend until a human resolves the pending approval signal."""
    return await handler.await_decision("hitl-approval")


def resolve_approval(handler: InMemorySignalHandler, decision: dict[str, Any]) -> None:
    """Resolve the pending approval (test/local seam; Temporal owns prod)."""
    handler.resolve(decision)
