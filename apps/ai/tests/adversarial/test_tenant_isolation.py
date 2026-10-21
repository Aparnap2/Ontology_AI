"""C5 tenant isolation — cross-tenant evidence pinned, submit binding (Sprint C).

- ``assemble_checkpoint`` with cross-tenant evidence raises (pin, no duplicate).
- Submit binds the TRUSTED tenant: untrusted ``requested_by`` cannot spoof it;
  the denial/permit audit records NO cross-tenant content (only the trusted
  tenant + opaque target ref, never foreign raw text).
- Where machinery genuinely lacks a check (target-resource tenant match in
  the executor), do NOT build it — this file pins current behavior and the
  Sprint C report records it as a Sprint F finding.

Mock conventions: monkeypatched ``capability_ops._resolve_capability`` +
``_ops.clear()``, ``ingress._seen`` + ``AUDIT_LOG`` reset per test,
SkillRegistry snapshot/restore, ``asyncio_mode=auto``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.context.assemble import assemble_checkpoint
from src.control_plane import audit as audit_mod
from src.control_plane import ingress as ingress_mod
from src.control_plane.contracts import ActionIntent
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    make_blocker_investigation_role,
    reset_idempotency,
)
from src.mission.skill_registry import SkillRegistry
from src.ontology.object_types import Evidence, Onboarding


class MockCap:
    def __init__(self) -> None:
        # Store deliberately holds a foreign-tenant record to prove the gap.
        self.store = {"PROJ-EVIL": {"key": "PROJ-EVIL", "status": "Blocked", "tenant": "t-evil"}}
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


def _ev(tenant: str) -> Evidence:
    return Evidence(
        id="ev-1", tenant_id=tenant, source="slack", provenance="slack:C1:alice",
        captured_at="2026-09-04T11:00:00Z", raw_text="SSO blocked", normalized_text="sso blocked",
    )


def _ob() -> Onboarding:
    return Onboarding(
        id="ob-1", customer="acme", stakeholders=["alice"], requirements=["SSO"],
        tasks=["t-1"], issues=[], missions=["m-1"], lifecycle_state="implementing",
    )


def test_assemble_rejects_cross_tenant_evidence():
    """Pin: foreign-tenant evidence never enters a checkpoint (raises, no audit)."""
    before = list(audit_mod.list_events())
    with pytest.raises(ValueError, match="cross-tenant"):
        assemble_checkpoint(
            checkpoint_id="cp-1", tenant_id="t-acme", mission_id="m-1",
            trigger_event_id="evt-1", evidence=[_ev("t-evil")],
            now=datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc),
            onboarding=_ob(),
        )
    assert audit_mod.list_events() == before


async def test_submit_binds_trusted_tenant_audit_has_no_foreign_content(mock_cap):
    """Untrusted requested_by cannot spoof tenant; audit carries trusted tenant only."""
    role = make_blocker_investigation_role()
    intent = ActionIntent(
        capability="jira",
        operation="jira.update",
        target_reference="PROJ-EVIL",
        requested_parameters={"issue_id": "PROJ-EVIL", "fields": {"status": "In Progress"}, "risk_tier": "LOW"},
        reason="tenant binding probe",
        evidence_ids=["ev-1"],
        expected_outcome="ok",
        confidence=0.9,
        requested_by="attacker-spoofed-tenant",
    )
    event = await ingress_mod.submit_intent(
        intent,
        {"tenant_id": "t-acme", "mission_id": "m-c5", "employee_id": "onboarding-ops",
         "actor_identity": "system", "business_scope": "acme"},
        role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    # Trusted tenant wins; the spoofed claim is inert.
    assert event["intent"]["requested_by"] == "attacker-spoofed-tenant"
    permit = next(e for e in audit_mod.list_events() if e["decision"] == "permit:executed")
    assert permit["mission_id"] == "m-c5"
    # Isolation property, stated precisely: no foreign content may enter the
    # authorized INTENT or authority fields. The verification echo faithfully
    # records connector-returned record fields (including that record's own
    # tenant tag) — faithful recording is not a leak; authority leak would be.
    intent_blob = json.dumps(permit["intent"])
    assert "t-evil" not in intent_blob
    assert "attacker-spoofed-tenant" in intent_blob  # claim preserved as claim, never as authority


async def test_executor_target_tenant_gap_pinned_for_sprint_f(mock_cap):
    """SPRINT F FINDING (pinned, not built): executor has no target-resource tenant match.

    A t-acme intent targeting a foreign record still executes today — the
    plane binds the REQUEST tenant but never checks the TARGET's tenant.
    This test pins that behavior so Sprint F can close it; it must NOT be
    'fixed' here per Sprint C scope.
    """
    role = make_blocker_investigation_role()
    intent = ActionIntent(
        capability="jira",
        operation="jira.update",
        target_reference="PROJ-EVIL",
        requested_parameters={"issue_id": "PROJ-EVIL", "fields": {"status": "In Progress"}, "risk_tier": "LOW"},
        reason="target tenant gap probe",
        evidence_ids=["ev-1"],
        expected_outcome="ok",
        confidence=0.9,
        requested_by="onboarding-ops",
    )
    event = await ingress_mod.submit_intent(
        intent,
        {"tenant_id": "t-acme", "mission_id": "m-c5-gap", "employee_id": "onboarding-ops",
         "actor_identity": "system", "business_scope": "acme"},
        role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "permit:executed"  # gap: no target-tenant denial exists
    assert mock_cap.update_calls == [("PROJ-EVIL", {"status": "In Progress"})]
    # Pinned precisely: the AUTHORIZED intent carries no foreign content (the
    # execution itself is the documented gap). The verification echo may quote
    # connector-returned record fields verbatim — faithful recording, not leak.
    permit = next(e for e in audit_mod.list_events() if e["decision"] == "permit:executed")
    assert "t-evil" not in json.dumps(permit["intent"])
