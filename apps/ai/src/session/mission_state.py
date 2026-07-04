"""
MissionState — Shared Context Object.

Per PRD Section 11:
All agents read MissionState before running.
All agents write their domain fields after running.
Stored in PostgreSQL `mission_states` table. Updated atomically.

Schema matches 001_session_layer.sql (columns, not JSONB).
"""
from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.config.database import get_database_url

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url("iterateswarm")


@dataclass
class MissionState:
    """Shared context object read/written by all agents.

    Per PRD Section 11:
    - All agents read MissionState before running
    - All agents write their domain fields after running
    - Stored in PostgreSQL mission_states table

    Schema matches 001_session_layer.sql (columns, not JSONB).
    """

    tenant_id: str
    timestamp: datetime | None = None

    # Data Quality Gate fields
    data_last_synced: datetime | None = None
    mrr: float | None = None
    burn_rate: float | None = None

    # Finance domain (Finance Guardian writes)
    runway_days: int | None = None
    burn_alert: bool = False
    burn_severity: str | None = None  # low, medium, high, critical

    # BI domain (BI Analyst writes)
    mrr_trend: str | None = None  # growing, stable, declining
    churn_rate: float | None = None

    # Ops domain (Ops Watch writes)
    churn_risk_users: str | None = None  # comma-separated
    top_feature_ask: str | None = None
    error_spike: bool = False

    # Cross-agent signals (Co-founder manages)
    active_alerts: str | None = None  # comma-separated
    founder_focus: str | None = None

    # Trust Battery integration (V3.0)
    trust_score: float | None = None  # 0.00-1.00 from trust battery
    route_priority: int | None = None  # routing priority based on trust

    # Runtime fields (not persisted to DB)
    skip_reason: str | None = None
    data_quality: "DataQualityResult" = None

    # ── Derived finance metrics (from finance_rules.py) ─────────────
    burn_multiple: float | None = None
    effective_runway_days: int | None = None
    working_capital_ratio: float | None = None
    npv_last_decision: float | None = None
    wacc_estimate: float | None = None

    # ── Guardrail state fields (from guardrails.py) ────────────────
    last_approval_tier: str | None = None         # auto | review | blocking
    last_reversible: bool | None = None
    active_authority_limit: str | None = None      # founder | board | none
    guardrail_override_reason: str | None = None

    # ── Decision pipeline fields ────────────────────────────────────
    guardrail_risk_type: str | None = None         # financial | legal | reputational | operational | none
    guardrail_blocking: bool = False
    investor_facing_alert: bool = False

    # ── Cognitive offloading fields ──────────────────────────────────
    prepared_brief: str | None = None              # LLM-generated brief for founder context
    pending_decisions: list[dict] | None = None    # JSONB array of pending founder decisions
    last_updated_by: str | None = None             # which agent/specialist last wrote to MissionState

    # ── Explainability fields (Paperclip-inspired) ──────────────────
    last_update_reason: str | None = None          # why this write happened
    last_changed_fields: list[str] | None = None   # which fields were modified
    active_agent_roles: list[str] | None = None    # derived from authority manifest

    # ── Policy state ─────────────────────────────────────────────────
    policy_state: dict | None = None               # last PolicyDecision dict for dashboard display


async def get_mission_state(tenant_id: str) -> MissionState:
    """Get MissionState from database.

    Returns empty MissionState if not found (graceful fallback per PRD Section 25).

    Args:
        tenant_id: The tenant to get state for

    Returns:
        MissionState (empty if not found)
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow(
            """
            SELECT tenant_id, timestamp, runway_days, burn_alert, burn_severity,
                   mrr_trend, churn_rate, churn_risk_users, top_feature_ask,
                   error_spike, active_alerts, founder_focus, trust_score, route_priority,
                   burn_multiple, effective_runway_days, working_capital_ratio,
                   npv_last_decision, wacc_estimate, last_approval_tier, last_reversible,
                   active_authority_limit, guardrail_override_reason, guardrail_risk_type,
                   guardrail_blocking, investor_facing_alert,
                   prepared_brief, pending_decisions, last_updated_by,
                   last_update_reason, last_changed_fields, active_agent_roles,
                   policy_state
            FROM mission_states
            WHERE tenant_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            tenant_id,
        )
        await conn.close()

        if row:
            return MissionState(
                tenant_id=row["tenant_id"],
                timestamp=row["timestamp"],
                runway_days=row["runway_days"],
                burn_alert=row["burn_alert"],
                burn_severity=row["burn_severity"],
                mrr_trend=row["mrr_trend"],
                churn_rate=row["churn_rate"],
                churn_risk_users=row["churn_risk_users"],
                top_feature_ask=row["top_feature_ask"],
                error_spike=row["error_spike"],
                active_alerts=row["active_alerts"],
                founder_focus=row["founder_focus"],
                trust_score=row["trust_score"],
                route_priority=row["route_priority"],
                burn_multiple=row["burn_multiple"],
                effective_runway_days=row["effective_runway_days"],
                working_capital_ratio=row["working_capital_ratio"],
                npv_last_decision=row["npv_last_decision"],
                wacc_estimate=row["wacc_estimate"],
                last_approval_tier=row["last_approval_tier"],
                last_reversible=row["last_reversible"],
                active_authority_limit=row["active_authority_limit"],
                guardrail_override_reason=row["guardrail_override_reason"],
                guardrail_risk_type=row["guardrail_risk_type"],
                guardrail_blocking=row["guardrail_blocking"],
                investor_facing_alert=row["investor_facing_alert"],
                prepared_brief=row["prepared_brief"],
                pending_decisions=row["pending_decisions"],
                last_updated_by=row["last_updated_by"],
                last_update_reason=row["last_update_reason"],
                last_changed_fields=row["last_changed_fields"],
                active_agent_roles=row["active_agent_roles"],
                policy_state=row["policy_state"],
            )
    except Exception as e:
        log.warning(f"MissionState lookup failed for {tenant_id}: {e}")

    return MissionState(tenant_id=tenant_id)


