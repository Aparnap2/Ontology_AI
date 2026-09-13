"""Control Plane ingress — the single entry point for action intents.

All callers (LangGraph nodes, Temporal activities/workflows, event
consumers, API handlers) submit intents ONLY via :func:`submit_intent`.

HARD RULE: no direct connector (``src/connectors.*``) or capability
(``src/mission/capability*.py``) imports are allowed in this package —
execution funnels exclusively through :mod:`executor`, which wraps
``CapabilityOpRegistry``. No LLM calls in this scaffold.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.control_plane.approval import await_approval, request_approval
from src.control_plane.audit import append_event
from src.control_plane.authorization import authorize
from src.control_plane.concurrency import get_store
from src.control_plane.contracts import ActionIntent
from src.control_plane.executor import execute as _execute
from src.control_plane.idempotency import get_seen
from src.control_plane.policy import is_blocked, needs_approval
from src.control_plane.verification import outcome_event, verify_execution

_seen = get_seen()


async def submit_intent(
    intent: ActionIntent,
    trusted_context: dict[str, Any],
    *,
    role_config: Any = None,
    signal_handler: Any = None,
    capabilities: Any = None,
) -> dict[str, Any]:
    """Authorize → policy → idempotency → approval → execute → verify → audit."""
    ctx = dict(trusted_context or {})
    if role_config is not None:
        ctx.setdefault("role_config", role_config)
    authorized = authorize(intent, ctx)
    role_caps = list(getattr(ctx.get("role_config"), "capabilities", []) or [])
    if (
        ctx.get("version") is not None
        and ctx.get("current_version") is not None
        and ctx["version"] != ctx["current_version"]
    ):
        return append_event(
            mission_id=authorized.mission_id, action_id=authorized.action_id,
            intent=intent, decision="deny:stale_context", verified=False,
        )
    if is_blocked(intent, ctx.get("role_config")):
        return append_event(
            mission_id=authorized.mission_id, action_id=authorized.action_id,
            intent=intent, decision="deny:blocked", verified=False,
        )
    if _seen.is_duplicate(authorized.idempotency_key):
        return append_event(
            mission_id=authorized.mission_id, action_id=authorized.action_id,
            intent=intent, decision="deny:duplicate", verified=False,
        )
    version_key = f"{authorized.tenant_id}:{authorized.mission_id}"
    if authorized.expected_version is not None:
        if get_store().current(version_key) != authorized.expected_version:
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="deny:stale_version", verified=False,
            )
    if needs_approval(intent, ctx.get("role_config")):
        if signal_handler is None:
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="require_approval:no_handler", verified=False,
            )
        request_approval(authorized, signal_handler)
        timeout = ctx.get("approval_timeout_seconds")
        try:
            if timeout is None:
                decision = await await_approval(signal_handler)
            else:
                decision = await asyncio.wait_for(
                    await_approval(signal_handler), timeout=float(timeout)
                )
        except TimeoutError:
            _seen.mark(authorized.idempotency_key)
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="deny:approval_expired", verified=False,
            )
        if not decision.get("approved", False):
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="deny:approval_rejected",
                result=decision, verified=False,
            )
    result = _execute(authorized, role_caps=role_caps or None)
    if authorized.expected_version is not None:
        get_store().advance(version_key)
    verified = False
    if capabilities is not None:
        outcome = await verify_execution(
            intent.operation, dict(intent.requested_parameters or {}),
            {}, authorized.tenant_id, capabilities=capabilities,
            role_caps=role_caps or None,
            result=result.get("data") if isinstance(result, dict) else result,
        )
        verified = outcome.verified
        result = {**result, **outcome_event(authorized.action_id, outcome)}
    _seen.mark(authorized.idempotency_key)
    return append_event(
        mission_id=authorized.mission_id, action_id=authorized.action_id,
        intent=intent, decision="permit:executed", result=result, verified=verified,
    )
