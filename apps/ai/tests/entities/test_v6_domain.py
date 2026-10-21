"""Entity model validation tests for the V6 Virtual COO domain.

Tests the extended ``Process`` model, the ``BusinessPillar`` enum, and the
new V6 domain entities (ProcessStep, SOP, SOPVersion, Mission, MissionEvent,
MissionSnapshot, Action, ActionResult, EmployeeDefinition, EmployeeRun,
Outcome, Review) — construction, defaults, constraints, and the
``extra="forbid"`` / ``strict=True`` policies.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.entities.models import (
    Action,
    ActionResult,
    BusinessPillar,
    EmployeeDefinition,
    EmployeeRun,
    Mission,
    MissionEvent,
    MissionSnapshot,
    Outcome,
    Process,
    ProcessStep,
    Review,
    SOP,
    SOPVersion,
)


# ═══════════════════════════════════════════════════════════════════════════
# BusinessPillar
# ═══════════════════════════════════════════════════════════════════════════


class TestBusinessPillar:
    def test_exactly_four_pillars(self):
        """The MVP defines exactly four business pillars."""
        assert [p.value for p in BusinessPillar] == [
            "marketing",
            "sales",
            "operations",
            "finance",
        ]

    def test_pillar_is_str_enum(self):
        """BusinessPillar members are usable as plain strings."""
        assert BusinessPillar.SALES == "sales"
        assert str(BusinessPillar.FINANCE) == "BusinessPillar.FINANCE"


# ═══════════════════════════════════════════════════════════════════════════
# Process (extended)
# ═══════════════════════════════════════════════════════════════════════════


class TestProcessExtended:
    def test_minimal_process_still_constructs(self):
        """Backward compatibility: the original required fields still work."""
        p = Process(id="p-1", tenant_id="t1", name="Onboarding")
        assert p.status == "mapped"
        assert p.process_type == "core"
        assert p.pillar is None
        assert p.owner_id is None
        assert p.steps == []

    def test_process_with_pillar_and_owner(self):
        """A fully-specified process carries pillar, owner, and cadence."""
        p = Process(
            id="p-1",
            tenant_id="t1",
            name="Lead Qualification",
            pillar=BusinessPillar.SALES,
            owner_id="stk-1",
            relationship_to_owner="owns",
            objective="Qualify inbound leads within 24h",
            scope="Inbound only",
            decision_rules=["rule-1"],
            definition_of_done=["Leads tagged and routed"],
            kpi_ids=["kpi-1"],
            dependencies=["p-0"],
            allowed_actions=["send_email"],
            review_cadence="monthly",
            process_type="core",
            steps=[
                ProcessStep(
                    id="ps-1",
                    tenant_id="t1",
                    process_id="p-1",
                    name="Capture lead",
                    order_index=1,
                )
            ],
        )
        assert p.pillar == BusinessPillar.SALES
        assert p.relationship_to_owner == "owns"
        assert p.review_cadence == "monthly"
        assert p.steps[0].name == "Capture lead"
        assert p.steps[0].order_index == 1

    def test_invalid_pillar_value_rejected(self):
        """A non-canonical pillar value must raise a ValidationError."""
        with pytest.raises(ValidationError):
            Process(id="p-1", tenant_id="t1", name="x", pillar="hr")

    def test_invalid_relationship_rejected(self):
        """relationship_to_owner must be one of the four literals."""
        with pytest.raises(ValidationError):
            Process(
                id="p-1",
                tenant_id="t1",
                name="x",
                relationship_to_owner="mentors",
            )

    def test_extra_field_forbidden(self):
        """extra='forbid' still rejects unknown fields on Process."""
        with pytest.raises(ValidationError):
            Process(id="p-1", tenant_id="t1", name="x", bogus=1)


# ═══════════════════════════════════════════════════════════════════════════
# ProcessStep
# ═══════════════════════════════════════════════════════════════════════════


class TestProcessStep:
    def test_valid_step(self):
        s = ProcessStep(id="ps-1", tenant_id="t1", process_id="p-1", name="Step")
        assert s.status == "draft"
        assert s.order_index == 0

    def test_step_status_literal(self):
        with pytest.raises(ValidationError):
            ProcessStep(
                id="ps-1",
                tenant_id="t1",
                process_id="p-1",
                name="Step",
                status="gone",
            )


# ═══════════════════════════════════════════════════════════════════════════
# SOP + SOPVersion
# ═══════════════════════════════════════════════════════════════════════════


class TestSOP:
    def test_valid_sop(self):
        sop = SOP(id="sop-1", tenant_id="t1", name="Onboarding SOP")
        assert sop.status == "draft"
        assert sop.current_version_id is None

    def test_sop_status_literal(self):
        with pytest.raises(ValidationError):
            SOP(id="sop-1", tenant_id="t1", name="x", status="published")


class TestSOPVersion:
    def test_valid_version(self):
        v = SOPVersion(
            id="v-1",
            tenant_id="t1",
            sop_id="sop-1",
            version="1.0",
            content_hash="abc123",
            author="alice",
        )
        assert v.changes == []
        assert v.supersedes_id is None

    def test_version_requires_content_hash(self):
        with pytest.raises(ValidationError):
            SOPVersion(
                id="v-1",
                tenant_id="t1",
                sop_id="sop-1",
                version="1.0",
                author="alice",
            )


# ═══════════════════════════════════════════════════════════════════════════
# Mission + MissionEvent + MissionSnapshot
# ═══════════════════════════════════════════════════════════════════════════


class TestMission:
    def test_valid_mission(self):
        m = Mission(id="m-1", tenant_id="t1", title="Reduce churn")
        assert m.status == "pending"
        assert m.priority == "medium"
        assert m.confidence == 0.0

    def test_mission_status_literal(self):
        with pytest.raises(ValidationError):
            Mission(id="m-1", tenant_id="t1", title="x", status="done")

    def test_mission_priority_literal(self):
        with pytest.raises(ValidationError):
            Mission(id="m-1", tenant_id="t1", title="x", priority="critical")

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Mission(id="m-1", tenant_id="t1", title="x", confidence=1.5)


class TestMissionEvent:
    def test_valid_event(self):
        ev = MissionEvent(id="e-1", mission_id="m-1", event_type="created")
        assert ev.version == 1
        assert ev.event_type == "created"

    def test_event_type_accepts_any_verb(self):
        """MissionEvent mirrors MissionEventType verbs but stays open."""
        for verb in [
            "started",
            "reviewed",
            "redirected",
            "confidence_changed",
            "recommendation_updated",
            "archived",
        ]:
            ev = MissionEvent(id="e-1", mission_id="m-1", event_type=verb)
            assert ev.event_type == verb


class TestMissionSnapshot:
    def test_valid_snapshot(self):
        snap = MissionSnapshot(
            id="sn-1", mission_id="m-1", body={"kpi": 1}
        )
        assert snap.snapshot_type == "periodic"
        assert snap.version == 1

    def test_snapshot_type_literal(self):
        with pytest.raises(ValidationError):
            MissionSnapshot(
                id="sn-1",
                mission_id="m-1",
                body={},
                snapshot_type="hourly",
            )


# ═══════════════════════════════════════════════════════════════════════════
# Action + ActionResult
# ═══════════════════════════════════════════════════════════════════════════


class TestAction:
    def test_valid_action(self):
        a = Action(
            id="a-1",
            tenant_id="t1",
            mission_id="m-1",
            employee_role="RevOpsIntern",
            capability="send_email",
            idempotency_key="k-1",
        )
        assert a.risk_tier == "LOW"
        assert a.status == "draft"

    def test_action_requires_idempotency_key(self):
        with pytest.raises(ValidationError):
            Action(
                id="a-1",
                tenant_id="t1",
                mission_id="m-1",
                employee_role="RevOpsIntern",
                capability="send_email",
            )

    def test_risk_tier_literal(self):
        with pytest.raises(ValidationError):
            Action(
                id="a-1",
                tenant_id="t1",
                mission_id="m-1",
                employee_role="RevOpsIntern",
                capability="send_email",
                idempotency_key="k-1",
                risk_tier="EXTREME",
            )

    def test_status_lifecycle_literal(self):
        with pytest.raises(ValidationError):
            Action(
                id="a-1",
                tenant_id="t1",
                mission_id="m-1",
                employee_role="RevOpsIntern",
                capability="send_email",
                idempotency_key="k-1",
                status="done",
            )


class TestActionResult:
    def test_valid_result(self):
        ar = ActionResult(id="ar-1", action_id="a-1")
        assert ar.verified is False
        assert ar.result_summary == ""

    def test_verified_flag(self):
        ar = ActionResult(
            id="ar-1",
            action_id="a-1",
            result_summary="Sent",
            verified=True,
            verified_by="alice",
        )
        assert ar.verified is True
        assert ar.verified_by == "alice"


# ═══════════════════════════════════════════════════════════════════════════
# EmployeeDefinition vs EmployeeRun (config/state separation)
# ═══════════════════════════════════════════════════════════════════════════


class TestEmployeeDefinition:
    def test_valid_definition(self):
        ed = EmployeeDefinition(id="ed-1", tenant_id="t1", role="RevOpsIntern")
        assert ed.risk_threshold == "MEDIUM"
        assert ed.goals == []
        assert ed.memory_namespace == ""

    def test_definition_has_no_runtime_state(self):
        """Config must not carry runtime-only fields."""
        ed = EmployeeDefinition(id="ed-1", tenant_id="t1", role="RevOpsIntern")
        assert not hasattr(ed, "current_mission_id")
        assert not hasattr(ed, "status")


class TestEmployeeRun:
    def test_valid_run(self):
        er = EmployeeRun(
            id="er-1",
            tenant_id="t1",
            employee_definition_id="ed-1",
            role="RevOpsIntern",
        )
        assert er.status == "idle"
        assert er.current_mission_id is None

    def test_run_has_no_config_fields(self):
        """Runtime state must not carry config-only fields."""
        er = EmployeeRun(
            id="er-1",
            tenant_id="t1",
            employee_definition_id="ed-1",
            role="RevOpsIntern",
        )
        assert not hasattr(er, "goals")
        assert not hasattr(er, "capabilities")

    def test_run_status_literal(self):
        with pytest.raises(ValidationError):
            EmployeeRun(
                id="er-1",
                tenant_id="t1",
                employee_definition_id="ed-1",
                role="RevOpsIntern",
                status="retired",
            )


# ═══════════════════════════════════════════════════════════════════════════
# Outcome + Review
# ═══════════════════════════════════════════════════════════════════════════


class TestOutcome:
    def test_valid_outcome(self):
        o = Outcome(id="o-1", tenant_id="t1", mission_id="m-1", result="success")
        assert o.result == "success"
        assert o.evidence_refs == []

    def test_outcome_result_literal(self):
        with pytest.raises(ValidationError):
            Outcome(id="o-1", tenant_id="t1", mission_id="m-1", result="won")


class TestReview:
    def test_valid_review(self):
        r = Review(
            id="r-1",
            tenant_id="t1",
            target_type="Process",
            target_id="p-1",
            reviewer="alice",
        )
        assert r.cadence is None

    def test_review_with_cadence(self):
        r = Review(
            id="r-1",
            tenant_id="t1",
            target_type="Process",
            target_id="p-1",
            reviewer="alice",
            cadence="monthly",
        )
        assert r.cadence == "monthly"