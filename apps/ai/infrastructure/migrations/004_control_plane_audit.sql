-- Migration 004: Add control plane audit logging
-- Creates the audit_log table for tracking all control-plane-gated actions
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,
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

COMMENT ON TABLE audit_log IS 'Control plane audit trail for all agent actions gated by policy, risk, and HITL routing';
COMMENT ON COLUMN audit_log.policy_decision IS 'Snapshot of the PolicyDecision that governed this action';
COMMENT ON COLUMN audit_log.approval_state IS 'auto | review | approve | blocked';
COMMENT ON COLUMN audit_log.outcome IS 'completed | blocked | failed';
