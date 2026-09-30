"""P0 RED: control-plane submission must report honestly.

Vulnerability
-------------
``submit_to_control_plane`` swallowed every exception and then returned
``{"submitted": True}`` unconditionally::

    try:
        result = await _submit_intent(intent, trusted_context)
    except Exception as exc:
        result = {"decision": "error", "error": str(exc)}
    return {..., "submitted": True}

A denied, blocked, duplicate, unauthorized or crashed submission was
therefore indistinguishable from an executed one. Any metric, alert or
workflow branch reading ``submitted`` was reporting success for actions
that never happened.

Required behaviour
------------------
* ``submitted`` is True ONLY when the control plane accepted the intent
* a rejection surfaces as ``accepted=False`` plus the real decision
* an exception propagates (or is reported as an error) — never as success
* a real execution still reports ``submitted=True``
"""

from __future__ import annotations

import pytest

from src.activities import incident_activities as act

VALID_TICKET_PARAMS = {"vendor_id": "vendor-acme-001", "incident_id": "INC-1"}


def _intent(**overrides) -> dict:
    """Return the dict wire format Temporal delivers to an activity."""
    payload = {
        "capability": "vendor",
        "operation": "vendor_ticket.create",
        "target_reference": "vendor-acme-001",
        "requested_parameters": dict(VALID_TICKET_PARAMS),
        "reason": "vendor incident escalation",
        "evidence_ids": ["ev-1"],
        "expected_outcome": "ticket created",
        "confidence": 0.9,
        "requested_by": "untrusted-planner",
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _isolate():
    from src.control_plane.idempotency import reset_seen

    reset_seen()
    yield
    reset_seen()


# ---------------------------------------------------------------------------
# 1. A rejection must not be reported as submitted
# ---------------------------------------------------------------------------


class TestRejectionIsNotSuccess:
    async def test_unauthorized_intent_is_not_submitted(self) -> None:
        """An operation outside the allowlist must not report submitted."""
        out = await act.submit_to_control_plane(
            _intent(operation="slack.send", requested_parameters={}, capability="slack"),
            {
                "tenant_id": "t1",
                "mission_id": "m-1",
                "employee_id": "emp-1",
                "actor_identity": "system",
                "permissions": ["vendor_ticket.create"],
            },
        )

        assert out["submitted"] is False, (
            "unauthorized intent was reported as submitted"
        )
        assert out["accepted"] is False
        assert out["control_plane_result"]["decision"].startswith("deny")

    async def test_duplicate_intent_is_not_submitted(self) -> None:
        """A second identical submission is a rejection, not a success."""
        trusted = {
            "tenant_id": "t1",
            "mission_id": "m-dup",
            "employee_id": "emp-1",
            "actor_identity": "system",
            "permissions": ["vendor_ticket.create"],
        }
        first = await act.submit_to_control_plane(_intent(), trusted)
        assert first["submitted"] is True

        second = await act.submit_to_control_plane(_intent(), trusted)

        assert second["submitted"] is False, (
            "duplicate submission was reported as submitted"
        )
        assert second["control_plane_result"]["decision"] == "deny:duplicate"

    async def test_blocked_intent_is_not_submitted(self) -> None:
        """A CRITICAL-tier principal is blocked and must not report success.

        The role travels inside trusted_context, which is how the control
        plane reads it, so this exercises the genuine CRITICAL block rather
        than an incidental authorization denial.
        """
        from src.mission.blocker_investigation_mission import (
            make_blocker_investigation_role,
        )

        role = make_blocker_investigation_role(risk_threshold="CRITICAL")
        out = await act.submit_to_control_plane(
            _intent(
                capability="jira",
                operation="jira.update",
                requested_parameters={"issue_id": "P-1", "fields": {}},
            ),
            {
                "tenant_id": "t1",
                "mission_id": "m-crit",
                "employee_id": "onboarding-ops",
                "actor_identity": "system",
                "role_config": role,
            },
        )

        assert out["submitted"] is False, "blocked intent was reported as submitted"
        assert out["control_plane_result"]["decision"] == "deny:blocked"


# ---------------------------------------------------------------------------
# 2. Exceptions must never become success
# ---------------------------------------------------------------------------


class TestExceptionsAreNotSwallowed:
    async def test_control_plane_crash_is_not_reported_as_success(
        self, monkeypatch
    ) -> None:
        """If the control plane raises, the activity must not say submitted."""

        async def _boom(*_a, **_k):
            raise RuntimeError("control plane exploded")

        monkeypatch.setattr(act, "_submit_intent", _boom)

        with pytest.raises(RuntimeError):
            await act.submit_to_control_plane(
                _intent(),
                {
                    "tenant_id": "t1",
                    "mission_id": "m-1",
                    "employee_id": "emp-1",
                    "actor_identity": "system",
                    "permissions": ["vendor_ticket.create"],
                },
            )


# ---------------------------------------------------------------------------
# 3. Genuine execution still reports success
# ---------------------------------------------------------------------------


class TestGenuineExecutionStillReportsSuccess:
    async def test_authorized_execution_reports_submitted(self) -> None:
        out = await act.submit_to_control_plane(
            _intent(),
            {
                "tenant_id": "t1",
                "mission_id": "m-ok",
                "employee_id": "emp-1",
                "actor_identity": "system",
                "permissions": ["vendor_ticket.create"],
            },
        )

        assert out["submitted"] is True
        assert out["accepted"] is True
        assert out["control_plane_result"]["decision"] == "permit:executed"


# ---------------------------------------------------------------------------
# 4. The workflow must act on the rejection (no execution after a deny)
# ---------------------------------------------------------------------------


class TestWorkflowRespectsRejection:
    def test_workflow_gates_execution_on_acceptance(self) -> None:
        """A denied submission must not reach execute_capability.

        The honest result is only useful if the orchestrator branches on it.
        This asserts the workflow source contains the acceptance gate, since
        executing the workflow in-process would require a Temporal worker.
        """
        import inspect

        from src.workflows import incident_workflow

        source = inspect.getsource(incident_workflow.IncidentWorkflow.run)

        assert "accepted" in source, (
            "workflow never inspects the control-plane acceptance flag"
        )
        gate = source.index("accepted")
        execute = source.index('"execute_capability"')
        assert gate < execute, (
            "execute_capability must be gated behind the acceptance check"
        )
