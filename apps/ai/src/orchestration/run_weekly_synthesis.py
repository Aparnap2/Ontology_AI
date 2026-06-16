"""
Weekly Synthesis Orchestration.

Aggregates metrics, alerts, decisions, and investor state into a weekly brief.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from src.activities.synthesize_weekly_brief import synthesize_weekly_brief
from src.activities.send_slack_message import send_slack_message
from src.config.database import get_database_url
from src.events.bus import emit
from src.db.db import get_db_connection

log = logging.getLogger(__name__)


async def get_current_metrics_snapshot(tenant_id: str) -> dict[str, Any]:
    """Get current metrics snapshot from finance_snapshots table."""
    import psycopg2
    DATABASE_URL = get_database_url()
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Query finance_snapshots for real KPIs
        cur.execute("""
            SELECT monthly_revenue, monthly_expense, burn_rate, runway_months, created_at
            FROM finance_snapshots
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (tenant_id,))

        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return {
                "monthly_revenue": row[0],
                "monthly_expense": row[1],
                "burn_rate": row[2],
                "runway_months": row[3],
                "snapshot_at": row[4].isoformat() if row[4] else None,
            }
        return {}
    except Exception as e:
        log.error(f"Failed to get metrics snapshot: {e}")
        return {}


async def get_recent_alerts(tenant_id: str, days: int = 7) -> list[dict[str, Any]]:
    """Get recent alerts from database."""
    import psycopg2
    DATABASE_URL = get_database_url()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Use bind parameter for interval - pass days value and construct interval in SQL
    cur.execute("""
        SELECT id, title, severity, created_at
        FROM agentalerts
        WHERE tenant_id = %s
          AND created_at >= NOW() - (CAST(%s AS TEXT) || ' days')::interval
        ORDER BY created_at DESC
    """, (tenant_id, days))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "severity": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


async def get_recent_investor_state(tenant_id: str, days: int = 14) -> dict[str, Any]:
    """Get recent investor state."""
    import psycopg2
    DATABASE_URL = get_database_url()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Filter by days parameter
    cur.execute("""
        SELECT narrative, created_at
        FROM investorupdates
        WHERE tenant_id = %s
          AND created_at >= NOW() - (CAST(%s AS TEXT) || ' days')::interval
        ORDER BY created_at DESC
        LIMIT 1
    """, (tenant_id, days))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        return {"narrative": row[0]}
    return {}


async def get_recent_decisions(tenant_id: str, days: int = 14) -> list[dict[str, Any]]:
    """Get recent decisions if table exists."""
    import psycopg2
    from psycopg2 import errors as psycopg2_errors
    
    DATABASE_URL = get_database_url()
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, decided, reasoning, created_at
            FROM decisions
            WHERE tenant_id = %s
              AND created_at >= NOW() - (CAST(%s AS TEXT) || ' days')::interval
            ORDER BY created_at DESC
        """, (tenant_id, days))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "id": row[0],
                "decided": row[1],
                "reasoning": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
            }
            for row in rows
        ]
    except psycopg2_errors.UndefinedTable as e:
        log.warning(f"Decisions table not found: {e}")
        return []
    except Exception as e:
        log.error(f"Failed to get recent decisions: {e}")
        raise


async def run_weekly_synthesis(tenant_id: str) -> dict[str, Any]:
    """
    Run weekly synthesis job.

    This orchestrates:
    1. Get current metrics snapshot
    2. Get recent alerts (7 days)
    3. Get recent investor state (14 days)
    4. Get recent decisions (14 days)
    5. Synthesize into weekly brief
    6. Send to Slack

    Args:
        tenant_id: Tenant identifier

    Returns:
        dict with execution results
    """
    run_id = str(uuid4())
    log.info(f"Running weekly synthesis for {tenant_id}, run_id={run_id}")

    result = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "brief": "",
        "ok": True,
    }

    # Collect data
    try:
        metrics = await get_current_metrics_snapshot(tenant_id)
        alerts = await get_recent_alerts(tenant_id, days=7)
        investor = await get_recent_investor_state(tenant_id, days=14)
        decisions = await get_recent_decisions(tenant_id, days=14)

        log.info(f"Weekly synthesis data: {len(alerts)} alerts, {len(decisions)} decisions")

    except Exception as e:
        log.error(f"Failed to collect data: {e}")
        result["ok"] = False
        result["error"] = str(e)
        return result

    # Synthesize brief
    try:
        brief = await synthesize_weekly_brief(
            tenant_id=tenant_id,
            alerts=alerts,
            decisions=decisions,
            metrics=metrics,
            investor_status=investor,
            founder_name="Founder",
            company_name="Company",
        )

        result["brief"] = brief

    except Exception as e:
        log.error(f"Failed to synthesize brief: {e}")
        result["ok"] = False
        result["error"] = str(e)
        return result

    # Send to Slack
    try:
        await send_slack_message(brief)

    except Exception as e:
        log.warning(f"Failed to send brief: {e}")

    # Emit completion event
    await emit("weekly_synthesis.completed", tenant_id, {
        "run_id": run_id,
        "agent": "weekly_synthesis",
    })

    return result