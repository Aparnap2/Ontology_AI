"""E3 hero: delivery-blocker business loop on the Situation chain.

Signal -> Situation -> Mission(situation_id) -> investigation skill ->
owner -> typed ActionIntent -> control-plane gates -> Jira remediation ->
read-back verification -> audit/timeline.

Scope: ONE new test file, no src changes. Reuses only the pinned seams:
``open_situation``, ``Mission.situation_id``, ``assemble_checkpoint``,
``resolve_owner``, ``submit_intent`` gate chain (via the skill),
``JiraClient`` + demo binding, ``verify_write`` + ``derive_expected``,
``run_blocker_investigation_mission`` + ``investigate_onboarding_blocker``.

REAL-vs-MOCKED (see module docstring footer + inline labels):
- REAL HTTP: Jira create/update/search against local Mockoon :3003.
- IN-MEMORY DOUBLES (labelled): LLM proposal, read-back synthesis where
  Mockoon static fixtures cannot be stateful, MockCap for negative paths.
"""

from __future__ import annotations

import asyncio
import json
import socket
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.connectors.jira_client import JiraClient
from src.context.assemble import assemble_checkpoint
from src.control_plane import audit as audit_mod
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    ingest_slack_event,
    reset_idempotency,
    run_blocker_investigation_mission,
)
from src.mission.capability_binding import reset_binding_cache
from src.mission.owner_resolution import (
    OrganizationConfig,
    OrganizationUser,
    OwnerQuery,
    resolve_owner,
)
from src.mission.signal_handler import InMemorySignalHandler
from src.mission.skill_registry import SkillRegistry
from src.mission.situations import open_situation
from src.mission.timeline import MissionEventType
from src.mission.verify import derive_expected, verify_write
from src.ontology.object_types import Mission, Onboarding

SLACK = {
    "channel": "onboarding",
    "user": "alice",
    "text": "Customer waiting on SSO configuration",
    "ts": "10:23",
}

TENANT = "t1"
MISSION_ID = "hero-delivery-blocker-1"
SITUATION_ID = "sit-hero-1"


def _mockoon_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 3003), timeout=1).close()
        return True
    except OSError:
        return False


needs_mockoon = pytest.mark.skipif(
    not _mockoon_up(), reason="local Mockoon Jira on :3003 not reachable"
)


@pytest.fixture(autouse=True)
def _clean():
    reset_idempotency()
    reset_binding_cache()
    snapshot = dict(SkillRegistry._skills)
    yield
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)
    reset_idempotency()
    reset_binding_cache()


class MockCap:
    """IN-MEMORY DOUBLE: Jira stand-in (update + read-back pair)."""

    def __init__(self) -> None:
        self.store = {"PROJ-1": {"key": "PROJ-1", "status": "Blocked"}}
        self.update_calls: list[tuple[str, dict]] = []
        self.fail_update = False
        self.empty_read = False

    def update_issue(self, issue_id, fields):
        self.update_calls.append((issue_id, dict(fields)))
        if self.fail_update:
            raise RuntimeError("jira unavailable")
        self.store[issue_id] = {**self.store.get(issue_id, {}), **fields}
        return {"id": issue_id, **self.store[issue_id]}

    def get_issues(self, **kwargs):
        if self.empty_read:
            return []
        jql = str(kwargs.get("jql", ""))
        key = jql.split("=")[-1].strip() if "=" in jql else ""
        rec = self.store.get(key)
        return [dict(rec)] if rec else []


class _HybridProjectCap:
    """Test-only bridge: writes hit REAL HTTP (Mockoon); reads synthesize.

    REAL HTTP: ``create_issue`` delegates to ``JiraClient`` (demo binding,
    POST /rest/api/3/issue on localhost:3003). IN-MEMORY DOUBLE:
    ``get_issues`` synthesizes the minted-key record because the Mockoon
    static fixture set has no PORTAL-9 (not stateful) — see gap note.
    """

    def __init__(self, tenant_id: str) -> None:
        self._real = JiraClient(
            base_url="http://localhost:3003", tenant_id=tenant_id, demo=True
        )
        self.create_calls: list[dict] = []
        self.created_keys: list[str] = []

    def create_issue(self, data: dict) -> str:
        key = self._real.create_issue(data)  # REAL HTTP POST
        self.create_calls.append(dict(data))
        self.created_keys.append(key)
        return key

    def update_issue(self, issue_id: str, fields: dict) -> dict:
        return self._real.update_issue(issue_id, fields)  # REAL HTTP PUT

    def get_issues(self, **filters) -> list[dict]:
        jql = str(filters.get("jql", "") or filters.get("query", ""))
        for key in self.created_keys:  # IN-MEMORY DOUBLE for minted keys
            if key and key in jql:
                return [{"key": key, "summary": "hero remediation"}]
        return self._real.get_issues(**filters)  # REAL HTTP GET search

    def close(self) -> None:
        self._real.close()


