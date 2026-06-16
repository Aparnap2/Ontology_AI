-- Migration: Session Layer Tables for TrackGuard V3.0
-- Created: 2026-04-27
-- Purpose: Session management for tenant context and mission state tracking
--
-- Tables:
--   - mission_states: Stores tenant mission state (finance, BI, ops, cross-functional)
--   - session_messages: Stores conversation messages for context retrieval

-- Mission States table
-- Stores the current state of each tenant across all domains
-- Used by relevance gate to determine agent responsiveness
CREATE TABLE IF NOT EXISTS mission_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,

    -- Timestamp of when this state was captured
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Finance Domain
    runway_days INTEGER,
    burn_alert BOOLEAN DEFAULT FALSE,
    burn_severity VARCHAR(20),  -- low, medium, high, critical

    -- BI Domain
    mrr_trend VARCHAR(20),  -- growing, stable, declining
    churn_rate FLOAT,  -- percentage

    -- Ops Domain
    churn_risk_users TEXT,  -- comma-separated list of user IDs
    top_feature_ask TEXT,
    error_spike BOOLEAN DEFAULT FALSE,

    -- Cross-functional
    active_alerts TEXT,  -- comma-separated list of alert IDs
    founder_focus TEXT,

    -- Constraints
    CONSTRAINT mission_states_severity_check
        CHECK (burn_severity IN ('low', 'medium', 'high', 'critical', NULL)),
    CONSTRAINT mission_states_trend_check
        CHECK (mrr_trend IN ('growing', 'stable', 'declining', NULL)),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Session Messages table
-- Stores conversation messages for session context retrieval
CREATE TABLE IF NOT EXISTS session_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,

    -- Message role
    role VARCHAR(20) NOT NULL,  -- user, assistant, system

    -- Message content
    content TEXT NOT NULL,

    -- Metadata
    channel_id VARCHAR(100),
    user_id VARCHAR(100),

    -- Timestamp
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT session_messages_role_check
        CHECK (role IN ('user', 'assistant', 'system')),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_mission_states_tenant_time
    ON mission_states(tenant_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_session_messages_tenant_time
    ON session_messages(tenant_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_mission_states_burn_alert
    ON mission_states(tenant_id, burn_alert)
    WHERE burn_alert = TRUE;

CREATE INDEX IF NOT EXISTS idx_mission_states_active_alerts
    ON mission_states(tenant_id)
    WHERE active_alerts IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE mission_states IS
    'Stores tenant mission state across finance, BI, ops, and cross-functional domains. Used by relevance gate for agent routing.';

COMMENT ON TABLE session_messages IS
    'Stores conversation messages for session context retrieval. Provides last N messages for agent context.';

COMMENT ON COLUMN mission_states.runway_days IS
    'Number of months of runway remaining based on current burn rate';

COMMENT ON COLUMN mission_states.burn_alert IS
    'Flag indicating if burn rate has exceeded threshold';

COMMENT ON COLUMN mission_states.mrr_trend IS
    'Monthly recurring revenue trend direction';

COMMENT ON COLUMN mission_states.active_alerts IS
    'Comma-separated list of currently active alerts requiring attention';

-- Example data for testing (optional)
-- INSERT INTO mission_states (tenant_id, runway_days, burn_alert, burn_severity, mrr_trend, churn_rate, active_alerts)
-- VALUES ('test-tenant', 12, TRUE, 'high', 'stable', 2.5, 'alert-001,alert-002');