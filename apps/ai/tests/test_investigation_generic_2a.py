"""Phase 2a generic investigation runtime tests (slice style).

Mocked LLM + monkeypatched ``_resolve_capability`` (same conventions as
``test_blocker_investigation_slice.py``). Covers: ONE InvestigationContext,
shared runner core, vendor skill framing/allowlist, and evidence grounding.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.control_plane import audit as audit_mod
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    make_blocker_investigation_role,
    reset_idempotency,
)
from src.mission.skill_contracts import SkillContext
from src.mission.skill_registry import SkillRegistry
from src.mission.skills import onboarding_ops as ops_mod
from src.mission.skills.onboarding_ops import (
    BLOCKER_INVESTIGATION_SKILL,
    VENDOR_INVESTIGATION_SKILL,
    BlockerInvestigationWorkItem,
    InvestigationContext,
    InvestigationResult,
    _BlockerInvestigationIn,
    grounding_violation,
    set_investigation_work_item,
)


class MockCap:
    """In-memory Jira stand-in (update + read-back pair)."""

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


def _clean_fixture():
    reset_idempotency()
    snapshot = dict(SkillRegistry._skills)
    return snapshot


@pytest.fixture(autouse=True)
def _clean():
    snapshot = _clean_fixture()
    yield
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)
    reset_idempotency()


@pytest.fixture
def mock_cap(monkeypatch):
    cap = MockCap()
    monkeypatch.setattr(
        capability_ops, "_resolve_capability", lambda name, config: cap
    )
    capability_ops.CapabilityOpRegistry._ops.clear()
    return cap


def _mock_llm(monkeypatch, proposal):
    def fake(messages, **kwargs):
        return SimpleNamespace(content=json.dumps(proposal))

    monkeypatch.setattr("src.config.llm.chat_completion_with_metrics", fake)


def _proposal(**over):
    base = {
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
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _ctx():
    role = make_blocker_investigation_role(
        ["jira.update", "jira.create", "jira.read", "slack.send"]
    )
    return SkillContext(
        tenant_id="t1",
        role=role.role_id,
        role_config=role,
        capabilities=capability_ops.CapabilityOpRegistry,
    )


def _item(**over):
    base = dict(
        mission_id="m-1",
        tenant_id="t1",
        employee_id="analyst-1",
        actor_identity="system",
        evidence_ids=["ev-1"],
        evidence_texts=["[slack report]: SSO blocked"],
        blocker_ref="PROJ-1",
    )
    base.update(over)
    return BlockerInvestigationWorkItem(**base)


async def _run_skill(skill, item):
    with set_investigation_work_item(item):
        await skill.run(_ctx(), _BlockerInvestigationIn(tenant_id="t1"))
    return item.observations[-1]


# ── ONE InvestigationContext ────────────────────────────────────────────

class TestInvestigationContext:
    def test_single_context_class_no_vendor_duplicate(self):
        assert not hasattr(ops_mod, "VendorInvestigationContext")
        assert InvestigationContext.__name__ == "InvestigationContext"

    def test_from_work_item_defaults(self):
        ictx = InvestigationContext.from_work_item(_item())
        assert (ictx.target_type, ictx.target_id) == (None, None)
        assert ictx.mission_id == "m-1"
        assert ictx.allowed_capabilities == []
        assert ictx.checkpoint is None

    def test_from_work_item_carries_target_and_checkpoint(self):
        cp = {"allowed_capabilities": ["jira.update"]}
        ictx = InvestigationContext.from_work_item(
            _item(target_type="vendor", target_id="v-9", checkpoint=cp)
        )
        assert (ictx.target_type, ictx.target_id) == ("vendor", "v-9")
        assert ictx.checkpoint == cp
        assert ictx.allowed_capabilities == ["jira.update"]


# ── Shared core, two skills ─────────────────────────────────────────────

class TestSharedCore:
    def test_both_skills_share_core_and_input_output(self):
        assert BLOCKER_INVESTIGATION_SKILL.name == "investigate_onboarding_blocker"
        assert VENDOR_INVESTIGATION_SKILL.name == "investigate_vendor_incident"
        assert (
            BLOCKER_INVESTIGATION_SKILL.input_model
            is VENDOR_INVESTIGATION_SKILL.input_model
        )
        assert (
            BLOCKER_INVESTIGATION_SKILL.output_model
            is VENDOR_INVESTIGATION_SKILL.output_model
        )
        # Distinct framing + distinct allowlist, nothing else.
        assert ops_mod._SYSTEM != ops_mod._VENDOR_SYSTEM
        assert (
            ops_mod.BLOCKER_INVESTIGATION_ALLOWED_OPS
            != ops_mod.VENDOR_INVESTIGATION_ALLOWED_OPS
        )

    def test_register_registers_both(self):
        ops_mod.register()
        assert SkillRegistry.get_skill("investigate_onboarding_blocker") is (
            BLOCKER_INVESTIGATION_SKILL
        )
        assert SkillRegistry.get_skill("investigate_vendor_incident") is (
            VENDOR_INVESTIGATION_SKILL
        )

    async def test_vendor_happy_path_verified(self, mock_cap, monkeypatch):
        _mock_llm(monkeypatch, _proposal())
        obs = await _run_skill(VENDOR_INVESTIGATION_SKILL, _item())
        assert obs["outcome"] == "BUSINESS_OUTCOME_VERIFIED"
        assert obs["verified"] is True
        assert mock_cap.update_calls == [("PROJ-1", {"status": "In Progress"})]

    async def test_allowlist_differs_only_by_surface(self, mock_cap, monkeypatch):
        create = _proposal(
            action={
                "capability": "jira",
                "operation": "jira.create",
                "target": "PROJ-1",
                "parameters": {"issue_id": "PROJ-1"},
            }
        )
        _mock_llm(monkeypatch, create)
        vendor_obs = await _run_skill(VENDOR_INVESTIGATION_SKILL, _item())
        assert vendor_obs["outcome"] == "POLICY_BLOCKED"
        assert mock_cap.update_calls == []

        _mock_llm(monkeypatch, create)
        ob_obs = await _run_skill(BLOCKER_INVESTIGATION_SKILL, _item())
        assert ob_obs["outcome"] != "POLICY_BLOCKED"

    async def test_vendor_records_generic_target(self, mock_cap, monkeypatch):
        _mock_llm(monkeypatch, _proposal())
        obs = await _run_skill(
            VENDOR_INVESTIGATION_SKILL,
            _item(target_type="vendor", target_id="v-9"),
        )
        assert obs["outcome"] == "BUSINESS_OUTCOME_VERIFIED"
        assert obs["target_type"] == "vendor"
        assert obs["target_id"] == "v-9"


# ── InvestigationResult + evidence grounding ────────────────────────────

class TestInvestigationResult:
    def test_legacy_proposal_validates(self):
        result = InvestigationResult.model_validate(_proposal())
        assert result.root_cause.startswith("SSO")
        assert result.findings == []
        assert result.confidence == 0.91

    def test_extra_fields_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            InvestigationResult.model_validate(
                {**_proposal(), "vendor_entity": {"id": "v-1"}}
            )

    def test_grounding_helper_flags_uncited(self):
        result = InvestigationResult.model_validate(
            {
                **_proposal(),
                "findings": [{"statement": "SSO is down", "evidence_ids": []}],
            }
        )
        assert grounding_violation(result.findings, ["ev-1"]) is not None
        assert (
            grounding_violation(result.findings, ["ev-1", "ev-2"]) is not None
        )

    def test_grounding_helper_flags_unknown_id(self):
        result = InvestigationResult.model_validate(
            {
                **_proposal(),
                "findings": [
                    {"statement": "SSO is down", "evidence_ids": ["ev-unknown"]}
                ],
            }
        )
        assert grounding_violation(result.findings, ["ev-1"]) is not None

    def test_grounding_helper_accepts_cited(self):
        result = InvestigationResult.model_validate(
            {
                **_proposal(),
                "findings": [
                    {"statement": "SSO is down", "evidence_ids": ["ev-1"]}
                ],
            }
        )
        assert grounding_violation(result.findings, ["ev-1"]) is None

    async def test_uncited_finding_fails_honestly_no_intent(
        self, mock_cap, monkeypatch
    ):
        _mock_llm(
            monkeypatch,
            {
                **_proposal(),
                "findings": [{"statement": "SSO is down", "evidence_ids": []}],
            },
        )
        obs = await _run_skill(BLOCKER_INVESTIGATION_SKILL, _item())
        assert obs["outcome"] == "UNGROUNDED_FINDING"
        assert obs["action_taken"] is False
        assert "SSO is down" in obs["unresolved_questions"]
        assert mock_cap.update_calls == []
        assert audit_mod.list_events() == []

    async def test_unknown_evidence_id_fails_honestly(
        self, mock_cap, monkeypatch
    ):
        _mock_llm(
            monkeypatch,
            {
                **_proposal(),
                "findings": [
                    {"statement": "SSO is down", "evidence_ids": ["ev-forged"]}
                ],
            },
        )
        obs = await _run_skill(VENDOR_INVESTIGATION_SKILL, _item())
        assert obs["outcome"] == "UNGROUNDED_FINDING"
        assert mock_cap.update_calls == []
        assert audit_mod.list_events() == []

    async def test_cited_findings_pass_through(self, mock_cap, monkeypatch):
        _mock_llm(
            monkeypatch,
            {
                **_proposal(),
                "findings": [
                    {
                        "statement": "SSO is down",
                        "evidence_ids": ["ev-1"],
                        "confidence": 0.8,
                    }
                ],
                "evidence_refs": ["ev-1"],
            },
        )
        obs = await _run_skill(BLOCKER_INVESTIGATION_SKILL, _item())
        assert obs["outcome"] == "BUSINESS_OUTCOME_VERIFIED"
        assert len(mock_cap.update_calls) == 1

    async def test_recommended_action_shape_supported(
        self, mock_cap, monkeypatch
    ):
        proposal = _proposal()
        action = proposal.pop("action")
        proposal["recommended_action"] = action
        _mock_llm(monkeypatch, proposal)
        obs = await _run_skill(VENDOR_INVESTIGATION_SKILL, _item())
        assert obs["outcome"] == "BUSINESS_OUTCOME_VERIFIED"