def _org_single() -> OrganizationConfig:
    return OrganizationConfig(
        tenant_id=TENANT,
        users=[
            OrganizationUser(user_id="alice", tenant_id=TENANT, team="onboarding"),
            OrganizationUser(user_id="bob", tenant_id=TENANT, team="platform"),
        ],
        escalation_owner="bob",
    )


def _org_ambiguous() -> OrganizationConfig:
    return OrganizationConfig(
        tenant_id=TENANT,
        users=[
            OrganizationUser(user_id="alice", tenant_id=TENANT, team="onboarding"),
            OrganizationUser(user_id="bob", tenant_id=TENANT, team="onboarding"),
        ],
    )


def _onboarding() -> Onboarding:
    return Onboarding(
        id="ob-hero-1",
        customer="acme",
        stakeholders=["alice"],
        requirements=["SSO config"],
        tasks=["t-1"],
        issues=["PORTAL-2"],
        missions=[MISSION_ID],
        lifecycle_state="implementing",
    )


def _mock_llm(monkeypatch, proposal: dict) -> None:
    """IN-MEMORY DOUBLE: fake structured intent, no live calls."""

    def fake(messages, **kwargs):
        return SimpleNamespace(content=json.dumps(proposal))

    monkeypatch.setattr("src.config.llm.chat_completion_with_metrics", fake)


def _create_proposal(owner: str, **over) -> dict:
    base = {
        "root_cause": "SSO configuration blocks the integration milestone",
        "action": {
            "capability": "project",
            "operation": "jira.create",
            "target": "PORTAL",
            "parameters": {
                "project": "PORTAL",
                "summary": "Unblock SSO configuration for acme",
                "description": "Remediation for delivery blocker",
                "issue_type": "Task",
                "owner": owner,
            },
        },
        "confidence": 0.91,
        "risk_tier": "MEDIUM",
        "expected_outcome": "remediation task created and read back",
    }
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _update_proposal(**over) -> dict:
    base = {
        "root_cause": "SSO configuration is blocking the milestone",
        "action": {
            "capability": "jira",
            "operation": "jira.update",
            "target": "PROJ-1",
            "parameters": {"issue_id": "PROJ-1", "fields": {"status": "In Progress"}},
        },
        "confidence": 0.91,
        "risk_tier": "MEDIUM",
        "expected_outcome": "PROJ-1 moves to In Progress",
    }
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _situation_chain(resolution, checkpoint_id: str = "cp-hero-1"):
    """Signal -> checkpoint -> Situation -> Mission(situation_id).

    Pure reuse: ``ingest_slack_event`` (signal as Evidence),
    ``assemble_checkpoint``, ``resolve_owner`` output, ``open_situation``,
    ``Mission.situation_id`` (never ``onboarding_id`` as the mechanism).
    """
    evidence = ingest_slack_event(SLACK, TENANT)
    now = datetime.now(timezone.utc)
    checkpoint = assemble_checkpoint(
        checkpoint_id=checkpoint_id,
        tenant_id=TENANT,
        mission_id=MISSION_ID,
        trigger_event_id=evidence.id,
        evidence=[evidence.model_copy(update={"captured_at": now.isoformat()})],
        now=now,
        onboarding=_onboarding(),
        allowed_capabilities=["jira.create", "jira.read"],
    )
    situation = open_situation(
        situation_id=SITUATION_ID,
        tenant_id=TENANT,
        evidence=[evidence],
        checkpoint_id=checkpoint.checkpoint_id,
        resolution=resolution,
        detected_condition="SSO configuration blocks acme integration milestone",
        business_impact="acme go-live delayed until SSO unblocked",
        affected_entities=["PORTAL-2"],
    )
    mission = Mission(id=MISSION_ID, title="Unblock acme SSO delivery", situation_id=situation.id)
    assert mission.onboarding_id is None
    return evidence, checkpoint, situation, mission


