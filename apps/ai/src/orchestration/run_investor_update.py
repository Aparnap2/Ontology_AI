"""
Investor Update Orchestration.

Reuses existing run_investor_agent and check_relationship_health logic.
Preserves criteria-based evaluation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from uuid import uuid4

from src.activities.run_investor_agent import run_investor_agent
from src.activities.check_relationship_health import check_relationship_health
from src.activities.send_slack_message import send_slack_message
from src.events import emit
from src.db import db

log = logging.getLogger(__name__)


async def get_investor_warmup_alerts(tenant_id: str) -> List[Dict]:
    """
    Returns investors overdue for contact based on their warm_up_days window.
    Sorted by raise priority (1 = warmest) then days overdue descending.
    """
    rows = await db.fetch("""
        SELECT
            ir.id as relationship_id,
            ir.investor_name,
            ir.firm,
            ir.raise_priority,
            ir.warm_up_days,
            ir.last_contact_at,
            EXTRACT(DAY FROM NOW() - ir.last_contact_at)::INT AS days_since_contact,
            EXTRACT(DAY FROM NOW() - ir.last_contact_at)::INT
                - ir.warm_up_days AS days_overdue,
            ir.notes AS last_interaction_summary
        FROM investor_relationships ir
        WHERE ir.tenant_id = %s
          AND ir.last_contact_at IS NOT NULL
          AND NOW() - ir.last_contact_at > (ir.warm_up_days || ' days')::interval
        ORDER BY ir.raise_priority ASC, days_overdue DESC
        LIMIT 5
    """, (tenant_id,))

    return [dict(r) for r in rows]


async def get_investor_status_summary(tenant_id: str) -> Dict:
    """
    Full investor status for weekly synthesis.
    """
    overdue = await get_investor_warmup_alerts(tenant_id)

    total_row = await db.fetchval("""
        SELECT COUNT(*) FROM investor_relationships WHERE tenant_id = %s
    """, tenant_id)

    return {
        "total_tracked": total_row or 0,
        "overdue_count": len(overdue),
        "overdue": overdue,
        "top_priority": overdue[0]["investor_name"] if overdue else None,
    }


async def run_investor_update(tenant_id: str) -> dict[str, Any]:
    """
    Run investor update job.

    This orchestrates:
    1. Check investor relationship health (warmup alerts)
    2. Run InvestorAgent to generate investor update
    3. Send Slack notification

    Args:
        tenant_id: Tenant identifier

    Returns:
        dict with execution results
    """
    run_id = str(uuid4())
    log.info(f"Running investor update for {tenant_id}, run_id={run_id}")

    result = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "relationship_health": {},
        "investor_result": {},
        "ok": True,
    }

    # Step 1: Check relationship health
    try:
        relationship_health = await check_relationship_health(tenant_id)
        result["relationship_health"] = relationship_health

        if relationship_health.get("ok") and relationship_health.get("high_priority_cold", 0) > 0:
            cold_count = relationship_health["high_priority_cold"]
            log.warning(f"{cold_count} high-priority investors need warmup")

    except Exception as e:
        log.warning(f"Relationship health check failed: {e}")

    # Step 2: Run InvestorAgent
    try:
        investor_result = await run_investor_agent(tenant_id)
        result["investor_result"] = investor_result

        if not investor_result.get("ok"):
            error_msg = investor_result.get("error", "Unknown error")
            log.error(f"InvestorAgent failed: {error_msg}")

            try:
                await send_slack_message(
                    f"❌ Investor Update failed for {tenant_id}: {error_msg}",
                )
            except Exception as slack_err:
                log.error(f"Slack notification failed: {slack_err}")

            result["ok"] = False
            result["error"] = error_msg
            return result

        log.info(f"InvestorAgent completed: {investor_result.get('narrative', '')[:100]}")

    except Exception as e:
        log.error(f"InvestorAgent activity failed: {e}")

        try:
            await send_slack_message(
                f"❌ Investor Update failed for {tenant_id}: {str(e)}",
            )
        except Exception as slack_err:
            log.error(f"Slack notification failed: {slack_err}")

        result["ok"] = False
        result["error"] = str(e)
        return result

    # Step 3: Send Slack notification
    try:
        narrative = investor_result.get("narrative", "No narrative generated")
        slack_blocks = investor_result.get("slack_blocks", [])

        await send_slack_message(
            narrative,
            blocks=slack_blocks if slack_blocks else None,
        )

    except Exception as e:
        log.warning(f"Slack notification failed: {e}")

    # Emit completion event
    await emit("investor.completed", tenant_id, {
        "run_id": run_id,
        "agent": "investor",
    })

    return result