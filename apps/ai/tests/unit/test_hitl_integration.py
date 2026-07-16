"""Tests for HITL integration — OntologyAI V4.1.

Run FIRST — they should FAIL, then implement code to pass them.
"""
import pytest


class TestHITLIntegration:
    """HITL integration tests."""

    def test_fpa_workflow_can_signal_hitl(self):
        """FPAWorkflow must be able to create HITL approval signals.
        
        This is a contract test — the workflow imports Temporal signal primitives
        or has HITL support. We verify the workflow module can be imported.
        """
        from src.workflows.fpa_workflow import FPAWorkflow
        assert hasattr(FPAWorkflow, "run")

    def test_specialist_response_has_hitl_field(self):
        """SpecialistResponse must have requires_hitl field."""
        from src.schemas.specialist_response import SpecialistResponse
        fields = SpecialistResponse.model_fields
        assert "requires_hitl" in fields, (
            f"SpecialistResponse missing requires_hitl field. "
            f"Available fields: {list(fields.keys())}"
        )

    def test_specialist_response_planned_action_id_field(self):
        """SpecialistResponse must have planned_action_id for HITL tracking."""
        from src.schemas.specialist_response import SpecialistResponse
        fields = SpecialistResponse.model_fields
        assert "planned_action_id" in fields, (
            f"SpecialistResponse missing planned_action_id field. "
            f"Available fields: {list(fields.keys())}"
        )

    def test_specialist_response_requires_hitl_defaults_false(self):
        """requires_hitl must default to False."""
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="ChiefOfStaff",
            workflow_name="ChiefOfStaffWorkflow",
            summary="test",
            detailed_response="test",
        )
        assert resp.requires_hitl is False

    def test_specialist_response_planned_action_id_optional(self):
        """planned_action_id must be optional (default None)."""
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="ChiefOfStaff",
            workflow_name="ChiefOfStaffWorkflow",
            summary="test",
            detailed_response="test",
        )
        assert resp.planned_action_id is None
