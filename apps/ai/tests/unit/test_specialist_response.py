"""TDD tests for SpecialistResponse schema (PRD §15.1, V5.1 rebrand).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.

The V5.1 rebrand migrates specialist/workflow Literals to the new canonical
set and renames ``mission_state_patch`` -> ``engagement_state_patch`` (with a
backward-compatible alias).
"""
import pytest
from pydantic import ValidationError


SPECIALISTS = [
    "Discovery", "OntologyMapper", "TruthAnalyst",
    "WorkflowBuilder", "Governance", "ChiefOfStaff",
]
WORKFLOWS = [
    "ChiefOfStaffWorkflow", "DiscoveryWorkflow", "OntologyMappingWorkflow",
    "TruthAnalysisWorkflow", "WorkflowBuilderWorkflow", "GovernanceWorkflow",
]


class TestSpecialistResponse:
    """SpecialistResponse schema tests (PRD §15.1)."""

    def test_new_specialist_literals_accepted(self):
        from src.schemas.specialist_response import SpecialistResponse
        for name in SPECIALISTS:
            resp = SpecialistResponse(
                specialist=name, workflow_name="ChiefOfStaffWorkflow",
                summary="s", detailed_response="d",
            )
            assert resp.specialist == name

    def test_old_specialist_names_rejected(self):
        from src.schemas.specialist_response import SpecialistResponse
        for old in ["Chief of Staff", "FP&A", "Growth Analytics",
                    "Reliability & Delivery", "Communications"]:
            with pytest.raises(ValidationError):
                SpecialistResponse(
                    specialist=old, workflow_name="ChiefOfStaffWorkflow",
                    summary="s", detailed_response="d",
                )

    def test_new_workflow_literals_accepted(self):
        from src.schemas.specialist_response import SpecialistResponse
        for wf in WORKFLOWS:
            resp = SpecialistResponse(
                specialist="ChiefOfStaff", workflow_name=wf,
                summary="s", detailed_response="d",
            )
            assert resp.workflow_name == wf

    def test_new_fields_default_empty(self):
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="Discovery", workflow_name="DiscoveryWorkflow",
            summary="s", detailed_response="d",
        )
        assert resp.objects_read == []
        assert resp.objects_written == []
        assert resp.actions_proposed == []
        assert resp.unresolved_questions == []
        assert resp.engagement_state_patch is None
        assert resp.confidence is None

    def test_engagement_state_patch_field(self):
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="Governance", workflow_name="GovernanceWorkflow",
            summary="s", detailed_response="d",
            engagement_state_patch={"phase": "governance_review"},
        )
        assert resp.engagement_state_patch == {"phase": "governance_review"}

    def test_mission_state_patch_alias_copies(self):
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="Governance", workflow_name="GovernanceWorkflow",
            summary="s", detailed_response="d",
            mission_state_patch={"phase": "governance_review"},
        )
        # Backward-compat alias must populate engagement_state_patch
        assert resp.engagement_state_patch == {"phase": "governance_review"}

    def test_requires_hitl_and_planned_action_kept(self):
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="ChiefOfStaff", workflow_name="ChiefOfStaffWorkflow",
            summary="s", detailed_response="d",
            requires_hitl=True, planned_action_id="pa-123",
        )
        assert resp.requires_hitl is True
        assert resp.planned_action_id == "pa-123"

    def test_citations_followups_kept(self):
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="TruthAnalyst", workflow_name="TruthAnalysisWorkflow",
            summary="s", detailed_response="d",
            citations=["src1"], followups=["q?"],
        )
        assert resp.citations == ["src1"]
        assert resp.followups == ["q?"]

    def test_serialization_round_trip(self):
        from src.schemas.specialist_response import SpecialistResponse
        resp = SpecialistResponse(
            specialist="WorkflowBuilder", workflow_name="WorkflowBuilderWorkflow",
            summary="s", detailed_response="d",
            objects_read=["Invoice"], objects_written=["WorkflowSpec"],
            actions_proposed=["ApproveInvoice"],
            engagement_state_patch={"phase": "workflow_design"},
            confidence=0.9, unresolved_questions=["clarify threshold?"],
        )
        d = resp.model_dump()
        resp2 = SpecialistResponse.model_validate(d)
        assert resp2.specialist == "WorkflowBuilder"
        assert resp2.objects_written == ["WorkflowSpec"]
        assert resp2.engagement_state_patch == {"phase": "workflow_design"}
        assert resp2.confidence == 0.9
