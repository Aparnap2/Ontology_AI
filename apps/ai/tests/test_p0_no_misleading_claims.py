"""FG-2: no path may emit a verification or recovery claim it cannot substantiate.

FREEZE-GATE correctness suite.  These tests pin the rule that a verdict must
come from an *independent observable source*, never from the same claim (or the
same write) that the verdict is meant to confirm.

Four claims are pinned as un-substantiatable until evidenced:

1. ``verify_recovery_activity`` must not report VERIFIED from a vendor's own
   ticket status.  It previously fabricated ``{"error_rate": 0.0,
   "success_rate": 1.0}`` and verified that invention — during a total outage.
2. Recovery metrics must never be synthesised from the vendor claim.
3. Expectations derived FROM the write (transport fidelity) must be labelled
   as derived, never presented as independent semantic confirmation.
4. ROI/savings figures must be traceable to a source event, or explicitly
   marked not-evidenced.

No real network, no real LLM, no external services.  Zero-phase unit gate.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.activities.incident_activities import (
    resolve_situation,
    verify_recovery_activity,
)
from src.control_plane.verification import outcome_event
from src.mission import verify as verify_mod
from src.mission.roi_measurement import ROIMetrics, calculate_roi
from src.mission.verify import VerifyOutcome

INCIDENT_ACTIVITIES = pathlib.Path(__file__).resolve().parents[1] / (
    "src/activities/incident_activities.py"
)


def _vendor_ticket(status: str) -> dict:
    return {
        "vendor_ticket": {
            "ticket_id": "vt-1",
            "vendor_id": "stripe",
            "incident_id": "inc-1",
            "status": status,
        }
    }


# ══════════════════════════════════════════════════════════════════════════
# 1. A self-certifying path must not report VERIFIED from its own input
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_vendor_claim_alone_cannot_certify_recovery():
    """The vendor marking its own ticket 'resolved' is not evidence.

    This is the exact self-certification that let a total outage report
    VERIFIED: the activity read the ticket status and then 'verified'
    numbers it had just invented from that same status.
    """
    result = await verify_recovery_activity(
        {"situation": {"id": "sit-1"}, "vendor_result": _vendor_ticket("resolved")}
    )

    assert result["verified"] is False, (
        "recovery was certified from the vendor's own claim — "
        "the claim under verification cannot also be its evidence"
    )


@pytest.mark.asyncio
async def test_total_outage_never_reports_verified():
    """A 100% outage must not yield VERIFIED from any code path.

    Reproduces the audit finding: observed error_rate=1.0 / success_rate=0.0
    (the service is fully down) while the vendor ticket says 'resolved'.
    """
    result = await verify_recovery_activity(
        {
            "situation": {"id": "sit-outage"},
            "vendor_result": _vendor_ticket("resolved"),
            "observed": {"error_rate": 1.0, "success_rate": 0.0},
        }
    )

    assert result["verified"] is False
    assert result["mismatches"], "an outage must record which predicates failed"


@pytest.mark.asyncio
async def test_every_vendor_status_fails_closed_without_evidence():
    """No vendor status — resolved, closed, or open — may certify recovery.

    Pins the whole input domain: the verdict must not be a function of the
    vendor claim at all.
    """
    verdicts = []
    for status in ("open", "pending", "resolved", "closed"):
        result = await verify_recovery_activity(
            {"situation": {"id": "sit-1"}, "vendor_result": _vendor_ticket(status)}
        )
        verdicts.append(result["verified"])

    assert verdicts == [False, False, False, False]


@pytest.mark.asyncio
async def test_missing_evidence_fails_closed_with_explicit_reason():
    """Refusing to certify must be *legible*, not a silent False.

    An operator has to be able to tell 'we checked and it failed' from
    'we never had evidence to check with'.
    """
    result = await verify_recovery_activity(
        {"situation": {"id": "sit-1"}, "vendor_result": _vendor_ticket("resolved")}
    )

    assert result["verified"] is False
    assert result.get("state") == "INDETERMINATE", (
        "absent evidence is indeterminate, not a negative measurement"
    )
    reason = str(result.get("reason", ""))
    assert reason, "a fail-closed refusal must carry a reason"
    assert "evidence" in reason.lower(), (
        f"reason must name the missing evidence, got {reason!r}"
    )


@pytest.mark.asyncio
async def test_empty_observed_is_not_evidence():
    """An empty evidence payload is the absence of evidence, not a pass."""
    for observed in ({}, {"error_rate": None}, {"error_rate": None, "success_rate": None}):
        result = await verify_recovery_activity(
            {
                "situation": {"id": "sit-1"},
                "vendor_result": _vendor_ticket("resolved"),
                "observed": observed,
            }
        )
        assert result["verified"] is False, f"{observed!r} was accepted as evidence"


# ══════════════════════════════════════════════════════════════════════════
# 2. Recovery metrics must not be produced from invented values
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_recovery_verdict_ignores_the_vendor_claim():
    """With real evidence injected, the verdict must follow the evidence alone.

    Two vendor statuses, identical healthy observation → identical verdict.
    This also proves the activity now *uses* real observations, which the
    fabrication branch made impossible: it discarded them.
    """
    healthy = {"error_rate": 0.001, "success_rate": 0.999}

    from_open = await verify_recovery_activity(
        {
            "situation": {"id": "sit-1"},
            "vendor_result": _vendor_ticket("open"),
            "observed": healthy,
        }
    )
    from_resolved = await verify_recovery_activity(
        {
            "situation": {"id": "sit-1"},
            "vendor_result": _vendor_ticket("resolved"),
            "observed": healthy,
        }
    )

    assert from_open["verified"] is from_resolved["verified"] is True
    assert from_open["passed"] == from_resolved["passed"]


@pytest.mark.asyncio
async def test_healthy_observation_verifies_with_evidence():
    """Positive control: real evidence + failing predicates must still verify.

    Fail-closed must not be fail-everything — that would be its own kind of
    dishonesty, hiding real recoveries.
    """
    result = await verify_recovery_activity(
        {
            "situation": {"id": "sit-1"},
            "vendor_result": _vendor_ticket("resolved"),
            "observed": {"error_rate": 0.002, "success_rate": 0.999},
        }
    )

    assert result["verified"] is True
    assert result["mismatches"] == []


def test_no_fabricated_metric_literals_remain():
    """Static guard: the invented recovery metrics must be gone from source.

    The literals {"error_rate": 0.0, "success_rate": 1.0} existed only to be
    fed to the predicates the same function was about to pass them against.
    """
    tree = ast.parse(INCIDENT_ACTIVITIES.read_text())
    literals: set[tuple[float, ...]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            try:
                literals.add(tuple(
                    float(v.value)
                    for v in node.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                ))
            except (TypeError, ValueError):
                continue
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            try:
                literals.add(tuple(
                    float(v.value)
                    for v in node.value.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                ))
            except (TypeError, ValueError):
                continue

    fabricated = {(0.0, 1.0), (0.35, 0.65)}
    assert not (literals & fabricated), (
        "invented recovery metrics still present in incident_activities.py — "
        "metrics must come from an evidence source, never be constructed here"
    )


# ══════════════════════════════════════════════════════════════════════════
# 3. Derived-from-write expectations must be labelled, not laundered
# ══════════════════════════════════════════════════════════════════════════


def test_verify_outcome_declares_expectation_provenance():
    """Every verification must carry where its expectations came from."""
    outcome = VerifyOutcome(state="VERIFIED")

    assert hasattr(outcome, "expectation_source"), (
        "VerifyOutcome must expose expectation_source so a derived "
        "verification cannot be read as independent confirmation"
    )


def test_derived_expectations_are_labelled_derived():
    """derive_expected output must be self-identifying as derived.

    ``derive_expected`` can only ever prove 'the fields I sent are the fields
    that arrived' — transport fidelity.  It can never prove the change was
    semantically correct.
    """
    derived = verify_mod.derive_expected(
        "jira.update", {"issue_id": "K-1", "fields": {"summary": "wrong"}}
    )
    assert derived == {"summary": "wrong"}

    labelled = verify_mod.label_expectation_source(derived, explicit=False)
    assert labelled["expectation_source"] == "derived_from_write"


def test_caller_supplied_expectations_are_labelled_caller_supplied():
    """Caller-supplied expectations are a different, stronger class."""
    supplied = {"summary": "intended"}

    labelled = verify_mod.label_expectation_source(supplied, explicit=True)
    assert labelled["expectation_source"] == "caller_supplied"


def test_derived_expectation_cannot_prove_semantic_correctness():
    """Documenting the real limit: derived expectations verify transport only.

    The write sends a WRONG value; read-back faithfully returns that wrong
    value.  The read-back check passes — which is correct and honest for what
    it measures — but it is not evidence the change was right, and the
    outcome must say so.
    """
    params = {"issue_id": "K-1", "fields": {"summary": "WRONG VALUE"}}
    derived = verify_mod.derive_expected("jira.update", params)
    assert derived == {"summary": "WRONG VALUE"}

    record = {"key": "K-1", "summary": "WRONG VALUE"}
    assert all(record[k] == v for k, v in derived.items()), (
        "read-back matches the write — proving transport fidelity only"
    )
    assert verify_mod.label_expectation_source(derived, explicit=False)[
        "expectation_source"
    ] == "derived_from_write"


@pytest.mark.asyncio
async def test_control_plane_labels_derived_verification_end_to_end():
    """The label must survive to the auditable outcome event.

    ``ingress.submit_intent`` calls verify_execution with expected={} — i.e.
    every production control-plane verification is derived.  If the label is
    dropped on the way to the audit event, the laundering is complete.
    """

    class _Caps:
        def execute(self, op, params, tenant_id, role_caps=None):
            # Faithful read-back of whatever was written.
            return {"data": {"key": "K-1", "summary": params.get("fields", {}).get("summary")}}

    from src.control_plane.verification import verify_execution

    outcome = await verify_execution(
        "jira.update",
        {"issue_id": "K-1", "fields": {"summary": "WRONG VALUE"}},
        {},
        "t-acme",
        capabilities=_Caps(),
    )
    event = outcome_event("act-1", outcome)

    assert event["expectation_source"] == "derived_from_write", (
        "a verification derived from its own write was presented as "
        "independent confirmation"
    )


# ══════════════════════════════════════════════════════════════════════════
# 4. ROI / savings must be traceable, or explicitly marked not-evidenced
# ══════════════════════════════════════════════════════════════════════════


def _metrics(**over) -> ROIMetrics:
    base = {
        "time_to_detect_minutes": 2.0,
        "time_to_acknowledge_minutes": 10.0,
        "time_to_resolve_minutes": 45.0,
        "sla_compliance": True,
        "escalation_count": 1,
        "vendor_ticket_created": True,
        "recovery_verified": True,
        "total_cost_usd": 2250.0,
    }
    base.update(over)
    return ROIMetrics(**base)


def test_roi_savings_are_not_evidenced_without_provenance():
    """A savings figure with no source event must be marked not-evidenced."""
    savings = calculate_roi(_metrics(), _metrics(time_to_resolve_minutes=240.0))

    assert savings.total_savings_usd > 0, "arithmetic itself must be preserved"
    assert savings.evidenced is False, (
        "savings were computed with no traceable source event but were "
        "presented as evidenced"
    )


def test_roi_savings_are_evidenced_with_provenance():
    """Traceable source events → the figure may be presented as evidenced."""
    governed = _metrics(evidence_refs=["sla_clock:inc-1", "recovery:obs-1"])
    baseline = _metrics(
        time_to_resolve_minutes=240.0, evidence_refs=["manual_baseline:q3"]
    )

    savings = calculate_roi(governed, baseline)

    assert savings.evidenced is True


def test_roi_metrics_rejects_unevidenced_source_events():
    """Provenance must be real references, not a self-asserted flag."""
    with pytest.raises(Exception):
        _metrics(evidence_refs=["sla_clock:inc-1", ""])


# ══════════════════════════════════════════════════════════════════════════
# 5. A recovery STATE may not be emitted without substantiated recovery
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resolve_situation_requires_verified_recovery():
    """Emitting RESOLVED is a recovery claim and needs a verified recovery."""
    result = await resolve_situation({"id": "sit-1", "status": "OPEN"})

    assert result.get("status") != "RESOLVED", (
        "a situation was marked RESOLVED with no verified recovery behind it"
    )


@pytest.mark.asyncio
async def test_resolve_situation_accepts_verified_recovery():
    """Positive control: a substantiated recovery may still resolve."""
    result = await resolve_situation(
        {
            "id": "sit-1",
            "status": "OPEN",
            "recovery": {"verified": True, "state": "VERIFIED"},
        }
    )

    assert result["status"] == "RESOLVED"