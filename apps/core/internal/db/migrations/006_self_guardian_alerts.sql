-- 006_self_guardian_alerts.sql
-- Add self_guardian_alerts table for self-monitoring deviation tracking
-- Also ensure audit_log table exists for control plane queries

-- ── Self-Guardian Alerts ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS self_guardian_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL DEFAULT 'default',
    agent_name VARCHAR(100) NOT NULL,
    deviation_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    description TEXT,
    suggested_action TEXT,
    observation_action VARCHAR(100),
    observation_tool_id VARCHAR(100),
    observation_success BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sga_tenant_created
    ON self_guardian_alerts(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sga_agent
    ON self_guardian_alerts(agent_name);
CREATE INDEX IF NOT EXISTS idx_sga_severity
    ON self_guardian_alerts(severity);

-- ── Audit log (control plane audit trail) ───────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL DEFAULT 'default',
    agent_name VARCHAR(200) NOT NULL,
    action VARCHAR(100) NOT NULL,
    tool_name VARCHAR(200),
    model_used VARCHAR(100),
    policy_decision JSONB,
    approval_state VARCHAR(20),
    outcome VARCHAR(20) NOT NULL,
    details JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_time
    ON audit_log(tenant_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_agent
    ON audit_log(agent_name, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_outcome
    ON audit_log(outcome, timestamp DESC);
