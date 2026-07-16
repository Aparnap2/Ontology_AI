"""TDD tests for the n8n runtime compiler (PRD §17, §19.3, §12.7).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.

Critical invariants asserted here:
* Compiler purity: ``export_payload`` is ONLY set via ``set_export_payload``.
  Constructing a draft with ``export_payload`` directly must raise ``ValueError``.
* Determinism: the same draft compiles to byte-identical payloads (no UUID/random).
* Output shape: the payload is valid n8n-shaped JSON (nodes + connections).
"""
from __future__ import annotations

import json

import pytest

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.n8n_compiler import compile_n8n


def _make_draft() -> ExecutableWorkflowDraft:
    """Build a representative draft with all fields populated."""
    return ExecutableWorkflowDraft(
        id="draft-n8n-1",
        runtime="n8n",
        name="Invoice Overdue Reminder",
        source_workflow_spec_id="ws-001",
        trigger={"type": "schedule", "cron": "0 9 * * *"},
        inputs=[{"name": "customer_id", "type": "string"}],
        steps=[
            {"id": "s1", "action": "fetch_invoice", "params": {"status": "overdue"}},
            {"id": "s2", "action": "send_email", "params": {"template": "reminder"}},
        ],
        decision_points=[{"id": "d1", "condition": "amount > 1000"}],
        approvals=[{"id": "a1", "role": "finance"}],
        side_effects=[{"id": "e1", "effect": "email_sent"}],
        fallback_paths=[{"id": "f1", "on": "email_failed", "goto": "s1"}],
        success_criteria=["email_delivered", "invoice_marked_reminded"],
    )


class TestN8nCompilerPurity:
    """export_payload may ONLY be set by the deterministic compiler."""

    def test_constructing_draft_with_export_payload_directly_raises(self):
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="draft-x",
                runtime="n8n",
                name="X",
                source_workflow_spec_id="ws-x",
                export_payload={"nodes": [], "connections": {}},
            )

    def test_compile_sets_export_payload_via_sanctioned_setter(self):
        draft = _make_draft()
        assert draft.export_payload is None
        payload = compile_n8n(draft)
        # The compiler must have populated export_payload through set_export_payload.
        assert draft.export_payload is not None
        assert draft.export_payload == payload
        # The internal bookkeeping flag proves the sanctioned path was used.
        assert draft._export_payload_set_by_compiler is True

    def test_compiler_returns_payload_dict(self):
        draft = _make_draft()
        payload = compile_n8n(draft)
        assert isinstance(payload, dict)


class TestN8nCompilerDeterminism:
    """Same draft -> byte-identical payload (no uuid4 / random)."""

    def test_same_draft_produces_identical_bytes(self):
        draft_a = _make_draft()
        draft_b = _make_draft()
        payload_a = compile_n8n(draft_a)
        payload_b = compile_n8n(draft_b)
        assert json.dumps(payload_a, sort_keys=True) == json.dumps(payload_b, sort_keys=True)

    def test_no_random_identifiers_in_payload(self):
        import re

        draft = _make_draft()
        payload = compile_n8n(draft)
        blob = json.dumps(payload)
        # n8n node ids must be deterministic, ordered indices — not UUIDs.
        assert re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", blob) is None


class TestN8nCompilerShape:
    """Output is valid n8n-shaped JSON (nodes + connections)."""

    def test_payload_has_nodes_and_connections(self):
        draft = _make_draft()
        payload = compile_n8n(draft)
        assert "nodes" in payload
        assert "connections" in payload
        assert isinstance(payload["nodes"], list)
        assert isinstance(payload["connections"], dict)
        assert len(payload["nodes"]) >= 1

    def test_node_has_required_n8n_fields(self):
        draft = _make_draft()
        payload = compile_n8n(draft)
        node = payload["nodes"][0]
        for field in ("id", "name", "type", "typeVersion", "parameters", "position"):
            assert field in node, f"n8n node missing field {field!r}"

    def test_connections_reference_real_node_ids(self):
        draft = _make_draft()
        payload = compile_n8n(draft)
        node_ids = {n["id"] for n in payload["nodes"]}
        for src, targets in payload["connections"].items():
            assert src in node_ids
            # n8n connections: {src: {"main": [[{node, type, index}, ...]]}}
            for output_pin, link_lists in targets.items():
                assert output_pin == "main"
                for link_list in link_lists:
                    for link in link_list:
                        assert link["node"] in node_ids

    def test_trigger_node_present(self):
        draft = _make_draft()
        payload = compile_n8n(draft)
        trigger_nodes = [n for n in payload["nodes"] if n.get("is_trigger")]
        assert len(trigger_nodes) == 1