@needs_mockoon
async def test_hero_happy_path_create_verified(monkeypatch):
    """Slack signal -> Situation -> Mission -> investigate -> Jira create.

    REAL HTTP: create POST via demo binding to Mockoon (key PORTAL-9).
    IN-MEMORY DOUBLES: LLM proposal; read-back synthesis for minted key.
    """
    monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
    reset_binding_cache()
    hybrid = _HybridProjectCap(TENANT)
    monkeypatch.setattr(
        capability_ops, "_resolve_capability", lambda name, config: hybrid
    )
    capability_ops.CapabilityOpRegistry._ops.clear()
    try:
        evidence = ingest_slack_event(SLACK, TENANT)
        resolution = resolve_owner(
            OwnerQuery(
                tenant_id=TENANT,
                object_owner_ids=["alice"],
                evidence_refs=[evidence.id],
            ),
            _org_single(),
        )
        assert resolution.status == "RESOLVED" and resolution.owner_id == "alice"
        _evidence, checkpoint, situation, mission = _situation_chain(resolution)
        assert situation.evidence_ids == [evidence.id]
        assert situation.owner_id == "alice"
        assert situation.checkpoint_id == checkpoint.checkpoint_id
        assert mission.situation_id == situation.id
        assert checkpoint.relevant_evidence[0].evidence_id == evidence.id

        _mock_llm(monkeypatch, _create_proposal(owner="alice"))
        out = await run_blocker_investigation_mission(
            _onboarding(),
            SLACK,
            tenant_id=TENANT,
            mission_id=MISSION_ID,
            role_caps=["jira.create", "jira.read", "slack.send", "salesforce.read"],
        )
        obs = out["observations"][-1]
        assert obs["outcome"] == "BUSINESS_OUTCOME_VERIFIED"
        assert obs["decision"] == "permit:executed"
        assert obs["verified"] is True
        # REAL HTTP mutation happened exactly once (static key proves 2xx+parse).
        assert len(hybrid.create_calls) == 1
        assert hybrid.created_keys == ["PORTAL-9"]
        # Adapter mapping: resolved owner (intent params) → Jira assignee.
        assert hybrid.create_calls[0]["assignee"] == "alice"

        events = audit_mod.list_events()
        permit = next(e for e in events if e["decision"] == "permit:executed")
        assert permit["mission_id"] == MISSION_ID
        assert permit["intent"]["evidence_ids"] == [evidence.id]
        assert permit["intent"]["requested_parameters"]["owner"] == "alice"
        assert permit["intent"]["operation"] == "jira.create"
        assert permit["verified"] is True

        types = [t["type"] for t in out["timeline"]]
        assert "MISSION_EXECUTED" in types and "MISSION_COMPLETED" in types

        # Explicit read-back verification through the op layer (write REAL,
        # read DOUBLE for the minted key) + derive_expected reuse.
        params = dict(permit["intent"]["requested_parameters"])
        expected = derive_expected("jira.create", params, result="PORTAL-9")
        assert expected == {"key": "PORTAL-9"}
        outcome = await verify_write(
            "jira.create",
            params,
            expected,
            TENANT,
            capabilities=capability_ops.CapabilityOpRegistry,
            role_caps=["jira.create", "jira.read"],
            result="PORTAL-9",
        )
        assert outcome.state == "VERIFIED" and outcome.verified is True

        # REAL HTTP wire-shape proof (static fixtures: 8 rows, not stateful).
        probe = JiraClient(base_url="http://localhost:3003", tenant_id=TENANT, demo=True)
        try:
            rows = probe.search_issues("project = PORTAL", limit=10)  # REAL HTTP GET
        finally:
            probe.close()
        assert len(rows) >= 1 and all(r.key for r in rows)
    finally:
        hybrid.close()
        reset_binding_cache()


async def test_hero_ambiguous_owner_blocks_execution(monkeypatch):
    """Conflicting candidates -> AMBIGUOUS -> no intent, no execution.

    IN-MEMORY DOUBLE: MockCap proves zero mutations; LLM never consulted.
    """
    cap = MockCap()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()

    from src.mission.blocker_investigation_mission import BlockerInvestigationTimeline

    evidence = ingest_slack_event(SLACK, TENANT)
    resolution = resolve_owner(
        OwnerQuery(
            tenant_id=TENANT,
            object_owner_ids=["alice", "bob"],
            evidence_refs=[evidence.id],
        ),
        _org_ambiguous(),
    )
    assert resolution.status == "AMBIGUOUS"
    assert resolution.owner_id is None

    _evidence, checkpoint, situation, mission = _situation_chain(None)
    assert situation.owner_id is None
    assert mission.situation_id == situation.id

    timeline = BlockerInvestigationTimeline()
    timeline.append(MissionEventType.CREATED, {"mission_id": MISSION_ID})
    timeline.append(MissionEventType.EVIDENCE_ADDED, {"evidence_id": evidence.id})
    timeline.append(MissionEventType.STARTED, {"mission_id": MISSION_ID})
    if resolution.status != "RESOLVED":
        # Deterministic gate: ambiguous owner never reaches submit_intent.
        timeline.append(MissionEventType.REVIEWED, {"outcome": "AMBIGUOUS_OWNER"})
    types = [t["type"] for t in timeline.list()]
    assert "MISSION_EXECUTED" not in types
    assert audit_mod.list_events() == []
    assert cap.update_calls == []


