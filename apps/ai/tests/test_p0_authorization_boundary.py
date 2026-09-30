"""P0 RED: control-plane authorization boundary must fail CLOSED.

Threat model
------------
``ActionIntent`` is untrusted LLM output. Every field on it — including
``requested_parameters`` — is attacker-influenced. The control plane must
therefore never derive authority or risk from the intent body. Authority
comes only from trusted server state (``trusted_context`` / ``role_config``).

Vulnerabilities pinned down here
--------------------------------
1. ``authorize()`` hardcoded ``policy_decision="permit"`` and never compared
   ``intent.operation`` against the principal's allowed capabilities.
2. An empty/absent permissions list produced an empty allowlist that was then
   never consulted — fail-OPEN.

Test discipline
---------------
Every op used below is a REAL registered capability op (see
``CapabilityOpRegistry``), so a passing denial proves the *authorization
layer* blocked it — not that the op happened to be unknown/broken.

Required behaviour
------------------
* unauthorized operation  -> rejected, executor never invoked
* empty allowlist         -> deny-by-default, not permit-all
* allowlisted operation   -> still permitted (no over-blocking)
"""

from __future__ import annotations

import pytest

from src.control_plane import authorization as authz
from src.control_plane.contracts import ActionIntent
from src.control_plane.idempotency import reset_seen
from src.control_plane.ingress import submit_intent
from src.mission.employee_role_config import EmployeeRoleConfig

VALID_TICKET_PARAMS = {"vendor_id": "vendor-acme-001", "incident_id": "INC-1"}


@pytest.fixture(autouse=True)
def _isolate_idempotency():
    """Process-global SeenSet would otherwise leak keys between tests."""
    reset_seen()
    yield
    reset_seen()


def _intent(
    operation: str = "vendor_ticket.create",
    parameters: dict | None = None,
    capability: str = "vendor",
) -> ActionIntent:
    return ActionIntent(
        capability=capability,
        operation=operation,
        target_reference="vendor-acme-001",
        requested_parameters=VALID_TICKET_PARAMS if parameters is None else parameters,
        reason="vendor incident escalation",
        evidence_ids=["ev-1"],
        expected_outcome="ticket created",
        confidence=0.9,
        requested_by="untrusted-planner",
    )


def _trusted(**overrides) -> dict:
    ctx = {
        "tenant_id": "t-acme",
        "mission_id": "m-1",
        "employee_id": "emp-1",
        "actor_identity": "svc-control-plane",
        "permissions": ["vendor_ticket.create"],
        "business_scope": "payments",
    }
    ctx.update(overrides)
    return ctx


# ---------------------------------------------------------------------------
# 1. Operation outside the principal's allowlist must be rejected
# ---------------------------------------------------------------------------


class TestUnauthorizedOperationRejected:
    async def test_operation_outside_allowlist_is_denied(self) -> None:
        """`slack.send` is a real op but NOT in permissions -> must not execute."""
        intent = _intent(operation="slack.send", parameters={}, capability="slack")

        result = await submit_intent(intent, _trusted())

        assert result["decision"].startswith("deny"), (
            f"expected deny for unauthorized op, got {result['decision']!r}"
        )
        assert result["verified"] is False

    async def test_unauthorized_op_does_not_reach_executor(self, monkeypatch) -> None:
        """The executor must never be invoked for an unauthorized op."""
        import src.control_plane.ingress as ingress_mod

        calls: list[object] = []
        monkeypatch.setattr(
            ingress_mod, "_execute", lambda *a, **k: calls.append(a) or {"ok": True}
        )

        intent = _intent(operation="slack.send", parameters={}, capability="slack")
        result = await submit_intent(intent, _trusted())

        assert result["decision"].startswith("deny")
        assert calls == [], "executor was invoked for an unauthorized operation"

    async def test_capability_allowlist_also_enforced(self) -> None:
        """Role capability allowlist is a second, independent boundary."""
        role = EmployeeRoleConfig(
            role_id="r1",
            role="it_ops",
            capabilities=["vendor_ticket.create"],
            permissions=["vendor_ticket.create"],
        )
        intent = _intent(operation="jira.create", parameters={}, capability="jira")

        result = await submit_intent(
            intent, _trusted(permissions=[]), role_config=role
        )

        assert result["decision"].startswith("deny"), (
            f"expected deny for op outside capability allowlist, got {result['decision']!r}"
        )


# ---------------------------------------------------------------------------
# 2. Empty / absent allowlist must deny-by-default (fail CLOSED)
# ---------------------------------------------------------------------------


class TestEmptyAllowlistFailsClosed:
    async def test_absent_permissions_rejects(self) -> None:
        """No permissions in trusted state -> reject, not permit."""
        ctx = _trusted()
        ctx.pop("permissions")

        result = await submit_intent(_intent(), ctx)

        assert result["decision"].startswith("deny"), (
            f"absent permissions must fail closed, got {result['decision']!r}"
        )

    async def test_empty_permissions_rejects(self) -> None:
        result = await submit_intent(_intent(), _trusted(permissions=[]))

        assert result["decision"].startswith("deny"), (
            f"empty allowlist must fail closed, got {result['decision']!r}"
        )

    def test_authorize_raises_on_unauthorized(self) -> None:
        """`authorize` itself must refuse, not return a permit decision."""
        intent = _intent(operation="slack.send", parameters={}, capability="slack")
        with pytest.raises(PermissionError):
            authz.authorize(intent, _trusted())

    def test_authorize_raises_when_no_allowlist(self) -> None:
        with pytest.raises(PermissionError):
            authz.authorize(_intent(), _trusted(permissions=[]))


# ---------------------------------------------------------------------------
# 3. Allowlisted operation still works (no over-blocking)
# ---------------------------------------------------------------------------


class TestAuthorizedOperationStillPermits:
    async def test_allowlisted_op_is_permitted(self) -> None:
        result = await submit_intent(_intent(), _trusted())

        assert result["decision"] == "permit:executed", (
            f"allowlisted op must still execute, got {result['decision']!r}"
        )

    def test_authorize_returns_permit_for_allowlisted(self) -> None:
        action = authz.authorize(_intent(), _trusted())

        assert action.policy_decision == "permit"
        assert action.tenant_id == "t-acme"
        assert action.operation == "vendor_ticket.create"
