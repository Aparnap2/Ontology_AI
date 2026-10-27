"""Control Plane authorization — trusted identity derivation.

Derives tenant/employee/mission/role/permissions/scope from trusted
server state (Temporal/MissionState/session), never from prompt fields
such as ``ActionIntent.requested_by`` (treated as a claim only).

Delegates to ``src/ontology/governance.py`` (blast-radius policy) and
``EmployeeRoleConfig`` (capability/permission allowlists + risk
threshold). No connector imports. No LLM calls.
"""

from __future__ import annotations

from typing import Any

from src.control_plane.contracts import AuthorizedAction
from src.control_plane.idempotency import build_idempotency_key
from src.control_plane.policy import classify


def _require(trusted: dict[str, Any], key: str) -> str:
    """Return a required trusted field or raise ``KeyError``."""
    value = trusted.get(key)
    if not value:
        raise KeyError(f"trusted_context missing required key: {key}")
    return str(value)


def _resolve_allowlist(
    trusted_context: dict[str, Any], role_config: Any
) -> list[str]:
    """Return the operations this principal may perform.

    Both sources are trusted server state:

    * ``role_config.capabilities`` — canonical allowlist of operation names
      (this is what ``CapabilityOpRegistry.assert_allowed`` also enforces).
    * ``role_config.permissions`` / ``trusted_context.permissions`` — coarse
      grants that may also name operations directly.

    When ``role_config`` is present it is authoritative. An empty result
    means *no authority whatsoever* and callers must treat it as deny-all.
    """
    if role_config is not None:
        grants = list(getattr(role_config, "capabilities", []) or [])
        grants += list(getattr(role_config, "permissions", []) or [])
    else:
        grants = list(trusted_context.get("capabilities") or [])
        grants += list(trusted_context.get("permissions") or [])
    return [str(g) for g in grants if g]


def _assert_authorized(intent: Any, allowlist: list[str]) -> None:
    """Fail closed unless the intent's operation is inside trusted authority.

    The intent is untrusted: its ``operation`` is attacker-influenced, so
    membership is decided solely against the trusted allowlist. An empty
    allowlist grants nothing — absence of configuration is not permission.
    """
    operation = str(getattr(intent, "operation", "") or "")

    if not allowlist:
        raise PermissionError(
            f"no authority granted for operation {operation!r}: "
            "principal has an empty capability/permission allowlist"
        )
    if operation not in allowlist:
        raise PermissionError(
            f"operation {operation!r} is not in the principal's allowlist"
        )


def authorize(intent: Any, trusted_context: dict[str, Any]) -> AuthorizedAction:
    """Bind an untrusted intent to trusted identity + permissions.

    Fails CLOSED: raises :class:`PermissionError` when the requested
    operation or capability is outside the principal's allowlist, and when
    the principal holds no authority at all. Authority is derived only from
    trusted server state — never from the intent body, so a prompt-injected
    ``requested_parameters`` payload cannot widen scope.

    Args:
        intent: Validated :class:`ActionIntent` (prompt output).
        trusted_context: Server-owned state with ``tenant_id``,
            ``mission_id``, ``employee_id``, ``actor_identity`` and
            optional ``permissions``, ``capabilities``,
            ``business_scope``, ``role_config``.

    Raises:
        KeyError: trusted identity is incomplete.
        PermissionError: the intent is outside the principal's authority.
    """
    role_config = trusted_context.get("role_config")
    allowlist = _resolve_allowlist(trusted_context, role_config)
    _assert_authorized(intent, allowlist)

    permissions = list(allowlist)
    risk_tier = classify(intent, role_config)
    tenant_id = _require(trusted_context, "tenant_id")
    mission_id = _require(trusted_context, "mission_id")
    scope = str(trusted_context.get("business_scope") or "")
    key = build_idempotency_key(
        tenant_id, mission_id, intent.operation, intent.target_reference, scope
    )
    return AuthorizedAction.from_intent(
        intent,
        tenant_id=tenant_id,
        mission_id=mission_id,
        employee_id=_require(trusted_context, "employee_id"),
        actor_identity=_require(trusted_context, "actor_identity"),
        permissions=permissions,
        expected_version=trusted_context.get("expected_version"),
        policy_decision="permit",
        risk_tier=risk_tier,  # type: ignore[arg-type]
        idempotency_key=key,
        action_id=f"act-{abs(hash(key)) % 10**12:012d}",
    )
