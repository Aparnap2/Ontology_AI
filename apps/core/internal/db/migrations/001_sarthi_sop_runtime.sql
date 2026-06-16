-- ══════════════════════════════════════════════════════════════════
-- MIGRATION 001: TrackGuard SOP Runtime Foundation
-- APPEND ONLY — never modify existing tables
-- Apply: psql $DATABASE_URL -f this_file.sql
-- ══════════════════════════════════════════════════════════════════

-- ── Raw event archive ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id       UUID NOT NULL,
    source           VARCHAR(50)  NOT NULL,
    event_name       VARCHAR(100) NOT NULL,
    topic            VARCHAR(150) NOT NULL,
    sop_name         VARCHAR(100) NOT NULL,
    payload_hash     VARCHAR(100) NOT NULL,
    payload_body     JSONB        NOT NULL,
    signature_valid  BOOLEAN      DEFAULT TRUE,
    idempotency_key  VARCHAR(200) UNIQUE,
    received_at      TIMESTAMPTZ  DEFAULT NOW(),
    processed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_raw_events_founder_source
    ON raw_events(founder_id, source, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_events_idempotency
    ON raw_events(idempotency_key) WHERE idempotency_key IS NOT NULL;

-- ── SOP execution jobs ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sop_jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id       UUID NOT NULL,
    raw_event_id     UUID REFERENCES raw_events(id),
    sop_name         VARCHAR(100) NOT NULL,
    temporal_run_id  VARCHAR(200),
    temporal_wf_id   VARCHAR(200),
    status           VARCHAR(30)  DEFAULT 'pending',
    hitl_level       VARCHAR(10)  DEFAULT 'low',
    input_ref        VARCHAR(200),
    output_ref       VARCHAR(200),
    error_message    TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sop_jobs_founder_sop
    ON sop_jobs(founder_id, sop_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sop_jobs_status
    ON sop_jobs(status, created_at DESC);

-- ── Connector states ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS connector_states (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id       UUID NOT NULL,
    connector        VARCHAR(50)  NOT NULL,
    access_token     TEXT,
    refresh_token    TEXT,
    token_expires_at TIMESTAMPTZ,
    last_sync_at     TIMESTAMPTZ,
    backfill_done    BOOLEAN DEFAULT FALSE,
    backfill_cursor  VARCHAR(200),
    health           VARCHAR(20)  DEFAULT 'active',
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE(founder_id, connector)
);

-- ── Dead letter queue ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dead_letter_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_event_id     UUID REFERENCES raw_events(id),
    founder_id       UUID,
    source           VARCHAR(50),
    event_name       VARCHAR(100),
    failure_reason   TEXT NOT NULL,
    raw_payload      JSONB,
    retry_count      INT  DEFAULT 0,
    last_retry_at    TIMESTAMPTZ,
    resolved         BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── Normalized transaction ledger ────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id           UUID NOT NULL,
    raw_event_id         UUID REFERENCES raw_events(id),
    txn_date             DATE NOT NULL,
    description          TEXT NOT NULL,
    debit                NUMERIC(18,2) DEFAULT 0,
    credit               NUMERIC(18,2) DEFAULT 0,
    balance              NUMERIC(18,2),
    category             VARCHAR(50),
    category_confidence  FLOAT,
    source               VARCHAR(50),
    external_id          VARCHAR(200),
    qdrant_point_id      VARCHAR(100),
    needs_review         BOOLEAN DEFAULT FALSE,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(founder_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_transactions_founder_date
    ON transactions(founder_id, txn_date DESC);

-- ── Accounts payable ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts_payable (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id       UUID NOT NULL,
    vendor_name      VARCHAR(200) NOT NULL,
    amount           NUMERIC(18,2) NOT NULL,
    currency         CHAR(3)      DEFAULT 'INR',
    due_date         DATE,
    invoice_number   VARCHAR(100),
    source           VARCHAR(50),
    status           VARCHAR(30)  DEFAULT 'pending_approval',
    raw_event_id     UUID REFERENCES raw_events(id),
    approved_at      TIMESTAMPTZ,
    paid_at          TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- ── Compliance calendar ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_calendar (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id       UUID NOT NULL,
    jurisdiction     VARCHAR(20)  DEFAULT 'IN',
    filing_type      VARCHAR(100) NOT NULL,
    due_date         DATE NOT NULL,
    description      TEXT,
    status           VARCHAR(30)  DEFAULT 'pending',
    data_ref         VARCHAR(200),
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- ── SOP output findings ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sop_findings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sop_job_id       UUID REFERENCES sop_jobs(id),
    founder_id       UUID NOT NULL,
    sop_name         VARCHAR(100) NOT NULL,
    finding_type     VARCHAR(50),
    headline         TEXT,
    body             TEXT,
    do_this          TEXT,
    hitl_risk        VARCHAR(10)  DEFAULT 'low',
    telegram_sent    BOOLEAN DEFAULT FALSE,
    telegram_msg_id  VARCHAR(100),
    is_good_news     BOOLEAN DEFAULT FALSE,
    fire_alert       BOOLEAN DEFAULT FALSE,
    output_json      JSONB,
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);
