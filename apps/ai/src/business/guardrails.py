"""Guardrails policy engine — deterministic evaluation of business decisions.

Per Kautilyan architecture: the guardrail layer enforces business rules
(e.g., "never auto-approve refunds > ₹10,000") entirely through deterministic
policy evaluation. No LLM calls. No side effects.

7 evaluation stages (ALL stages run — non-short-circuiting):
    1. investor_facing      — Check if decision is investor-facing
    2. authority            — Map severity to approval tier
    3. reversibility        — Check if decision is reversible
    4. risk_classification  — Classify risk type
    5. privacy              — Check for PII indicators
    6. approval_tier_final  — Final approval tier determination
    7. blocking_override    — Blocking override for critical conditions

Each stage takes a BusinessDecisionEnvelope and a GuardrailResult, returns
the (potentially modified) GuardrailResult. Stages are composed sequentially
in ``evaluate_envelope``.
"""
from __future__ import annotations

from src.llmops.tracer import traced

import re
from typing import Literal

from src.schemas.event_envelope import EventEnvelope
from src.schemas.guardian import AlertDecision
from src.business.envelope import (
    BusinessDecisionEnvelope,
    FinancialSnapshot,
    GuardrailResult,
)

__all__ = [
    "evaluate_envelope",
    "evaluate_decision",
]

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

_FINANCE_SOURCES = {"razorpay", "stripe", "bank"}
_OPS_SOURCES = {"intercom", "crisp", "keka", "darwinbox"}

_PAYOUT_KEYWORDS = [
    "refund",
    "payout",
    "payment release",
    "wire",
    "transfer",
    "contract change",
    "contract amendment",
    "termination",
    "public communication",
    "press release",
    "public statement",
]

_PII_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
_PII_PHONE = re.compile(r"\b\d{10,15}\b|\b\d{3}[-.]\d{3}[-.]\d{4}\b")
_PII_ADDRESS = re.compile(
    r"\b\d{1,5}\s\w+\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b",
    re.IGNORECASE,
)

_SEVERITY_RANK = {"auto": 0, "review": 1, "blocking": 2}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _infer_domain(event: EventEnvelope, decision: AlertDecision) -> Literal["finance", "bi", "ops"]:
    """Infer domain from event source, falling back to decision content."""
    src = event.source.lower()
    if src in _FINANCE_SOURCES:
        return "finance"
    if src in _OPS_SOURCES:
        return "ops"
    return "bi"


def _contains_pii(text: str) -> bool:
    """Check if text contains PII indicators (email, phone, address).

    Args:
        text: The text to scan.

    Returns:
        True if any PII pattern is found.
    """
    return bool(
        _PII_EMAIL.search(text)
        or _PII_PHONE.search(text)
        or _PII_ADDRESS.search(text)
    )


def _has_payout_indicators(decision: AlertDecision) -> bool:
    """Check if decision involves financial payout, contract, or public communication.

    Args:
        decision: The alert decision to check.

    Returns:
        True if payout-related keywords are found.
    """
    text = f"{decision.primary_signal} {decision.context_note}".lower()
    return any(kw in text for kw in _PAYOUT_KEYWORDS)


def _has_burn_alert(finance: FinancialSnapshot) -> bool:
    """Check if finance snapshot shows burn alert conditions.

    A burn alert is triggered when:
    - Burn rate is positive, OR
    - Burn multiple exceeds 2.0x (Series A red flag), OR
    - Runway is under 180 days.

    Args:
        finance: The financial snapshot to evaluate.

    Returns:
        True if any burn alert condition is met.
    """
    return bool(
        finance.burn_rate > 0
        or (finance.burn_multiple is not None and finance.burn_multiple > 2.0)
        or (finance.runway_days > 0 and finance.runway_days < 180)
    )


def _escalate_tier(current: str, target: str) -> str:
    """Return the higher of two approval tiers.

    Args:
        current: Current approval tier.
        target: Target approval tier to compare.

    Returns:
        The more restrictive tier.
    """
    if _SEVERITY_RANK.get(target, 0) > _SEVERITY_RANK.get(current, 0):
        return target
    return current


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 — investor_facing
# ═══════════════════════════════════════════════════════════════════════════


