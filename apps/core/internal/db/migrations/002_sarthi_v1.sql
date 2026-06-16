-- ══════════════════════════════════════════════════════════════════
-- MIGRATION 002: TrackGuard v1.0 Foundation
-- APPEND ONLY — never modify 001_* or any existing table
-- Apply: psql $DATABASE_URL -f 002_sarthi_v1.sql
-- ══════════════════════════════════════════════════════════════════

-- ── Tenant / Founder ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS founders (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) UNIQUE NOT NULL,
    telegram_chat_id  VARCHAR(50) NOT NULL,
    name              VARCHAR(100),
    stage             VARCHAR(30) DEFAULT 'prerevenue',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── Raw event archive ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_events (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    source            VARCHAR(50) NOT NULL,
    event_type        VARCHAR(100) NOT NULL,
    payload_hash      VARCHAR(100) NOT NULL,
    payload_body      JSONB NOT NULL,
    idempotency_key   VARCHAR(200) UNIQUE,
    received_at       TIMESTAMPTZ DEFAULT NOW(),
    processed_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_raw_events_tenant_type
    ON raw_events(tenant_id, event_type, received_at DESC);

-- ── Transactions / Revenue ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    raw_event_id      UUID REFERENCES raw_events(id),
    txn_date          DATE NOT NULL,
    description       TEXT NOT NULL,
    debit             NUMERIC(18,2) DEFAULT 0,
    credit            NUMERIC(18,2) DEFAULT 0,
    category          VARCHAR(50),
    confidence        FLOAT,
    source            VARCHAR(50),
    external_id       VARCHAR(200),
    UNIQUE(tenant_id, external_id)
);

-- ── CRM Pipeline Deals ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_deals (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    deal_id           VARCHAR(100) NOT NULL,
    name              VARCHAR(200),
    amount            NUMERIC(18,2),
    stage             VARCHAR(50),
    last_contact_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, deal_id)
);

-- ── Customer Success ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cs_customers (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    customer_id       VARCHAR(100) NOT NULL,
    telegram_id       VARCHAR(50),
    signup_at         TIMESTAMPTZ,
    last_seen_at      TIMESTAMPTZ,
    onboarding_stage  VARCHAR(20) DEFAULT 'WELCOME',
    risk_score        FLOAT DEFAULT 0,
    UNIQUE(tenant_id, customer_id)
);

-- ── People / HR ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employees (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    employee_id       VARCHAR(100) NOT NULL,
    name              VARCHAR(100),
    role_function     VARCHAR(20),
    status            VARCHAR(20) DEFAULT 'ONBOARDING',
    checklist         JSONB DEFAULT '{}',
    hired_at          TIMESTAMPTZ,
    terminated_at     TIMESTAMPTZ,
    UNIQUE(tenant_id, employee_id)
);

-- ── Finance ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS finance_snapshots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    snapshot_date     DATE NOT NULL,
    monthly_revenue   NUMERIC(18,2),
    monthly_expense   NUMERIC(18,2),
    burn_rate         NUMERIC(18,2),
    runway_months     FLOAT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vendor_baselines (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    vendor_name       VARCHAR(200) NOT NULL,
    avg_monthly       NUMERIC(18,2),
    stddev_monthly    NUMERIC(18,2),
    sample_count      INT DEFAULT 0,
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, vendor_name)
);

-- ── Agent output log (consumed by Chief of Staff) ─────────────────
CREATE TABLE IF NOT EXISTS agent_outputs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    agent_name        VARCHAR(50) NOT NULL,
    output_type       VARCHAR(50),
    headline          TEXT,
    urgency           VARCHAR(10) DEFAULT 'low',
    hitl_sent         BOOLEAN DEFAULT FALSE,
    output_json       JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── Telegram HITL action log ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS hitl_actions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(50) NOT NULL,
    agent_name        VARCHAR(50),
    message_sent      TEXT,
    buttons           JSONB,
    founder_response  VARCHAR(50),
    responded_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
