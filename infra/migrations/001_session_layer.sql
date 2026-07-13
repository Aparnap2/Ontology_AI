-- 001_session_layer.sql - V3.0 Session Layer
-- Per PRD: mission_states + session_messages tables

-- mission_states: Shared context for all agents
-- Per PRD Section 11: All agents read/write this state
CREATE TABLE IF NOT EXISTS mission_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    data_last_synced TIMESTAMPTZ,

    -- Finance domain fields (Finance Guardian writes)
    mrr NUMERIC(12, 2),
    burn_rate NUMERIC(12, 2),
    runway_days INTEGER,
    burn_alert BOOLEAN DEFAULT FALSE,
    burn_severity TEXT CHECK (burn_severity IN ('low', 'medium', 'high', 'critical')),

    -- BI domain fields (BI Analyst writes)
    mrr_trend TEXT CHECK (mrr_trend IN ('growing', 'stable', 'declining')),
    churn_rate NUMERIC(5, 4),

    -- Ops domain fields (Ops Watch writes)
    churn_risk_users TEXT,  -- comma-separated user IDs
    top_feature_ask TEXT,
    error_spike BOOLEAN DEFAULT FALSE,

    -- Cross-agent signals (Co-founder manages)
    active_alerts TEXT,  -- comma-separated alert IDs
    founder_focus TEXT,

    -- Trust Battery integration fields
    trust_score NUMERIC(3, 2),  -- 0.00-1.00 from trust battery
    route_priority INTEGER,  -- routing priority based on trust

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_mission_states_tenant
    ON mission_states(tenant_id);

CREATE INDEX IF NOT EXISTS idx_mission_states_timestamp
    ON mission_states(timestamp DESC);

-- session_messages: channel history
-- Per PRD Section 7: All agents read, employees write
CREATE TABLE IF NOT EXISTS session_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('founder', 'finance', 'bi', 'ops', 'sarthi')),
    content TEXT NOT NULL,
    agent_name TEXT,
    conversation_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_messages_tenant_created
    ON session_messages(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_session_messages_role
    ON session_messages(tenant_id, role);

-- Add missing columns to existing mission_states table (if exists)
-- These are idempotent ALTER statements for existing deployments
ALTER TABLE mission_states
    ADD COLUMN IF NOT EXISTS trust_score NUMERIC(3, 2);

ALTER TABLE mission_states
    ADD COLUMN IF NOT EXISTS route_priority INTEGER;

ALTER TABLE mission_states
    ADD COLUMN IF NOT EXISTS mrr NUMERIC(12, 2);

ALTER TABLE mission_states
    ADD COLUMN IF NOT EXISTS burn_rate NUMERIC(12, 2);

ALTER TABLE mission_states
    ADD COLUMN IF NOT EXISTS data_last_synced TIMESTAMPTZ;