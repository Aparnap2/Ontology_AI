"""Control Plane audit — immutable event log for consumers.

Appends frozen event dicts (mission/action/intent/decision/result/
verified) consumed by the timeline, SSE hub, and memory writers.
Events are copied on append so later mutation cannot rewrite history.
No connector imports. No LLM calls.
"""

from __future__ import annotations

import copy
from typing import Any

AUDIT_LOG: list[dict[str, Any]] = []


def append_event(
    store: list[dict[str, Any]] | None = None,
    *,
    mission_id: str,
    action_id: str,
    intent: Any,
    decision: str,
    result: Any = None,
    verified: bool = False,
) -> dict[str, Any]:
    """Append an immutable audit event and return it."""
    target = store if store is not None else AUDIT_LOG
    payload = getattr(intent, "model_dump", None)
    intent_dict = payload() if callable(payload) else copy.deepcopy(dict(intent))
    event = {
        "mission_id": mission_id,
        "action_id": action_id,
        "intent": copy.deepcopy(intent_dict),
        "decision": decision,
        "result": copy.deepcopy(result),
        "verified": bool(verified),
    }
    target.append(copy.deepcopy(event))
    return event


def list_events(store: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return a defensive copy of the audit events."""
    target = store if store is not None else AUDIT_LOG
    return copy.deepcopy(target)
