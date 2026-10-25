-- 014_investor_relationships.sql
--
-- Canonical investor-relations schema.
--
-- WHY THIS EXISTS
-- The investor update orchestration reads `investor_relationships`
-- (apps/ai/src/orchestration/run_investor_update.py) and the AI DB helpers
-- write `investor_relationships` / `investor_interactions`
-- (apps/ai/src/db/investor_relationships.py), but no migration in either
-- runner directory ever created those tables. The only CREATE TABLE lived in
-- archive/PRD_V4.2.md, which no runner executes. A runner-provisioned database
-- therefore failed every investor warmup/status query with SQLSTATE 42P01.
--
-- Column names, types and defaults match the application reads/writes and the
-- frozen V4.2 contract. Every statement is idempotent so this migration is safe
-- on an empty database and on databases where the table was hand-created.

CREATE TABLE IF NOT EXISTS investor_relationships (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    investor_name TEXT NOT NULL,
    firm TEXT NOT NULL,
    last_contact_at TIMESTAMPTZ,
    warm_up_days INTEGER NOT NULL DEFAULT 30,
    raise_priority INTEGER NOT NULL DEFAULT 5,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_investor_relationships_tenant
    ON investor_relationships (tenant_id);

CREATE INDEX IF NOT EXISTS idx_investor_relationships_warmup
    ON investor_relationships (tenant_id, last_contact_at);

CREATE TABLE IF NOT EXISTS investor_interactions (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    investor_id BIGINT REFERENCES investor_relationships(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL,
    summary TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_investor_interactions_tenant
    ON investor_interactions (tenant_id, occurred_at DESC);
