-- OntologyAI Command Center tables

-- Mission state (compiled operational state from Python AI layer)
CREATE TABLE IF NOT EXISTS mission_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,
    mrr DECIMAL(12,2),
    burn_rate DECIMAL(12,2),
    runway_days INTEGER,
    burn_alert BOOLEAN DEFAULT FALSE,
    burn_severity VARCHAR(20),
    mrr_trend VARCHAR(10),
    churn_rate DECIMAL(5,2),
    error_spike BOOLEAN,
    active_alerts TEXT,
    founder_focus TEXT,
    trust_score INTEGER,
    burn_multiple DECIMAL(5,2),
    effective_runway_days INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mission_state_tenant ON mission_state(tenant_id);

-- Planned actions (approval queue from Python AI)
CREATE TABLE IF NOT EXISTS planned_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100),
    actor VARCHAR(50),
    action_type VARCHAR(50),
    target_ref TEXT,
    risk_level VARCHAR(20) DEFAULT 'low',
    requires_approval BOOLEAN DEFAULT TRUE,
    approval_reason TEXT,
    status VARCHAR(20) DEFAULT 'planned',
    created_at TIMESTAMP DEFAULT NOW(),
    executed_at TIMESTAMP,
    error TEXT,
    -- V5.1 extensions (PRD §12.6 / PLAN §4): non-destructive, nullable.
    -- Existing columns above are preserved — DO NOT drop or rename.
    engagement_id TEXT,
    target_type TEXT,
    target_id TEXT,
    requested_by TEXT,
    approved_by TEXT,
    reason TEXT,
    temporal_workflow_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_planned_actions_status ON planned_actions(status);
CREATE INDEX IF NOT EXISTS idx_planned_actions_tenant ON planned_actions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_planned_actions_engagement ON planned_actions(engagement_id);
CREATE INDEX IF NOT EXISTS idx_planned_actions_status_created ON planned_actions(status, created_at DESC);

-- Agent traces (from Python AI trace_store)
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

-- Chat messages (from command center agent chat)
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) DEFAULT 'default',
    sender VARCHAR(50) NOT NULL DEFAULT 'founder',
    mention VARCHAR(50),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at DESC);