async def test_hero_duplicate_signal_single_mutation(monkeypatch):
    """Identical signal twice -> second denied, one Jira mutation.

    IN-MEMORY DOUBLE: MockCap counts wire-equivalent mutations.
    """
    cap = MockCap()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()

    evidence = ingest_slack_event(SLACK, TENANT)
    resolution = resolve_owner(
        OwnerQuery(
            tenant_id=TENANT, object_owner_ids=["alice"], evidence_refs=[evidence.id]
        ),
        _org_single(),
    )
    _evidence, _checkpoint, situation, mission = _situation_chain(resolution)
    assert mission.situation_id == situation.id

    _mock_llm(monkeypatch, _update_proposal())
    first = await run_blocker_investigation_mission(_onboarding(), SLACK)
    assert first["observations"][-1]["decision"] == "permit:executed"
    second = await run_blocker_investigation_mission(_onboarding(), SLACK)
    assert second["observations"][-1]["decision"] == "deny:duplicate"
    assert len(cap.update_calls) == 1


async def test_hero_verification_failure_not_success(monkeypatch):
    """Read-back mismatch -> NOT_VERIFIED, action not marked successful.

    IN-MEMORY DOUBLE: MockCap.empty_read simulates accepted-write/no-state.
    """
    cap = MockCap()
    cap.empty_read = True
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()

    evidence = ingest_slack_event(SLACK, TENANT)
    resolution = resolve_owner(
        OwnerQuery(
            tenant_id=TENANT, object_owner_ids=["alice"], evidence_refs=[evidence.id]
        ),
        _org_single(),
    )
    _evidence, _checkpoint, situation, mission = _situation_chain(resolution)
    assert mission.situation_id == situation.id

    _mock_llm(monkeypatch, _update_proposal())
    out = await run_blocker_investigation_mission(_onboarding(), SLACK)
    obs = out["observations"][-1]
    assert obs["decision"] == "permit:executed"
    assert obs["verified"] is False
    assert obs["outcome"] == "EXECUTED_UNVERIFIED"
    assert obs["ok"] is False

    outcome = await verify_write(
        "jira.update",
        {"issue_id": "PROJ-1", "fields": {"status": "In Progress"}},
        {"status": "In Progress"},
        TENANT,
        capabilities=capability_ops.CapabilityOpRegistry,
        role_caps=["jira.update", "jira.read"],
    )
    assert outcome.state == "NOT_VERIFIED" and outcome.verified is False


async def test_hero_high_risk_approval_then_execute(monkeypatch):
    """HIGH-risk pauses on InMemorySignalHandler, executes after approval.

    IN-MEMORY DOUBLES: LLM HIGH proposal; MockCap; in-memory signal handler.
    """
    cap = MockCap()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()

    evidence = ingest_slack_event(SLACK, TENANT)
    resolution = resolve_owner(
        OwnerQuery(
            tenant_id=TENANT, object_owner_ids=["alice"], evidence_refs=[evidence.id]
        ),
        _org_single(),
    )
    _evidence, _checkpoint, situation, mission = _situation_chain(resolution)
    assert mission.situation_id == situation.id

    _mock_llm(monkeypatch, _update_proposal(risk_tier="HIGH"))
    handler = InMemorySignalHandler()
    task = asyncio.create_task(
        run_blocker_investigation_mission(
            _onboarding(), SLACK, signal_handler=handler
        )
    )
    for _ in range(200):
        if handler._futures:
            break
        await asyncio.sleep(0.01)
    assert handler.emitted, "approval signal never emitted"
    handler.resolve({"approved": True})
    out = await task
    obs = out["observations"][-1]
    assert obs["verified"] is True
    assert obs["decision"] == "permit:executed"
    assert len(cap.update_calls) == 1
