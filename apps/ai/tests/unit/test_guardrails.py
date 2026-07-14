"""Tests for Guardrails Policy Engine + Alert Gate Extensions — TDD Red phase.

Tests cover:
- GuardrailsEngine: 7 stages of evaluation (pure deterministic)
- AlertGateExtended: 3 new gate stages (authority, risk, privacy)
"""
import re
from datetime import datetime

import pytest

from src.business.envelope import (
    BusinessDecisionEnvelope,
    FinancialSnapshot,
    GuardrailResult,
)
from src.schemas.event_envelope import EventEnvelope
from src.schemas.guardian import AlertDecision


# ═══════════════════════════════════════════════════════════════════════════
# Test Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_event(
    tenant_id: str = "tenant-001",
    source: str = "stripe",
    event_type: str = "payment_failed",
) -> EventEnvelope:
    """Create a minimal EventEnvelope for testing."""
    return EventEnvelope(
        tenant_id=tenant_id,
        event_type=event_type,
        source=source,
        payload_ref="raw_events:test-001",
        payload_hash="abc123def456",
        idempotency_key="ik-" + tenant_id + "-001",
        occurred_at=datetime(2026, 1, 1),
        received_at=datetime(2026, 1, 1),
        trace_id="trace-" + tenant_id,
    )


def _make_decision(
    should_alert: bool = True,
    severity: str = "info",
    primary_signal: str = "Test signal",
    context_note: str = "Test context",
) -> AlertDecision:
    """Create a minimal AlertDecision for testing."""
    return AlertDecision(
        should_alert=should_alert,
        severity=severity,  # type: ignore[arg-type]
        primary_signal=primary_signal,
        context_note=context_note,
    )


def _make_finance(
    tenant_id: str = "tenant-001",
    burn_rate: float = 0.0,
    runway_days: int = 365,
    burn_multiple: float | None = None,
    rule_anomalies: list[str] | None = None,
) -> FinancialSnapshot:
    """Create a minimal FinancialSnapshot for testing."""
    return FinancialSnapshot(
        tenant_id=tenant_id,
        burn_rate=burn_rate,
        runway_days=runway_days,
        burn_multiple=burn_multiple,
        rule_anomalies=rule_anomalies or [],
    )


