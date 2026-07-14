"""
Synthesize Weekly Brief Activity for Temporal.

Uses LLM to synthesize weekly brief from alerts, decisions, and metrics.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from temporalio import activity

from src.llm.client import LLMClient

log = logging.getLogger(__name__)

WEEKLY_SYNTHESIS_PROMPT = """
You are OntologyAI — a founder's Chief of Staff.
Write the Monday morning brief for {founder_name} at {company_name}.

RULES:
- Start with ONE THING — the single most important thing this week
- Be direct. No fluff. No "leverage". No "synergy".
- Numbers first, then narrative
- Maximum 300 words total
- If the decision log has a relevant entry, reference it
- End with [Ask OntologyAI anything] as a Slack button, not text

DATA:
Metrics: {metrics}
Alerts this week: {alerts}
Investor status: {investor_status}
Recent decisions: {decisions}

Write the brief now. Start with the emoji 🎯 and ONE THING.
"""

@activity.defn(name="synthesize_weekly_brief")
async def synthesize_weekly_brief(
    tenant_id: str,
    alerts: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    metrics: dict[str, Any],
    investor_status: dict[str, Any],
    founder_name: str = "Founder",
    company_name: str = "Company"
) -> str:
    """
    Synthesize all data into weekly brief using LLM.

    Args:
        tenant_id: Tenant identifier
        alerts: List of alert dictionaries
        decisions: List of decision dictionaries
        metrics: Current metrics snapshot
        investor_status: Investor relationship health
        founder_name: Name of the founder
        company_name: Name of the company

    Returns:
        Synthesized weekly brief text
    """
    if not tenant_id:
        return "Error: tenant_id is required"

    try:
        # Format data for prompt
        metrics_str = "\n".join([f"- {k}: {v}" for k, v in metrics.items()])
        alerts_str = "\n".join([f"- {alert.get('message', 'Alert')}" for alert in alerts])
        decisions_str = "\n".join([f"- {decision.get('decided', 'Decision')}" for decision in decisions])
        investor_str = "\n".join([f"- {k}: {v}" for k, v in investor_status.items()])

        prompt = WEEKLY_SYNTHESIS_PROMPT.format(
            founder_name=founder_name,
            company_name=company_name,
            metrics=metrics_str,
            alerts=alerts_str,
            investor_status=investor_str,
            decisions=decisions_str,
        )

        # Call LLM
        llm_client = LLMClient()
        response = await llm_client.generate_completion(
            prompt=prompt,
            max_tokens=300,
            temperature=0.3,
        )

        brief = response.get("text", "").strip()
        if not brief:
            # Fallback brief
            brief = f"🎯 ONE THING: Review business metrics\n\nWeekly Brief for {founder_name} at {company_name}\n\nMetrics this week:\n{metrics_str}\n\n[Ask OntologyAI anything]"

        return brief

    except Exception as e:
        log.error(f"Failed to synthesize weekly brief for tenant {tenant_id}: {e}")
        return f"🎯 ONE THING: Check system status\n\nError generating weekly brief. Please contact support.\n\n[Ask OntologyAI anything]"