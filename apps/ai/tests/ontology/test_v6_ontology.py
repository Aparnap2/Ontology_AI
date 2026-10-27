"""TDD tests for OntologyAI V6 — Virtual COO domain ontology.

These tests assert the 16 new Object Types, the 12 new link types, and the
governed write paths for the V6 domain (Process, SOP, Mission, Action,
EmployeeRun, Outcome, Review, KPI).

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/ontology/test_v6_ontology.py -v
"""
import pytest
from pydantic import ValidationError

from src.ontology.object_types import (
    Action,
    ActionResult,
    Employee,
    EmployeeRun,
    KPI,
    Mission,
    MissionEvent,
    MissionSnapshot,
    OBJECT_TYPES,
    Outcome,
    Pillar,
    Process,
    ProcessStep,
    Review,
    SOP,
    SOPVersion,
    Stakeholder,
)
from src.ontology.link_types import LINK_TYPES, LinkType, validate_link_types
from src.ontology.governance import (
    GovernanceError,
    OBJECT_WRITE_POLICY,
    governed_action_execute,
    governed_employee_pause,
    governed_kpi_target_change,
    governed_mission_redirect,
    governed_outcome_record,
    governed_process_owner_change,
    governed_review_schedule,
    governed_sop_publish,
)


# ---------------------------------------------------------------------------
# Object Type: valid construction
# ---------------------------------------------------------------------------
class TestV6ObjectTypeValidConstruction:
    def test_stakeholder_valid(self):
        s = Stakeholder(
            id="stk-1", name="Alice", email="a@x.com", role="Process Owner",
            status="active", source_refs=["src1"],
        )
        assert s.role == "Process Owner"

    def test_pillar_valid(self):
        p = Pillar(id="pl-1", name="sales", status="active", source_refs=[])
        assert p.name == "sales"

    def test_process_valid(self):
        p = Process(
            id="p-1", name="Lead Qualification", pillar="sales",
            owner_id="stk-1", status="mapped", process_type="core",
            source_refs=[],
        )
        assert p.pillar == "sales"

    def test_process_step_valid(self):
        ps = ProcessStep(
            id="ps-1", process_id="p-1", name="Capture lead",
            order_index=1, owner_id=None, status="draft", source_refs=[],
        )
        assert ps.order_index == 1

    def test_sop_valid(self):
        sop = SOP(
            id="sop-1", name="Onboarding SOP", process_id="p-1",
            owner_id="stk-1", status="draft", current_version_id=None,
            source_refs=[],
        )
        assert sop.status == "draft"

    def test_sop_version_valid(self):
        v = SOPVersion(
            id="v-1", sop_id="sop-1", version="1.0", content_hash="abc",
            status="draft", source_refs=[],
        )
        assert v.content_hash == "abc"

    def test_employee_valid(self):
        e = Employee(id="emp-1", role="RevOpsIntern", status="active", source_refs=[])
        assert e.role == "RevOpsIntern"

    def test_employee_run_valid(self):
        er = EmployeeRun(
            id="er-1", employee_id="emp-1", status="idle",
            current_mission_id=None, source_refs=[],
        )
        assert er.status == "idle"

    def test_mission_valid(self):
        m = Mission(
            id="m-1", title="Reduce churn", status="pending",
            priority="medium", owner_id="stk-1", employee_role="RevOpsIntern",
            source_refs=[],
        )
        assert m.status == "pending"

    def test_mission_event_valid(self):
        ev = MissionEvent(
            id="e-1", mission_id="m-1", event_type="created",
            version=1, source_refs=[],
        )
        assert ev.event_type == "created"

    def test_mission_snapshot_valid(self):
        snap = MissionSnapshot(
            id="sn-1", mission_id="m-1", version=1,
            snapshot_type="periodic", source_refs=[],
        )
        assert snap.snapshot_type == "periodic"

    def test_action_valid(self):
        a = Action(
            id="a-1", mission_id="m-1", employee_role="RevOpsIntern",
            capability="send_email", risk_tier="LOW", status="draft",
            idempotency_key="k-1", source_refs=[],
        )
        assert a.idempotency_key == "k-1"

    def test_action_result_valid(self):
        ar = ActionResult(
            id="ar-1", action_id="a-1", result_summary="Sent",
            verified=False, source_refs=[],
        )
        assert ar.verified is False

    def test_outcome_valid(self):
        o = Outcome(
            id="o-1", mission_id="m-1", result="success",
            evidence_refs=["ev-1"], source_refs=[],
        )
        assert o.evidence_refs == ["ev-1"]

    def test_review_valid(self):
        r = Review(
            id="r-1", target_type="Process", target_id="p-1",
            reviewer="alice", cadence="monthly", source_refs=[],
        )
        assert r.cadence == "monthly"

    def test_kpi_valid(self):
        k = KPI(
            id="kpi-1", name="Lead conversion", target_value=0.25,
            unit="%", owner_id="stk-1", status="active", source_refs=[],
        )
        assert k.target_value == 0.25


# ---------------------------------------------------------------------------
# Object Type: strict + extra="forbid" rejects unknown fields
# ---------------------------------------------------------------------------
class TestV6ObjectTypeRejectsExtraFields:
    def test_process_rejects_extra(self):
        with pytest.raises(ValidationError):
            Process(id="p-1", name="x", pillar="sales", surprise="boom")

    def test_mission_rejects_extra(self):
        with pytest.raises(ValidationError):
            Mission(id="m-1", title="x", status="pending", bogus=1)

    def test_action_rejects_extra(self):
        with pytest.raises(ValidationError):
            Action(
                id="a-1", mission_id="m-1", employee_role="r",
                capability="c", idempotency_key="k", extra=1,
            )