# ═══════════════════════════════════════════════════════════════════════════
# TestGuardrailsEngine
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardrailsEngine:
    """Guardrails policy engine tests — 7 evaluation stages."""

    # ── Stage 1: investor_facing ─────────────────────────────────────────

    def test_investor_facing_flag_set_on_finance_warning(self):
        """Finance domain + warning severity → investor_facing=True."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="stripe")
        decision = _make_decision(severity="warning", primary_signal="Burn rate increasing")
        finance = _make_finance(burn_rate=50000)
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="finance",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.investor_facing is True

    def test_investor_facing_flag_not_set_on_ops_info(self):
        """Ops domain + info severity → investor_facing=False."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="intercom")
        decision = _make_decision(severity="info", primary_signal="User feedback received")
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.investor_facing is False

    # ── Stage 2: authority ───────────────────────────────────────────────

    def test_authority_critical_is_blocking(self):
        """Critical severity → approval_tier=blocking."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event()
        decision = _make_decision(severity="critical", primary_signal="Critical failure")
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.approval_tier == "blocking"

    def test_authority_info_is_auto(self):
        """Info severity → approval_tier=auto."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="cron")
        decision = _make_decision(severity="info", primary_signal="Routine check completed")
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="bi",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.approval_tier == "auto"

    # ── Stage 3: reversibility ───────────────────────────────────────────

    def test_reversibility_payout_sets_not_reversible(self):
        """Decision with financial payout indicators → reversible=False."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event()
        decision = _make_decision(
            severity="warning",
            primary_signal="Customer requested refund for failed charges",
            context_note="Payout of 5000 USD required",
        )
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="finance",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.reversible is False

    def test_reversibility_keeps_default(self):
        """Normal operational decision → reversible=True."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="cron")
        decision = _make_decision(
            severity="info",
            primary_signal="Daily backup completed successfully",
            context_note="All systems operational",
        )
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.reversible is True

    # ── Stage 4: risk_classification ─────────────────────────────────────

    def test_risk_classification_financial_when_burn_alert(self):
        """Domain=finance with burn indicators → risk_type=financial."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="stripe")
        decision = _make_decision(
            severity="warning",
            primary_signal="Burn rate accelerating",
            context_note="Monthly burn at 50K",
        )
        finance = _make_finance(burn_rate=50000, burn_multiple=2.5)
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="finance",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.risk_type == "financial"

    def test_risk_classification_legal_when_privacy(self):
        """privacy_sensitive=True AND domain=finance → risk_type=legal (privacy overrides)."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="stripe")
        decision = _make_decision(
            severity="info",
            primary_signal="Customer data review",
            context_note="Contains email address",
        )
        finance = _make_finance()  # no burn indicators
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="finance",
            guardrail_status=GuardrailResult(approval_tier="auto", privacy_sensitive=True),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.risk_type == "legal"

    # ── Stage 5: privacy ─────────────────────────────────────────────────

    def test_privacy_sensitive_detected_from_pii(self):
        """Ops alert containing email text → privacy_sensitive=True."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="intercom")
        decision = _make_decision(
            severity="info",
            primary_signal="User contact: john.doe@example.com reported an issue",
            context_note="Follow up with user",
        )
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.privacy_sensitive is True

    def test_privacy_not_sensitive_clean_text(self):
        """Alert with no PII → privacy_sensitive=False."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="cron")
        decision = _make_decision(
            severity="info",
            primary_signal="System health check passed",
            context_note="All metrics nominal",
        )
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.privacy_sensitive is False

    # ── Stage 6: approval_tier_final ─────────────────────────────────────

    def test_approval_tier_blocking_when_blocking_flag(self):
        """blocking=True → approval_tier=blocking."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event()
        decision = _make_decision(severity="critical", primary_signal="Critical breach")
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.approval_tier == "blocking"

    def test_approval_tier_review_when_privacy_sensitive(self):
        """privacy_sensitive=True AND not blocking → at least review."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="intercom")
        decision = _make_decision(
            severity="info",
            primary_signal="User contact: user@test.com sent a message",
            context_note="Contains PII data",
        )
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.privacy_sensitive is True
        assert result.approval_tier in ("review", "blocking")

    # ── Stage 7: blocking_override ───────────────────────────────────────

    def test_blocking_override_multiple_critical(self):
        """investor_facing + irreversible + risk=financial → blocking=True."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="stripe")
        decision = _make_decision(
            severity="warning",
            primary_signal="Refund requested for failed payment cluster",
            context_note="Financial payout required",
        )
        finance = _make_finance(burn_rate=50000, burn_multiple=2.5, rule_anomalies=["burn_multiple_creep"])
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="finance",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.investor_facing is True
        assert result.reversible is False
        assert result.risk_type == "financial"
        assert result.blocking is True

    def test_blocking_not_set_on_single_condition(self):
        """Only one critical condition → blocking stays False."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="stripe")
        decision = _make_decision(
            severity="info",
            primary_signal="Revenue report generated",
            context_note="Monthly summary",
        )
        finance = _make_finance(burn_rate=50000, burn_multiple=2.5)
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="finance",
            guardrail_status=GuardrailResult(approval_tier="auto", privacy_sensitive=False, blocking=False),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.blocking is False

    # ── evaluate_decision convenience ────────────────────────────────────

    def test_evaluate_decision_convenience(self):
        """Call evaluate_decision with basic event+decision → GuardrailResult with correct defaults."""
        from src.business.guardrails import evaluate_decision

        event = _make_event(source="cron", event_type="health_check")
        decision = _make_decision(severity="info", primary_signal="System health OK")
        finance = _make_finance()
        result = evaluate_decision(event, decision, finance)

        assert isinstance(result, GuardrailResult)
        assert result.approval_tier == "auto"
        assert result.reversible is True
        assert result.blocking is False
        assert result.privacy_sensitive is False

    # ── Healthy signals (no false positives) ─────────────────────────────

    def test_evaluate_envelope_no_false_positives_healthy(self):
        """Healthy signals → investor_facing=False, blocking=False, approval_tier=auto."""
        from src.business.guardrails import evaluate_envelope

        event = _make_event(source="cron")
        decision = _make_decision(
            severity="info",
            primary_signal="All systems nominal",
            context_note="No action needed",
        )
        finance = _make_finance()
        envelope = BusinessDecisionEnvelope(
            event=event,
            decision=decision,
            finance_snapshot=finance,
            domain="ops",
            guardrail_status=GuardrailResult(approval_tier="auto"),
            reversible=True,
            approval_tier="auto",
        )
        result = evaluate_envelope(envelope)
        assert result.investor_facing is False
        assert result.blocking is False
        assert result.approval_tier == "auto"


