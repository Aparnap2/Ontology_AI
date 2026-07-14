-- 008_command_center_tables.sql
-- Add command center tables for agent traces and app configuration.
-- Agent traces are emitted by the Python AI layer via trace_store.
-- App config is used by the HTMX dashboard for per-tenant settings.

-- ── Agent Traces ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100),
    agent_name VARCHAR(50),
    action TEXT,
    duration_ms INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    llm_tokens INTEGER DEFAULT 0,
    llm_cost_usd DECIMAL(10,6) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'success',
    failure_bucket VARCHAR(50),
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_traces_tenant ON agent_traces(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_agent ON agent_traces(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_traces_created ON agent_traces(created_at DESC);

-- ── App Config ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) DEFAULT 'default',
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW()
);
