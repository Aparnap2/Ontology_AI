"""OntologyAI V5.1 — OntologySetupState (PRD §14.3 / §25.2).

The ontology setup wizard is a guided 5-step HTMX flow that orchestrates
existing ChiefOfStaff + Discovery + OntologyMapping workflows. This module
defines the Pydantic state models for the wizard's step-by-step UX.

Design (UX/orchestration layer, NOT a new workflow):
  * ``OntologySetupState`` tracks the current step, tenant, and engagement.
  * Transition logic is deterministic — forward-only, sequential, validated.
  * Serialization is JSON-compatible for Windmill persistence (ADR-009).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SetupStep(str, Enum):
    """Ordered steps in the ontology setup wizard."""
    PROBLEM_FRAMING = "problem_framing"
    EVIDENCE_INTAKE = "evidence_intake"
    CANDIDATE_REVIEW = "candidate_review"
    RELATIONSHIP_REVIEW = "relationship_review"
    APPROVAL = "approval"


# ── Ordered sequence for deterministic transition validation ──────────
_STEP_ORDER: list[SetupStep] = [
    SetupStep.PROBLEM_FRAMING,
    SetupStep.EVIDENCE_INTAKE,
    SetupStep.CANDIDATE_REVIEW,
    SetupStep.RELATIONSHIP_REVIEW,
    SetupStep.APPROVAL,
]


class ProblemFramingData(BaseModel):
    """Step 1: Business context and scope definition."""
    business_goal: str = ""
    scope_description: str = ""
    key_stakeholders: list[str] = Field(default_factory=list)
    success_criteria: str = ""


class EvidenceIntakeData(BaseModel):
    """Step 2: Source documents and data sources."""
    source_documents: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    interview_notes: str = ""


class CandidateReviewData(BaseModel):
    """Step 3: Review proposed ontology object and link types."""
    proposed_object_types: list[str] = Field(default_factory=list)
    proposed_link_types: list[dict] = Field(default_factory=list)
    user_feedback: str = ""


class RelationshipReviewData(BaseModel):
    """Step 4: Review object relationships and cardinality."""
    object_relationships: list[dict] = Field(default_factory=list)
    cardinality_notes: str = ""
    user_feedback: str = ""


def _is_data_populated(data: Optional[BaseModel]) -> bool:
    """Check if a step data model has at least one meaningful field populated.

    A model is considered "populated" if at least one string field is
    non-empty or at least one list field is non-empty.
    """
    if data is None:
        return False
    for field_name, field_value in data:
        if isinstance(field_value, str) and field_value.strip():
            return True
        if isinstance(field_value, list) and field_value:
            return True
    return False


class OntologySetupState(BaseModel):
    """Wizard state for the 5-step ontology setup flow.

    The state is immutable — ``transition_to`` returns a new instance.
    Serializes to JSON for Windmill / Redis persistence.
    """
    engagement_id: str
    tenant_id: str
    current_step: SetupStep = SetupStep.PROBLEM_FRAMING
    is_complete: bool = False

    # Step data (None = not yet started/incomplete)
    problem_framing: Optional[ProblemFramingData] = None
    evidence_intake: Optional[EvidenceIntakeData] = None
    candidate_review: Optional[CandidateReviewData] = None
    relationship_review: Optional[RelationshipReviewData] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transition_to(self, step: SetupStep) -> OntologySetupState:
        """Validate and transition to the next step.

        Returns a NEW ``OntologySetupState`` with the updated step.
        The original state is never mutated.

        Raises:
            ValueError: If the transition is invalid (wrong order, missing
                        data, already complete).
        """
        if self.is_complete:
            raise ValueError(
                f"Setup is already complete. Cannot transition to {step.value}."
            )

        if step == self.current_step:
            raise ValueError(
                f"Already at step '{step.value}'. Cannot transition to the same step."
            )

        current_idx = _STEP_ORDER.index(self.current_step)
        target_idx = _STEP_ORDER.index(step)

        # Validate forward-only
        if target_idx <= current_idx:
            raise ValueError(
                f"Cannot transition backward from '{self.current_step.value}' "
                f"to '{step.value}'."
            )

        # Validate sequential (no skipping)
        if target_idx != current_idx + 1:
            raise ValueError(
                f"Cannot transition from '{self.current_step.value}' to "
                f"'{step.value}'. Steps must be sequential."
            )

        # Validate current step data exists
        if not self.is_step_complete(self.current_step):
            raise ValueError(
                f"Current step '{self.current_step.value}' is not complete. "
                f"Please complete it before proceeding."
            )

        # Transition is valid — build new state
        is_complete = step == SetupStep.APPROVAL
        return OntologySetupState(
            engagement_id=self.engagement_id,
            tenant_id=self.tenant_id,
            current_step=step,
            is_complete=is_complete,
            problem_framing=self.problem_framing,
            evidence_intake=self.evidence_intake,
            candidate_review=self.candidate_review,
            relationship_review=self.relationship_review,
        )

    def is_step_complete(self, step: SetupStep) -> bool:
        """Check if a given step has been completed (data populated)."""
        mapping = {
            SetupStep.PROBLEM_FRAMING: self.problem_framing,
            SetupStep.EVIDENCE_INTAKE: self.evidence_intake,
            SetupStep.CANDIDATE_REVIEW: self.candidate_review,
            SetupStep.RELATIONSHIP_REVIEW: self.relationship_review,
            SetupStep.APPROVAL: None,  # Approval is always "complete" when reached
        }
        data = mapping.get(step)
        if step == SetupStep.APPROVAL:
            # Approval is complete when all prior steps are complete
            return all(
                self.is_step_complete(s)
                for s in _STEP_ORDER
                if s != SetupStep.APPROVAL
            )
        return _is_data_populated(data)
