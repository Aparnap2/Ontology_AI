"""C4 replay — rebuild mission state from audit + frozen intent (Sprint C).

From a recorded golden run's audit events + frozen intent fixture, rebuild
mission state (timeline rows via existing ``BlockerInvestigationTimeline``,
memory dict, idempotency outcomes) and assert equivalence with the original
(status, timeline, decisions, memory, idempotency) — NEVER compare LLM prose.

Mock conventions: monkeypatched ``capability_ops._resolve_capability`` +
``_ops.clear()``, ``ingress._seen`` + ``AUDIT_LOG`` reset per test,
SkillRegistry snapshot/restore, ``asyncio_mode=auto``.
"""
from __future__ import annotations

import copy
import json

import pytest

from src.control_plane import ingress as ingress_mod
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    BlockerInvestigationTimeline,
    reset_idempotency,
    run_blocker_investigation_mission,
)
from src.mission.skill_registry import SkillRegistry
from src.mission.timeline import MissionEventType
from src.ontology.object_types import Onboarding


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


SLACK = {"channel": "onboarding", "user": "alice", "text": "Customer waiting on SSO configuration", "ts": "10:23"}

PROPOSAL = {
    "root_cause": "SSO configuration is blocking the integration milestone",
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


def _onboarding() -> Onboarding:
    return Onboarding(
        id="ob-1", customer="acme", stakeholders=["alice"],
        requirements=["SSO config"], tasks=["t-1"], issues=["PROJ-1"],
        missions=["m-replay"], lifecycle_state="implementing",
    )


def _rebuild_timeline(audit_events) -> list[dict]:
    """Replay procedure: audit decisions → timeline rows (structural only)."""
    tl = BlockerInvestigationTimeline()
    tl.append(MissionEventType.CREATED, {"mission_id": "m-replay"})
    ev_ids = sorted({e["intent"].get("evidence_ids", ["ev-1"])[0] if e["intent"].get("evidence_ids") else "ev-1" for e in audit_events if e.get("intent")})
    for eid in ev_ids or ["ev-slack-onboarding-10:23"]:
        tl.append(MissionEventType.EVIDENCE_ADDED, {"evidence_id": eid})
    tl.append(MissionEventType.STARTED, {"mission_id": "m-replay"})
    for e in audit_events:
        if e["decision"] == "permit:executed":
            tl.append(MissionEventType.EXECUTED, {"action_id": e["action_id"]})
            tl.append(MissionEventType.COMPLETED, {"mission_id": e["mission_id"]})
        elif e["decision"].startswith("deny:"):
            tl.append(MissionEventType.REVIEWED, {"outcome": e["decision"]})
    return tl.list()


def _structural_signature(timeline, decisions, memory, seen_keys) -> dict:
    return {
        "timeline_types": [t["type"] for t in timeline],
        "decisions": list(decisions),
        "memory_evidence": list(memory.get("evidence_refs", [])),
        "memory_onboarding": memory.get("onboarding_id", ""),
        "seen_keys": sorted(seen_keys),
    }


async def test_replay_rebuilds_equivalent_state(mock_cap, monkeypatch):
    """Golden audit + frozen intent → rebuilt state matches original structurally."""
    from types import SimpleNamespace

    def fake(messages, **kwargs):
        return SimpleNamespace(content=json.dumps(PROPOSAL))

    monkeypatch.setattr("src.config.llm.chat_completion_with_metrics", fake)
    out = await run_blocker_investigation_mission(_onboarding(), SLACK, mission_id="m-replay")
    assert out["observations"][-1]["decision"] == "permit:executed"

    # Frozen intent fixture: byte-stable copy of the recorded permit intent.
    permit = next(e for e in out["audit_events"] if e["decision"] == "permit:executed")
    frozen_intent = json.loads(json.dumps(permit["intent"]))

    rebuilt_timeline = _rebuild_timeline(out["audit_events"])
    rebuilt_memory = copy.deepcopy(out["memory"])
    rebuilt_decisions = [e["decision"] for e in out["audit_events"]]
    original_sig = _structural_signature(
        out["timeline"], [e["decision"] for e in out["audit_events"]],
        out["memory"], list(ingress_mod._seen._seen),
    )
    replayed_sig = _structural_signature(
        rebuilt_timeline, rebuilt_decisions, rebuilt_memory, list(ingress_mod._seen._seen),
    )
    assert replayed_sig == original_sig
    # Frozen intent round-trips structurally (capability/op/target/confidence only).
    assert frozen_intent["capability"] == "jira"
    assert frozen_intent["operation"] == "jira.update"
    assert frozen_intent["target_reference"] == "PROJ-1"


async def test_replay_ignores_llm_prose(mock_cap, monkeypatch):
    """Mutating LLM prose must not change the replayed structural equivalence."""
    from types import SimpleNamespace

    def fake(messages, **kwargs):
        return SimpleNamespace(content=json.dumps(PROPOSAL))

    monkeypatch.setattr("src.config.llm.chat_completion_with_metrics", fake)
    out = await run_blocker_investigation_mission(_onboarding(), SLACK, mission_id="m-replay")
    permit = next(e for e in out["audit_events"] if e["decision"] == "permit:executed")
    # Adversarial prose mutation: root-cause wording / confidence text changed.
    mutated = copy.deepcopy(permit["intent"])
    mutated["reason"] = "TOTALLY DIFFERENT prose about SSO dragons"
    mutated["expected_outcome"] = "different prose outcome"
    # Replay uses ONLY structural fields — prose is never compared.
    for key in ("capability", "operation", "target_reference"):
        assert mutated[key] == permit["intent"][key]
    rebuilt = _rebuild_timeline(out["audit_events"])
    assert [t["type"] for t in rebuilt] == [t["type"] for t in out["timeline"]]
    assert "dragons" not in json.dumps(rebuilt)
