"""Owner resolution A–K matrix — deterministic service, no network.

Pure resolver tests (A–J) run with zero mocks. The hero contract (K)
composes a RESOLVED owner into an ``ActionIntent`` submitted through the
Control Plane with the established mock conventions (monkeypatched
``_resolve_capability``, cleared op registry, ``_seen``/``AUDIT_LOG``
reset) — the investigate skill and runner are never modified.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.control_plane import audit as audit_mod
from src.control_plane import ingress as ingress_mod
from src.control_plane.contracts import ActionIntent
from src.control_plane.ingress import submit_intent
from src.mission import capability_ops
from src.mission.capability_ops import CapabilityOpRegistry
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.owner_resolution import (
    OrganizationConfig,
    OwnerQuery,
    OwnerResolution,
    load_organization_config,
    resolve_owner,
)

CONFIG_PATH = str(Path(__file__).resolve().parents[2] / "config" / "organization.yaml")


def _org() -> OrganizationConfig:
    return load_organization_config(CONFIG_PATH)


def _q(**over) -> OwnerQuery:
    base: dict = {"tenant_id": "acme", "evidence_refs": ["ev-1"]}
    base.update(over)
    return OwnerQuery(**base)


class MockCap:
    """In-memory Jira stand-in (update + read-back pair, slice convention)."""

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


@pytest.fixture
def mock_cap(monkeypatch):
    cap = MockCap()
    monkeypatch.setattr(
        capability_ops, "_resolve_capability", lambda name, config: cap
    )
    CapabilityOpRegistry._ops.clear()
    ingress_mod._seen.clear()
    audit_mod.AUDIT_LOG.clear()
    yield cap
    CapabilityOpRegistry._ops.clear()
    ingress_mod._seen.clear()
    audit_mod.AUDIT_LOG.clear()


def test_a_object_owner_chosen():
    res = resolve_owner(_q(object_owner_ids=["priya"]), _org())
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "OBJECT_OWNER")
    assert res.escalation_required is False
    assert res.resolution_path[0].startswith("L1:OBJECT_OWNER")


def test_b_fallback_to_process_owner():
    res = resolve_owner(_q(process_id="sso-setup"), _org())
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "PROCESS_OWNER")
    assert any("L1:OBJECT_OWNER skipped" in step for step in res.resolution_path)


def test_c_fallback_to_role_mapping():
    res = resolve_owner(_q(role="sso-oncall"), _org())
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "ROLE_MAPPING")


def test_d_same_level_multiples_ambiguous():
    res = resolve_owner(_q(object_owner_ids=["priya", "alice"]), _org())
    assert res.status == "AMBIGUOUS"
    assert res.owner_id is None
    assert res.source == "OBJECT_OWNER"
    assert sorted(res.candidate_ids) == ["alice", "priya"]
    assert res.escalation_required is True


def test_e_inactive_skipped_precedence_continues():
    res = resolve_owner(
        _q(object_owner_ids=["bob"], process_id="sso-setup"), _org()
    )
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "PROCESS_OWNER")
    assert any("bob(inactive)" in step for step in res.resolution_path)


def test_f_foreign_tenant_rejected():
    org = _org()
    # Rejected + precedence continues to the process owner.
    res = resolve_owner(
        _q(object_owner_ids=["mallory"], process_id="sso-setup"), org
    )
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "PROCESS_OWNER")
    assert any("mallory(foreign-tenant" in step for step in res.resolution_path)
    # Rejected with nothing safe anywhere -> INVALID_OWNER, never invented.
    # (Escalation owner cleared: with L5 configured this would RESOLVE/fiona,
    # which is the escalation path, not the INVALID_OWNER terminal.)
    alone = resolve_owner(
        _q(object_owner_ids=["mallory"]),
        org.model_copy(update={"escalation_owner": None}),
    )
    assert alone.status == "INVALID_OWNER"
    assert alone.owner_id is None
    assert alone.escalation_required is True


def test_g_nothing_anywhere_unresolved_or_escalation():
    # Escalation owner cleared so the test probes the UNRESOLVED terminal;
    # the configured-escalation path is covered by the escalation tests.
    res = resolve_owner(
        _q(), _org().model_copy(update={"escalation_owner": None})
    )
    assert res.status in {"UNRESOLVED", "ESCALATION_REQUIRED"}
    assert res.status == "UNRESOLVED"
    assert res.owner_id is None
    assert res.escalation_required is True


def test_h_cross_level_conflict_precedence_wins_never_arbitrary():
    res = resolve_owner(
        _q(object_owner_ids=["priya"], process_owner_ids=["alice"]), _org()
    )
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "OBJECT_OWNER")


def test_i_agent_recommendation_only_post_deterministic_failure():
    # Escalation owner cleared so L6 is reachable; otherwise L5 resolves first.
    res = resolve_owner(
        _q(agent_recommended_id="alice"),
        _org().model_copy(update={"escalation_owner": None}),
    )
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("alice", "AGENT_RECOMMENDATION")
    levels = [step.split(" ")[0] for step in res.resolution_path]
    assert levels.index("L6:AGENT_RECOMMENDATION") > levels.index("L1:OBJECT_OWNER")


def test_j_recommendation_vs_deterministic_deterministic_wins():
    org = _org()
    res = resolve_owner(
        _q(object_owner_ids=["priya"], agent_recommended_id="alice"), org
    )
    assert res.status == "RESOLVED"
    assert (res.owner_id, res.source) == ("priya", "OBJECT_OWNER")
    assert "overridden" in res.resolution_path[-1]
    # Explicit HITL policy flips the conflict to ESCALATION_REQUIRED.
    hitl = resolve_owner(
        _q(
            object_owner_ids=["priya"],
            agent_recommended_id="alice",
            hitl_on_agent_conflict=True,
        ),
        org,
    )
    assert hitl.status == "ESCALATION_REQUIRED"
    assert sorted(hitl.candidate_ids) == ["alice", "priya"]
    assert hitl.escalation_required is True


async def test_k_hero_blocker_resolution_feeds_action_intent(mock_cap):
    """Blocker -> resolution -> resolved owner feeds ActionIntent params."""
    res = resolve_owner(
        _q(
            object_owner_ids=["priya"],
            evidence_refs=["ev-slack-onboarding-10:23"],
        ),
        _org(),
    )
    assert isinstance(res, OwnerResolution)
    assert res.status == "RESOLVED" and res.owner_id == "priya"

    intent = ActionIntent(
        capability="jira",
        operation="jira.update",
        target_reference="PROJ-1",
        requested_parameters={
            "issue_id": "PROJ-1",
            "fields": {"status": "In Progress", "assignee": res.owner_id},
            "risk_tier": "MEDIUM",
        },
        reason=f"Blocker owner {res.owner_id} assigned ({res.source})",
        evidence_ids=["ev-slack-onboarding-10:23"],
        expected_outcome="PROJ-1 moves to In Progress owned by priya",
        confidence=res.confidence,
        requested_by="owner-resolution",
    )
    role = EmployeeRoleConfig(
        role_id="onboarding-ops",
        role="Onboarding Operations Analyst",
        goals=["keep implementation moving toward first value"],
        skills=[],
        capabilities=["jira.update", "jira.read"],
        permissions=["read"],
        policies=[],
        authority={},
        risk_threshold="MEDIUM",
        kpis=[],
    )
    event = await submit_intent(
        intent,
        {
            "tenant_id": "acme",
            "mission_id": "blocker-investigation-1",
            "employee_id": "onboarding-ops",
            "actor_identity": "system",
            "business_scope": "acme",
        },
        role_config=role,
        capabilities=CapabilityOpRegistry,
    )
    assert event["decision"] == "permit:executed"
    assert event["verified"] is True
    assert mock_cap.update_calls == [
        ("PROJ-1", {"status": "In Progress", "assignee": "priya"})
    ]
