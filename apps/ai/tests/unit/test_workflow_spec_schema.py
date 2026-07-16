"""TDD tests for WorkflowSpec schema (PRD §15.2).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.
"""
import pytest
from pydantic import ValidationError


VALID_SPEC = {
    "workflow_spec_id": "ws-001",
    "workflow_name": "InvoiceApproval",
    "business_goal": "Approve vendor invoices under $5k automatically",
    "trigger": "invoice.received",
    "preconditions": ["vendor verified", "po exists"],
    "required_inputs": ["invoice_pdf", "po_id"],
    "responsible_role": "Finance",
    "decision_points": ["amount > threshold?"],
    "approval_points": ["CFO sign-off over $50k"],
    "exception_paths": ["duplicate invoice -> flag"],
    "expected_output": "approved invoice record",
    "success_metric": "95% auto-approved under threshold",
    "linked_objects": ["Invoice", "Vendor"],
    "sop_id": "sop-inv-001",
    "draft_runtime_targets": ["n8n", "custom_agent"],
}


class TestWorkflowSpec:
    """WorkflowSpec schema tests (PRD §15.2)."""

    def test_valid_spec_constructs(self):
        from src.schemas.workflow_spec import WorkflowSpec
        spec = WorkflowSpec(**VALID_SPEC)
        assert spec.workflow_spec_id == "ws-001"
        assert spec.sop_id == "sop-inv-001"
        assert spec.draft_runtime_targets == ["n8n", "custom_agent"]

    def test_all_required_fields_present(self):
        from src.schemas.workflow_spec import WorkflowSpec
        fields = set(WorkflowSpec.model_fields.keys())
        expected = {
            "workflow_spec_id", "workflow_name", "business_goal", "trigger",
            "preconditions", "required_inputs", "responsible_role",
            "decision_points", "approval_points", "exception_paths",
            "expected_output", "success_metric", "linked_objects", "sop_id",
            "draft_runtime_targets",
        }
        assert expected <= fields

    def test_missing_required_field_rejected(self):
        from src.schemas.workflow_spec import WorkflowSpec
        bad = dict(VALID_SPEC)
        del bad["business_goal"]
        with pytest.raises(ValidationError):
            WorkflowSpec(**bad)

    def test_unknown_field_rejected(self):
        from src.schemas.workflow_spec import WorkflowSpec
        bad = dict(VALID_SPEC)
        bad["extra_unknown_field"] = "nope"
        with pytest.raises(ValidationError):
            WorkflowSpec(**bad)

    def test_list_fields_default_empty(self):
        from src.schemas.workflow_spec import WorkflowSpec
        minimal = {
            "workflow_spec_id": "ws-002",
            "workflow_name": "Minimal",
            "business_goal": "g",
            "trigger": "t",
            "responsible_role": "R",
            "expected_output": "o",
            "success_metric": "m",
            "sop_id": "s",
        }
        spec = WorkflowSpec(**minimal)
        assert spec.preconditions == []
        assert spec.required_inputs == []
        assert spec.decision_points == []
        assert spec.approval_points == []
        assert spec.exception_paths == []
        assert spec.linked_objects == []
        assert spec.draft_runtime_targets == []

    def test_serialization_round_trip(self):
        from src.schemas.workflow_spec import WorkflowSpec
        spec = WorkflowSpec(**VALID_SPEC)
        d = spec.model_dump()
        spec2 = WorkflowSpec.model_validate(d)
        assert spec2.workflow_spec_id == spec.workflow_spec_id
        assert spec2.draft_runtime_targets == spec.draft_runtime_targets
