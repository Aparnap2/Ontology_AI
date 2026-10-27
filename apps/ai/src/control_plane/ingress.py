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
import hashlib
import json
from typing import Any

from src.control_plane.approval import await_approval, request_approval
from src.control_plane.audit import append_event
from src.control_plane.authorization import authorize
from src.control_plane.concurrency import get_store
from src.control_plane.contracts import ActionIntent
from src.control_plane.executor import execute as _execute
from src.control_plane.idempotency import IdempotencyConflictError, get_seen
from src.control_plane.policy import is_blocked, needs_approval
from src.control_plane.verification import outcome_event, verify_execution

_seen = get_seen()



def _payload_hash(intent: Any) -> str:
    """Stable hash of the request an idempotency key stands for.

    Two submissions sharing a key but carrying different payloads are not
    duplicates — they are a key collision, and must be surfaced rather than
    silently collapsed.
    """
    try:
        blob = json.dumps(
            {
                "operation": intent.operation,
                "target": intent.target_reference,
                "params": intent.requested_parameters,
            },
            sort_keys=True,
            default=str,
        )
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(blob.encode()).hexdigest()


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
    try:
        authorized = authorize(intent, ctx)
    except PermissionError as exc:
        # Fail closed and make the rejection VISIBLE to the caller as an
        # audit event. Authority is decided before any policy/idempotency
        # work, so nothing downstream can widen scope.
        return append_event(
            mission_id=str(ctx.get("mission_id") or "unknown"),
            action_id="",
            intent=intent,
            decision=f"deny:unauthorized:{exc}",
            verified=False,
        )
    except KeyError as exc:
        return append_event(
            mission_id=str(ctx.get("mission_id") or "unknown"),
            action_id="",
            intent=intent,
            decision=f"deny:invalid_trusted_context:{exc}",
            verified=False,
        )
    role_caps = list(getattr(ctx.get("role_config"), "capabilities", []) or [])
    # The executor's allowlist is the SAME trusted allowlist authorize()
    # already validated — AuthorizedAction.permissions is derived from
    # trusted state by authorize() and is guaranteed non-empty (an empty
    # allowlist fails closed there). Defaulting to None here would hand the
    # registry an absent allowlist, which it now correctly denies.
    exec_allowlist = list(authorized.permissions) or role_caps
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
    # ATOMIC RESERVATION. This used to be check-then-act: is_duplicate()
    # checked here and mark() ran only after execution, so every concurrent
    # submitter inside the execution window passed the check and executed.
    # claim() is a compare-and-set, so exactly one caller can proceed.
    payload_hash = _payload_hash(intent)
    claim_owner = f"{authorized.action_id}:{id(authorized)}"
    try:
        claimed = _seen.claim(
            authorized.idempotency_key, claim_owner, payload_hash
        )
    except IdempotencyConflictError:
        return append_event(
            mission_id=authorized.mission_id, action_id=authorized.action_id,
            intent=intent, decision="deny:idempotency_key_conflict", verified=False,
        )
    if not claimed:
        return append_event(
            mission_id=authorized.mission_id, action_id=authorized.action_id,
            intent=intent, decision="deny:duplicate", verified=False,
        )
    version_key = f"{authorized.tenant_id}:{authorized.mission_id}"
    if authorized.expected_version is not None:
        if get_store().current(version_key) != authorized.expected_version:
            _seen.release(authorized.idempotency_key, claim_owner)
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="deny:stale_version", verified=False,
            )
    if needs_approval(intent, ctx.get("role_config")):
        if signal_handler is None:
            # Nothing executed and no approval will ever arrive, so the claim
            # must be released. Leaving it PENDING wedged this key for the
            # full lease (DEFAULT_LEASE_SECONDS), denying a legitimate retry.
            _seen.release(authorized.idempotency_key, claim_owner)
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
            # Nothing executed, so the claim must stay retryable.
            _seen.release(authorized.idempotency_key, claim_owner)
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="deny:approval_expired", verified=False,
            )
        if not decision.get("approved", False):
            _seen.release(authorized.idempotency_key, claim_owner)
            return append_event(
                mission_id=authorized.mission_id, action_id=authorized.action_id,
                intent=intent, decision="deny:approval_rejected",
                result=decision, verified=False,
            )
    try:
        result = _execute(authorized, role_caps=exec_allowlist or None)
    except Exception:
        # The external outcome is unknown. Release rather than commit: a
        # committed key can never run again, and an unknown outcome must be
        # verified before any retry rather than silently dropped.
        _seen.release(authorized.idempotency_key, claim_owner)
        raise
    if authorized.expected_version is not None:
        get_store().advance(version_key)
    verified = False
    if capabilities is not None:
        outcome = await verify_execution(
            intent.operation, dict(intent.requested_parameters or {}),
            {}, authorized.tenant_id, capabilities=capabilities,
            role_caps=exec_allowlist or None,
            result=result.get("data") if isinstance(result, dict) else result,
        )
        verified = outcome.verified
        result = {**result, **outcome_event(authorized.action_id, outcome)}
    _seen.commit(authorized.idempotency_key, claim_owner)
    return append_event(
        mission_id=authorized.mission_id, action_id=authorized.action_id,
        intent=intent, decision="permit:executed", result=result, verified=verified,
    )
