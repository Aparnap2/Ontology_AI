"""C6 concurrency — optimistic version gate (Sprint C).

RED-first: fails until ``src/control_plane/concurrency.py`` (``VersionStore``
with ``check_and_advance``, in-memory) is called from ingress ONLY when
``authorized.expected_version is not None`` (default None → zero behavior
change). Mismatch → audited ``deny:stale_version``, no execution, no blind
overwrite; refresh + resubmit proceeds.

Flow under test: A-reads-v10 / B-reads-v10 / A-writes-v11 / B-rejected.

Mock conventions: monkeypatched ``capability_ops._resolve_capability`` +
``_ops.clear()``, ``ingress._seen`` + ``AUDIT_LOG`` reset per test,
SkillRegistry snapshot/restore, ``asyncio_mode=auto``.
"""
from __future__ import annotations

import pytest

from src.control_plane import audit as audit_mod
from src.control_plane import ingress as ingress_mod
from src.control_plane.concurrency import get_store, reset_store
from src.control_plane.contracts import ActionIntent
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    make_blocker_investigation_role,
    reset_idempotency,
)
from src.mission.skill_registry import SkillRegistry


class MockCap:
    def __init__(self) -> None:
        self.store = {
            "PROJ-1": {"key": "PROJ-1", "status": "Blocked"},
            "PROJ-2": {"key": "PROJ-2", "status": "Blocked"},
        }
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
    reset_store()
    snapshot = dict(SkillRegistry._skills)
    yield
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)
    reset_idempotency()
    reset_store()


@pytest.fixture
def mock_cap(monkeypatch):
    cap = MockCap()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()
    return cap


def _intent(target: str) -> ActionIntent:
    return ActionIntent(
        capability="jira",
        operation="jira.update",
        target_reference=target,
        requested_parameters={"issue_id": target, "fields": {"status": "In Progress"}, "risk_tier": "LOW"},
        reason="concurrency probe",
        evidence_ids=["ev-1"],
        expected_outcome=f"{target} moves to In Progress",
        confidence=0.9,
        requested_by="onboarding-ops",
    )


def _trusted(mission: str = "m-c6", **over):
    base = {
        "tenant_id": "t1",
        "mission_id": mission,
        "employee_id": "onboarding-ops",
        "actor_identity": "system",
        "business_scope": "acme",
    }
    base.update(over)
    return base


async def test_no_expected_version_zero_behavior_change(mock_cap):
    """Default (no expected_version) → permit, no version interaction."""
    role = make_blocker_investigation_role()
    event = await ingress_mod.submit_intent(
        _intent("PROJ-1"), _trusted(), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "permit:executed"
    assert mock_cap.update_calls == [("PROJ-1", {"status": "In Progress"})]


async def test_concurrent_write_loser_rejected_no_overwrite(mock_cap):
    """A-reads-v10 / B-reads-v10 / A-writes-v11 / B-rejected; no blind overwrite."""
    role = make_blocker_investigation_role()
    get_store().seed("t1:m-c6", 10)
    first = await ingress_mod.submit_intent(
        _intent("PROJ-1"), _trusted(expected_version=10), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert first["decision"] == "permit:executed"
    assert get_store().current("t1:m-c6") == 11
    second = await ingress_mod.submit_intent(
        _intent("PROJ-2"), _trusted(expected_version=10), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert second["decision"] == "deny:stale_version"
    assert mock_cap.update_calls == [("PROJ-1", {"status": "In Progress"})]
    assert mock_cap.store["PROJ-2"]["status"] == "Blocked"
    assert any(e["decision"] == "deny:stale_version" for e in audit_mod.list_events())


async def test_refresh_resubmit_proceeds(mock_cap):
    """B refreshes to v11 and resubmits → permit:executed exactly once more."""
    role = make_blocker_investigation_role()
    get_store().seed("t1:m-c6", 10)
    first = await ingress_mod.submit_intent(
        _intent("PROJ-1"), _trusted(expected_version=10), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert first["decision"] == "permit:executed"
    stale = await ingress_mod.submit_intent(
        _intent("PROJ-2"), _trusted(expected_version=10), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert stale["decision"] == "deny:stale_version"
    refreshed = await ingress_mod.submit_intent(
        _intent("PROJ-2"), _trusted(expected_version=11), role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert refreshed["decision"] == "permit:executed"
    assert mock_cap.update_calls == [
        ("PROJ-1", {"status": "In Progress"}),
        ("PROJ-2", {"status": "In Progress"}),
    ]