async def update_mission_state(state: MissionState, generate_brief: bool = True, update_reason: str | None = None, changed_fields: list[str] | None = None) -> bool:
    """Update MissionState in database atomically.

    Per PRD Section 11: Updated atomically.

    Args:
        state: MissionState to persist
        generate_brief: Whether to auto-generate prepared_brief if missing
        update_reason: Why this write happened
        changed_fields: Which fields were modified in this update

    Returns:
        True if successful, False otherwise
    """
    if generate_brief:
        state.last_update_reason = update_reason
        state.last_changed_fields = changed_fields
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            """
            INSERT INTO mission_states (
                tenant_id, timestamp, runway_days, burn_alert, burn_severity,
                mrr_trend, churn_rate, churn_risk_users, top_feature_ask,
                error_spike, active_alerts, founder_focus, trust_score, route_priority,
                burn_multiple, effective_runway_days, working_capital_ratio,
                npv_last_decision, wacc_estimate, last_approval_tier, last_reversible,
                active_authority_limit, guardrail_override_reason, guardrail_risk_type,
                guardrail_blocking, investor_facing_alert, created_at,
                prepared_brief, pending_decisions, last_updated_by,
                last_update_reason, last_changed_fields, active_agent_roles,
                policy_state
            )
            VALUES ($1, NOW(), $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, NOW(),
                    $26, $27, $28, $29, $30, $31, $32)
            ON CONFLICT (tenant_id) DO UPDATE SET
                timestamp = NOW(),
                runway_days = EXCLUDED.runway_days,
                burn_alert = EXCLUDED.burn_alert,
                burn_severity = EXCLUDED.burn_severity,
                mrr_trend = EXCLUDED.mrr_trend,
                churn_rate = EXCLUDED.churn_rate,
                churn_risk_users = EXCLUDED.churn_risk_users,
                top_feature_ask = EXCLUDED.top_feature_ask,
                error_spike = EXCLUDED.error_spike,
                active_alerts = EXCLUDED.active_alerts,
                founder_focus = EXCLUDED.founder_focus,
                trust_score = EXCLUDED.trust_score,
                route_priority = EXCLUDED.route_priority,
                burn_multiple = EXCLUDED.burn_multiple,
                effective_runway_days = EXCLUDED.effective_runway_days,
                working_capital_ratio = EXCLUDED.working_capital_ratio,
                npv_last_decision = EXCLUDED.npv_last_decision,
                wacc_estimate = EXCLUDED.wacc_estimate,
                last_approval_tier = EXCLUDED.last_approval_tier,
                last_reversible = EXCLUDED.last_reversible,
                active_authority_limit = EXCLUDED.active_authority_limit,
                guardrail_override_reason = EXCLUDED.guardrail_override_reason,
                guardrail_risk_type = EXCLUDED.guardrail_risk_type,
                guardrail_blocking = EXCLUDED.guardrail_blocking,
                investor_facing_alert = EXCLUDED.investor_facing_alert,
                prepared_brief = EXCLUDED.prepared_brief,
                pending_decisions = EXCLUDED.pending_decisions,
                last_updated_by = EXCLUDED.last_updated_by,
                last_update_reason = EXCLUDED.last_update_reason,
                last_changed_fields = EXCLUDED.last_changed_fields,
                active_agent_roles = EXCLUDED.active_agent_roles,
                policy_state = EXCLUDED.policy_state
            """,
            state.tenant_id,
            state.runway_days,
            state.burn_alert,
            state.burn_severity,
            state.mrr_trend,
            state.churn_rate,
            state.churn_risk_users,
            state.top_feature_ask,
            state.error_spike,
            state.active_alerts,
            state.founder_focus,
            state.trust_score,
            state.route_priority,
            state.burn_multiple,
            state.effective_runway_days,
            state.working_capital_ratio,
            state.npv_last_decision,
            state.wacc_estimate,
            state.last_approval_tier,
            state.last_reversible,
            state.active_authority_limit,
            state.guardrail_override_reason,
            state.guardrail_risk_type,
            state.guardrail_blocking,
            state.investor_facing_alert,
            state.prepared_brief,
            state.pending_decisions,
            state.last_updated_by,
            state.last_update_reason,
            json.dumps(state.last_changed_fields) if state.last_changed_fields else '[]',
            json.dumps(state.active_agent_roles) if state.active_agent_roles else '[]',
            json.dumps(state.policy_state) if state.policy_state else None,
        )
        await conn.close()
        if generate_brief and not state.prepared_brief:
            try:
                from src.session.brief_generator import generate_prepared_brief
                await generate_prepared_brief(state.tenant_id)
            except Exception:
                log.exception("generate_prepared_brief callback failed")
        log.info(f"MissionState updated for tenant: {state.tenant_id}")
        return True
    except Exception as e:
        log.error(f"MissionState update failed for {state.tenant_id}: {e}")
        return False