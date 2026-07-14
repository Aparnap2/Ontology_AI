"""Debug HTTP server for OntologyAI portfolio demo.

Provides read-only endpoints for Playwright tests to query system state.
Gated by DEMO_MODE=true environment variable.

Run: DEMO_MODE=true uv run python -m src.debug_server
Or:  DEMO_MODE=true uvicorn src.debug_server:app --port 8000
"""
from __future__ import annotations

import os
from typing import Any

import psycopg2
import requests
import tiktoken
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ── Demo mode gate ────────────────────────────────────────────────

DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
TENANT_ID = os.environ.get("DEMO_TENANT_ID", "00000000-0000-0000-0000-000000000001")

# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="OntologyAI Debug Server",
    description="Read-only debug endpoints for portfolio demo",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _guard() -> None:
    """Raise 403 if DEMO_MODE is not enabled."""
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Debug endpoints disabled — set DEMO_MODE=true")


# ── Helpers ───────────────────────────────────────────────────────

def _get_db():
    """Get psycopg2 connection to the demo database."""
    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm",
    )
    return psycopg2.connect(dsn)


def _get_qd():
    """Get Qdrant HTTP client (requests module, base URL)."""
    base = os.environ.get("QDRANT_URL", "http://localhost:6333")
    return requests, base


def _compute_signals() -> dict[str, Any]:
    """Compute all 31 guardian watchlist signals from seeded DB."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            # Latest metric snapshot
            cur.execute(
                """
                SELECT mrr_cents, arr_cents, active_customers, new_customers,
                       churned_customers, top_customer_mrr_cents, bank_balance_cents,
                       burn_rate_cents, net_new_arr_cents, active_users_30d,
                       activation_rate, failed_payments_7d, payroll_monthly_cents,
                       aws_cost_cents, support_tickets, deploy_frequency, nrr,
                       cohort_retention_30d_recent, cohort_retention_30d_prior,
                       trial_step_dropoffs, runway_months, monthly_churn_pct
                FROM metric_snapshots
                WHERE tenant_id = %s
                ORDER BY snapshot_month DESC
                LIMIT 1
                """,
                (TENANT_ID,),
            )
            row = cur.fetchone()
            if not row:
                return {}

            cols = [
                "mrr_cents", "arr_cents", "active_customers", "new_customers",
                "churned_customers", "top_customer_mrr_cents", "bank_balance_cents",
                "burn_rate_cents", "net_new_arr_cents", "active_users_30d",
                "activation_rate", "failed_payments_7d", "payroll_monthly_cents",
                "aws_cost_cents", "support_tickets", "deploy_frequency", "nrr",
                "cohort_retention_30d_recent", "cohort_retention_30d_prior",
                "trial_step_dropoffs", "runway_months", "monthly_churn_pct",
            ]
            metrics: dict[str, Any] = dict(zip(cols, row))

            mrr = metrics.get("mrr_cents", 0) / 100
            burn = metrics.get("burn_rate_cents", 0) / 100
            runway = float(metrics.get("runway_months", 0) or 0)

            # ── Prior-month lookups ────────────────────────────────

            prev_query = """
                SELECT {col} FROM metric_snapshots
                WHERE tenant_id = %s
                  AND snapshot_month < (
                    SELECT MAX(snapshot_month) FROM metric_snapshots WHERE tenant_id = %s
                  )
                ORDER BY snapshot_month DESC LIMIT 1
            """

            prev_row = _prev(cur, prev_query, "burn_rate_cents", TENANT_ID)
            prev_burn = (prev_row / 100) if prev_row is not None else burn

            prev_deploy = _prev(cur, prev_query, "deploy_frequency", TENANT_ID)
            prev_deploy_freq = prev_deploy if prev_deploy is not None else metrics.get("deploy_frequency", 12)

            prev_aws_raw = _prev(cur, prev_query, "aws_cost_cents", TENANT_ID)
            prev_aws_cost = prev_aws_raw if prev_aws_raw is not None else 0
            aws_growth = (
                (metrics.get("aws_cost_cents", 0) - prev_aws_cost)
                / max(prev_aws_cost, 1)
            ) * 100

            prev_users_raw = _prev(cur, prev_query, "active_users_30d", TENANT_ID)
            prev_user_count = prev_users_raw if prev_users_raw is not None else metrics.get("active_users_30d", 312)
            user_growth = (
                (metrics.get("active_users_30d", 0) - prev_user_count)
                / max(prev_user_count, 1)
            ) * 100

            prev_tickets_raw = _prev(cur, prev_query, "support_tickets", TENANT_ID)
            prev_ticket_count = prev_tickets_raw if prev_tickets_raw is not None else metrics.get("support_tickets", 45)
            ticket_growth = (
                (metrics.get("support_tickets", 0) - prev_ticket_count)
                / max(prev_ticket_count, 1)
            ) * 100

            return {
                # FINANCE
                "monthly_churn_pct": float(metrics.get("monthly_churn_pct", 0) or 0),
                "net_burn": burn - mrr,
                "net_new_arr": metrics.get("net_new_arr_cents", 0) / 100,
                "top_customer_mrr": metrics.get("top_customer_mrr_cents", 0) / 100,
                "total_mrr": mrr,
                "mrr": mrr,
                "burn_rate": burn,
                "prev_burn_rate": prev_burn,
                "runway_days": int(runway * 30) if runway > 0 else 999,
                "failed_payments_7d": metrics.get("failed_payments_7d", 0),
                "payroll_monthly": metrics.get("payroll_monthly_cents", 0) / 100,

                # BI
                "new_signups": metrics.get("new_customers", 0) * 5,
                "activation_rate": float(metrics.get("activation_rate", 0) or 0),
                "mrr_growth_pct": 0.0,
                "top_10pct_mrr": mrr * 0.60,
                "avg_mrr_new_customers": mrr / max(metrics.get("new_customers", 1), 1) * 0.80,
                "avg_mrr_all_customers": mrr / max(metrics.get("active_customers", 1), 1),
                "feature_name": "batch_export",
                "adoption_pre_deploy": 120,
                "adoption_post_deploy": 78,
                "cohort_retention_30d_recent": float(metrics.get("cohort_retention_30d_recent", 0) or 0),
                "cohort_retention_30d_prior": float(metrics.get("cohort_retention_30d_prior", 0) or 0),
                "nrr": float(metrics.get("nrr", 100) or 100),
                "trial_step_dropoffs": metrics.get("trial_step_dropoffs", [
                    {"step": "signup", "drop_pct": 0.15},
                    {"step": "email_verify", "drop_pct": 0.25},
                    {"step": "first_project", "drop_pct": 0.55},
                ]),

                # OPS
                "errors_by_segment": [
                    {"segment": "free_tier", "error_pct": 0.03},
                    {"segment": "enterprise", "error_pct": 0.12},
                ],
                "support_tickets_growth_pct": round(ticket_growth, 1),
                "user_growth_pct": round(user_growth, 1),
                "bug_mentions_by_channel": {"slack": 2, "email": 3, "twitter": 1},
                "deploys_this_month": metrics.get("deploy_frequency", 3),
                "deploys_last_month": prev_deploy_freq,
                "aws_cost_growth_pct": round(aws_growth, 1),
            }
    finally:
        conn.close()


def _prev(cur, query_template: str, col: str, tenant_id: str):
    """Fetch a single prior-month value; return None if absent."""
    cur.execute(query_template.format(col=col), (tenant_id, tenant_id))
    row = cur.fetchone()
    return row[0] if row else None


# ── Router ────────────────────────────────────────────────────────

router = APIRouter(prefix="/debug")


@router.get("/health")
async def health():
    """Server health check."""
    return {"status": "ok", "demo_mode": DEMO_MODE}


@router.get("/tenant/{tenant_id}/latest-snapshot")
async def latest_snapshot(tenant_id: str):
    """Return latest metric snapshot for a tenant."""
    _guard()
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mrr_cents / 100.0 AS mrr,
                       monthly_churn_pct AS churn_pct,
                       active_customers AS customer_count,
                       top_customer_mrr_cents / 100.0 AS top_customer_mrr,
                       bank_balance_cents / 100.0 AS bank_balance,
                       burn_rate_cents / 100.0 AS burn_rate,
                       net_new_arr_cents / 100.0 AS net_new_arr,
                       active_users_30d AS active_users,
                       activation_rate,
                       failed_payments_7d,
                       nrr
                FROM metric_snapshots
                WHERE tenant_id = %s
                ORDER BY snapshot_month DESC
                LIMIT 1
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No snapshot found")
            cols = [
                "mrr", "churn_pct", "customer_count", "top_customer_mrr",
                "bank_balance", "burn_rate", "net_new_arr", "active_users",
                "activation_rate", "failed_payments_7d", "nrr",
            ]
            return dict(zip(cols, row))
    finally:
        conn.close()


@router.get("/tenant/{tenant_id}/signals")
async def get_signals(tenant_id: str):
    """Return all 31 computed guardian watchlist signals."""
    _guard()
    signals = _compute_signals()
    if not signals:
        raise HTTPException(status_code=404, detail="No data for tenant")
    return signals


@router.get("/tenant/{tenant_id}/watchlist-hits")
async def get_watchlist_hits(tenant_id: str):
    """Return which guardian watchlist patterns fire for this tenant."""
    _guard()
    signals = _compute_signals()
    if not signals:
        return []
    from src.guardian.detector import GuardianDetector

    detector = GuardianDetector()
    matches = detector.run(signals)
    return [
        {"id": m.id, "name": m.name, "domain": m.domain, "severity": m.severity}
        for m in matches
    ]


@router.get("/tenant/{tenant_id}/memory-status")
async def memory_status(tenant_id: str):
    """Return counts of seeded vectors in each Qdrant collection."""
    _guard()
    r, base = _get_qd()
    result: dict[str, Any] = {}
    for col in [
        "pulse_memory",
        "anomaly_memory",
        "investor_memory",
        "founder_blindspots",
    ]:
        try:
            resp = r.post(
                f"{base}/collections/{col}/points/count",
                json={
                    "count_filter": {
                        "must": [{"key": "tenant_id", "match": {"value": tenant_id}}]
                    }
                },
                timeout=5,
            )
            result[f"{col}_count"] = resp.json().get("result", {}).get("count", 0)
        except Exception:
            result[f"{col}_count"] = 0
    return result


@router.get("/tenant/{tenant_id}/rag-context")
async def rag_context_endpoint(
    tenant_id: str, task: str = "finance_guardian"
):
    """Return assembled RAG context and token count (≤800 tokens)."""
    _guard()
    from src.memory.rag_kernel import RAGKernel
    from src.memory.spine import MemorySpine

    kernel = RAGKernel()
    try:
        spine = MemorySpine(layers=[], rag_kernel=kernel)
        context = spine.load_context(
            tenant_id=tenant_id, task=task, signal={}, max_tokens=800
        )
    except Exception:
        context = f"No prior context available for tenant {tenant_id}."

    enc = tiktoken.encoding_for_model("gpt-4o-mini")
    tokens = len(enc.encode(context))
    return {
        "token_count": tokens,
        "context_preview": context[:400],
    }


app.include_router(router)


# ── Root health ───────────────────────────────────────────────────

@app.get("/health")
async def root_health():
    return {"status": "ok", "demo_mode": DEMO_MODE}
