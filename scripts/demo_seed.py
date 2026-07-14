#!/usr/bin/env python3
"""
demo_seed.py — Seed NovaPulse demo data for OntologyAI Pulse portfolio.

Inserts 6 months of realistic synthetic B2B SaaS metrics into PostgreSQL
and Qdrant so that Guardian watchlist patterns actually trigger.

Usage:
    python scripts/demo_seed.py

Prerequisites (all checked at startup):
    - PostgreSQL  at postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm
    - Qdrant      at http://localhost:6333
    - Ollama      at http://localhost:11434  (nomic-embed-text model)

Idempotent: safe to re-run.  Uses IF NOT EXISTS / ON CONFLICT / DELETE WHERE.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import random
import hashlib
from datetime import date, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import requests

# ── Configuration ────────────────────────────────────────────────────

PG_DSN = os.getenv("DEMO_PG_DSN", "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm")
QDRANT_URL = os.getenv("DEMO_QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("DEMO_OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("DEMO_EMBED_MODEL", "nomic-embed-text:latest")
VECTOR_DIM = 768

TENANT_ID = "00000000-0000-0000-0000-000000000042"  # fixed demo tenant
SEED = 42
random.seed(SEED)

# 6-month window ending on "today"
TODAY = date(2026, 4, 13)
MONTHS = [TODAY - timedelta(days=30 * i) for i in reversed(range(6))]
MONTHS = [d.replace(day=1) for d in MONTHS]  # first of each month

# ── NovaPulse synthetic data (6 months) ─────────────────────────────
# Index 0 = oldest month, Index 5 = most recent month

MRR =          [820000, 910000, 1040000, 1180000, 1240000, 1210000]
CHURN_PCT =    [0.021,   0.024,    0.028,    0.031,    0.034,    0.036]
CUSTOMERS =    [41,      46,       52,       57,       60,       58]
TOP_CUST_MRR = [213000,  245000,   280000,   320000,   350000,   380000]
BANK_BALANCE = [14800000,13400000, 11900000, 10300000, 8700000,  7100000]
BURN_RATE =    [1400000, 1520000,  1590000,  1680000,  1620000,  1640000]
NET_NEW_ARR =  [1080000, 1320000,  1560000,  1680000,  720000,   360000]
ACTIVE_USERS = [312,     334,      358,      371,      368,      352]
ACTIVATION =   [0.68,    0.64,     0.59,     0.54,     0.49,     0.44]
FAILED_PAY_7D =[0,       0,        1,        2,        3,        4]
PAYROLL =      [980000] * 6
AWS_COST =     [120000,  135000,   142000,   155000,   168000,   182000]
SUPPORT_TICKETS=[45,     52,       58,       67,       78,       89]
DEPLOY_FREQ =  [12,      14,       11,       8,        5,        3]
NRR =          [108,     105,      102,      98,       96,       94]
COHORT_RECENT = [0.52,   0.50,     0.48,     0.45,     0.42,     0.38]
COHORT_PRIOR =  [0.55,   0.54,     0.53,     0.52,     0.51,     0.48]

TRIAL_DROPOFFS = [
    {"step": "signup", "drop_pct": 0.15},
    {"step": "email_verify", "drop_pct": 0.25},
    {"step": "first_project", "drop_pct": 0.55},
]

# Derived
RUNWAY_MONTHS = [round(b / burn, 1) for b, burn in zip(BANK_BALANCE, BURN_RATE)]

# ── Helpers ──────────────────────────────────────────────────────────


def check_prereqs() -> bool:
    """Verify PostgreSQL, Qdrant, and Ollama are reachable."""
    ok = True

    # PostgreSQL
    try:
        conn = psycopg2.connect(PG_DSN, connect_timeout=5)
        conn.close()
        print("✅  PostgreSQL reachable")
    except Exception as e:
        print(f"❌  PostgreSQL NOT reachable: {e}")
        ok = False

    # Qdrant
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        resp.raise_for_status()
        print("✅  Qdrant reachable")
    except Exception as e:
        print(f"❌  Qdrant NOT reachable: {e}")
        ok = False

    # Ollama
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        if EMBED_MODEL in models or EMBED_MODEL.replace(":latest", "") in models:
            print(f"✅  Ollama reachable with {EMBED_MODEL}")
        else:
            print(f"⚠️  Ollama reachable but '{EMBED_MODEL}' not found; available: {models}")
            print("    Will attempt embedding anyway (may fail).")
    except Exception as e:
        print(f"⚠️  Ollama NOT reachable: {e}")
        print("    → Will use deterministic hash-based fallback for embeddings.")

    return ok


def get_embedding(text: str) -> list[float]:
    """Generate a 768-dim embedding via Ollama nomic-embed-text."""
    # Try new /api/embed endpoint
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if embeddings and isinstance(embeddings, list) and len(embeddings) > 0:
            vec = embeddings[0] if isinstance(embeddings[0], list) else embeddings
            if len(vec) == VECTOR_DIM:
                return vec
    except Exception:
        pass

    # Fallback: deprecated /api/embeddings
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=15,
        )
        resp.raise_for_status()
        vec = resp.json().get("embedding", [])
        if len(vec) == VECTOR_DIM:
            return vec
    except Exception:
        pass

    # Last resort: deterministic hash-based pseudo-vector
    # (ensures script always succeeds even without Ollama)
    print(f"    ⚠️  Ollama embed failed for text[:50]={text[:50]!r}; using deterministic fallback")
    return _hash_vector(text)


def _hash_vector(text: str) -> list[float]:
    """Deterministic 768-dim vector from text (not semantically meaningful)."""
    h = hashlib.sha256(text.encode()).digest()
    random.Random(h.hex()).seed(SEED)
    rng = random.Random(text)
    vec = [rng.gauss(0, 1) for _ in range(VECTOR_DIM)]
    # Normalize
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


# ── PostgreSQL seeding ───────────────────────────────────────────────


def create_tables(cur):
    """Create demo tables IF NOT EXISTS."""
    # metric_snapshots: one row per month with all NovaPulse signals
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metric_snapshots (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            snapshot_month  DATE NOT NULL,
            mrr_cents       BIGINT NOT NULL,
            arr_cents       BIGINT NOT NULL,
            active_customers INTEGER NOT NULL,
            new_customers   INTEGER NOT NULL,
            churned_customers INTEGER NOT NULL,
            top_customer_mrr_cents BIGINT NOT NULL,
            bank_balance_cents BIGINT NOT NULL,
            burn_rate_cents BIGINT NOT NULL,
            net_new_arr_cents BIGINT NOT NULL,
            active_users_30d INTEGER NOT NULL,
            activation_rate NUMERIC(5,4) NOT NULL,
            failed_payments_7d INTEGER NOT NULL DEFAULT 0,
            payroll_monthly_cents BIGINT NOT NULL,
            aws_cost_cents  BIGINT NOT NULL,
            support_tickets INTEGER NOT NULL,
            deploy_frequency INTEGER NOT NULL,
            nrr             NUMERIC(6,2) NOT NULL,
            cohort_retention_30d_recent NUMERIC(5,4),
            cohort_retention_30d_prior  NUMERIC(5,4),
            trial_step_dropoffs JSONB,
            runway_months   NUMERIC(6,2),
            monthly_churn_pct NUMERIC(5,4),
            UNIQUE(tenant_id, snapshot_month)
        );
    """)

    # agent_alerts: historical Guardian alerts (may already exist from migrations)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_alerts (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL,
            alert_type          TEXT NOT NULL,
            severity            TEXT NOT NULL,
            message             TEXT NOT NULL,
            metadata            JSONB,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            insight_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
            insight_already_knew BOOLEAN NOT NULL DEFAULT FALSE,
            insight_not_relevant BOOLEAN NOT NULL DEFAULT FALSE,
            blindspot_id        TEXT,
            guardian_pattern_name TEXT
        );
    """)

    # company_context: NovaPulse profile (simplified, no FK to founders)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_context (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            founder_id      UUID,
            context_type    VARCHAR(50) NOT NULL,
            content         TEXT NOT NULL,
            source          VARCHAR(50) NOT NULL,
            captured_from   VARCHAR(100),
            confidence      FLOAT DEFAULT 1.0,
            valid_until     TIMESTAMPTZ,
            qdrant_point_id VARCHAR(100),
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # resolved_blindspots: previously detected & resolved patterns (may already exist)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resolved_blindspots (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL,
            blindspot_id        TEXT NOT NULL,
            detected_at         TIMESTAMPTZ NOT NULL,
            resolved_at         TIMESTAMPTZ,
            metric_at_detection NUMERIC,
            metric_at_resolution NUMERIC,
            founder_action      TEXT,
            created_at          TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # eval_scores: historical eval scoring data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS eval_scores (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            agent_type TEXT NOT NULL,
            week_of DATE NOT NULL,
            guardian_score NUMERIC,
            accuracy_score NUMERIC,
            tone_score NUMERIC,
            action_score NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(tenant_id, agent_type, week_of)
        );
    """)


