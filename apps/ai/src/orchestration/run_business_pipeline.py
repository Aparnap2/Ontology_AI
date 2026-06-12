"""
Business Decision Pipeline Orchestration.

Chains:
    0. Predictive Guardian (optional V4) — forecast metric trends
    1. Finance rules (FinancialSnapshot computation)
    2. Guardrails (7-stage policy evaluation)
    3. HITL extended routing
    4. MissionState update
    5. Event emission
    6. Slack alert on failure

Pattern follows ``run_investor_update.py`` and ``run_finance_guardian.py``:
sequential steps with independent try/except, uuid4 run_id, emit events,
Slack on critical failure.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.llmops.tracer import traced

from src.activities.run_finance_rules import run_finance_rules
from src.activities.run_guardrails import run_guardrails
from src.activities.send_slack_message import send_slack_message
from src.events.bus import emit
from src.hitl.manager import HITLManager
from src.schemas.event_envelope import EventEnvelope
from src.schemas.guardian import AlertDecision
from src.session.mission_state import MissionState, update_mission_state

log = logging.getLogger(__name__)


def _build_minimal_event(tenant_id: str, run_id: str) -> dict:
    """Build a minimal EventEnvelope-compatible dict when none is provided."""
    now = datetime.utcnow().isoformat()
    return {
        "tenant_id": tenant_id,
        "event_type": "business_pipeline",
        "source": "cron",
        "payload_ref": "pg:auto",
        "payload_hash": "auto",
        "idempotency_key": f"biz-pipeline-{run_id}",
        "occurred_at": now,
        "received_at": now,
        "trace_id": run_id,
    }


def _build_minimal_decision(triggered_rules: list[str] | None = None) -> dict:
    """Build a minimal AlertDecision-compatible dict."""
    rules = triggered_rules or []
    if rules:
        return {
            "should_alert": True,
            "severity": "warning",
            "primary_signal": f"Triggered rules: {', '.join(rules)}",
            "context_note": f"{len(rules)} finance rule(s) triggered",
        }
    return {
        "should_alert": False,
        "severity": "info",
        "primary_signal": "Business pipeline completed — no issues detected",
        "context_note": "All checks passed",
    }


def _build_envelope_dict(
    tenant_id: str,
    run_id: str,
    finance_result: dict,
    event_envelope: dict | None,
    alert_decision: dict | None,
) -> dict:
    """Build a BusinessDecisionEnvelope-compatible dict from pipeline results."""
    # Build event
    if event_envelope:
        event = dict(event_envelope)
    else:
        event = _build_minimal_event(tenant_id, run_id)

    # Build decision
    if alert_decision:
        decision = dict(alert_decision)
    else:
        triggered = finance_result.get("triggered_rules", [])
        decision = _build_minimal_decision(triggered)

    # Snapshot from finance result
    snapshot = finance_result.get("snapshot", {})

    # Determine domain based on signals
    domain = "finance"
    source = event.get("source", "").lower()
    if source in ("intercom", "crisp", "keka", "darwinbox"):
        domain = "ops"
    elif source in ("cron",):
        domain = "bi"

    return {
        "event": event,
        "decision": decision,
        "finance_snapshot": snapshot,
        "guardrail_status": {
            "approval_tier": "auto",
            "reversible": True,
            "risk_type": "none",
            "authority_required": "none",
            "blocking": False,
            "privacy_sensitive": False,
            "investor_facing": False,
        },
        "domain": domain,
        "reversible": True,
        "approval_tier": "auto",
    }


def _determine_severity(alert_decision: dict | None, finance_result: dict) -> str:
    """Determine severity from alert decision or finance result."""
    if alert_decision:
        return alert_decision.get("severity", "info")
    triggered = finance_result.get("triggered_rules", [])
    if len(triggered) >= 3:
        return "critical"
    if len(triggered) >= 1:
        return "warning"
    return "info"


@traced(agent="pipeline", signature="run_pipeline", as_type="span")
async def run_business_pipeline(
    tenant_id: str,
    signals: dict,
    alert_decision: dict | None = None,
    event_envelope: dict | None = None,
    agent_name: str = "business_pipeline",
    risk_tolerance: str = "standard",
    run_predictive: bool = False,
) -> dict[str, Any]:
    """Run the full business decision pipeline.

    Stages:
    0. Predictive Guardian (optional) — forecast metric trends & generate alerts.
    1. Run finance_rules activity — compute FinancialSnapshot from signals.
    2. Build BusinessDecisionEnvelope from event + decision + snapshot.
    3. Run guardrails activity — evaluate envelope through 7 stages.
    4. Route through HITL extended router.
    5. Update MissionState in DB.
    6. Emit events for tracking.
    7. Send Slack alert if blocked.

    Args:
        tenant_id: Tenant identifier.
        signals: dict of structured metrics signals.
        alert_decision: Optional pre-built alert decision dict.
        event_envelope: Optional event envelope dict.
        agent_name: Name for trust battery routing.
        risk_tolerance: Risk tolerance setting (standard|conservative|aggressive).
        run_predictive: If True, run predictive guardian (Step 0) before finance rules.

    Returns:
        dict with pipeline execution results.
    """
    run_id = str(uuid4())
    log.info("Running business pipeline for %s, run_id=%s, risk_tolerance=%s",
             tenant_id, run_id, risk_tolerance)

    result = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "finance_result": {},
        "guardrail_result": {},
        "routing": "auto",
        "ok": True,
    }

    # ═════════════════════════════════════════════════════════════════════
    # Step 0: Predictive Guardian (optional, V4 scope)
    # ═════════════════════════════════════════════════════════════════════
    if run_predictive:
        try:
            from src.activities.run_predictive_guardian import run_predictive_guardian as _run_pred

            predictive_result = await _run_pred(tenant_id, signals)
            result["predictive_result"] = predictive_result
            if predictive_result.get("ok"):
                alert_count = len(predictive_result.get("alerts", []))
                log.info("Predictive Guardian: %d alerts generated", alert_count)
                # If critical predictive alerts exist, bump severity
                critical_alerts = [
                    a for a in predictive_result.get("alerts", [])
                    if a.get("severity") == "critical"
                ]
                if critical_alerts:
                    log.warning("Predictive Guardian: %d critical alerts", len(critical_alerts))
                    result["predictive_has_critical"] = True
            else:
                log.warning("Predictive Guardian skipped: %s", predictive_result.get("error"))
        except Exception as e:
            log.warning("Predictive Guardian failed (non-blocking): %s", e)
            result["predictive_result"] = {"ok": False, "error": str(e)}

    # ═════════════════════════════════════════════════════════════════════
    # Step 1: Run finance rules
    # ═════════════════════════════════════════════════════════════════════
    try:
        finance_result = await run_finance_rules(tenant_id, signals)
        result["finance_result"] = finance_result

        if not finance_result.get("ok"):
            error_msg = finance_result.get("error", "Unknown error")
            log.error("Finance rules failed: %s", error_msg)

            try:
                await send_slack_message(
                    f"❌ Business Pipeline failed for {tenant_id} (Step 1 - Finance Rules): {error_msg}",
                )
            except Exception as slack_err:
                log.warning("Slack notification failed: %s", slack_err)

            result["ok"] = False
            result["error"] = error_msg
            return result

        log.info("Finance rules completed: %d triggered rules",
                 len(finance_result.get("triggered_rules", [])))

    except Exception as e:
        log.exception("Finance rules activity failed: %s", e)

        try:
            await send_slack_message(
                f"❌ Business Pipeline failed for {tenant_id} (Step 1 - Exception): {str(e)}",
            )
        except Exception as slack_err:
            log.warning("Slack notification failed: %s", slack_err)

        result["ok"] = False
        result["error"] = str(e)
        return result

    # ═════════════════════════════════════════════════════════════════════
    # Step 2: Build BusinessDecisionEnvelope
    # ═════════════════════════════════════════════════════════════════════
    try:
        envelope_dict = _build_envelope_dict(
            tenant_id, run_id, finance_result, event_envelope, alert_decision,
        )
        result["envelope"] = envelope_dict
    except Exception as e:
        log.warning("Envelope construction failed (non-blocking): %s", e)
        envelope_dict = _build_envelope_dict(tenant_id, run_id, finance_result, None, None)
        result["envelope"] = envelope_dict

    # ═════════════════════════════════════════════════════════════════════
    # Step 3: Run guardrails (non-blocking)
    # ═════════════════════════════════════════════════════════════════════
    try:
        guardrail_result = await run_guardrails(tenant_id, envelope_dict)
        result["guardrail_result"] = guardrail_result
        log.info("Guardrails completed: approval_tier=%s, blocking=%s",
                 guardrail_result.get("guardrail_result", {}).get("approval_tier"),
                 guardrail_result.get("guardrail_result", {}).get("blocking"))
    except Exception as e:
        log.warning("Guardrails failed (non-blocking): %s", e)
        # Provide a fallback guardrail result
        result["guardrail_result"] = {
            "ok": False,
            "error": str(e),
            "guardrail_result": {
                "approval_tier": "review",
                "reversible": True,
                "risk_type": "operational",
                "authority_required": "founder",
                "blocking": False,
                "privacy_sensitive": False,
                "investor_facing": False,
            },
        }

    # Extract guardrail data for downstream use
    guardrail_data = result.get("guardrail_result", {}).get("guardrail_result", {})

    # ═════════════════════════════════════════════════════════════════════
    # Step 4: Route through HITL (non-blocking)
    # ═════════════════════════════════════════════════════════════════════
    try:
        severity = _determine_severity(alert_decision, finance_result)
        # Escalate severity based on predictive alerts
        if result.get("predictive_has_critical"):
            severity = "critical"
        blocking = guardrail_data.get("blocking", False)
        approval_required = guardrail_data.get("approval_tier", "auto") in ("review", "blocking")

        hitl = HITLManager()
        routing_result = hitl.route_extended(
            severity=severity,
            confidence=0.85,
            risk_tolerance=risk_tolerance,
            approval_required=approval_required,
            blocking=blocking,
        )
        result["routing"] = routing_result
        log.info("HITL routing: %s (severity=%s, blocking=%s, approval_required=%s)",
                 routing_result, severity, blocking, approval_required)
    except Exception as e:
        log.warning("HITL routing failed (non-blocking): %s", e)
        result["routing"] = "review"

    # ═════════════════════════════════════════════════════════════════════
    # Step 5: Update MissionState (non-blocking)
    # ═════════════════════════════════════════════════════════════════════
    try:
        snapshot = finance_result.get("snapshot", {})
        triggered_rules = finance_result.get("triggered_rules", [])

        # Map guardrail fields
        guardrail_risk_type = guardrail_data.get("risk_type", "none")
        guardrail_blocking = guardrail_data.get("blocking", False)
        investor_facing = guardrail_data.get("investor_facing", False)
        approval_tier = guardrail_data.get("approval_tier", "auto")
        reversible = guardrail_data.get("reversible", True)
        authority_required = guardrail_data.get("authority_required", "none")
        override_reason = guardrail_data.get("override_reason", "")

        mission_state = MissionState(
            tenant_id=tenant_id,
            mrr=snapshot.get("mrr"),
            burn_rate=snapshot.get("burn_rate"),
            runway_days=snapshot.get("runway_days"),
            burn_alert=len(triggered_rules) > 0,
            burn_severity=_determine_severity(alert_decision, finance_result),
            burn_multiple=snapshot.get("burn_multiple"),
            effective_runway_days=snapshot.get("effective_runway_days"),
            working_capital_ratio=snapshot.get("working_capital_ratio"),
            npv_last_decision=snapshot.get("npv"),
            wacc_estimate=snapshot.get("wacc_estimate"),
            active_alerts=",".join(triggered_rules) if triggered_rules else None,
            # Guardrail state fields
            last_approval_tier=approval_tier,
            last_reversible=reversible,
            active_authority_limit=authority_required,
            guardrail_override_reason=override_reason,
            guardrail_risk_type=guardrail_risk_type,
            guardrail_blocking=guardrail_blocking,
            investor_facing_alert=investor_facing,
        )

        ms_ok = await update_mission_state(mission_state)
        result["mission_state_updated"] = ms_ok
        log.info("MissionState updated: %s", ms_ok)
    except Exception as e:
        log.warning("MissionState update failed (non-blocking): %s", e)
        result["mission_state_updated"] = False

    # ═════════════════════════════════════════════════════════════════════
    # Step 6: Emit events (non-blocking)
    # ═════════════════════════════════════════════════════════════════════
    try:
        is_blocked = guardrail_data.get("blocking", False)

        # Always emit completion
        await emit("business_pipeline.completed", tenant_id, {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "ok": True,
            "triggered_rules": finance_result.get("triggered_rules", []),
            "routing": result.get("routing"),
            "approval_tier": approval_tier,
            "risk_type": guardrail_risk_type,
        })

        # Emit blocked event if guardrail blocked
        if is_blocked:
            await emit("business_pipeline.blocked", tenant_id, {
                "run_id": run_id,
                "tenant_id": tenant_id,
                "approval_tier": approval_tier,
                "risk_type": guardrail_risk_type,
                "triggered_rules": finance_result.get("triggered_rules", []),
            })
    except Exception as e:
        log.warning("Event emission failed (non-blocking): %s", e)

    # ═════════════════════════════════════════════════════════════════════
    # Step 7: Send Slack alert on blocking (non-blocking)
    # ═════════════════════════════════════════════════════════════════════
    try:
        is_blocked = guardrail_data.get("blocking", False)
        if is_blocked:
            triggered = finance_result.get("triggered_rules", [])
            risk_type = guardrail_data.get("risk_type", "unknown")
            slack_text = (
                f"🚫 Business Pipeline BLOCKED for {tenant_id}\n"
                f"Run ID: {run_id}\n"
                f"Risk Type: {risk_type}\n"
                f"Approval Tier: {approval_tier}\n"
                f"Triggered Rules: {', '.join(triggered) if triggered else 'None'}\n"
                f"Routing: {result.get('routing')}"
            )
            await send_slack_message(slack_text)
    except Exception as e:
        log.warning("Slack alert failed (non-blocking): %s", e)

    return result