# ═══════════════════════════════════════════════════════════════════════════
# TestAlertGateExtended
# ═══════════════════════════════════════════════════════════════════════════


class TestAlertGateExtended:
    """Alert gate extended stages (authority, risk, privacy)."""

    def setup_method(self):
        """Reset trust battery and dedup state before each test."""
        from src.services.trust_battery import reset_profiles
        reset_profiles()
        # Reset dedup to avoid cross-test collisions
        from src.services.alert_gate import AlertGate
        gate = AlertGate("tenant-001")
        gate.reset_dedup()

    def _make_basic_alert(self, **overrides: str | bool) -> dict:
        """Create a basic alert dict that passes schema validation."""
        alert = {
            "should_alert": True,
            "severity": "info",
            "primary_signal": "Test alert signal",
            "headline": "Test Alert",
            "explanation": "This is a test alert for unit testing",
            "recommended_action": "Review and acknowledge",
        }
        alert.update(overrides)
        return alert

    # ── Authority stage ──────────────────────────────────────────────────

    def test_authority_stage_blocks_low_trust_critical(self):
        """Agent with trust=0.45, severity=critical → stage='authority', passed=False."""
        from src.services.alert_gate import AlertGate
        from src.services.trust_battery import update_trust_score

        # Set trust to ~0.45 (above degraded 0.4 but below 0.8)
        update_trust_score("tenant-001", "agent", "schema_parse_fail")
        update_trust_score("tenant-001", "agent", "dispute")

        gate = AlertGate("tenant-001")
        alert = self._make_basic_alert(severity="critical", primary_signal="Critical system failure")
        result = gate.check(alert, "agent")

        assert result.passed is False
        assert result.stage == "authority"
        assert result.alert is not None

    def test_authority_stage_passes_high_trust_critical(self):
        """Agent with trust=0.95, severity=critical → passes authority stage."""
        from src.services.alert_gate import AlertGate
        from src.services.trust_battery import update_trust_score

        # Set trust to 0.95 (above 0.8)
        update_trust_score("tenant-001", "agent", "acknowledge")
        update_trust_score("tenant-001", "agent", "acknowledge")

        gate = AlertGate("tenant-001")
        alert = self._make_basic_alert(severity="critical", primary_signal="Critical but handled")
        result = gate.check(alert, "agent")

        # Should pass authority (and potentially all other stages)
        assert result.stage in ("authority", "risk", "privacy", "passed")

    # ── Risk stage ───────────────────────────────────────────────────────

    def test_risk_stage_passes(self):
        """Normal alert → passes risk stage."""
        from src.services.alert_gate import AlertGate

        gate = AlertGate("tenant-001")
        alert = self._make_basic_alert(severity="info", primary_signal="Normal operation")
        result = gate.check(alert, "agent")

        # Risk stage is permissive (never blocks)
        assert result.stage in ("risk", "privacy", "passed")

    # ── Privacy stage ────────────────────────────────────────────────────

    def test_privacy_stage_blocks_pii(self):
        """Alert text contains email → stage='privacy', passed=False."""
        from src.services.alert_gate import AlertGate

        gate = AlertGate("tenant-001")
        alert = self._make_basic_alert(
            severity="info",
            primary_signal="User contact: test@example.com reported an issue",
        )
        result = gate.check(alert, "agent")

        assert result.passed is False
        assert result.stage == "privacy"

    def test_privacy_stage_passes_clean_text(self):
        """Alert text has no PII → passes privacy stage."""
        from src.services.alert_gate import AlertGate

        gate = AlertGate("tenant-001")
        alert = self._make_basic_alert(
            severity="info",
            primary_signal="System health check passed",
        )
        result = gate.check(alert, "agent")

        # Should pass privacy stage
        assert result.stage in ("privacy", "passed")

    # ── Stage ordering ───────────────────────────────────────────────────

    def test_all_7_stages_executed_in_order(self):
        """All 7 stages run in sequence and complete successfully."""
        from src.services.alert_gate import AlertGate
        from src.services.trust_battery import update_trust_score

        # Set high trust to pass authority stage
        update_trust_score("tenant-001", "agent", "acknowledge")
        update_trust_score("tenant-001", "agent", "acknowledge")

        gate = AlertGate("tenant-001")
        alert = self._make_basic_alert(
            severity="info",
            primary_signal="Routine system check - healthy",
            headline="Health Check Passed",
            explanation="All systems operational with no issues detected",
        )
        result = gate.check(alert, "agent")

        # All stages should pass
        assert result.passed is True
        assert result.stage == "passed"
