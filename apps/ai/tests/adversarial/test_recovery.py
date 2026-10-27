"""C3 recovery — crash before/after execution (Sprint C).

RED-first against current ``submit_intent`` semantics:
- Crash BEFORE execution (executor raises mid-flight): no audit ``permit``,
  idempotency key UNMARKED (retry allowed), retry succeeds exactly once.
- Crash AFTER side effect but BEFORE reconcile: compose existing
  ``verify_write`` + ``audit.append_event`` as the recovery procedure (NO new
  recovery framework) over a pre-seeded store; assert verified + single
  write + audited reconcile event, no duplicate mutation.

Mock conventions: monkeypatched ``capability_ops._resolve_capability`` +
``_ops.clear()``, ``ingress._seen`` + ``AUDIT_LOG`` reset per test,
SkillRegistry snapshot/restore, ``asyncio_mode=auto``.
"""
from __future__ import annotations

import pytest

from src.control_plane import audit as audit_mod
from src.control_plane import ingress as ingress_mod
from src.control_plane.contracts import ActionIntent
from src.mission import capability_ops
from src.mission import verify as verify_mod
from src.mission.blocker_investigation_mission import (
    make_blocker_investigation_role,
    reset_idempotency,
)
from src.mission.skill_registry import SkillRegistry


class MockCap:
    def __init__(self) -> None:
        self.store = {"PROJ-1": {"key": "PROJ-1", "status": "Blocked"}}
        self.update_calls: list[tuple[str, dict]] = []

    def update_issue(self, issue_id, fields):
        self.update_calls.append((issue_id, dict(fields)))
        self.store[issue_id] = {**self.store.get(issue_id, {}), **fields}
        return {"id": issue_id, **self.store[issue_id]}

    def get_issues(self, **kwargs):
        jql = str(kwargs.get("jql", ""))
        key = jql.split("=")[-1].strip() if "=" in jql else ""
        rec = self.store.get(key)
        return [dict(rec)] if rec else []


@pytest.fixture(autouse=True)
def _clean():
    reset_idempotency()
    snapshot = dict(SkillRegistry._skills)
    yield
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)
    reset_idempotency()


@pytest.fixture
def mock_cap(monkeypatch):
    cap = MockCap()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()
    return cap


def _intent() -> ActionIntent:
    return ActionIntent(
        capability="jira",
        operation="jira.update",
        target_reference="PROJ-1",
        requested_parameters={"issue_id": "PROJ-1", "fields": {"status": "In Progress"}, "risk_tier": "LOW"},
        reason="recovery probe",
        evidence_ids=["ev-1"],
        expected_outcome="PROJ-1 moves to In Progress",
        confidence=0.9,
        requested_by="onboarding-ops",
    )


def _trusted(**over):
    base = {
        "tenant_id": "t1",
        "mission_id": "m-c3",
        "employee_id": "onboarding-ops",
        "actor_identity": "system",
        "business_scope": "acme",
    }
    base.update(over)
    return base


async def test_crash_before_execution_unmarked_retry_succeeds_once(mock_cap, monkeypatch):
    """Executor raises mid-flight → no permit, key unmarked, retry wins once."""
    role = make_blocker_investigation_role()
    calls = {"n": 0}
    real_execute = capability_ops.CapabilityOpRegistry.execute

    def flaky(name, params, tenant_id, *, role_caps=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash before reconcile")
        return real_execute(name, params, tenant_id, role_caps=role_caps)

    monkeypatch.setattr(capability_ops.CapabilityOpRegistry, "execute", flaky)
    with pytest.raises(RuntimeError, match="crash before reconcile"):
        await ingress_mod.submit_intent(
            _intent(), _trusted(), role_config=role,
            capabilities=capability_ops.CapabilityOpRegistry,
        )
    assert mock_cap.update_calls == []
    assert not any(e["decision"] == "permit:executed" for e in audit_mod.list_events())
    # Key must be UNMARKED — the crash happened before execution completed.
    assert len(ingress_mod._seen._seen) == 0
    # Retry succeeds exactly once.
    event = await ingress_mod.submit_intent(
        _intent(), _trusted(), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "permit:executed"
    assert mock_cap.update_calls == [("PROJ-1", {"status": "In Progress"})]
    assert len([e for e in audit_mod.list_events() if e["decision"] == "permit:executed"]) == 1


async def test_crash_after_side_effect_recovery_reconciles_no_duplicate(mock_cap):
    """Write landed but reconcile crashed: verify + audited reconcile, no rewrite."""
    # Pre-seed the store AS IF the crashed write had landed (no update call yet).
    mock_cap.store["PROJ-1"] = {"key": "PROJ-1", "status": "In Progress"}
    params = {"issue_id": "PROJ-1", "fields": {"status": "In Progress"}}
    # Recovery procedure = existing verify_write + audited reconcile event.
    outcome = await verify_mod.verify_write(
        "jira.update", params, {"status": "In Progress"}, "t1",
        capabilities=capability_ops.CapabilityOpRegistry,
        role_caps=["jira.update", "jira.read"],
    )
    assert outcome.verified is True
    event = audit_mod.append_event(
        mission_id="m-c3", action_id="act-recovery-1", intent=_intent(),
        decision="permit:executed",
        result={"reconciled": True, "verified": True},
        verified=True,
    )
    assert event["decision"] == "permit:executed"
    assert event["verified"] is True
    # No duplicate mutation: recovery only READ, never re-wrote.
    assert mock_cap.update_calls == []
    assert mock_cap.store["PROJ-1"]["status"] == "In Progress"
    assert any(e["decision"] == "permit:executed" and e["verified"] for e in audit_mod.list_events())
