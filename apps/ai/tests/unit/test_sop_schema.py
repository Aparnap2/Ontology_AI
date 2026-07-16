"""TDD tests for SOP schema (PRD §15.3).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.
"""
import pytest
from pydantic import ValidationError


VALID_STEP = {
    "step_number": 1,
    "actor": "Finance",
    "instruction": "Open the invoice",
    "input": "invoice_pdf",
    "output": "parsed invoice",
    "approval_required": False,
    "fallback_if_failed": "escalate to human",
}

VALID_SOP = {
    "sop_id": "sop-inv-001",
    "title": "Invoice Approval SOP",
    "business_goal": "Approve invoices quickly",
    "trigger": "invoice.received",
    "preconditions": ["vendor verified"],
    "required_inputs": ["invoice_pdf"],
    "steps": [VALID_STEP],
    "decision_points": ["amount > threshold?"],
    "approval_points": ["CFO sign-off"],
    "exception_paths": ["duplicate -> flag"],
    "completion_criteria": "invoice marked approved",
    "owner_role": "Finance",
    "reporting_output": "approval report",
    "linked_objects": ["Invoice"],
    "linked_actions": ["ApproveInvoice"],
}


class TestSOPStep:
    """SOPStep schema tests."""

    def test_valid_step_constructs(self):
        from src.schemas.sop import SOPStep
        step = SOPStep(**VALID_STEP)
        assert step.step_number == 1
        assert step.approval_required is False
        assert step.fallback_if_failed == "escalate to human"

    def test_step_number_required(self):
        from src.schemas.sop import SOPStep
        bad = dict(VALID_STEP)
        del bad["step_number"]
        with pytest.raises(ValidationError):
            SOPStep(**bad)

    def test_approval_required_must_be_bool(self):
        from src.schemas.sop import SOPStep
        bad = dict(VALID_STEP)
        bad["approval_required"] = "yes"
        with pytest.raises(ValidationError):
            SOPStep(**bad)

    def test_unknown_field_rejected(self):
        from src.schemas.sop import SOPStep
        bad = dict(VALID_STEP)
        bad["bogus"] = 1
        with pytest.raises(ValidationError):
            SOPStep(**bad)


class TestSOP:
    """SOP schema tests (PRD §15.3)."""

    def test_valid_sop_constructs(self):
        from src.schemas.sop import SOP
        sop = SOP(**VALID_SOP)
        assert sop.sop_id == "sop-inv-001"
        assert len(sop.steps) == 1
        assert sop.steps[0].step_number == 1

    def test_all_required_fields_present(self):
        from src.schemas.sop import SOP
        fields = set(SOP.model_fields.keys())
        expected = {
            "sop_id", "title", "business_goal", "trigger", "preconditions",
            "required_inputs", "steps", "decision_points", "approval_points",
            "exception_paths", "completion_criteria", "owner_role",
            "reporting_output", "linked_objects", "linked_actions",
        }
        assert expected <= fields

    def test_missing_required_field_rejected(self):
        from src.schemas.sop import SOP
        bad = dict(VALID_SOP)
        del bad["completion_criteria"]
        with pytest.raises(ValidationError):
            SOP(**bad)

    def test_unknown_field_rejected(self):
        from src.schemas.sop import SOP
        bad = dict(VALID_SOP)
        bad["extra"] = "nope"
        with pytest.raises(ValidationError):
            SOP(**bad)

    def test_list_fields_default_empty(self):
        from src.schemas.sop import SOP
        minimal = {
            "sop_id": "sop-002",
            "title": "T",
            "business_goal": "g",
            "trigger": "t",
            "completion_criteria": "c",
            "owner_role": "R",
            "reporting_output": "o",
        }
        sop = SOP(**minimal)
        assert sop.preconditions == []
        assert sop.required_inputs == []
        assert sop.steps == []
        assert sop.decision_points == []
        assert sop.approval_points == []
        assert sop.exception_paths == []
        assert sop.linked_objects == []
        assert sop.linked_actions == []

    def test_serialization_round_trip(self):
        from src.schemas.sop import SOP
        sop = SOP(**VALID_SOP)
        d = sop.model_dump()
        sop2 = SOP.model_validate(d)
        assert sop2.sop_id == sop.sop_id
        assert sop2.steps[0].step_number == 1
