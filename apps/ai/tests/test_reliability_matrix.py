"""V7 Vendor Operations Desk — reliability & observability test suite.

Proves eight core reliability properties of the control-plane + mission
layer are correct, deterministic, and fail-closed.  All tests run without
network, without LLM, and without wall-clock time (timestamps injected).

Properties under test:
  1. Duplicate event handling (idempotent deny)
  2. Stale context rejection (version mismatch → stale_context)
  3. Tenant isolation (cross-tenant evidence → ValueError)
  4. Empty evidence fail-closed (no evidence → rejected)
  5. Recovery predicate fail-closed (empty predicates → verified=False)
  6. Governed write without PlannedAction → GovernanceError
  7. SLA clock invalid transition (DEADLINE_PASSED from ACTIVE)
  8. Unknown capability op → UnknownCapabilityOpError
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

# ── 1. Idempotency + ingress ────────────────────────────────────────────
from src.control_plane.contracts import ActionIntent
from src.control_plane.idempotency import SeenSet, build_idempotency_key
from src.control_plane.ingress import submit_intent

# ── 2. Concurrency (VersionStore) ───────────────────────────────────────
from src.control_plane.concurrency import VersionStore, reset_store

# ── 3. Tenant isolation (context checkpoint) ────────────────────────────
from src.context.assemble import assemble_checkpoint
from src.ontology.object_types import Evidence

# ── 5. Recovery predicates ──────────────────────────────────────────────
from src.mission.recovery_verification import (
    RecoveryPredicate,
    evaluate_predicates,
    verify_recovery,
)

# ── 6. Governance gate ──────────────────────────────────────────────────
from src.ontology.governance import (
    GovernanceError,
    governed_write,
)

# ── 7. SLA clock state machine ──────────────────────────────────────────
from src.mission.sla_clocks import (
    ClockEvent,
    ClockState,
    InvalidClockTransitionError,
    SLADeadlines,
    open_clock,
    transition,
)

# ── 8. Capability op registry ───────────────────────────────────────────
from src.mission.capability_ops import CapabilityOpRegistry, UnknownCapabilityOpError


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

_TENANT_A = "tenant-alpha"
_TENANT_B = "tenant-bravo"
_MISSION_A = "mission-001"


def _make_intent(**overrides: object) -> ActionIntent:
    """Build a minimal valid ActionIntent with sensible defaults."""
    defaults: dict[str, object] = {
        "capability": "vendor",
        "operation": "incident.search",
        "target_reference": "inc-42",
        "requested_parameters": {"query": "latency spike"},
        "reason": "vendor reported latency degradation",
        "evidence_ids": ["ev-1"],
        "expected_outcome": "incident identified",
        "confidence": 0.85,
        "requested_by": "reliability-test",
    }
    defaults.update(overrides)
    return ActionIntent(**defaults)  # type: ignore[arg-type]


def _trusted_ctx(**overrides: object) -> dict[str, object]:
    """Build a minimal trusted_context dict with sensible defaults."""
    base: dict[str, object] = {
        "tenant_id": _TENANT_A,
        "mission_id": _MISSION_A,
        "employee_id": "emp-qa-01",
        "actor_identity": "qa-agent",
        "permissions": ["vendor.search"],
    }
    base.update(overrides)
    return base


# ═════════════════════════════════════════════════════════════════════════
# 1. DUPLICATE EVENT HANDLING — second submit is deny:duplicate
# ═════════════════════════════════════════════════════════════════════════


class TestDuplicateEventHandling:
    """Idempotency: the same domain key is denied on second submission."""

    def test_same_intent_twice_second_denied(self) -> None:
        """Two identical intents → second returns deny:duplicate."""
        seen = SeenSet()
        key = build_idempotency_key("t", "m", "op", "tgt")

        # First submission: not a duplicate → should proceed.
        assert not seen.is_duplicate(key)
        seen.mark(key)

        # Second submission: detected as duplicate.
        assert seen.is_duplicate(key)

    def test_submit_intent_duplicate_via_ingress(self) -> None:
        """submit_intent returns deny:duplicate when the same key is reused."""
        import asyncio

        intent = _make_intent()
        ctx = _trusted_ctx()

        result_first = asyncio.run(submit_intent(intent, ctx))
        assert result_first["decision"] == "permit:executed"

        # Second submission with the same intent — same idempotency key.
        result_second = asyncio.run(submit_intent(intent, ctx))
        assert result_second["decision"] == "deny:duplicate"


# ═════════════════════════════════════════════════════════════════════════
# 2. STALE CONTEXT REJECTION — version mismatch → deny:stale_context
# ═════════════════════════════════════════════════════════════════════════


class TestStaleContextRejection:
    """Optimistic concurrency: stale version → deny:stale_context."""

    def test_version_mismatch_denied(self) -> None:
        """submit_intent rejects when version ≠ current_version."""
        import asyncio

        intent = _make_intent()
        ctx = _trusted_ctx(version=1, current_version=2)

        result = asyncio.run(submit_intent(intent, ctx))
        assert result["decision"] == "deny:stale_context"

    def test_version_match_permitted(self) -> None:
        """submit_intent proceeds when version == current_version."""
        import asyncio

        reset_store()
        intent = _make_intent()
        ctx = _trusted_ctx(version=1, current_version=1)

        result = asyncio.run(submit_intent(intent, ctx))
        # Should NOT be stale_context — proceeds to permit or deny:stale_version.
        assert result["decision"] != "deny:stale_context"

    def test_version_store_advance(self) -> None:
        """VersionStore.advance increments the version correctly."""
        store = VersionStore()
        key = "tenant:mission"
        store.seed(key, 5)
        assert store.current(key) == 5
        new_v = store.advance(key)
        assert new_v == 6
        assert store.current(key) == 6


# ═════════════════════════════════════════════════════════════════════════
# 3. TENANT ISOLATION — cross-tenant evidence → ValueError
# ═════════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    """Evidence from tenant A must not leak into tenant B's checkpoint."""

    def _ev(self, eid: str, tenant: str) -> Evidence:
        return Evidence(
            id=eid,
            tenant_id=tenant,
            source="test",
            provenance="test:unit",
            captured_at="2026-09-12T00:00:00Z",
            raw_text="test",
            normalized_text="test",
        )

    def test_cross_tenant_evidence_rejected(self) -> None:
        """assemble_checkpoint raises ValueError for cross-tenant evidence."""
        ev_a = self._ev("ev-a1", _TENANT_A)
        ev_b = self._ev("ev-b1", _TENANT_B)  # different tenant!

        with pytest.raises(ValueError, match="cross-tenant evidence rejected"):
            assemble_checkpoint(
                checkpoint_id="cp-1",
                tenant_id=_TENANT_A,
                mission_id=_MISSION_A,
                trigger_event_id="evt-1",
                evidence=[ev_a, ev_b],
                now=datetime(2026, 9, 12, tzinfo=timezone.utc),
            )

    def test_same_tenant_evidence_accepted(self) -> None:
        """Same-tenant evidence passes the isolation check."""
        ev_a1 = self._ev("ev-a1", _TENANT_A)
        ev_a2 = self._ev("ev-a2", _TENANT_A)

        cp = assemble_checkpoint(
            checkpoint_id="cp-2",
            tenant_id=_TENANT_A,
            mission_id=_MISSION_A,
            trigger_event_id="evt-2",
            evidence=[ev_a1, ev_a2],
            now=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        assert cp.tenant_id == _TENANT_A
        assert len(cp.relevant_evidence) == 2


# ═════════════════════════════════════════════════════════════════════════
# 4. EMPTY EVIDENCE FAIL-CLOSED — no evidence → unresolved questions
# ═════════════════════════════════════════════════════════════════════════


class TestEmptyEvidenceFailClosed:
    """Investigation with no evidence must not silently produce a clean checkpoint."""

    def test_no_evidence_yields_unresolved_questions(self) -> None:
        """An empty evidence list produces an unresolved entity question."""
        cp = assemble_checkpoint(
            checkpoint_id="cp-empty",
            tenant_id=_TENANT_A,
            mission_id=_MISSION_A,
            trigger_event_id="evt-empty",
            evidence=[],
            now=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        # Empty evidence → entity resolution is unresolved.
        assert any("entity resolution unresolved" in q for q in cp.unresolved_questions)
        # Evidence list should be empty.
        assert cp.relevant_evidence == []

    def test_no_evidence_checkpoint_has_no_citations(self) -> None:
        """Zero evidence → zero RelevantEvidence citations."""
        cp = assemble_checkpoint(
            checkpoint_id="cp-zero",
            tenant_id=_TENANT_A,
            mission_id=_MISSION_A,
            trigger_event_id="evt-zero",
            evidence=[],
            now=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        assert len(cp.relevant_evidence) == 0
        # Must still produce a valid checkpoint.
        assert cp.checkpoint_id == "cp-zero"


# ═════════════════════════════════════════════════════════════════════════
# 5. RECOVERY PREDICATE FAIL-CLOSED — empty predicates → verified=False
# ═════════════════════════════════════════════════════════════════════════


class TestRecoveryPredicateFailClosed:
    """Recovery claims are rejected when predicates are empty or unverifiable."""

    def test_empty_predicates_fail_closed(self) -> None:
        """No predicates → verified=False with no_predicates mismatch."""
        outcome = evaluate_predicates([], {"cpu": 0.1})
        assert outcome.verified is False
        assert "no_predicates" in outcome.mismatches

    def test_missing_observed_field_fail_closed(self) -> None:
        """Predicate references a field not in observed state → verified=False."""
        preds = [RecoveryPredicate(field="cpu", op="lt", threshold=90.0)]
        outcome = evaluate_predicates(preds, {"memory": 50})  # no "cpu"
        assert outcome.verified is False
        assert "missing:cpu" in outcome.mismatches

    def test_unknown_operator_fail_closed(self) -> None:
        """Predicate with unknown op → verified=False with unknown_op mismatch."""
        preds = [RecoveryPredicate(field="cpu", op="UNKNOWN_OP", threshold=90.0)]
        outcome = evaluate_predicates(preds, {"cpu": 10.0})
        assert outcome.verified is False
        assert "unknown_op:UNKNOWN_OP" in outcome.mismatches

    def test_all_predicates_pass(self) -> None:
        """When every predicate passes → verified=True."""
        preds = [
            RecoveryPredicate(field="cpu", op="lt", threshold=90.0),
            RecoveryPredicate(field="memory", op="lte", threshold=80.0),
        ]
        outcome = evaluate_predicates(preds, {"cpu": 42.0, "memory": 60.0})
        assert outcome.verified is True
        assert outcome.mismatches == []
        assert sorted(outcome.passed) == ["cpu", "memory"]

    def test_one_predicate_fails(self) -> None:
        """Any single predicate failure → verified=False."""
        preds = [
            RecoveryPredicate(field="cpu", op="lt", threshold=90.0),
            RecoveryPredicate(field="memory", op="lte", threshold=50.0),
        ]
        outcome = evaluate_predicates(preds, {"cpu": 42.0, "memory": 80.0})
        assert outcome.verified is False
        assert "memory" in outcome.mismatches
        assert "cpu" in outcome.passed

    def test_verify_recovery_wraps_outcome(self) -> None:
        """verify_recovery delegates to evaluate_predicates and tags incident_id."""
        incident = {"id": "INC-999"}
        outcome = verify_recovery(incident, [], {"cpu": 10})
        assert outcome.verified is False
        assert outcome.incident_id == "INC-999"
        assert "no_predicates" in outcome.mismatches


# ═════════════════════════════════════════════════════════════════════════
# 6. GOVERNED WRITE WITHOUT PlannedAction → GovernanceError
# ═════════════════════════════════════════════════════════════════════════


class TestGovernedWriteWithoutApproval:
    """Writes gated by @governed_write must raise GovernanceError when no
    PlannedAction is provided."""

    def test_notification_send_without_planned_action(self) -> None:
        """notification.send_internal (Message.direction, requires_approval=True)
        raises GovernanceError when invoked directly without PlannedAction."""
        from src.mission.capability_ops_vendor import _execute_notify_internal

        with pytest.raises(GovernanceError, match="requires a PlannedAction"):
            _execute_notify_internal(
                {"channel": "ops", "text": "alert", "recipient": "oncall"},
                "tenant-test",
            )

    def test_notification_send_vendor_without_planned_action(self) -> None:
        """notification.send_vendor (Message.direction, requires_approval=True)
        raises GovernanceError when invoked directly without PlannedAction."""
        from src.mission.capability_ops_vendor import _execute_notify_vendor

        with pytest.raises(GovernanceError, match="requires a PlannedAction"):
            _execute_notify_vendor(
                {"vendor_id": "v-1", "text": "ticket created"},
                "tenant-test",
            )

    def test_custom_governed_write_raises(self) -> None:
        """A custom @governed_write on a high-blast property raises
        GovernanceError when no PlannedAction is provided."""
        policy = {
            "Widget": {
                "value": {"requires_approval": True, "blast_radius": "high"},
            },
        }

        @governed_write(
            object_type="Widget",
            property_name="value",
            policy=policy,
            requested_by="test",
        )
        def _write_widget(widget_id: str, value: float) -> dict:
            return {"id": widget_id, "value": value}

        with pytest.raises(GovernanceError, match="requires a PlannedAction"):
            _write_widget("w-1", 42.0)

    def test_low_blast_write_proceeds_without_action(self) -> None:
        """A low-blast write that does NOT require approval proceeds directly."""
        policy = {
            "Widget": {
                "label": {"requires_approval": False, "blast_radius": "low"},
            },
        }

        @governed_write(
            object_type="Widget",
            property_name="label",
            policy=policy,
            requested_by="test",
        )
        def _label_widget(widget_id: str, label: str) -> dict:
            return {"id": widget_id, "label": label}

        result = _label_widget("w-2", "safe")
        assert result == {"id": "w-2", "label": "safe"}


# ═════════════════════════════════════════════════════════════════════════
# 7. SLA CLOCK INVALID TRANSITION — DEADLINE_PASSED from ACTIVE
# ═════════════════════════════════════════════════════════════════════════


class TestSLAClockInvalidTransition:
    """The SLA clock state machine rejects structurally invalid transitions."""

    def _make_active_clock(self) -> object:
        """Open a clock and START it (ACTIVE → WAITING_FOR_ACK)."""
        deadlines = SLADeadlines(
            ack_deadline=datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc),
            update_deadline=None,
            resolution_deadline=datetime(2026, 9, 12, 6, 0, tzinfo=timezone.utc),
        )
        clock = open_clock("inc-1", "t1", deadlines, has_update_phase=False)
        return transition(clock, ClockEvent.START)

    def test_deadline_passed_from_active_raises(self) -> None:
        """DEADLINE_PASSED on an ACTIVE clock → InvalidClockTransitionError."""
        deadlines = SLADeadlines(
            ack_deadline=datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc),
            update_deadline=None,
            resolution_deadline=datetime(2026, 9, 12, 6, 0, tzinfo=timezone.utc),
        )
        clock = open_clock("inc-2", "t1", deadlines, has_update_phase=False)
        # clock.state == ACTIVE
        assert clock.state == ClockState.ACTIVE

        with pytest.raises(
            InvalidClockTransitionError, match="DEADLINE_PASSED invalid from ACTIVE"
        ):
            transition(clock, ClockEvent.DEADLINE_PASSED)

    def test_deadline_passed_from_waiting_succeeds(self) -> None:
        """DEADLINE_PASSED on a WAITING_FOR_ACK clock transitions to BREACHED."""
        clock = self._make_active_clock()
        assert clock.state == ClockState.WAITING_FOR_ACK

        breached = transition(clock, ClockEvent.DEADLINE_PASSED)
        assert breached.state == ClockState.BREACHED
        assert breached.breached_phase == "ack"

    def test_start_from_non_active_raises(self) -> None:
        """START on a non-ACTIVE clock → InvalidClockTransitionError."""
        clock = self._make_active_clock()  # already WAITING_FOR_ACK
        with pytest.raises(InvalidClockTransitionError, match="START invalid from"):
            transition(clock, ClockEvent.START)

    def test_duplicate_response_id_is_idempotent(self) -> None:
        """Duplicate response_id → same clock returned (no-op)."""
        clock = self._make_active_clock()
        first = transition(
            clock,
            ClockEvent.ACK_RECEIVED,
            response_id="resp-1",
        )
        second = transition(
            first,
            ClockEvent.ACK_RECEIVED,
            response_id="resp-1",
        )
        # Identical clock state — idempotent.
        assert first.incident_id == second.incident_id
        assert first.state == second.state


# ═════════════════════════════════════════════════════════════════════════
# 8. UNKNOWN CAPABILITY OP → UnknownCapabilityOpError
# ═════════════════════════════════════════════════════════════════════════


class TestUnknownCapabilityOp:
    """The CapabilityOpRegistry rejects unregistered op names."""

    def test_unknown_op_raises(self) -> None:
        """Registry.get with an unregistered name → UnknownCapabilityOpError."""
        with pytest.raises(UnknownCapabilityOpError, match="unknown capability op"):
            CapabilityOpRegistry.get("nonexistent.op.name")

    def test_known_op_returns(self) -> None:
        """Registry.get with a registered name succeeds."""
        op = CapabilityOpRegistry.get("incident.search")
        assert op.name == "incident.search"
        assert op.kind == "search"

    def test_list_ops_includes_vendor(self) -> None:
        """The frozen op list includes the V7 vendor ops."""
        ops = CapabilityOpRegistry.list_ops()
        assert "vendor_ticket.create" in ops
        assert "incident.search" in ops
        assert "notification.send_internal" in ops

    def test_assert_allowed_rejects_unauthorized(self) -> None:
        """assert_allowed raises when op is not in the role allowlist."""
        from src.mission.capability_ops import CapabilityNotAllowedError

        with pytest.raises(
            CapabilityNotAllowedError, match="not in role capability allowlist"
        ):
            CapabilityOpRegistry.assert_allowed("incident.search", ["other.op"])
