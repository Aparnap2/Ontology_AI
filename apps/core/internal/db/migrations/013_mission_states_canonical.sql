-- 013_mission_states_canonical.sql
--
-- Canonical `mission_states` schema.
--
-- WHY THIS EXISTS
-- Three production writers depend on `INSERT ... ON CONFLICT (tenant_id)`:
--   * apps/ai/src/session/mission_state.py      (update_mission_state)
--   * apps/ai/src/services/trust_battery_db.py  (save_trust_profile)
--   * apps/core/internal/web/handler_workspace.go
-- `ON CONFLICT (tenant_id)` requires a matching unique constraint or unique
-- index. The base table was only ever created by the hand-applied
-- apps/ai/src/session/001_session_layer.sql, which no migration runner runs;
-- no migration in either runner directory ever issued CREATE TABLE
-- mission_states. As a result a runner-provisioned database satisfied none of
-- the writers: on real PostgreSQL the upserts fail with SQLSTATE 42P10 ("there
-- is no unique or exclusion constraint matching the ON CONFLICT
-- specification"), which the AI writers swallow and turn into `False`.
--
-- This migration makes the table a first-class member of the runner series so
-- that a runner-provisioned database satisfies every writer, and adds the
-- UNIQUE(tenant_id) the upserts have always assumed.
--
-- Column names, types and semantics match what the application reads/writes
-- (see apps/ai/src/session/mission_state.py). `active_alerts` and
-- `churn_risk_users` intentionally remain TEXT (comma-separated) — the AI
-- contract stores/reads them as strings, not jsonb.
--
-- Every statement is idempotent so the migration is safe against an empty
-- database and against a database bootstrapped from an older subset
-- (001_session_layer.sql, then 003_finance_guardrail_fields.sql, then 004).

CREATE TABLE IF NOT EXISTS mission_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Finance domain
    runway_days INTEGER,
    burn_alert BOOLEAN DEFAULT FALSE,
    burn_severity VARCHAR(20),

    -- BI domain
    mrr_trend VARCHAR(20),
    churn_rate FLOAT,

    -- Ops domain
    churn_risk_users TEXT,
    top_feature_ask TEXT,
    error_spike BOOLEAN DEFAULT FALSE,

    -- Cross-functional
    active_alerts TEXT,
    founder_focus TEXT,

    -- Trust battery integration
    trust_score INTEGER,
    route_priority INTEGER,

    -- Derived finance + guardrail fields (mirrors 003_finance_guardrail_fields.sql)
    burn_multiple NUMERIC,
    effective_runway_days INT,
    working_capital_ratio NUMERIC,
    npv_last_decision NUMERIC,
    wacc_estimate NUMERIC,
    last_approval_tier TEXT,
    last_reversible BOOLEAN,
    active_authority_limit TEXT,
    guardrail_override_reason TEXT,
    guardrail_risk_type TEXT,
    guardrail_blocking BOOLEAN DEFAULT FALSE,
    investor_facing_alert BOOLEAN DEFAULT FALSE,

    -- Command-center bridge fields (mirrors 004_resolve_mission_state_drift.sql)
    prepared_brief TEXT,
    pending_decisions JSONB DEFAULT '[]',
    last_updated_by TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT mission_states_severity_check
        CHECK (burn_severity IN ('low', 'medium', 'high', 'critical', NULL)),
    CONSTRAINT mission_states_trend_check
        CHECK (mrr_trend IN ('growing', 'stable', 'declining', NULL))
);

-- Bring an already-existing older table up to the canonical column set.
-- No-ops on a database created by the CREATE TABLE above.
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS trust_score INTEGER;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS route_priority INTEGER;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS burn_multiple NUMERIC;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS effective_runway_days INT;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS working_capital_ratio NUMERIC;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS npv_last_decision NUMERIC;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS wacc_estimate NUMERIC;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS last_approval_tier TEXT;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS last_reversible BOOLEAN;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS active_authority_limit TEXT;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS guardrail_override_reason TEXT;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS guardrail_risk_type TEXT;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS guardrail_blocking BOOLEAN DEFAULT FALSE;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS investor_facing_alert BOOLEAN DEFAULT FALSE;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS prepared_brief TEXT;
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS pending_decisions JSONB DEFAULT '[]';
ALTER TABLE mission_states ADD COLUMN IF NOT EXISTS last_updated_by TEXT;

CREATE INDEX IF NOT EXISTS idx_mission_states_tenant_time
    ON mission_states(tenant_id, timestamp DESC);

-- Exactly one row per tenant.
--
-- Cardinality was verified across the writers: every writer is an upsert on
-- tenant_id, and the only id-keyed per-mission writer
-- (apps/ai/scripts/real_pg_mission.py) is a manual script with no caller. If a
-- pre-existing database already violates the invariant, fail loudly so the
-- operator can reconcile rather than have rows silently dropped by the index.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM mission_states GROUP BY tenant_id HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'mission_states has duplicate tenant_id rows; reconcile before adding UNIQUE(tenant_id)';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mission_states_tenant
    ON mission_states(tenant_id);
