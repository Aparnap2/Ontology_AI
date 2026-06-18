"""
Startup Guardian Orchestration — Startup Health Assessment Pipeline.

Assembles the unified MissionStateV2 from multiple data connectors and
computes cross-domain overall health. Sends Slack alerts on CRITICAL/ATTENTION.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from src.activities.send_slack_message import send_slack_message
from src.events.bus import emit
from src.guardian.assemblers import (
    assemble_execution_state,
    assemble_finance_state,
    assemble_revenue_state,
    assemble_support_state,
    assemble_team_state,
)
from src.integrations.erpnext import get_erpnext_snapshot
from src.integrations.hubspot import get_hubspot_snapshot
from src.integrations.quickbooks import get_quickbooks_snapshot
from src.services.dead_letter import send_to_dlq
from src.states.schemas import (
    ExecutionHealth,
    FinancialHealth,
    MissionStateV2,
    SupportHealth,
)

log = logging.getLogger(__name__)

_CONNECTORS: list[tuple[str, Any]] = [
    ("erpnext", get_erpnext_snapshot),
    ("hubspot", get_hubspot_snapshot),
    ("quickbooks", get_quickbooks_snapshot),
]

_HEALTH_MAP: dict[str, SupportHealth] = {
    "critical": SupportHealth.CRITICAL,
    "attention": SupportHealth.ATTENTION,
    "good": SupportHealth.GOOD,
    "on_track": SupportHealth.GOOD,
    "at_risk": SupportHealth.ATTENTION,
    "blocked": SupportHealth.CRITICAL,
    "healthy": SupportHealth.GOOD,
    "warning": SupportHealth.ATTENTION,
}

_HEALTH_PRIORITY: list[SupportHealth] = [
    SupportHealth.CRITICAL,
    SupportHealth.ATTENTION,
    SupportHealth.GOOD,
]


def _map_health(health: Any) -> SupportHealth:
    raw = health.value if hasattr(health, "value") else str(health)
    return _HEALTH_MAP.get(raw, SupportHealth.GOOD)


def _format_health_emoji(health: SupportHealth) -> str:
    return {
        SupportHealth.CRITICAL: "🔴",
        SupportHealth.ATTENTION: "🟡",
        SupportHealth.GOOD: "🟢",
    }.get(health, "⚪")


def _build_alert_message(state: MissionStateV2) -> str:
    """Build human-readable Slack alert from MissionStateV2."""
    emoji = _format_health_emoji(state.overall_health)
    lines = [
        f"{emoji} *Startup Guardian — {state.overall_health.value.upper()}*",
        f"Tenant: `{state.tenant_id}` | Run: `{state.run_id[:8]}`",
        "",
        "*Domain Health:*",
        f"  • Support: {state.support.health.value}",
        f"  • Execution: {state.execution.health.value}",
        f"  • Team: {state.team.health.value}",
        f"  • Finance: {state.finance.health.value}",
        f"  • Revenue: {state.revenue.health.value}",
    ]

    failed = [k for k, v in state.connectors_ok.items() if not v]
    if failed:
        lines.append("")
        lines.append(f"⚠️ *Failed connectors:* {', '.join(failed)}")

    return "\n".join(lines)


async def run_startup_guardian(tenant_id: str) -> dict[str, Any]:
    run_id = str(uuid4())
    state = MissionStateV2(tenant_id=tenant_id, run_id=run_id)
    log.info("Starting Startup Guardian run_id=%s tenant=%s", run_id, tenant_id)

    connectors_ok: dict[str, bool] = {}
    snapshots: dict[str, dict[str, Any]] = {}

    for name, func in _CONNECTORS:
        try:
            snap = await asyncio.to_thread(func, tenant_id)
            snapshots[name] = snap
            connectors_ok[name] = True
            log.info("Connector %s succeeded for tenant %s", name, tenant_id)
        except Exception as exc:
            log.error("Connector %s failed for tenant %s: %s", name, tenant_id, exc)
            connectors_ok[name] = False
            send_to_dlq(
                source=name,
                operation=f"get_{name}_snapshot",
                error=str(exc),
                tenant_id=tenant_id,
            )

    if "erpnext" in snapshots:
        raw = snapshots["erpnext"]
        state.support = assemble_support_state(raw)
        state.execution = assemble_execution_state(raw)
        state.team = assemble_team_state(raw)
        state.finance = assemble_finance_state(raw)

    if "hubspot" in snapshots:
        raw = snapshots["hubspot"]
        state.revenue = assemble_revenue_state(raw)

    if "quickbooks" in snapshots:
        raw = snapshots["quickbooks"]
        state.finance = assemble_finance_state(raw)

    domain_healths = [
        _map_health(state.support.health),
        _map_health(state.execution.health),
        _map_health(state.team.health),
        _map_health(state.finance.health),
    ]

    worst = SupportHealth.GOOD
    for h in domain_healths:
        if _HEALTH_PRIORITY.index(h) < _HEALTH_PRIORITY.index(worst):
            worst = h
    state.overall_health = worst

    state.connectors_ok = connectors_ok
    state.raw_snapshots = snapshots

    log.info("Startup Guardian complete run_id=%s tenant=%s ok=%s", run_id, tenant_id, all(connectors_ok.values()))

    # ── Alert delivery (non-blocking) ──────────────────────────────
    if state.overall_health in (SupportHealth.CRITICAL, SupportHealth.ATTENTION):
        try:
            alert_text = _build_alert_message(state)
            await send_slack_message(alert_text)
            await emit("startup_guardian.alert_delivered", tenant_id, {
                "run_id": run_id,
                "overall_health": state.overall_health.value,
                "connectors_ok": connectors_ok,
            })
        except Exception as exc:
            log.warning("Failed to send Startup Guardian alert: %s", exc)

    # Emit completion event
    await emit("startup_guardian.completed", tenant_id, {
        "run_id": run_id,
        "overall_health": state.overall_health.value,
        "connectors_ok": connectors_ok,
    })

    return state.model_dump()