def _stage1_investor_facing(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Check if decision is investor-facing.

    Conditions:
    - Domain is "finance" AND severity is "critical" or "warning".
    - Decision involves fundraising metrics: burn_multiple > 2.0x
      or runway < 180 days.

    If investor-facing, sets ``investor_facing=True`` and escalates
    approval tier to at least "review".
    """
    severity = envelope.decision.severity
    is_finance_severity = envelope.domain == "finance" and severity in ("critical", "warning")

    has_fundraising_metrics = False
    fs = envelope.finance_snapshot
    if fs.burn_multiple is not None and fs.burn_multiple > 2.0:
        has_fundraising_metrics = True
    if fs.runway_days > 0 and fs.runway_days < 180:
        has_fundraising_metrics = True

    if is_finance_severity or has_fundraising_metrics:
        result.investor_facing = True
        result.approval_tier = _escalate_tier(result.approval_tier, "review")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 — authority
# ═══════════════════════════════════════════════════════════════════════════


def _stage2_authority(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Map severity to approval tier and authority required.

    Mapping:
        critical → approval_tier="blocking",  authority_required="founder"
        warning  → approval_tier="review",    authority_required="founder"
        info     → approval_tier="auto",      authority_required="none"
    """
    severity_map = {
        "critical": ("blocking", "founder"),
        "warning": ("review", "founder"),
        "info": ("auto", "none"),
    }
    tier, authority = severity_map.get(envelope.decision.severity, ("auto", "none"))
    result.approval_tier = tier
    result.authority_required = authority
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3 — reversibility
# ═══════════════════════════════════════════════════════════════════════════


def _stage3_reversibility(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Check if decision is reversible.

    If the decision involves a financial payout, contract change, or
    public communication → set ``reversible=False`` and bump approval
    tier to at least "review".
    """
    if _has_payout_indicators(envelope.decision):
        result.reversible = False
        result.approval_tier = _escalate_tier(result.approval_tier, "review")
    else:
        result.reversible = True
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 — risk_classification
# ═══════════════════════════════════════════════════════════════════════════


def _stage4_risk_classification(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Classify risk type.

    Priority order:
    1. Any triggered detection in ``rule_anomalies`` → "financial"
    2. Burn alert or failed payment indicators → "financial"
    3. Privacy-sensitive (PII detected) → "legal"
    4. Investor-facing → "reputational"
    5. Default → "operational"
    """
    # 1. Triggered finance rules
    if envelope.finance_snapshot.rule_anomalies:
        result.risk_type = "financial"
    # 2. Burn alert
    elif _has_burn_alert(envelope.finance_snapshot):
        result.risk_type = "financial"
    # 3. Privacy-sensitive
    elif result.privacy_sensitive:
        result.risk_type = "legal"
    # 4. Investor-facing
    elif result.investor_facing:
        result.risk_type = "reputational"
    # 5. Default
    else:
        result.risk_type = "operational"

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Stage 5 — privacy
# ═══════════════════════════════════════════════════════════════════════════


def _stage5_privacy(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Check for PII indicators in decision text.

    If domain is "ops" AND the combined decision text contains PII
    (email, phone, or address patterns) → set ``privacy_sensitive=True``
    and bump approval tier to at least "review".
    """
    text = f"{envelope.decision.primary_signal} {envelope.decision.context_note}"
    if envelope.domain == "ops" and _contains_pii(text):
        result.privacy_sensitive = True
        result.approval_tier = _escalate_tier(result.approval_tier, "review")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Stage 6 — approval_tier_final
# ═══════════════════════════════════════════════════════════════════════════


def _stage6_approval_tier_final(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Final approval tier determination.

    Rules:
    - If ``blocking`` is True → tier is "blocking".
    - If ``privacy_sensitive`` is True AND not already "blocking" →
      tier is at least "review".
    """
    if result.blocking:
        result.approval_tier = "blocking"
    elif result.privacy_sensitive and result.approval_tier != "blocking":
        result.approval_tier = _escalate_tier(result.approval_tier, "review")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Stage 7 — blocking_override
# ═══════════════════════════════════════════════════════════════════════════


def _stage7_blocking_override(
    envelope: BusinessDecisionEnvelope,
    result: GuardrailResult,
) -> GuardrailResult:
    """Blocking override for critical conditions.

    Sets ``blocking=True`` when:
    - Multiple critical conditions met: investor-facing + irreversible
      + risk=financial, OR
    - Approval tier is "blocking" AND no override reason is provided.
    """
    multiple_critical = (
        result.investor_facing
        and not result.reversible
        and result.risk_type == "financial"
    )
    blocking_without_reason = (
        result.approval_tier == "blocking"
        and not result.override_reason
    )
    if multiple_critical or blocking_without_reason:
        result.blocking = True
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Main Entry Points
# ═══════════════════════════════════════════════════════════════════════════


@traced(agent="guardrails", signature="evaluate", as_type="span")
def evaluate_envelope(envelope: BusinessDecisionEnvelope) -> GuardrailResult:
    """Evaluate a BusinessDecisionEnvelope through all 7 guardrail stages.

    Pure deterministic function. No LLM calls. No side effects.
    ALL 7 stages run sequentially — no short-circuiting.

    Args:
        envelope: The fully composed business decision envelope.

    Returns:
        A fully populated GuardrailResult.
    """
    result = envelope.guardrail_status

    result = _stage1_investor_facing(envelope, result)
    result = _stage2_authority(envelope, result)
    result = _stage3_reversibility(envelope, result)
    result = _stage4_risk_classification(envelope, result)
    result = _stage5_privacy(envelope, result)
    result = _stage6_approval_tier_final(envelope, result)
    result = _stage7_blocking_override(envelope, result)

    return result


def evaluate_decision(
    event: EventEnvelope,
    decision: AlertDecision,
    finance_snapshot: FinancialSnapshot,
) -> GuardrailResult:
    """Convenience wrapper: creates envelope, evaluates, returns guardrail result.

    Infers the domain from the event source, constructs a minimal
    ``BusinessDecisionEnvelope``, and runs the full evaluation pipeline.

    Args:
        event: The incoming event envelope.
        decision: The alert decision from the guardian agent.
        finance_snapshot: Computed financial metrics (from finance_rules.py).

    Returns:
        Fully populated GuardrailResult.
    """
    domain = _infer_domain(event, decision)
    envelope = BusinessDecisionEnvelope(
        event=event,
        decision=decision,
        finance_snapshot=finance_snapshot,
        domain=domain,
        guardrail_status=GuardrailResult(approval_tier="auto"),
        reversible=True,
        approval_tier="auto",
    )
    return evaluate_envelope(envelope)
