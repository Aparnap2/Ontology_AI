"""Tool: draft_investor_update — HITL Tier: approve.

Always requires founder approval before sending. Assembles the
latest mission state metrics into an investor-facing update email.

Integrates prompt risk scanning (pre-generation), output risk scanning
(post-generation), and audit logging via the control plane.
"""
from __future__ import annotations

import logging
from typing import Any

from src.config.llm import chat_completion
from src.control_plane.audit import AuditLogger
from src.control_plane.policy import PolicyEngine
from src.control_plane.registry import ControlPlaneRegistry
from src.risk.prompt_risk import scan_prompt
from src.risk.output_risk import scan_output
from src.schemas.control_plane import AgentRegistration, AuditEvent
from src.session.mission_state import get_mission_state

log = logging.getLogger(__name__)

# Module-level control plane instances (registration happens at app startup)
_REGISTRY = ControlPlaneRegistry()
_POLICY = PolicyEngine()
_AUDIT = AuditLogger()

tool_def: dict[str, Any] = {
    "name": "draft_investor_update",
    "description": "Draft an investor update email for founder approval",
    "hitl_tier": "approve",
    "trigger_patterns": ["schedule", "manual"],
}


async def execute(tenant_id: str) -> dict[str, Any]:
    """Draft investor update with prompt/output risk scanning and audit logging.

    Args:
        tenant_id: Tenant identifier.

    Returns:
        Dict with draft text, risk scan results, audit event, and
        requires_approval flag.
    """
    log.info("draft_investor_update %s — tier=approve (risk-gated)", tenant_id)
    state = await get_mission_state(tenant_id)

    metrics = (
        f"Runway: {state.runway_days}d | "
        f"MRR trend: {state.mrr_trend} | "
        f"Churn: {state.churn_rate} | "
        f"Trust: {state.trust_score}"
    )
    metrics_prompt = (
        f"Write a brief investor update email draft based on: {metrics}. "
        "Professional tone, 2-3 paragraphs."
    )

    # ── Pre-generation prompt risk scan ──────────────────────────────
    prompt_scan = scan_prompt(metrics_prompt, context="investor_update")
    if prompt_scan.recommended_action == "block":
        log.warning("draft_investor_update %s — prompt risk scan blocked", tenant_id)
        return {
            "error": "Prompt risk scan blocked",
            "scan_result": prompt_scan.model_dump(),
            "tenant_id": tenant_id,
            "requires_approval": True,
        }

    # ── LLM call ─────────────────────────────────────────────────────
    draft = chat_completion(
        messages=[{"role": "user", "content": metrics_prompt}],
        max_tokens=300,
        temperature=0.5,
    )

    # ── Post-generation output risk scan ─────────────────────────────
    output_scan = scan_output(draft, context="investor_update")
    if output_scan.recommended_action == "block":
        log.warning("draft_investor_update %s — output risk scan blocked", tenant_id)
        audit_event = AuditEvent(
            agent_name="Sarthi",
            action="tool_execution",
            tool_name="draft_investor_update",
            model_used="gpt-4o",
            approval_state="blocked",
            outcome="blocked",
            tenant_id=tenant_id,
            details={
                "output_scan": output_scan.model_dump(),
                "reason": "Output risk scan blocked draft",
            },
        )
        _AUDIT.log(audit_event)
        return {
            "draft": draft,
            "risk_scan": output_scan.model_dump(),
            "tenant_id": tenant_id,
            "requires_approval": True,
            "message": "Draft blocked by output risk scan — requires approval",
        }

    # ── Audit log on successful generation ───────────────────────────
    audit_event = AuditEvent(
        agent_name="Sarthi",
        action="tool_execution",
        tool_name="draft_investor_update",
        model_used="gpt-4o",
        approval_state="approve",
        outcome="completed",
        tenant_id=tenant_id,
        details={
            "prompt_scan": prompt_scan.model_dump(),
            "output_scan": output_scan.model_dump(),
        },
    )
    _AUDIT.log(audit_event)

    return {
        "draft": draft,
        "tenant_id": tenant_id,
        "requires_approval": True,
        "audit_event": audit_event.model_dump(),
    }
