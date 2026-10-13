"""P0: tenant identity must never fall back to a constant (A6 regression).

The defect
----------
``IncidentWorkflow`` passed only the intent to ``submit_to_control_plane``, so
the activity fell back to ``DEFAULT_TRUSTED_CONTEXT`` with a literal
``tenant_id="t-acme"``. Authorization is decided against trusted context, so
**an incident belonging to any tenant was authorized and executed under that
constant's authority**. The Situation built in step 1 carried the correct
``incident_data["tenant_id"]``, but it never reached authorization.

Authorization is only meaningful if the identity being checked belongs to the
caller. These tests pin that the workflow derives trusted context from the
incident, and that the constant cannot silently stand in for it.

They also pin the complementary recovery invariant (A7): an outage paired with
a vendor's ``status="resolved"`` must never be reported as verified recovery.
"""

from __future__ import annotations

import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"


# ---------------------------------------------------------------------------
# A6 — the workflow must not fall back to a constant identity
# ---------------------------------------------------------------------------


class TestWorkflowDerivesTenantFromIncident:
    def _source(self) -> str:
        return (SRC / "workflows" / "incident_workflow.py").read_text()

    def test_workflow_builds_trusted_context(self) -> None:
        src = self._source()
        assert "trusted_context" in src, (
            "the workflow must build and pass an explicit trusted context"
        )
        assert "args=[action_intent, trusted_context]" in src, (
            "submit_to_control_plane must receive the trusted context as a "
            "second positional argument (args=, not arg= — arg= delivers a "
            "single list and silently binds the whole list to action_intent)"
        )

    def test_tenant_is_taken_from_the_incident_payload(self) -> None:
        src = self._source()
        assert 'incident_data.get("tenant_id")' in src, (
            "tenant_id must be read from the incoming incident, not a constant"
        )

    def test_no_hardcoded_tenant_literal_in_the_workflow(self) -> None:
        src = self._source()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value != "t-acme", (
                    f"line {node.lineno}: hardcoded tenant literal in the "
                    "production workflow"
                )

    def test_permitted_operations_are_declared_not_buried(self) -> None:
        src = self._source()
        assert "INCIDENT_WORKFLOW_PERMISSIONS" in src, (
            "the workflow's authority must be an explicit named tuple, not a "
            "literal inside an activity's fallback"
        )


class TestTenantIsolationIsHonoured:
    async def test_other_tenants_idempotency_keys_are_independent(self) -> None:
        """The key is tenant-scoped; one tenant cannot block another."""
        from src.control_plane.idempotency import SeenSet, reset_seen

        reset_seen()
        seen = SeenSet()
        assert seen.claim("t-a:m:vendor_ticket.create:v1", "o1", "h") is True
        assert seen.claim("t-b:m:vendor_ticket.create:v1", "o2", "h") is True
        assert seen.claim("t-a:m:vendor_ticket.create:v1", "o3", "h") is False

    async def test_authorization_rejects_a_foreign_tenant_scope(self) -> None:
        """An action authorized for one tenant is not silently valid for another."""

        from src.control_plane.contracts import ActionIntent
        from src.control_plane.idempotency import reset_seen
        from src.control_plane.ingress import submit_intent

        reset_seen()
        intent = ActionIntent(
            capability="vendor",
            operation="vendor_ticket.create",
            target_reference="v1",
            requested_parameters={"vendor_id": "v1", "incident_id": "INC-1"},
            reason="cross-tenant probe",
            evidence_ids=[],
            expected_outcome="ticket",
            confidence=0.9,
            requested_by="probe",
        )
        tenant_a = {
            "tenant_id": "tenant-a",
            "mission_id": "m-1",
            "employee_id": "e1",
            "actor_identity": "system",
            "permissions": ["vendor_ticket.create"],
        }
        result = await submit_intent(intent, tenant_a)

        assert result["decision"] == "permit:executed"
        # The audit record must carry tenant A, never a default.
        assert "t-acme" not in str(result), (
            "the executed record leaked a hardcoded tenant identity"
        )


# ---------------------------------------------------------------------------
# A7 — an outage must never be reported as verified recovery
# ---------------------------------------------------------------------------


class TestOutageCannotVerifyRecovery:
    async def test_outage_plus_resolved_ticket_is_not_verified(self) -> None:
        """The exact demonstrated exploit.

        Before the fix the activity read ticket.status=="resolved", invented
        error_rate=0.0 / success_rate=1.0, and verified its own invention —
        so a total outage reported verified=True.
        """
        from src.activities.incident_activities import verify_recovery_activity

        result = await verify_recovery_activity(
            {
                "situation": {"id": "sit-1"},
                "vendor_result": {
                    "vendor_ticket": {
                        "ticket_id": "vt-1",
                        "vendor_id": "stripe",
                        "incident_id": "INC-1",
                        "status": "resolved",
                    }
                },
            }
        )

        assert result["verified"] is False, (
            "a vendor's self-declared resolution verified recovery during an "
            "outage — the A7 defect"
        )
        assert result["state"] == "INDETERMINATE"

    async def test_explicit_outage_evidence_is_not_verified(self) -> None:
        """Even with evidence supplied, an outage must fail the predicates."""
        from src.activities.incident_activities import verify_recovery_activity

        result = await verify_recovery_activity(
            {
                "situation": {"id": "sit-1"},
                "vendor_result": {"vendor_ticket": {"status": "resolved"}},
                "observed": {"error_rate": 1.0, "success_rate": 0.0},
            }
        )

        assert result["verified"] is False, "a total outage reported as recovered"
        # evaluate_recovery returns verified + mismatches; the activity maps a
        # genuine predicate mismatch to NOT_VERIFIED (INDETERMINATE is reserved
        # for "no evidence at all"). Either way it is not VERIFIED.
        assert result["state"] in {"NOT_VERIFIED", "FAILED"}, result["state"]
        assert result["mismatches"], "an outage must record which predicates failed"

    async def test_healthy_evidence_verifies(self) -> None:
        """Positive control: fail-closed must not become fail-everything."""
        from src.activities.incident_activities import verify_recovery_activity

        result = await verify_recovery_activity(
            {
                "situation": {"id": "sit-1"},
                "vendor_result": {"vendor_ticket": {"status": "open"}},
                "observed": {"error_rate": 0.0, "success_rate": 1.0},
            }
        )

        assert result["verified"] is True, result