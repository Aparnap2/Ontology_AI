-- ══════════════════════════════════════════════════════════════════
-- MIGRATION 003: OntologyAI v1.0 Stripped Build (Finance + BI Agents)
-- APPEND ONLY — never modify existing tables
-- Apply: psql "$DATABASE_URL" -f infra/migrations/003_sarthi_stripped.sql
-- ══════════════════════════════════════════════════════════════════

-- ── BI Query History (for BI Agent memory) ────────────────────────
CREATE TABLE IF NOT EXISTS bi_queries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL,
    query_text    TEXT NOT NULL,
    generated_sql TEXT,
    row_count     INT,
    chart_path    TEXT,
    narrative     TEXT,
    qdrant_id     TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Vendor Baselines Enhancement ─────────────────────────────────
-- Add 30d/90d averages and transaction count for better anomaly detection
ALTER TABLE vendor_baselines
    ADD COLUMN IF NOT EXISTS avg_30d NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS avg_90d NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS transaction_count INT DEFAULT 0;

-- ── Agent Outputs Enhancement ────────────────────────────────────
-- Add Langfuse trace ID and anomaly score for observability
ALTER TABLE agent_outputs
    ADD COLUMN IF NOT EXISTS langfuse_trace TEXT,
    ADD COLUMN IF NOT EXISTS anomaly_score  FLOAT;

-- ── Indexes for Performance ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_bi_queries_tenant
    ON bi_queries(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_vendor_baselines_tenant_vendor_name
    ON vendor_baselines(tenant_id, vendor_name);

CREATE INDEX IF NOT EXISTS idx_agent_outputs_tenant_agent_name
    ON agent_outputs(tenant_id, agent_name, created_at DESC);

-- ── Comments for Documentation ───────────────────────────────────
COMMENT ON TABLE bi_queries IS 'BI Agent query history with SQL, charts, and narratives';
COMMENT ON COLUMN vendor_baselines.avg_30d IS 'Rolling 30-day average spend for this vendor';
COMMENT ON COLUMN vendor_baselines.avg_90d IS 'Rolling 90-day average spend for this vendor';
COMMENT ON COLUMN vendor_baselines.transaction_count IS 'Number of transactions used to calculate averages';
COMMENT ON COLUMN agent_outputs.langfuse_trace IS 'Langfuse trace ID for LLM observability';
COMMENT ON COLUMN agent_outputs.anomaly_score IS 'Anomaly score 0.0-1.0 for finance alerts';
