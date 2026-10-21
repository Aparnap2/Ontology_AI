"""E2: Situation business-problem aggregate — Event/Evidence → Situation → Mission → Action → Outcome."""
import pytest
from pydantic import ValidationError

from src.mission.owner_resolution import OwnerResolution
from src.mission.situations import open_situation
from src.ontology.link_types import resolve_link
from src.ontology.object_types import (
    Action,
    ActionResult,
    Evidence,
    Mission,
    Outcome,
    Situation,
)


def _evidence(ev_id: str) -> Evidence:
    return Evidence(
        id=ev_id,
        tenant_id="t-1",
        source="slack",
        provenance="slack:general:alice",
        captured_at="2026-09-09T00:00:00Z",
        raw_text="delivery blocked",
        normalized_text="[slack report]: delivery blocked",
    )


def _resolution(owner: str | None = "u-priya") -> OwnerResolution:
    return OwnerResolution(
        status="RESOLVED",
        owner_id=owner,
        owner_type="user" if owner else None,
        source="OBJECT_OWNER",
        confidence=0.95,
        reason="L1 select",
        candidate_ids=[owner] if owner else [],
        evidence_refs=["ev-1"],
        resolution_path=["L1:OBJECT_OWNER => SELECT"],
        escalation_required=False,
    )


class TestSituationValidation:
    def test_missing_required_fields_rejected(self):
        with pytest.raises(ValidationError):
            Situation(id="sit-1", tenant_id="t-1")  # type: ignore[call-arg]

    def test_bad_status_rejected(self):
        with pytest.raises(ValidationError):
            Situation(
                id="sit-1",
                tenant_id="t-1",
                detected_condition="blocked",
                checkpoint_id="cp-1",
                business_impact="revenue at risk",
                status="BROKEN",  # type: ignore[arg-type]
            )

    def test_defaults(self):
        sit = Situation(
            id="sit-1",
            tenant_id="t-1",
            detected_condition="blocked",
            checkpoint_id="cp-1",
            business_impact="revenue at risk",
        )
        assert sit.type == "DELIVERY_BLOCKER"
        assert sit.status == "OPEN"
        assert sit.owner_id is None

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            Situation(
                id="sit-1",
                tenant_id="t-1",
                detected_condition="blocked",
                checkpoint_id="cp-1",
                business_impact="revenue at risk",
                surprise="boom",
            )


class TestChainLinkage:
    def test_evidence_to_outcome_resolves_end_to_end(self):
        ev1, ev2 = _evidence("ev-1"), _evidence("ev-2")
        sit = open_situation(
            situation_id="sit-1",
            tenant_id="t-1",
            evidence=[ev1, ev2],
            checkpoint_id="cp-1",
            resolution=_resolution(),
            detected_condition="carrier delay blocks order o-9",
            business_impact="o-9 revenue at risk",
            affected_entities=["o-9"],
        )
        mission = Mission(id="m-1", title="unblock o-9", situation_id=sit.id)
        action = Action(
            id="a-1",
            mission_id=mission.id,
            employee_role="ops",
            capability="carrier.escalate",
            idempotency_key="a-1-key",
        )
        result = ActionResult(id="ar-1", action_id=action.id)
        outcome = Outcome(
            id="o-1", mission_id=mission.id, evidence_refs=[ev1.id]
        )
        assert sit.evidence_ids == [ev1.id, ev2.id]
        assert mission.situation_id == sit.id
        assert action.mission_id == mission.id
        assert result.action_id == action.id
        assert outcome.mission_id == mission.id
        assert outcome.evidence_refs[0] in sit.evidence_ids

    def test_onboarding_id_still_present_and_accepted(self):
        assert "onboarding_id" in Mission.model_fields
        mission = Mission(
            id="m-9", title="legacy", onboarding_id="ob-1", situation_id="sit-1"
        )
        assert mission.onboarding_id == "ob-1"
        assert mission.situation_id == "sit-1"


class TestOpenSituation:
    def test_wires_owner_evidence_checkpoint(self):
        sit = open_situation(
            situation_id="sit-2",
            tenant_id="t-1",
            evidence=[_evidence("ev-1")],
            checkpoint_id="cp-7",
            resolution=_resolution("u-ops"),
            detected_condition="blocked",
            business_impact="at risk",
        )
        assert sit.owner_id == "u-ops"
        assert sit.evidence_ids == ["ev-1"]
        assert sit.checkpoint_id == "cp-7"

    def test_no_resolution_leaves_owner_empty(self):
        sit = open_situation(
            situation_id="sit-3",
            tenant_id="t-1",
            evidence=[],
            checkpoint_id="cp-7",
            detected_condition="blocked",
            business_impact="at risk",
        )
        assert sit.owner_id is None
        assert sit.evidence_ids == []


class TestUnknownLinkRejected:
    def test_unknown_link_raises_keyerror(self):
        with pytest.raises(KeyError):
            resolve_link("evidence_situation", "ev-1")
