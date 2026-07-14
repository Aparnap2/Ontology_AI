"""Tests for SpecialistResponse schema — TDD approach.

These tests define the expected behavior BEFORE implementation.
Run FIRST — they should FAIL, then implement code to pass them.
"""
import pytest
from pydantic import ValidationError


class TestSpecialistResponse:
    """SpecialistResponse schema tests."""

    def test_specialist_response_has_all_fields(self):
        """Verify SpecialistResponse has all 9 required fields."""
        from src.schemas.specialist_response import SpecialistResponse
        fields = SpecialistResponse.model_fields
        assert "specialist" in fields
        assert "workflow_name" in fields
        assert "summary" in fields
        assert "detailed_response" in fields
        assert "requires_hitl" in fields
        assert "planned_action_id" in fields
        assert "mission_state_patch" in fields
        assert "citations" in fields
        assert "followups" in fields

    def test_specialist_validates_canonical_names(self):
        """specialist must be one of the 5 canonical names."""
        from src.schemas.specialist_response import SpecialistResponse
        # Valid names
        for name in ["Chief of Staff", "FP&A", "Growth Analytics", "Reliability & Delivery", "Communications"]:
            resp = SpecialistResponse(specialist=name, workflow_name="ChiefOfStaffWorkflow", summary="test", detailed_response="test")
            assert resp.specialist == name
        # Invalid name
        with pytest.raises(ValidationError):
            SpecialistResponse(specialist="Hiring", workflow_name="ChiefOfStaffWorkflow", summary="test", detailed_response="test")

    def test_workflow_name_validates_canonical_names(self):
        """workflow_name must be one of the 5 canonical names."""
        from src.schemas.specialist_response import SpecialistResponse
        for name in ["ChiefOfStaffWorkflow", "FPAWorkflow", "GrowthAnalyticsWorkflow", "ReliabilityWorkflow", "CommsWorkflow"]:
            resp = SpecialistResponse(specialist="Chief of Staff", workflow_name=name, summary="test", detailed_response="test")
            assert resp.workflow_name == name
        with pytest.raises(ValidationError):
            SpecialistResponse(specialist="Chief of Staff", workflow_name="HiringWorkflow", summary="test", detailed_response="test")

    def test_requires_hitl_defaults_false(self):
        """requires_hitl must default to False."""
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(specialist="Chief of Staff", workflow_name="ChiefOfStaffWorkflow", summary="test", detailed_response="test")
        assert resp.requires_hitl is False

    def test_citations_defaults_empty(self):
        """citations must default to empty list."""
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(specialist="Chief of Staff", workflow_name="ChiefOfStaffWorkflow", summary="test", detailed_response="test")
        assert resp.citations == []

    def test_followups_defaults_empty(self):
        """followups must default to empty list."""
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(specialist="Chief of Staff", workflow_name="ChiefOfStaffWorkflow", summary="test", detailed_response="test")
        assert resp.followups == []

    def test_serialization_round_trip(self):
        """Serialize to dict and back must preserve all fields."""
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="FP&A", workflow_name="FPAWorkflow", summary="test", detailed_response="test",
            requires_hitl=True, planned_action_id="pa-123", mission_state_patch={"burn_rate": 10000},
            citations=["source1"], followups=["What about next quarter?"]
        )
        d = resp.model_dump()
        resp2 = SpecialistResponse.model_validate(d)
        assert resp2.specialist == "FP&A"
        assert resp2.workflow_name == "FPAWorkflow"
        assert resp2.planned_action_id == "pa-123"
        assert resp2.mission_state_patch == {"burn_rate": 10000}
