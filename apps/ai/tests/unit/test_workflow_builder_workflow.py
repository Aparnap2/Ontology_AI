"""TDD tests for WorkflowBuilderWorkflow (PRD §8.5 / §16.5).

Run FIRST — must FAIL, then implement workflow_builder_workflow.py to pass.

Key behaviors asserted:
  * produces a WorkflowSpec (src.schemas.workflow_spec.WorkflowSpec),
  * produces an SOP (src.schemas.sop.SOP),
  * produces an ExecutableWorkflowDraft (status="draft"),
  * produces a PlannedAction when execution/export/activation proposed,
  * returns patches to workflow_specs, planned_actions, executable_workflow_drafts,
  * specialist="WorkflowBuilder".
"""
import pytest

from src.schemas.specialist_response import SpecialistResponse
from src.schemas.workflow_spec import WorkflowSpec
from src.schemas.sop import SOP
from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.ontology.object_types import PlannedAction


def _make_workflow(llm=None):
    from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
    return WorkflowBuilderWorkflow(llm_client=llm)


def _truth_findings():
    return [{
        "kind": "overdue_money_event",
        "target_type": "MoneyEvent",
        "target_id": "m1",
        "severity": "high",
        "summary": "Invoice m1 is overdue",
        "action_worthy": True,
    }]


class TestWorkflowBuilderOutputs:
    def test_produces_workflow_spec(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      truth_findings=_truth_findings())
        specs = resp.engagement_state_patch["workflow_specs"]
        assert specs
        spec_dict = {k: v for k, v in specs[0].items() if k != "sop"}
        WorkflowSpec(**spec_dict)

    def test_produces_sop(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      truth_findings=_truth_findings())
        # SOP is embedded alongside the spec (spec remains valid WorkflowSpec).
        specs = resp.engagement_state_patch["workflow_specs"]
        assert "sop" in specs[0]
        SOP(**specs[0]["sop"])
        # The spec itself must still validate as a pure WorkflowSpec.
        spec_dict = {k: v for k, v in specs[0].items() if k != "sop"}
        WorkflowSpec(**spec_dict)

    def test_produces_executable_draft_draft_status(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      truth_findings=_truth_findings())
        drafts = resp.engagement_state_patch["executable_workflow_drafts"]
        assert drafts
        d = ExecutableWorkflowDraft(**drafts[0])
        assert d.status == "draft"

    def test_produces_planned_action_when_execution_proposed(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            truth_findings=_truth_findings(),
            propose_execution=True,
        )
        actions = resp.engagement_state_patch.get("planned_actions", [])
        assert actions
        PlannedAction(**actions[0])
        assert resp.actions_proposed


class TestWorkflowBuilderResponse:
    def test_returns_workflow_builder_response(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      truth_findings=_truth_findings())
        assert isinstance(resp, SpecialistResponse)
        assert resp.specialist == "WorkflowBuilder"
        assert resp.workflow_name == "WorkflowBuilderWorkflow"
        assert "workflow_specs" in resp.engagement_state_patch
        assert "executable_workflow_drafts" in resp.engagement_state_patch
