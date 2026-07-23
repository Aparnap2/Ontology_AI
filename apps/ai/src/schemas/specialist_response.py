"""
SpecialistResponse schema for OntologyAI V5.1 (PRD §15.1).

Defines the output contract for specialist agent responses with the V5.1
canonical specialist names and workflow names enforced via Literal types.

The V5.1 rebrand migrates the specialist/workflow Literal sets to the new
canonical names and renames ``mission_state_patch`` -> ``engagement_state_patch``.
A backward-compatible alias accepts the old ``mission_state_patch`` keyword and
copies it into ``engagement_state_patch`` so existing callers do not break.

Usage:
    from src.schemas.specialist_response import SpecialistResponse

    resp = SpecialistResponse(
        specialist="ChiefOfStaff",
        workflow_name="ChiefOfStaffWorkflow",
        summary="Brief summary",
        detailed_response="Full response text",
    )
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SpecialistResponse(BaseModel, strict=True):
    """
    Output contract for specialist agent responses (PRD §15.1).

    Attributes:
        specialist: One of the 6 canonical V5.1 specialist names.
        workflow_name: One of the 6 canonical V5.1 Temporal workflow names.
        summary: Brief summary of the response.
        detailed_response: Full detailed response text.
        objects_read: Ontology object types read by this response.
        objects_written: Ontology object types written by this response.
        actions_proposed: Action type IDs proposed by this response.
        requires_hitl: Whether this response requires human-in-the-loop approval.
        planned_action_id: Optional ID for the planned action.
        engagement_state_patch: Optional dict of engagement-state fields to patch.
        citations: List of source citations.
        followups: List of follow-up questions or actions.
        confidence: Optional model confidence in [0, 1].
        unresolved_questions: Open questions this response could not resolve.
    """

    # V5.1 canonical: 6 specialists. V6 adds "Strategy" (gated behind
    # ENABLE_V6_WORKFLOWS=on), included here so StrategyWorkflow can
    # construct valid responses at runtime without conditional imports.
    specialist: Literal[
        "Discovery",
        "OntologyMapper",
        "TruthAnalyst",
        "WorkflowBuilder",
        "Governance",
        "ChiefOfStaff",
        "Strategy",
    ]
    # V5.1 canonical: 6 workflow names. V6 adds "StrategyWorkflow".
    workflow_name: Literal[
        "ChiefOfStaffWorkflow",
        "DiscoveryWorkflow",
        "OntologyMappingWorkflow",
        "TruthAnalysisWorkflow",
        "WorkflowBuilderWorkflow",
        "GovernanceWorkflow",
        "StrategyWorkflow",
    ]
    summary: str
    detailed_response: str
    objects_read: list[str] = Field(default_factory=list)
    objects_written: list[str] = Field(default_factory=list)
    actions_proposed: list[str] = Field(default_factory=list)
    requires_hitl: bool = Field(default=False)
    planned_action_id: Optional[str] = None
    engagement_state_patch: Optional[dict] = None
    citations: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _alias_mission_state_patch(cls, data: object) -> object:
        """Backward-compat: copy legacy ``mission_state_patch`` into ``engagement_state_patch``.

        Existing callers still pass ``mission_state_patch``. If provided and
        ``engagement_state_patch`` is not, copy it over so the value is not lost.
        """
        if isinstance(data, dict):
            if "mission_state_patch" in data and data["mission_state_patch"] is not None:
                if data.get("engagement_state_patch") is None:
                    data["engagement_state_patch"] = data["mission_state_patch"]
        return data
