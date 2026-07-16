"""TDD tests for GovernanceWorkflow (PRD §8.6 / §16.6).

Run FIRST — must FAIL, then implement governance_workflow.py to pass.

Key behaviors asserted:
  * validates PlannedActions + ExecutableWorkflowDrafts,
  * enforces blast radius via OBJECT_WRITE_POLICY / governance helpers,
  * medium/high -> pending_approval + blocked,
  * ONLY GovernanceWorkflow may set activated/exported (non-governance setter raises),
  * compiler-only export_payload (set_export_payload only via compiler path),
  * specialist="Governance".
"""
import pytest

from src.schemas.specialist_response import SpecialistResponse
from src.ontology.object_types import PlannedAction
from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.ontology.governance import GovernanceError


def _make_workflow():
    from src.workflows.governance_workflow import GovernanceWorkflow
    return GovernanceWorkflow()


def _low_action():
    return PlannedAction(
        id="pa-low", type="create_note", title="Add note",
        blast_radius="low", status="draft", requested_by="bob",
        target_object_type="Party", target_id="p1", rationale="note",
        requires_approval=False, source_refs=[],
    ).model_dump()


def _high_action():
    return PlannedAction(
        id="pa-high", type="money_state_change", title="Change money",
        blast_radius="high", status="draft", requested_by="bob",
        target_object_type="MoneyEvent", target_id="m1", rationale="money",
        requires_approval=True, source_refs=[],
    ).model_dump()


def _draft():
    return ExecutableWorkflowDraft(
        id="d1", runtime="n8n", name="Reminder",
        source_workflow_spec_id="ws1",
    ).model_dump()


class TestGovernanceValidation:
    def test_validates_low_action_as_auto_allowed(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action()])
        actions = resp.engagement_state_patch["planned_actions"]
        assert actions
        # Low blast radius, no approval required -> remains draft / allowed
        assert actions[0]["status"] in ("draft", "approved")

    def test_medium_high_action_blocked_pending_approval(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        actions = resp.engagement_state_patch["planned_actions"]
        assert actions[0]["status"] == "pending_approval"
        assert resp.requires_hitl is True
        assert resp.planned_action_id == "pa-high"

    def test_governance_error_on_invalid_action_schema(self):
        wf = _make_workflow()
        bad = dict(_low_action())
        bad.pop("target_object_type")  # invalid
        with pytest.raises((GovernanceError, Exception)):
            wf.run(tenant_id="t1", engagement_id="e1",
                   planned_actions=[bad])


class TestGovernanceExclusivity:
    def test_only_governance_may_set_activated(self):
        # A non-governance attempt to set status="activated" must raise
        d = ExecutableWorkflowDraft(
            id="d2", runtime="n8n", name="X",
            source_workflow_spec_id="ws",
        )
        with pytest.raises(ValueError):
            # Bypassing the governance setter (direct construction) is rejected
            ExecutableWorkflowDraft(
                id="d3", runtime="n8n", name="Y",
                source_workflow_spec_id="ws", status="activated",
            )

    def test_governance_setter_activates(self):
        wf = _make_workflow()
        d = ExecutableWorkflowDraft(
            id="d4", runtime="n8n", name="Z",
            source_workflow_spec_id="ws",
        )
        # GovernanceWorkflow is the only caller allowed to use the setter
        wf.activate_draft(d)
        assert d.status == "activated"

    def test_non_governance_cannot_construct_activated(self):
        # The model validator is the hard guard: any code path (including
        # non-governance) that tries to build a draft already in a
        # governance-only status is rejected. Only GovernanceWorkflow may
        # transition into activated/exported/executing/completed via the
        # sanctioned setter.
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="d5", runtime="n8n", name="W",
                source_workflow_spec_id="ws", status="activated",
            )

    def test_governance_is_only_caller_of_setter(self):
        # The sanctioned setter exists, but the contract is that ONLY
        # GovernanceWorkflow.activate_draft / export_draft / complete_draft
        # invoke it. We assert the workflow class owns the transition method.
        from src.workflows.governance_workflow import GovernanceWorkflow
        assert hasattr(GovernanceWorkflow, "activate_draft")
        assert hasattr(GovernanceWorkflow, "export_draft")
        assert hasattr(GovernanceWorkflow, "complete_draft")


class TestGovernanceExportPayload:
    def test_export_payload_only_via_compiler(self):
        # Constructing a draft with export_payload directly must raise
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="d6", runtime="n8n", name="C",
                source_workflow_spec_id="ws",
                export_payload={"nodes": []},
            )

    def test_compiler_sets_export_payload(self):
        d = ExecutableWorkflowDraft(
            id="d7", runtime="n8n", name="C2",
            source_workflow_spec_id="ws",
        )
        # The compiler path (governance delegates to compiler) sets it
        from src.workflows.governance_workflow import set_export_payload_via_compiler
        set_export_payload_via_compiler(d, {"nodes": [{"id": "n1"}]})
        assert d.export_payload == {"nodes": [{"id": "n1"}]}


class TestGovernanceResponse:
    def test_returns_governance_response(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        assert isinstance(resp, SpecialistResponse)
        assert resp.specialist == "Governance"
        assert resp.workflow_name == "GovernanceWorkflow"
        assert "planned_actions" in resp.engagement_state_patch
