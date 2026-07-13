"""
SpecialistResponse schema for TrackGuard V4.1.

Defines the output contract for specialist agent responses with
canonical specialist names and workflow names enforced via Literal types.

Usage:
    from src.schemas.specialist_response import SpecialistResponse

    resp = SpecialistResponse(
        specialist="Chief of Staff",
        workflow_name="ChiefOfStaffWorkflow",
        summary="Brief summary",
        detailed_response="Full response text",
    )
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional


class SpecialistResponse(BaseModel, strict=True):
    """
    Output contract for specialist agent responses.

    Attributes:
        specialist: One of the 5 canonical specialist display names.
        workflow_name: One of the 5 canonical Temporal workflow names.
        summary: Brief summary of the response.
        detailed_response: Full detailed response text.
        requires_hitl: Whether this response requires human-in-the-loop approval.
        planned_action_id: Optional ID for the planned action.
        mission_state_patch: Optional dict of mission state fields to patch.
        citations: List of source citations.
        followups: List of follow-up questions or actions.
    """
    specialist: Literal["Chief of Staff", "FP&A", "Growth Analytics", "Reliability & Delivery", "Communications"]
    workflow_name: Literal["ChiefOfStaffWorkflow", "FPAWorkflow", "GrowthAnalyticsWorkflow", "ReliabilityWorkflow", "CommsWorkflow"]
    summary: str
    detailed_response: str
    requires_hitl: bool = Field(default=False)
    planned_action_id: Optional[str] = None
    mission_state_patch: Optional[dict] = None
    citations: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
