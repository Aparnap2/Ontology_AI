-- ═══════════════════════════════════════════════════════════════
-- MIGRATION 009: OntologyAI MVP Pivot — Pulse, Anomaly, Investor, QA
-- ALL statements are idempotent (IF NOT EXISTS / ON CONFLICT DO NOTHING)
-- NEVER drops or alters existing tables
-- ═══════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────────
-- 1. MRR snapshots (PulseAgent writes once daily)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mrr_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    snapshot_date       DATE NOT NULL DEFAULT CURRENT_DATE,
    mrr_cents           BIGINT  NOT NULL DEFAULT 0,
    arr_cents           BIGINT  NOT NULL DEFAULT 0,
    active_customers    INTEGER NOT NULL DEFAULT 0,
    new_customers       INTEGER NOT NULL DEFAULT 0,
    churned_customers   INTEGER NOT NULL DEFAULT 0,
    expansion_cents     BIGINT  NOT NULL DEFAULT 0,
    contraction_cents   BIGINT  NOT NULL DEFAULT 0,
    burn_30d_cents      BIGINT  NOT NULL DEFAULT 0,
    runway_months       NUMERIC(6,2) NOT NULL DEFAULT 0,
    active_users_30d    INTEGER NOT NULL DEFAULT 0,
    data_sources        TEXT[]  NOT NULL DEFAULT '{}',
    UNIQUE (tenant_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_mrr_snapshots_tenant_date
    ON mrr_snapshots (tenant_id, snapshot_date DESC);

-- ────────────────────────────────────────────────────────────────
-- 2. Stripe events (raw webhook storage + idempotency)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stripe_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    stripe_event_id     TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    customer_id         TEXT,
    subscription_id     TEXT,
    amount_cents        INTEGER NOT NULL DEFAULT 0,
    currency            TEXT NOT NULL DEFAULT 'usd',
    mrr_delta_cents     INTEGER NOT NULL DEFAULT 0,
    raw_payload         JSONB,
    processed           BOOLEAN NOT NULL DEFAULT FALSE,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stripe_event_id)
);
CREATE INDEX IF NOT EXISTS idx_stripe_events_tenant_type
    ON stripe_events (tenant_id, event_type, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_stripe_events_unprocessed
    ON stripe_events (tenant_id, processed)
    WHERE processed = FALSE;

-- ────────────────────────────────────────────────────────────────
-- 3. Anomaly events (AnomalyAgent writes; links to Qdrant memory)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_name         TEXT NOT NULL,
    metric_value        NUMERIC NOT NULL,
    baseline_value      NUMERIC NOT NULL,
    deviation_pct       NUMERIC NOT NULL,
    explanation         TEXT,
    qdrant_point_id     TEXT,
    action_taken        TEXT NOT NULL DEFAULT 'ALERT',
    hitl_response       TEXT,
    resolved_at         TIMESTAMPTZ,
    slack_message_ts    TEXT
);
CREATE INDEX IF NOT EXISTS idx_anomaly_tenant_metric
    ON anomaly_events (tenant_id, metric_name, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_unresolved
    ON anomaly_events (tenant_id, resolved_at)
    WHERE resolved_at IS NULL;

-- ────────────────────────────────────────────────────────────────
-- 4. Investor updates (InvestorAgent generates weekly)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS investor_updates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    mrr_cents           BIGINT,
    mrr_growth_pct      NUMERIC(6,2),
    burn_cents          BIGINT,
    runway_months       NUMERIC(6,2),
    new_customers       INTEGER,
    churned_customers   INTEGER,
    draft_markdown      TEXT NOT NULL,
    sent_at             TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'DRAFT',
    UNIQUE (tenant_id, period_start)
);
CREATE INDEX IF NOT EXISTS idx_investor_updates_tenant
    ON investor_updates (tenant_id, generated_at DESC);

-- ────────────────────────────────────────────────────────────────
-- 5. Founder Q&A log (QAAgent writes every answered question)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS founder_queries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    question            TEXT NOT NULL,
    matched_template    TEXT,
    generated_sql       TEXT,
    data_snapshot       JSONB,
    answer              TEXT NOT NULL,
    slack_message       TEXT,
    latency_ms          INTEGER,
    asked_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_founder_queries_tenant
    ON founder_queries (tenant_id, asked_at DESC);

-- ────────────────────────────────────────────────────────────────
-- 6. Tenant integration credentials (Stripe + Plaid per tenant)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenant_integrations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    integration_type    TEXT NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    stripe_account_id   TEXT,
    plaid_access_token  TEXT,
    plaid_item_id       TEXT,
    slack_webhook_url   TEXT,
    slack_channel       TEXT,
    connected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_synced_at      TIMESTAMPTZ,
    sync_error          TEXT,
    UNIQUE (tenant_id, integration_type)
);
CREATE INDEX IF NOT EXISTS idx_tenant_integrations_active
    ON tenant_integrations (tenant_id, integration_type)
    WHERE is_active = TRUE;

-- ────────────────────────────────────────────────────────────────
-- 7. Verify all 6 new tables exist
-- ────────────────────────────────────────────────────────────────
DO $$
DECLARE
    expected TEXT[] := ARRAY[
        'mrr_snapshots',
        'stripe_events',
        'anomaly_events',
        'investor_updates',
        'founder_queries',
        'tenant_integrations'
    ];
    tbl TEXT;
    missing BOOLEAN := FALSE;
BEGIN
    FOREACH tbl IN ARRAY expected LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            RAISE WARNING 'MISSING TABLE: %', tbl;
            missing := TRUE;
        ELSE
            RAISE NOTICE '✓ %', tbl;
        END IF;
    END LOOP;
    IF missing THEN
        RAISE EXCEPTION 'Migration incomplete — missing tables';
    END IF;
    RAISE NOTICE '✓ Migration 009 complete';
END $$;