def seed_metric_snapshots(cur):
    """Insert 6 monthly metric snapshots for NovaPulse."""
    cur.execute("DELETE FROM metric_snapshots WHERE tenant_id = %s", (TENANT_ID,))

    rows = []
    for i, month in enumerate(MONTHS):
        new_cust = CUSTOMERS[i] - (CUSTOMERS[i - 1] if i > 0 else 35)
        churned = max(0, (CUSTOMERS[i - 1] if i > 0 else 35) + new_cust - CUSTOMERS[i])
        churned = max(churned, round(CUSTOMERS[i] * CHURN_PCT[i]))

        rows.append((
            TENANT_ID,
            month,
            MRR[i] * 100,              # mrr_cents
            MRR[i] * 12 * 100,         # arr_cents
            CUSTOMERS[i],
            new_cust,
            churned,
            TOP_CUST_MRR[i] * 100,
            BANK_BALANCE[i] * 100,
            BURN_RATE[i] * 100,
            NET_NEW_ARR[i] * 100,
            ACTIVE_USERS[i],
            ACTIVATION[i],
            FAILED_PAY_7D[i],
            PAYROLL[i] * 100,
            AWS_COST[i] * 100,
            SUPPORT_TICKETS[i],
            DEPLOY_FREQ[i],
            NRR[i],
            COHORT_RECENT[i],
            COHORT_PRIOR[i],
            json.dumps(TRIAL_DROPOFFS),
            RUNWAY_MONTHS[i],
            CHURN_PCT[i],
        ))

    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO metric_snapshots (
            tenant_id, snapshot_month, mrr_cents, arr_cents,
            active_customers, new_customers, churned_customers,
            top_customer_mrr_cents, bank_balance_cents, burn_rate_cents,
            net_new_arr_cents, active_users_30d, activation_rate,
            failed_payments_7d, payroll_monthly_cents, aws_cost_cents,
            support_tickets, deploy_frequency, nrr,
            cohort_retention_30d_recent, cohort_retention_30d_prior,
            trial_step_dropoffs, runway_months, monthly_churn_pct
        ) VALUES %s
        ON CONFLICT (tenant_id, snapshot_month) DO NOTHING""",
        rows,
    )
    return cur.rowcount


def seed_agent_alerts(cur):
    """Insert 4 historical Guardian alerts (last month's patterns)."""
    cur.execute("DELETE FROM agent_alerts WHERE tenant_id = %s", (TENANT_ID,))

    latest = MONTHS[-1]
    alerts = [
        (
            TENANT_ID, "guardian_watchlist", "critical",
            f"FG-01 Silent Churn Death triggered: monthly churn at {CHURN_PCT[-1]*100:.1f}% "
            f"(threshold 3.0%).  You are on track for 36% annual churn. "
            f"Action: Call one churned customer this week.",
            json.dumps({"monthly_churn_pct": CHURN_PCT[-1], "threshold": 0.03, "snapshot_month": latest.isoformat()}),
            True, False, False, "FG-01", "Silent Churn Death",
        ),
        (
            TENANT_ID, "guardian_watchlist", "warning",
            f"FG-03 Customer Concentration Risk: top customer is {TOP_CUST_MRR[-1]/MRR[-1]*100:.0f}% "
            f"of MRR (threshold 30%). If they churn, you lose a third overnight.",
            json.dumps({"top_customer_mrr": TOP_CUST_MRR[-1], "total_mrr": MRR[-1],
             "concentration_pct": TOP_CUST_MRR[-1] / MRR[-1], "snapshot_month": latest.isoformat()}),
            True, False, False, "FG-03", "Customer Concentration Risk",
        ),
        (
            TENANT_ID, "guardian_watchlist", "warning",
            f"FG-05 Failed Payment Cluster: {FAILED_PAY_7D[-1]} failed payments in 7 days "
            f"(threshold 3). Involuntary churn in progress.",
            json.dumps({"failed_payments_7d": FAILED_PAY_7D[-1], "threshold": 3,
             "snapshot_month": latest.isoformat()}),
            True, False, False, "FG-05", "Failed Payment Cluster",
        ),
        (
            TENANT_ID, "guardian_watchlist", "critical",
            f"BG-05 NRR Below 100: NRR at {NRR[-1]}% means you're losing more than expanding. "
            f"Fix expansion motion before fundraising.",
            json.dumps({"nrr": NRR[-1], "threshold": 100, "snapshot_month": latest.isoformat()}),
            True, False, False, "BG-05", "NRR Below 100 at Seed",
        ),
    ]

    for alert in alerts:
        cur.execute(
            """INSERT INTO agent_alerts (
                tenant_id, alert_type, severity, message, metadata,
                insight_acknowledged, insight_already_knew, insight_not_relevant,
                blindspot_id, guardian_pattern_name
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            alert,
        )
    return len(alerts)


def seed_company_context(cur):
    """Insert NovaPulse company profile."""
    # Delete existing NovaPulse entries by source
    cur.execute("DELETE FROM company_context WHERE source = 'demo_seed'")

    contexts = [
        (
            "company_profile",
            json.dumps({
                "name": "NovaPulse",
                "industry": "B2B SaaS — Developer Tooling",
                "stage": "seed",
                "founded": "2025-06",
                "team_size": 6,
                "funding_raised_cents": 18000000 * 100,
                "target_arr_cents": 2000000 * 12 * 100,
                "pricing_tiers": ["Starter ₹4,999/mo", "Pro ₹14,999/mo", "Enterprise ₹39,999/mo"],
                "ideal_customer": "Series A-B startups, 20-100 engineers, India/SEA",
                "tech_stack": "PostgreSQL, Redis, Next.js, Go, Temporal",
            }),
            "demo_seed", "script",
        ),
        (
            "financial_summary",
            json.dumps({
                "current_mrr_cents": MRR[-1] * 100,
                "current_runway_months": RUNWAY_MONTHS[-1],
                "burn_multiple": round(BURN_RATE[-1] / (NET_NEW_ARR[-1] / 12), 2) if NET_NEW_ARR[-1] > 0 else None,
                "payroll_pct_of_mrr": round(PAYROLL[-1] / MRR[-1] * 100, 1),
                "aws_per_user": round(AWS_COST[-1] / ACTIVE_USERS[-1], 0),
                "avg_revenue_per_customer": round(MRR[-1] / CUSTOMERS[-1], 0),
            }),
            "demo_seed", "script",
        ),
    ]

    for ctx_type, content, source, captured_from in contexts:
        cur.execute(
            """INSERT INTO company_context (
                context_type, content, source, captured_from, confidence
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING""",
            (ctx_type, content, source, captured_from, 1.0),
        )
    return len(contexts)


def seed_resolved_blindspots(cur):
    """Insert 2 previously resolved blindspot patterns."""
    cur.execute("DELETE FROM resolved_blindspots WHERE tenant_id = %s", (TENANT_ID,))

    detected_1 = (MONTHS[2] - timedelta(days=15)).isoformat()
    resolved_1 = (MONTHS[3] - timedelta(days=5)).isoformat()
    detected_2 = (MONTHS[1] - timedelta(days=20)).isoformat()
    resolved_2 = (MONTHS[2] - timedelta(days=10)).isoformat()

    rows = [
        (
            TENANT_ID, "BG-01",
            detected_1, resolved_1,
            0.38, 0.49,
            "Rebuilt onboarding flow; removed email_verify step friction. "
            "Added interactive tutorial on first login.",
        ),
        (
            TENANT_ID, "OG-04",
            detected_2, resolved_2,
            3, 11,
            "Allocated 1-week debt sprint. Fixed CI pipeline that was "
            "causing 40% test flakiness. Deploy frequency recovered to 11.",
        ),
    ]

    for row in rows:
        cur.execute(
            """INSERT INTO resolved_blindspots (
                tenant_id, blindspot_id, detected_at, resolved_at,
                metric_at_detection, metric_at_resolution, founder_action
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            row,
        )
    return len(rows)


def seed_eval_scores(cur):
    """Insert 2 weeks of eval scoring data."""
    # Delete by week_of range rather than agent_type pattern
    cur.execute(
        "DELETE FROM eval_scores WHERE tenant_id = %s AND week_of >= %s",
        (TENANT_ID, TODAY - timedelta(weeks=3))
    )

    weeks = [TODAY - timedelta(weeks=w) for w in reversed(range(2))]
    scores = [
        (TENANT_ID, "guardian_triage", weeks[0], 0.82, 0.78, 0.85, 0.80),
        (TENANT_ID, "guardian_triage", weeks[1], 0.79, 0.75, 0.83, 0.77),
        (TENANT_ID, "guardian_pulse", weeks[0], 0.88, 0.84, 0.90, 0.86),
        (TENANT_ID, "guardian_pulse", weeks[1], 0.85, 0.81, 0.88, 0.83),
        (TENANT_ID, "guardian_anomaly", weeks[0], 0.76, 0.72, 0.80, 0.74),
        (TENANT_ID, "guardian_anomaly", weeks[1], 0.73, 0.70, 0.78, 0.71),
    ]

    for row in scores:
        cur.execute(
            """INSERT INTO eval_scores (
                tenant_id, agent_type, week_of,
                guardian_score, accuracy_score, tone_score, action_score
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            row,
        )
    return len(scores)


# ── Qdrant seeding ───────────────────────────────────────────────────


def ensure_collection(name: str) -> bool:
    """Create collection if missing."""
    resp = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=5)
    if resp.status_code == 200:
        return True
    resp = requests.put(
        f"{QDRANT_URL}/collections/{name}",
        json={"vectors": {"size": VECTOR_DIM, "distance": "Cosine"}, "on_disk_payload": True},
        timeout=10,
    )
    return resp.status_code == 200


def upsert_points(collection: str, points: list[dict]) -> int:
    """Upsert vectors into a Qdrant collection."""
    if not points:
        return 0
    resp = requests.put(
        f"{QDRANT_URL}/collections/{collection}/points",
        json={"points": points},
        timeout=30,
    )
    resp.raise_for_status()
    return len(points)


def seed_pulse_memory() -> int:
    """6 vectors — one per monthly financial snapshot."""
    points = []
    for i, month in enumerate(MONTHS):
        text = (
            f"NovaPulse month {i+1} ({month.isoformat()}): "
            f"MRR ₹{MRR[i]/100000:.2f}L, churn {CHURN_PCT[i]*100:.1f}%, "
            f"customers {CUSTOMERS[i]}, burn ₹{BURN_RATE[i]/100000:.2f}L, "
            f"runway {RUNWAY_MONTHS[i]:.1f}mo, NRR {NRR[i]}%, "
            f"activation {ACTIVATION[i]*100:.0f}%, AWS ₹{AWS_COST[i]/1000:.1f}K"
        )
        vec = get_embedding(text)
        # Use integer IDs for Qdrant compatibility
        point_id = 1000 + i
        points.append({
            "id": point_id,
            "vector": vec,
            "payload": {
                "tenant_id": TENANT_ID,
                "type": "monthly_snapshot",
                "month": month.isoformat(),
                "mrr": MRR[i],
                "churn_pct": CHURN_PCT[i],
                "customers": CUSTOMERS[i],
                "burn_rate": BURN_RATE[i],
                "runway_months": RUNWAY_MONTHS[i],
                "nrr": NRR[i],
                "activation_rate": ACTIVATION[i],
                "active_users": ACTIVE_USERS[i],
                "summary": text,
            },
        })
    return upsert_points("pulse_memory", points)


def seed_anomaly_memory() -> int:
    """2 vectors — previously triggered anomalies."""
    anomalies = [
        {
            "id": 2000,
            "text": (
                "Month 3: AWS cost jumped 23% MoM (₹1.42L → ₹1.55L) "
                "while users grew only 3.6%. Unit economics divergence detected. "
                "Root cause: unoptimized RDS queries from new reporting feature."
            ),
            "payload": {
                "type": "aws_cost_spike",
                "month": MONTHS[3].isoformat(),
                "metric": "aws_cost_growth_pct",
                "value": 0.23,
                "baseline": 0.036,
                "resolved": True,
            },
        },
        {
            "id": 2001,
            "text": (
                "Month 5: Deploy frequency dropped from 8 to 5 per month (37% decline). "
                "CI flakiness at 40%. Team spending 2+ days/week debugging tests "
                "instead of shipping features."
            ),
            "payload": {
                "type": "deploy_collapse",
                "month": MONTHS[4].isoformat(),
                "metric": "deploy_frequency",
                "value": 5,
                "baseline": 11,
                "resolved": True,
            },
        },
    ]
    points = []
    for a in anomalies:
        vec = get_embedding(a["text"])
        points.append({
            "id": a["id"],
            "vector": vec,
            "payload": {**a["payload"], "tenant_id": TENANT_ID},
        })
    return upsert_points("anomaly_memory", points)


def seed_investor_memory() -> int:
    """2 vectors — past investor updates."""
    updates = [
        {
            "id": 3000,
            "text": (
                "Q4 2025 Investor Update — NovaPulse: "
                f"MRR grew from ₹{MRR[0]/100000:.1f}L to ₹{MRR[2]/100000:.1f}L ({(MRR[2]/MRR[0]-1)*100:.0f}% growth). "
                f"Customer count {CUSTOMERS[0]} → {CUSTOMERS[2]}. "
                f"Runway healthy at {RUNWAY_MONTHS[2]:.1f} months. "
                f"NRR at {NRR[2]}%. Team of 6, hiring 2 engineers in Q1."
            ),
            "payload": {
                "type": "investor_update",
                "period": "Q4-2025",
                "mrr_start": MRR[0],
                "mrr_end": MRR[2],
                "customers_start": CUSTOMERS[0],
                "customers_end": CUSTOMERS[2],
                "nrr": NRR[2],
            },
        },
        {
            "id": 3001,
            "text": (
                "Q1 2026 Investor Update — NovaPulse: "
                f"MRR ₹{MRR[2]/100000:.1f}L → ₹{MRR[-1]/100000:.1f}L. "
                f"Customers {CUSTOMERS[2]} → {CUSTOMERS[-1]}. "
                f"Note: NRR dipped below 100% to {NRR[-1]}% — investigating expansion revenue gap. "
                f"Runway {RUNWAY_MONTHS[-1]:.1f} months. Planning bridge round."
            ),
            "payload": {
                "type": "investor_update",
                "period": "Q1-2026",
                "mrr_start": MRR[2],
                "mrr_end": MRR[-1],
                "customers_start": CUSTOMERS[2],
                "customers_end": CUSTOMERS[-1],
                "nrr": NRR[-1],
                "flag": "NRR below 100%",
            },
        },
    ]
    points = []
    for u in updates:
        vec = get_embedding(u["text"])
        points.append({
            "id": u["id"],
            "vector": vec,
            "payload": {**u["payload"], "tenant_id": TENANT_ID},
        })
    return upsert_points("investor_memory", points)


def seed_founder_blindspots() -> int:
    """2 vectors — resolved blindspot patterns."""
    blindspots = [
        {
            "id": 4000,
            "text": (
                "BG-01 Leaky Bucket: activation rate dropped to 38% in month 2. "
                "Root cause: mandatory email verification step causing 25% dropoff. "
                "Resolution: Made email verify optional, added in-product tutorial. "
                "Activation recovered to 49% by month 4."
            ),
            "payload": {
                "type": "resolved_blindspot",
                "blindspot_id": "BG-01",
                "name": "Leaky Bucket Activation",
                "metric_at_detection": 0.38,
                "metric_at_resolution": 0.49,
                "action_taken": "Rebuilt onboarding flow",
            },
        },
        {
            "id": 4001,
            "text": (
                "OG-04 Deploy Collapse: deploy frequency fell from 14 to 8 per month. "
                "Root cause: CI test flakiness at 40%, team losing confidence in pipeline. "
                "Resolution: 1-week debt sprint, fixed flaky tests, added retry logic. "
                "Deploy frequency recovered to 11 by month 3."
            ),
            "payload": {
                "type": "resolved_blindspot",
                "blindspot_id": "OG-04",
                "name": "Deploy Frequency Collapse",
                "metric_at_detection": 8,
                "metric_at_resolution": 11,
                "action_taken": "CI debt sprint",
            },
        },
    ]
    points = []
    for b in blindspots:
        vec = get_embedding(b["text"])
        points.append({
            "id": b["id"],
            "vector": vec,
            "payload": {**b["payload"], "tenant_id": TENANT_ID},
        })
    return upsert_points("founder_blindspots", points)


# ── Pattern trigger analysis ─────────────────────────────────────────


def analyze_triggers() -> list[dict]:
    """Determine which Guardian watchlist patterns will trigger with the seeded data."""
    latest_signals = {
        "monthly_churn_pct": CHURN_PCT[-1],
        "mrr": MRR[-1],
        "top_customer_mrr": TOP_CUST_MRR[-1],
        "failed_payments_7d": FAILED_PAY_7D[-1],
        "activation_rate": ACTIVATION[-1],
        "new_signups": CUSTOMERS[-1] - CUSTOMERS[-2],
        "mrr_growth_pct": (MRR[-1] - MRR[-2]) / MRR[-2] if MRR[-2] > 0 else 0,
        "nrr": NRR[-1],
        "cohort_retention_30d_recent": COHORT_RECENT[-1],
        "cohort_retention_30d_prior": COHORT_PRIOR[-1],
        "payroll_monthly": PAYROLL[-1],
        "burn_rate": BURN_RATE[-1],
        "net_new_arr": NET_NEW_ARR[-1],
        "net_burn": BURN_RATE[-1] - MRR[-1],
        "runway_days": RUNWAY_MONTHS[-1] * 30,
        "prev_burn_rate": BURN_RATE[-2],
        "deploys_this_month": DEPLOY_FREQ[-1],
        "deploys_last_month": DEPLOY_FREQ[-2],
        "aws_cost_growth_pct": (AWS_COST[-1] - AWS_COST[-2]) / AWS_COST[-2] if AWS_COST[-2] > 0 else 0,
        "user_growth_pct": (ACTIVE_USERS[-1] - ACTIVE_USERS[-2]) / ACTIVE_USERS[-2] if ACTIVE_USERS[-2] > 0 else 0,
        "support_tickets_growth_pct": (SUPPORT_TICKETS[-1] - SUPPORT_TICKETS[-2]) / SUPPORT_TICKETS[-2] if SUPPORT_TICKETS[-2] > 0 else 0,
        "trial_step_dropoffs": TRIAL_DROPOFFS,
    }

    # Detection logic (mirrors watchlist.py)
    triggers = []

    # FG-01: monthly_churn_pct > 0.03
    if latest_signals["monthly_churn_pct"] > 0.03:
        triggers.append({
            "id": "FG-01", "name": "Silent Churn Death", "severity": "warning",
            "detail": f"Churn {latest_signals['monthly_churn_pct']*100:.1f}% > 3.0%",
        })

    # FG-03: top_customer_mrr / total_mrr > 0.30
    if MRR[-1] > 0 and TOP_CUST_MRR[-1] / MRR[-1] > 0.30:
        triggers.append({
            "id": "FG-03", "name": "Customer Concentration Risk", "severity": "warning",
            "detail": f"Top customer {TOP_CUST_MRR[-1]/MRR[-1]*100:.0f}% of MRR > 30%",
        })

    # FG-05: failed_payments_7d >= 3
    if FAILED_PAY_7D[-1] >= 3:
        triggers.append({
            "id": "FG-05", "name": "Failed Payment Cluster", "severity": "warning",
            "detail": f"{FAILED_PAY_7D[-1]} failed payments in 7d >= 3",
        })

    # BG-01: activation_rate < 0.40 AND new_signups > 0 AND mrr_growth_pct > 0
    if (ACTIVATION[-1] < 0.40 and
            (CUSTOMERS[-1] - CUSTOMERS[-2]) > 0 and
            (MRR[-1] - MRR[-2]) / MRR[-2] > 0 if MRR[-2] > 0 else False):
        triggers.append({
            "id": "BG-01", "name": "Leaky Bucket Activation", "severity": "warning",
            "detail": f"Activation {ACTIVATION[-1]*100:.0f}% < 40% (MRR still growing)",
        })

    # BG-04: cohort_retention_30d_recent < cohort_retention_30d_prior * 0.90
    if COHORT_RECENT[-1] < COHORT_PRIOR[-1] * 0.90:
        triggers.append({
            "id": "BG-04", "name": "Cohort Retention Degradation", "severity": "critical",
            "detail": f"Cohort {COHORT_RECENT[-1]*100:.0f}% vs prior {COHORT_PRIOR[-1]*100:.0f}% (>{10:.0f}% drop)",
        })

    # BG-05: nrr < 100
    if NRR[-1] < 100:
        triggers.append({
            "id": "BG-05", "name": "NRR Below 100 at Seed", "severity": "critical",
            "detail": f"NRR {NRR[-1]}% < 100%",
        })

    # BG-06: any trial step drop_pct > 0.50
    if any(s["drop_pct"] > 0.50 for s in TRIAL_DROPOFFS):
        triggers.append({
            "id": "BG-06", "name": "Trial Activation Wall", "severity": "warning",
            "detail": "first_project step has 55% dropoff > 50%",
        })

    # FG-06: payroll / mrr > 0.60
    if PAYROLL[-1] / MRR[-1] > 0.60:
        triggers.append({
            "id": "FG-06", "name": "Payroll Revenue Ratio Breach", "severity": "warning",
            "detail": f"Payroll {PAYROLL[-1]/MRR[-1]*100:.0f}% of MRR > 60%",
        })

    return triggers


# ── Main ─────────────────────────────────────────────────────────────


def main() -> int:
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     NovaPulse Demo Seed — OntologyAI Pulse                  ║")
    print("║     6-month synthetic B2B SaaS portfolio data            ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # 1. Prerequisites
    print("1. Checking prerequisites...")
    if not check_prereqs():
        print("\n❌ Aborting — fix prerequisites and re-run.")
        return 1
    print()

    # 2. PostgreSQL
    print("2. Seeding PostgreSQL...")
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        create_tables(cur)
        print("   ✅ Tables created/verified")

        n = seed_metric_snapshots(cur)
        print(f"   ✅ metric_snapshots: 6 rows inserted")

        n = seed_agent_alerts(cur)
        print(f"   ✅ agent_alerts: {n} rows inserted")

        n = seed_company_context(cur)
        print(f"   ✅ company_context: {n} rows inserted")

        n = seed_resolved_blindspots(cur)
        print(f"   ✅ resolved_blindspots: {n} rows inserted")

        n = seed_eval_scores(cur)
        print(f"   ✅ eval_scores: {n} rows inserted")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"\n❌ PostgreSQL error: {e}")
        conn.close()
        return 1
    conn.close()
    print()

    # 3. Qdrant
    print("3. Seeding Qdrant collections...")
    collections = ["pulse_memory", "anomaly_memory", "investor_memory", "founder_blindspots"]
    for coll in collections:
        if not ensure_collection(coll):
            print(f"   ❌ Failed to ensure collection '{coll}'")
            return 1
        print(f"   ✅ Collection '{coll}' ready (768-dim, Cosine)")

    total_vectors = 0

    n = seed_pulse_memory()
    total_vectors += n
    print(f"   ✅ pulse_memory: {n} vectors upserted")

    n = seed_anomaly_memory()
    total_vectors += n
    print(f"   ✅ anomaly_memory: {n} vectors upserted")

    n = seed_investor_memory()
    total_vectors += n
    print(f"   ✅ investor_memory: {n} vectors upserted")

    n = seed_founder_blindspots()
    total_vectors += n
    print(f"   ✅ founder_blindspots: {n} vectors upserted")

    print()

    # 4. Guardian watchlist trigger analysis
    print("4. Guardian watchlist trigger analysis...")
    triggers = analyze_triggers()
    for t in triggers:
        icon = "🔴" if t["severity"] == "critical" else "🟡"
        print(f"   {icon} {t['id']} {t['name']}: {t['detail']}")

    print()

    # Summary
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                    ✅ SEED COMPLETE                       ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"   PostgreSQL tables:     5 (metric_snapshots, agent_alerts,")
    print(f"                            company_context, resolved_blindspots, eval_scores)")
    print(f"   PostgreSQL rows:       6 + 4 + 2 + 2 + 6 = 20 total")
    print(f"   Qdrant collections:    4")
    print(f"   Qdrant vectors:        {total_vectors}")
    print(f"   Guardian triggers:     {len(triggers)} patterns will fire")
    print()
    print(f"   Triggered patterns:")
    for t in triggers:
        print(f"     - {t['id']} {t['name']}")
    print()
    print("   Tenant ID: " + TENANT_ID)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
