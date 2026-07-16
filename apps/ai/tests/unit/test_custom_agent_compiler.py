"""TDD tests for the custom_agent runtime compiler (PRD §17, §19.3, §12.7).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.

Same purity + determinism invariants as the n8n compiler, plus a
custom_agent-shaped config (instructions / tool list / state machine).
"""
from __future__ import annotations

import json

import pytest

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.custom_agent_compiler import compile_custom_agent


def _make_draft() -> ExecutableWorkflowDraft:
    return ExecutableWorkflowDraft(
        id="draft-agent-1",
        runtime="custom_agent",
        name="Triage Operational Chaos",
        source_workflow_spec_id="ws-002",
        trigger={"type": "webhook", "event": "message_received"},
        inputs=[{"name": "message", "type": "string"}],
        steps=[
            {"id": "s1", "action": "classify", "params": {"model": "intent"}},
            {"id": "s2", "action": "synthesize", "params": {"sources": ["chat", "uploads"]}},
        ],
        decision_points=[{"id": "d1", "condition": "needs_human"}],
        approvals=[{"id": "a1", "role": "ops_lead"}],
        side_effects=[{"id": "e1", "effect": "ticket_created"}],
        fallback_paths=[{"id": "f1", "on": "low_confidence", "goto": "s1"}],
        success_criteria=["triage_complete", "owner_assigned"],
    )


class TestCustomAgentCompilerPurity:
    """export_payload may ONLY be set by the deterministic compiler."""

    def test_constructing_draft_with_export_payload_directly_raises(self):
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="draft-y",
                runtime="custom_agent",
                name="Y",
                source_workflow_spec_id="ws-y",
                export_payload={"instructions": [], "tools": []},
            )

    def test_compile_sets_export_payload_via_sanctioned_setter(self):
        draft = _make_draft()
        assert draft.export_payload is None
        payload = compile_custom_agent(draft)
        assert draft.export_payload is not None
        assert draft.export_payload == payload
        assert draft._export_payload_set_by_compiler is True

    def test_compiler_returns_payload_dict(self):
        draft = _make_draft()
        payload = compile_custom_agent(draft)
        assert isinstance(payload, dict)


class TestCustomAgentCompilerDeterminism:
    """Same draft -> byte-identical payload (no uuid4 / random)."""

    def test_same_draft_produces_identical_bytes(self):
        draft_a = _make_draft()
        draft_b = _make_draft()
        payload_a = compile_custom_agent(draft_a)
        payload_b = compile_custom_agent(draft_b)
        assert json.dumps(payload_a, sort_keys=True) == json.dumps(payload_b, sort_keys=True)

    def test_no_random_identifiers_in_payload(self):
        import re

        draft = _make_draft()
        payload = compile_custom_agent(draft)
        blob = json.dumps(payload)
        assert re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", blob) is None


class TestCustomAgentCompilerShape:
    """Output is a valid custom_agent runtime config."""

    def test_payload_has_expected_top_level_keys(self):
        draft = _make_draft()
        payload = compile_custom_agent(draft)
        for key in ("runtime", "name", "instructions", "tools", "state_machine"):
            assert key in payload, f"custom_agent payload missing {key!r}"

    def test_runtime_is_custom_agent(self):
        draft = _make_draft()
        payload = compile_custom_agent(draft)
        assert payload["runtime"] == "custom_agent"

    def test_state_machine_is_deterministic_ordered(self):
        draft = _make_draft()
        payload = compile_custom_agent(draft)
        sm = payload["state_machine"]
        assert isinstance(sm, list)
        # States must be ordered and carry stable indices, not random ids.
        for i, state in enumerate(sm):
            assert state["index"] == i
            assert "id" in state

    def test_tools_derived_from_steps(self):
        draft = _make_draft()
        payload = compile_custom_agent(draft)
        assert isinstance(payload["tools"], list)
        assert len(payload["tools"]) >= 1