# ---------------------------------------------------------------------------
# Object Type: strict typing rejects wrong types / literals
# ---------------------------------------------------------------------------
class TestV6ObjectTypeStrictTyping:
    def test_pillar_name_literal(self):
        with pytest.raises(ValidationError):
            Pillar(id="pl-1", name="hr", status="active", source_refs=[])

    def test_process_status_literal(self):
        with pytest.raises(ValidationError):
            Process(id="p-1", name="x", status="done")

    def test_mission_priority_literal(self):
        with pytest.raises(ValidationError):
            Mission(id="m-1", title="x", priority="critical")

    def test_action_risk_tier_literal(self):
        with pytest.raises(ValidationError):
            Action(
                id="a-1", mission_id="m-1", employee_role="r",
                capability="c", idempotency_key="k", risk_tier="EXTREME",
            )

    def test_kpi_target_value_wrong_type(self):
        with pytest.raises(ValidationError):
            KPI(
                id="kpi-1", name="x", target_value="high",
                unit="%", owner_id=None, status="active", source_refs=[],
            )


# ---------------------------------------------------------------------------
# OBJECT_TYPES registry contains the 23 canonical types
# ---------------------------------------------------------------------------
class TestV6ObjectTypeRegistry:
    def test_registry_contains_v6_types(self):
        for name in [
            "Stakeholder", "Pillar", "Process", "ProcessStep", "SOP",
            "SOPVersion", "Employee", "EmployeeRun", "Mission",
            "MissionEvent", "MissionSnapshot", "Action", "ActionResult",
            "Outcome", "Review", "KPI",
        ]:
            assert name in OBJECT_TYPES, name

    def test_registry_total_count(self):
        assert len(OBJECT_TYPES) == 27


# ---------------------------------------------------------------------------
# LINK_TYPES registry — 24 canonical links including the 12 V6 links
# ---------------------------------------------------------------------------
class TestV6LinkTypesRegistry:
    V6_EXPECTED = {
        "stakeholder_owns_process", "process_has_sop", "sop_versions",
        "employee_runs_mission", "mission_involves_process",
        "mission_generates_actions", "action_targets_entity",
        "action_result_from", "action_results_of", "review_of_process",
        "outcome_of_mission", "kpi_monitors_entity",
    }

    def test_all_v6_links_present(self):
        assert self.V6_EXPECTED <= set(LINK_TYPES.keys())

    def test_total_link_count(self):
        assert len(LINK_TYPES) == 24

    def test_each_v6_link_is_linktype_with_required_fields(self):
        for name in self.V6_EXPECTED:
            lt = LINK_TYPES[name]
            assert isinstance(lt, LinkType)
            assert lt.name == name
            assert lt.source_type
            assert lt.target_type
            assert lt.cardinality
            assert lt.semantic_meaning

    def test_stakeholder_owns_process_link(self):
        lt = LINK_TYPES["stakeholder_owns_process"]
        assert lt.source_type == "Stakeholder"
        assert lt.target_type == "Process"
        assert lt.cardinality == "one_to_many"

    def test_wildcard_target_links(self):
        assert LINK_TYPES["action_targets_entity"].target_type == "*"
        assert LINK_TYPES["kpi_monitors_entity"].target_type == "*"

    def test_validate_link_types_passes(self):
        """All 24 links resolve against OBJECT_TYPES / Workflow / *."""
        assert validate_link_types() is None


# ---------------------------------------------------------------------------
# Governed writes for V6 object types
# ---------------------------------------------------------------------------
class TestV6GovernedWrites:
    def test_policy_entries_present(self):
        for name in [
            "Process", "SOP", "Mission", "Action", "EmployeeRun",
            "Outcome", "Review", "KPI",
        ]:
            assert name in OBJECT_WRITE_POLICY, name

    def test_low_blast_write_passes_through(self):
        """Review.cadence is low blast — no approval required."""
        result = governed_review_schedule("r-1", "weekly")
        assert result == {"updated": "r-1", "cadence": "weekly"}

    def test_medium_blast_write_blocks_without_planned_action(self):
        """Process.owner_id requires approval — blocks with GovernanceError."""
        with pytest.raises(GovernanceError):
            governed_process_owner_change("p-1", "stk-2")

    def test_high_blast_write_blocks(self):
        """Action.status is high blast — blocks with GovernanceError."""
        with pytest.raises(GovernanceError):
            governed_action_execute("a-1", "executing")

    def test_medium_blast_write_blocks_with_planned_action(self):
        """Providing create_planned_action produces a PlannedAction and BLOCKS."""
        created: list = []

        def create_planned_action(**kwargs):
            pa = {"id": "pa-1", "status": "pending_approval", **kwargs}
            created.append(pa)
            return pa

        result = governed_process_owner_change(
            "p-1", "stk-2", create_planned_action=create_planned_action
        )
        assert len(created) == 1
        assert result["id"] == "pa-1"
        assert result["status"] == "pending_approval"

    def test_mission_redirect_blocks(self):
        with pytest.raises(GovernanceError):
            governed_mission_redirect("m-1", "active")

    def test_employee_pause_blocks(self):
        with pytest.raises(GovernanceError):
            governed_employee_pause("emp-1", "paused")

    def test_outcome_record_blocks(self):
        with pytest.raises(GovernanceError):
            governed_outcome_record("o-1", "success")

    def test_sop_publish_blocks(self):
        with pytest.raises(GovernanceError):
            governed_sop_publish("sop-1", "active")

    def test_kpi_target_change_blocks(self):
        with pytest.raises(GovernanceError):
            governed_kpi_target_change("kpi-1", 0.5)