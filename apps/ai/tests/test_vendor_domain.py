"""V7 vendor operations domain models (Phase 3: models only).

Per-model validation, relation wiring against co-created fixtures,
tenant scoping, SLA deadline sanity, ROI source-event linkage,
Situation additive types, and the Outcome canonical-state mapping.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.entities.models import (
    OUTCOME_CANONICAL_TO_RESULT,
    OUTCOME_RESULT_TO_CANONICAL,
    BusinessImpact,
    EscalationPolicy,
    Incident,
    Outcome,
    ROIMeasurement,
    Service,
    ServiceDependency,
    SLA,
    Vendor,
    VendorContract,
    VendorTicket,
    canonical_outcome_state,
    outcome_result_from_canonical,
)
from src.ontology.object_types import Situation


def _ts() -> datetime:
    return datetime(2026, 9, 12, tzinfo=timezone.utc)


# ── fixtures: one co-created tenant graph ──────────────────────────────


@pytest.fixture()
def vendor() -> Vendor:
    return Vendor(
        id="v-acme",
        tenant_id="t-1",
        name="Acme Logistics",
        status="active",
        contacts=["ops@acme.example"],
        services=["svc-freight"],
        metadata={"tier": "preferred"},
    )


@pytest.fixture()
def service() -> Service:
    return Service(
        id="svc-freight",
        tenant_id="t-1",
        name="Freight API",
        criticality="high",
        owner_id="u-ops",
        vendor_id="v-acme",
    )


@pytest.fixture()
def contract() -> VendorContract:
    return VendorContract(
        id="vc-1",
        tenant_id="t-1",
        vendor_id="v-acme",
        service_ids=["svc-freight"],
        terms_summary="99.9% monthly availability",
        active=True,
    )


@pytest.fixture()
def policy() -> EscalationPolicy:
    return EscalationPolicy(
        id="ep-1",
        tenant_id="t-1",
        name="freight escalation",
        t0_vendor_primary="c-acme-primary",
        t1_vendor_escalation="c-acme-duty-manager",
        t2_internal_owner="u-ops",
        t3_hitl_material="u-founder",
        authority={"t3": "founder approval required"},
        requires_hitl=True,
    )


@pytest.fixture()
def sla(service: Service, contract: VendorContract, policy: EscalationPolicy) -> SLA:
    return SLA(
        id="sla-1",
        tenant_id="t-1",
        name="freight availability",
        service_id=service.id,
        contract_id=contract.id,
        priority="high",
        acknowledgement_minutes=15,
        update_minutes=60,
        resolution_minutes=240,
        escalation_policy_id=policy.id,
        business_calendar="24x7",
        active=True,
    )


@pytest.fixture()
def incident(service: Service, vendor: Vendor, sla: SLA) -> Incident:
    return Incident(
        id="inc-1",
        tenant_id="t-1",
        title="Freight API down",
        description="tracking endpoint 500s",
        severity="high",
        status="open",
        service_id=service.id,
        vendor_id=vendor.id,
        business_process_ids=["proc-dispatch"],
        detected_at=_ts(),
        impact=BusinessImpact(
            customer_impact_count=42,
            affected_process_ids=["proc-dispatch"],
            severity="high",
            estimated_downtime_minutes=120,
            criticality="high",
        ),
        sla_id=sla.id,
        owner_id="u-ops",
        situation_id="sit-1",
        evidence_refs=["ev-1"],
    )


# ── Vendor ─────────────────────────────────────────────────────────────


class TestVendor:
    def test_valid(self, vendor: Vendor):
        assert vendor.tenant_id == "t-1"
        assert vendor.contacts == ["ops@acme.example"]
        assert vendor.services == ["svc-freight"]

    def test_bad_status_rejected(self):
        with pytest.raises(ValidationError):
            Vendor(id="v-1", tenant_id="t-1", name="X", status="deleted")

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            Vendor(id="v-1", name="X")  # type: ignore[call-arg]

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            Vendor(id="v-1", tenant_id="t-1", name="X", bogus=1)  # type: ignore[call-arg]

    def test_defaults(self):
        v = Vendor(id="v-1", tenant_id="t-1", name="X")
        assert v.status == "active"
        assert v.contacts == [] and v.services == [] and v.metadata == {}


# ── Service / ServiceDependency ────────────────────────────────────────


class TestService:
    def test_valid(self, service: Service):
        assert service.vendor_id == "v-acme"
        assert service.owner_id == "u-ops"

    def test_bad_criticality_rejected(self):
        with pytest.raises(ValidationError):
            Service(
                id="s-1",
                tenant_id="t-1",
                name="X",
                criticality="extreme",  # type: ignore[arg-type]
                owner_id="u-1",
                vendor_id="v-1",
            )

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            Service(id="s-1", name="X", owner_id="u-1", vendor_id="v-1")  # type: ignore[call-arg]


class TestServiceDependency:
    def test_valid(self):
        d = ServiceDependency(
            id="dep-1", tenant_id="t-1", service_a_id="svc-a", service_b_id="svc-b"
        )
        assert d.dependency_type == "DEPENDS_ON"

    def test_wrong_dependency_type_rejected(self):
        with pytest.raises(ValidationError):
            ServiceDependency(
                id="dep-1",
                tenant_id="t-1",
                service_a_id="svc-a",
                service_b_id="svc-b",
                dependency_type="CALLS",  # type: ignore[arg-type]
            )

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            ServiceDependency(id="dep-1", service_a_id="a", service_b_id="b")  # type: ignore[call-arg]


# ── VendorContract / SLA ───────────────────────────────────────────────


class TestVendorContract:
    def test_valid(self, contract: VendorContract):
        assert contract.vendor_id == "v-acme"
        assert contract.service_ids == ["svc-freight"]
        assert contract.active is True

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            VendorContract(id="vc-1", vendor_id="v-1")  # type: ignore[call-arg]


class TestSLA:
    def test_valid(self, sla: SLA):
        assert sla.acknowledgement_minutes == 15
        assert sla.update_minutes == 60
        assert sla.resolution_minutes == 240

    def test_non_positive_minutes_rejected(self):
        with pytest.raises(ValidationError):
            SLA(
                id="sla-x",
                tenant_id="t-1",
                name="X",
                service_id="s-1",
                contract_id="c-1",
                acknowledgement_minutes=0,
                resolution_minutes=60,
                escalation_policy_id="ep-1",
            )
        with pytest.raises(ValidationError):
            SLA(
                id="sla-x",
                tenant_id="t-1",
                name="X",
                service_id="s-1",
                contract_id="c-1",
                acknowledgement_minutes=15,
                update_minutes=-5,
                resolution_minutes=60,
                escalation_policy_id="ep-1",
            )
        with pytest.raises(ValidationError):
            SLA(
                id="sla-x",
                tenant_id="t-1",
                name="X",
                service_id="s-1",
                contract_id="c-1",
                acknowledgement_minutes=15,
                resolution_minutes=-1,
                escalation_policy_id="ep-1",
            )

    def test_update_minutes_optional(self, sla: SLA):
        assert sla.update_minutes == 60
        clone = sla.model_copy(update={"update_minutes": None})
        assert clone.update_minutes is None

    def test_bad_priority_rejected(self):
        with pytest.raises(ValidationError):
            SLA(
                id="sla-x",
                tenant_id="t-1",
                name="X",
                service_id="s-1",
                contract_id="c-1",
                priority="p0",  # type: ignore[arg-type]
                acknowledgement_minutes=15,
                resolution_minutes=60,
                escalation_policy_id="ep-1",
            )

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            SLA(  # type: ignore[call-arg]
                id="sla-x",
                name="X",
                service_id="s-1",
                contract_id="c-1",
                acknowledgement_minutes=15,
                resolution_minutes=60,
                escalation_policy_id="ep-1",
            )


# ── Incident / BusinessImpact ──────────────────────────────────────────


class TestIncident:
    def test_valid(self, incident: Incident):
        assert incident.status == "open"
        assert incident.impact.customer_impact_count == 42
        assert incident.version == 1

    def test_bad_status_rejected(self):
        with pytest.raises(ValidationError):
            Incident(
                id="inc-x",
                tenant_id="t-1",
                title="X",
                status="triaged",  # type: ignore[arg-type]
                service_id="s-1",
            )

    def test_bad_severity_rejected(self):
        with pytest.raises(ValidationError):
            Incident(
                id="inc-x",
                tenant_id="t-1",
                title="X",
                severity="severe",  # type: ignore[arg-type]
                service_id="s-1",
            )

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            Incident(id="inc-x", title="X", service_id="s-1")  # type: ignore[call-arg]

    def test_full_lifecycle_statuses(self, incident: Incident):
        for status in (
            "open",
            "acknowledged",
            "escalated",
            "awaiting_evidence",
            "verified",
            "closed",
        ):
            assert incident.model_copy(update={"status": status}).status == status

    def test_negative_downtime_rejected(self):
        with pytest.raises(ValidationError):
            BusinessImpact(estimated_downtime_minutes=-10)

    def test_negative_customer_count_rejected(self):
        with pytest.raises(ValidationError):
            BusinessImpact(customer_impact_count=-1)

    def test_relation_integrity(
        self, incident: Incident, service: Service, vendor: Vendor, sla: SLA
    ):
        assert incident.service_id == service.id
        assert incident.vendor_id == vendor.id
        assert incident.sla_id == sla.id
        assert sla.service_id == service.id
        assert sla.contract_id == "vc-1"
        assert service.vendor_id == vendor.id
        tenants = {
            incident.tenant_id,
            service.tenant_id,
            vendor.tenant_id,
            sla.tenant_id,
        }
        assert tenants == {"t-1"}


# ── VendorTicket ───────────────────────────────────────────────────────


class TestVendorTicket:
    def test_valid(self, incident: Incident):
        t = VendorTicket(
            id="vt-1",
            tenant_id="t-1",
            vendor_id="v-acme",
            incident_id=incident.id,
            external_ticket_id="ACME-9876",
            status="open",
            opened_at=_ts(),
            external_url="https://acme.example/t/9876",
        )
        assert t.incident_id == "inc-1"
        assert t.external_ticket_id == "ACME-9876"

    def test_bad_status_rejected(self):
        with pytest.raises(ValidationError):
            VendorTicket(
                id="vt-1",
                tenant_id="t-1",
                vendor_id="v-1",
                incident_id="inc-1",
                external_ticket_id="X-1",
                status="stuck",  # type: ignore[arg-type]
            )

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            VendorTicket(  # type: ignore[call-arg]
                id="vt-1",
                vendor_id="v-1",
                incident_id="inc-1",
                external_ticket_id="X-1",
            )


# ── EscalationPolicy ───────────────────────────────────────────────────


class TestEscalationPolicy:
    def test_valid(self, policy: EscalationPolicy):
        assert policy.t0_vendor_primary == "c-acme-primary"
        assert policy.t3_hitl_material == "u-founder"
        assert policy.requires_hitl is True
        assert policy.authority == {"t3": "founder approval required"}

    def test_missing_tier_rejected(self):
        with pytest.raises(ValidationError):
            EscalationPolicy(  # type: ignore[call-arg]
                id="ep-x",
                tenant_id="t-1",
                name="X",
                t0_vendor_primary="c-1",
            )

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            EscalationPolicy(  # type: ignore[call-arg]
                id="ep-x",
                name="X",
                t0_vendor_primary="c-1",
                t1_vendor_escalation="c-2",
                t2_internal_owner="u-1",
                t3_hitl_material="u-2",
            )


# ── Tenant isolation ───────────────────────────────────────────────────
# Models hold REFERENCE IDs only; cross-tenant ref rejection is an
# application-layer concern (no registry exists in this models-only
# phase). What the models enforce: tenant_id is required everywhere and
# fixtures from different tenants never compare equal.


class TestTenantIsolation:
    def test_all_top_level_models_require_tenant(self):
        with pytest.raises(ValidationError):
            Vendor(id="v-1", name="X")  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            Incident(id="i-1", title="X", service_id="s-1")  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ROIMeasurement(id="r-1", mission_id="m-1", situation_id="s-1", metric_type="m")  # type: ignore[call-arg]

    def test_cross_tenant_wiring_is_visible(self, service: Service):
        other_vendor = Vendor(id="v-acme", tenant_id="t-2", name="Acme")
        assert other_vendor.tenant_id != service.tenant_id
        # Documented: models do not auto-reject cross-tenant ID refs;
        # the application layer must check tenant equality on refs.


# ── ROIMeasurement ─────────────────────────────────────────────────────


class TestROIMeasurement:
    def test_valid_with_source_events(self):
        m = ROIMeasurement(
            id="roi-1",
            tenant_id="t-1",
            mission_id="m-1",
            situation_id="sit-1",
            metric_type="downtime_minutes_avoided",
            baseline_value=240.0,
            actual_value=60.0,
            unit="minutes",
            source_event_ids=["mev-1", "mev-2"],
            measured_at=_ts(),
        )
        assert m.source_event_ids == ["mev-1", "mev-2"]
        assert m.baseline_value == 240.0

    def test_null_baseline_actual_allowed(self):
        m = ROIMeasurement(
            id="roi-1",
            tenant_id="t-1",
            mission_id="m-1",
            situation_id="sit-1",
            metric_type="csat",
            unit="score",
        )
        assert m.baseline_value is None and m.actual_value is None

    def test_no_savings_claim_fields(self):
        assert "savings" not in ROIMeasurement.model_fields
        assert "projected" not in ROIMeasurement.model_fields
        assert "claimed" not in ROIMeasurement.model_fields

    def test_tenant_required(self):
        with pytest.raises(ValidationError):
            ROIMeasurement(id="r-1", mission_id="m-1", situation_id="s-1", metric_type="m")  # type: ignore[call-arg]


# ── Situation additive types ───────────────────────────────────────────


class TestSituationVendorTypes:
    @pytest.mark.parametrize(
        "stype",
        ["VENDOR_INCIDENT", "SLA_RISK", "VENDOR_PERFORMANCE_ISSUE"],
    )
    def test_new_types_accepted(self, stype: str):
        sit = Situation(
            id="sit-v1",
            tenant_id="t-1",
            type=stype,  # type: ignore[arg-type]
            detected_condition="vendor outage",
            checkpoint_id="cp-1",
            business_impact="dispatch blocked",
        )
        assert sit.type == stype

    @pytest.mark.parametrize(
        "stype",
        [
            "DELIVERY_BLOCKER",
            "RESOURCE_RISK",
            "DEPENDENCY_DELAY",
            "QUALITY_DEFECT",
            "SCOPE_DRIFT",
        ],
    )
    def test_old_types_intact(self, stype: str):
        sit = Situation(
            id="sit-v1",
            tenant_id="t-1",
            type=stype,  # type: ignore[arg-type]
            detected_condition="blocked",
            checkpoint_id="cp-1",
            business_impact="at risk",
        )
        assert sit.type == stype


# ── Outcome canonical mapping (Outcome model untouched) ────────────────


class TestOutcomeMapping:
    def test_legacy_values_still_valid(self):
        for result in ("success", "partial", "failure", "na"):
            assert Outcome(id="o-1", tenant_id="t-1", mission_id="m-1", result=result).result == result  # type: ignore[arg-type]

    def test_forward_map(self):
        assert OUTCOME_RESULT_TO_CANONICAL == {
            "success": "verified",
            "failure": "failed",
            "partial": "partial",
            "na": "indeterminate",
        }
        assert canonical_outcome_state("success") == "verified"
        assert canonical_outcome_state("failure") == "failed"
        assert canonical_outcome_state("partial") == "partial"
        assert canonical_outcome_state("na") == "indeterminate"

    def test_reverse_map_round_trips(self):
        for result, state in OUTCOME_RESULT_TO_CANONICAL.items():
            assert OUTCOME_CANONICAL_TO_RESULT[state] == result
            assert outcome_result_from_canonical(state) == result

    def test_unknown_values_raise(self):
        with pytest.raises(ValueError, match="unknown Outcome.result value"):
            canonical_outcome_state("won")
        with pytest.raises(ValueError, match="unknown canonical outcome state"):
            outcome_result_from_canonical("celebrated")

    def test_outcome_model_has_no_canonical_field(self):
        assert set(Outcome.model_fields) == {
            "id",
            "tenant_id",
            "mission_id",
            "result",
            "evidence_refs",
            "created_at",
        }
