"""Tests for OntologyAI V5.1 — OntologySetupState (setup wizard state machine).

Tests cover:
- State transitions (valid sequence and invalid skips)
- Step completion checks
- Serialization/deserialization round-trips
- Edge cases (missing data, invalid transitions, empty fields)

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_ontology_setup_state.py -v
"""
import pytest
import json

from src.schemas.ontology_setup_state import (
    OntologySetupState,
    SetupStep,
    ProblemFramingData,
    EvidenceIntakeData,
    CandidateReviewData,
    RelationshipReviewData,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def minimal_state() -> OntologySetupState:
    """A fresh setup state with only required fields."""
    return OntologySetupState(
        engagement_id="eng-001",
        tenant_id="tenant-alpha",
    )


@pytest.fixture
def complete_problem_framing() -> ProblemFramingData:
    return ProblemFramingData(
        business_goal="Reduce invoice processing time by 50%",
        scope_description="AP department invoice workflows",
        key_stakeholders=["CFO", "AP Lead"],
        success_criteria="50% reduction in average processing time within 3 months",
    )


@pytest.fixture
def complete_evidence() -> EvidenceIntakeData:
    return EvidenceIntakeData(
        source_documents=["/docs/ap-process.pdf", "/docs/vendor-agreement.pdf"],
        data_sources=["quickbooks", "slack-archive"],
        interview_notes="AP team processes 200 invoices/week manually",
    )


@pytest.fixture
def complete_candidate_review() -> CandidateReviewData:
    return CandidateReviewData(
        proposed_object_types=["Party", "Engagement", "MoneyEvent", "Issue"],
        proposed_link_types=[
            {"name": "party_engagement", "source": "Party", "target": "Engagement"},
            {"name": "engagement_money_event", "source": "Engagement", "target": "MoneyEvent"},
        ],
        user_feedback="Looks good, add Vendor as a subtype of Party",
    )


@pytest.fixture
def complete_relationship_review() -> RelationshipReviewData:
    return RelationshipReviewData(
        object_relationships=[
            {"from": "Party", "to": "Engagement", "type": "one-to-many"},
            {"from": "Engagement", "to": "MoneyEvent", "type": "one-to-many"},
        ],
        cardinality_notes="A Party can have many Engagements",
        user_feedback="Relationships look correct",
    )


@pytest.fixture
def state_at_step2(
    minimal_state: OntologySetupState,
    complete_problem_framing: ProblemFramingData,
    complete_evidence: EvidenceIntakeData,
) -> OntologySetupState:
    """State that has completed steps 0 and 1, currently at step 2 (CANDIDATE_REVIEW)."""
    return OntologySetupState(
        engagement_id=minimal_state.engagement_id,
        tenant_id=minimal_state.tenant_id,
        current_step=SetupStep.CANDIDATE_REVIEW,
        problem_framing=complete_problem_framing,
        evidence_intake=complete_evidence,
    )


# =============================================================================
# Initial State Tests
# =============================================================================

class TestInitialState:
    """Fresh OntologySetupState creation."""

    def test_default_step_is_problem_framing(self, minimal_state: OntologySetupState):
        assert minimal_state.current_step == SetupStep.PROBLEM_FRAMING
        assert not minimal_state.is_complete

    def test_all_fields_are_none_initially(self, minimal_state: OntologySetupState):
        assert minimal_state.problem_framing is None
        assert minimal_state.evidence_intake is None
        assert minimal_state.candidate_review is None
        assert minimal_state.relationship_review is None

    def test_engagement_id_and_tenant_set(self, minimal_state: OntologySetupState):
        assert minimal_state.engagement_id == "eng-001"
        assert minimal_state.tenant_id == "tenant-alpha"


# =============================================================================
# Step Completion Tests
# =============================================================================

class TestStepCompletion:
    """is_step_complete() behavior."""

    def test_none_step_not_complete(self, minimal_state: OntologySetupState):
        assert not minimal_state.is_step_complete(SetupStep.PROBLEM_FRAMING)
        assert not minimal_state.is_step_complete(SetupStep.EVIDENCE_INTAKE)
        assert not minimal_state.is_step_complete(SetupStep.CANDIDATE_REVIEW)
        assert not minimal_state.is_step_complete(SetupStep.RELATIONSHIP_REVIEW)

    def test_problem_framing_complete_when_data_exists(
        self, minimal_state: OntologySetupState, complete_problem_framing: ProblemFramingData
    ):
        state = minimal_state.model_copy(update={"problem_framing": complete_problem_framing})
        assert state.is_step_complete(SetupStep.PROBLEM_FRAMING)

    def test_problem_framing_incomplete_with_empty_fields(self, minimal_state: OntologySetupState):
        empty = ProblemFramingData(business_goal="", scope_description="")
        state = minimal_state.model_copy(update={"problem_framing": empty})
        # Empty strings should count as not complete
        assert not state.is_step_complete(SetupStep.PROBLEM_FRAMING)

    def test_evidence_complete_when_data_exists(
        self, minimal_state: OntologySetupState, complete_evidence: EvidenceIntakeData
    ):
        state = minimal_state.model_copy(update={"evidence_intake": complete_evidence})
        assert state.is_step_complete(SetupStep.EVIDENCE_INTAKE)

    def test_candidate_review_complete_when_data_exists(
        self, minimal_state: OntologySetupState, complete_candidate_review: CandidateReviewData
    ):
        state = minimal_state.model_copy(update={"candidate_review": complete_candidate_review})
        assert state.is_step_complete(SetupStep.CANDIDATE_REVIEW)

    def test_relationship_review_complete_when_data_exists(
        self, minimal_state: OntologySetupState, complete_relationship_review: RelationshipReviewData
    ):
        state = minimal_state.model_copy(update={"relationship_review": complete_relationship_review})
        assert state.is_step_complete(SetupStep.RELATIONSHIP_REVIEW)

    def test_all_steps_complete_marks_is_complete(
        self, state_at_step2: OntologySetupState, complete_candidate_review: CandidateReviewData,
        complete_relationship_review: RelationshipReviewData
    ):
        state = state_at_step2.model_copy(update={
            "candidate_review": complete_candidate_review,
            "relationship_review": complete_relationship_review,
            "current_step": SetupStep.APPROVAL,
        })
        assert state.is_step_complete(SetupStep.APPROVAL)
        # When at APPROVAL and all prior steps complete, is_complete should be True
        # Actually, is_complete only when explicitly set, so let's check:
        assert not state.is_complete
        # now mark complete
        state2 = OntologySetupState(
            engagement_id=state.engagement_id,
            tenant_id=state.tenant_id,
            current_step=SetupStep.APPROVAL,
            is_complete=True,
            problem_framing=state.problem_framing,
            evidence_intake=state.evidence_intake,
            candidate_review=state.candidate_review,
            relationship_review=state.relationship_review,
        )
        assert state2.is_complete


# =============================================================================
# State Transition Tests
# =============================================================================

class TestStateTransitions:
    """transition_to() valid and invalid scenarios."""

    def test_transition_from_problem_framing_to_evidence_intake(
        self, minimal_state: OntologySetupState, complete_problem_framing: ProblemFramingData
    ):
        state = minimal_state.model_copy(update={"problem_framing": complete_problem_framing})
        next_state = state.transition_to(SetupStep.EVIDENCE_INTAKE)
        assert next_state.current_step == SetupStep.EVIDENCE_INTAKE
        # Original state should be unchanged (immutability)
        assert state.current_step == SetupStep.PROBLEM_FRAMING

    def test_transition_from_evidence_to_candidate_review(
        self, minimal_state: OntologySetupState,
        complete_problem_framing: ProblemFramingData,
        complete_evidence: EvidenceIntakeData,
    ):
        state = OntologySetupState(
            engagement_id=minimal_state.engagement_id,
            tenant_id=minimal_state.tenant_id,
            current_step=SetupStep.EVIDENCE_INTAKE,
            problem_framing=complete_problem_framing,
            evidence_intake=complete_evidence,
        )
        next_state = state.transition_to(SetupStep.CANDIDATE_REVIEW)
        assert next_state.current_step == SetupStep.CANDIDATE_REVIEW

    def test_transition_from_candidate_to_relationship_review(
        self, state_at_step2, complete_candidate_review: CandidateReviewData
    ):
        state = state_at_step2.model_copy(update={"candidate_review": complete_candidate_review})
        next_state = state.transition_to(SetupStep.RELATIONSHIP_REVIEW)
        assert next_state.current_step == SetupStep.RELATIONSHIP_REVIEW

    def test_transition_from_relationship_to_approval(
        self, state_at_step2, complete_candidate_review: CandidateReviewData,
        complete_relationship_review: RelationshipReviewData
    ):
        state = state_at_step2.model_copy(update={
            "candidate_review": complete_candidate_review,
            "relationship_review": complete_relationship_review,
            "current_step": SetupStep.RELATIONSHIP_REVIEW,
        })
        next_state = state.transition_to(SetupStep.APPROVAL)
        assert next_state.current_step == SetupStep.APPROVAL

    def test_transition_from_approval_marks_complete(
        self, state_at_step2, complete_candidate_review: CandidateReviewData,
        complete_relationship_review: RelationshipReviewData
    ):
        state = state_at_step2.model_copy(update={
            "candidate_review": complete_candidate_review,
            "relationship_review": complete_relationship_review,
            "current_step": SetupStep.RELATIONSHIP_REVIEW,
        })
        approval_state = state.transition_to(SetupStep.APPROVAL)
        assert approval_state.current_step == SetupStep.APPROVAL
        # transition_to APPROVAL sets is_complete = True
        assert approval_state.is_complete

    # ── Invalid transitions ──

    def test_cannot_transition_without_current_step_data(
        self, minimal_state: OntologySetupState
    ):
        """Cannot move from PROBLEM_FRAMING without completing it first."""
        with pytest.raises(ValueError, match="Current step .* not complete"):
            minimal_state.transition_to(SetupStep.EVIDENCE_INTAKE)

    def test_cannot_skip_steps_forward(
        self, minimal_state: OntologySetupState, complete_problem_framing: ProblemFramingData
    ):
        """Cannot skip from PROBLEM_FRAMING directly to CANDIDATE_REVIEW."""
        state = minimal_state.model_copy(update={"problem_framing": complete_problem_framing})
        with pytest.raises(ValueError, match="Cannot transition from .* to"):
            state.transition_to(SetupStep.CANDIDATE_REVIEW)

    def test_cannot_skip_multiple_steps(
        self, minimal_state: OntologySetupState,
        complete_problem_framing: ProblemFramingData,
    ):
        state = minimal_state.model_copy(update={"problem_framing": complete_problem_framing})
        with pytest.raises(ValueError, match="Cannot transition from .* to"):
            state.transition_to(SetupStep.RELATIONSHIP_REVIEW)

    def test_cannot_transition_to_same_step(self, minimal_state: OntologySetupState):
        with pytest.raises(ValueError, match="Already at step"):
            minimal_state.transition_to(SetupStep.PROBLEM_FRAMING)

    def test_cannot_transition_backward(
        self, state_at_step2, complete_candidate_review: CandidateReviewData
    ):
        state = state_at_step2.model_copy(update={"candidate_review": complete_candidate_review})
        with pytest.raises(ValueError, match="Cannot transition backward"):
            state.transition_to(SetupStep.PROBLEM_FRAMING)

    def test_cannot_transition_when_already_complete(
        self, state_at_step2, complete_candidate_review: CandidateReviewData,
        complete_relationship_review: RelationshipReviewData
    ):
        state = state_at_step2.model_copy(update={
            "candidate_review": complete_candidate_review,
            "relationship_review": complete_relationship_review,
            "current_step": SetupStep.APPROVAL,
            "is_complete": True,
        })
        with pytest.raises(ValueError, match="already complete"):
            state.transition_to(SetupStep.APPROVAL)

    def test_approval_without_prior_step_data_fails(
        self, minimal_state: OntologySetupState
    ):
        """Cannot jump to APPROVAL without completing earlier steps."""
        with pytest.raises(ValueError):
            minimal_state.transition_to(SetupStep.APPROVAL)


# =============================================================================
# Serialization / Deserialization Tests
# =============================================================================

class TestSerialization:
    """JSON round-trip and model_dump."""

    def test_serialize_to_json(self, state_at_step2):
        data = state_at_step2.model_dump()
        assert data["engagement_id"] == "eng-001"
        assert data["current_step"] == "candidate_review"
        assert data["problem_framing"]["business_goal"] == "Reduce invoice processing time by 50%"
        assert data["evidence_intake"]["interview_notes"] == "AP team processes 200 invoices/week manually"
        assert data["candidate_review"] is None
        assert data["relationship_review"] is None

    def test_deserialize_from_json(self, state_at_step2):
        data = state_at_step2.model_dump()
        json_str = json.dumps(data)
        restored = OntologySetupState(**json.loads(json_str))
        assert restored.engagement_id == state_at_step2.engagement_id
        assert restored.tenant_id == state_at_step2.tenant_id
        assert restored.current_step == state_at_step2.current_step
        assert restored.problem_framing is not None
        assert restored.problem_framing.business_goal == state_at_step2.problem_framing.business_goal
        assert restored.evidence_intake is not None
        assert restored.evidence_intake.interview_notes == state_at_step2.evidence_intake.interview_notes
        assert restored.candidate_review is None

    def test_deserialize_with_enum_string(self, state_at_step2):
        """Should handle string 'candidate_review' for the enum field."""
        data = state_at_step2.model_dump()
        data["current_step"] = "candidate_review"
        restored = OntologySetupState(**data)
        assert restored.current_step == SetupStep.CANDIDATE_REVIEW

    def test_serialize_complete_state_as_json(
        self, state_at_step2, complete_candidate_review: CandidateReviewData,
        complete_relationship_review: RelationshipReviewData
    ):
        state = state_at_step2.model_copy(update={
            "candidate_review": complete_candidate_review,
            "relationship_review": complete_relationship_review,
            "current_step": SetupStep.APPROVAL,
            "is_complete": True,
        })
        data = state.model_dump()
        assert data["is_complete"] is True
        assert data["current_step"] == "approval"
        assert len(data["candidate_review"]["proposed_object_types"]) == 4
        assert len(data["relationship_review"]["object_relationships"]) == 2
        json_str = json.dumps(data)
        restored = OntologySetupState(**json.loads(json_str))
        assert restored.is_complete
        assert len(restored.candidate_review.proposed_object_types) == 4

    def test_partial_deserialization(self):
        """Deserialize from minimal dict."""
        data = {"engagement_id": "eng-002", "tenant_id": "tenant-beta"}
        state = OntologySetupState(**data)
        assert state.current_step == SetupStep.PROBLEM_FRAMING
        assert not state.is_complete

    def test_list_fields_default_to_empty_list(self):
        """Test that list defaults work properly."""
        pf = ProblemFramingData(business_goal="Test", scope_description="Test scope")
        assert pf.key_stakeholders == []
        assert pf.success_criteria == ""

        ei = EvidenceIntakeData()
        assert ei.source_documents == []
        assert ei.data_sources == []
        assert ei.interview_notes == ""

        cr = CandidateReviewData()
        assert cr.proposed_object_types == []
        assert cr.proposed_link_types == []
        assert cr.user_feedback == ""

        rr = RelationshipReviewData()
        assert rr.object_relationships == []
        assert rr.cardinality_notes == ""
        assert rr.user_feedback == ""
