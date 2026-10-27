"""C1 context integrity — stale checkpoint rejection (Sprint C).

RED-first: fails until ``submit_intent`` enforces
``trusted_context["version/current_version"]`` with fail-closed
``deny:stale_context`` (audited, zero connector writes).

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
        reason="stale-context probe",
        evidence_ids=["ev-1"],
        expected_outcome="PROJ-1 moves to In Progress",
        confidence=0.9,
        requested_by="onboarding-ops",
    )


def _trusted(**over):
    base = {
        "tenant_id": "t1",
        "mission_id": "m-c1",
        "employee_id": "onboarding-ops",
        "actor_identity": "system",
        "business_scope": "acme",
    }
    base.update(over)
    return base


async def test_stale_version_cannot_authorize(mock_cap):
    """version=1 vs current_version=2 → fail closed, zero writes."""
    role = make_blocker_investigation_role()
    event = await ingress_mod.submit_intent(
        _intent(),
        _trusted(version=1, current_version=2),
        role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "deny:stale_context"
    assert mock_cap.update_calls == []
    assert "permit:executed" not in [e["decision"] for e in audit_mod.list_events()]


async def test_refresh_matching_versions_proceeds(mock_cap):
    """version == current_version → proceeds to permit:executed."""
    role = make_blocker_investigation_role()
    event = await ingress_mod.submit_intent(
        _intent(),
        _trusted(version=2, current_version=2),
        role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "permit:executed"
    assert mock_cap.update_calls == [("PROJ-1", {"status": "In Progress"})]


async def test_audit_records_stale_denial(mock_cap):
    """Stale denial is audited with checkpoint ids, no permit, no write."""
    role = make_blocker_investigation_role()
    trusted = _trusted(context_checkpoint_id="cp-m-c1", version=1, current_version=2)
    event = await ingress_mod.submit_intent(
        _intent(), trusted, role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "deny:stale_context"
    events = audit_mod.list_events()
    stale = [e for e in events if e["decision"] == "deny:stale_context"]
    assert len(stale) == 1
    assert stale[0]["mission_id"] == "m-c1"
    assert mock_cap.update_calls == []
