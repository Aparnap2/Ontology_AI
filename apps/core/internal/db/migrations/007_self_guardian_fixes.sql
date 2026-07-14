-- Migration 007: Self-Guardian fix proposals and execution results
-- Supports the bounded self-correction loop: fix_planner → remediator → audit

CREATE TABLE IF NOT EXISTS self_guardian_fix_proposals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id        UUID NOT NULL REFERENCES self_guardian_alerts(id) ON DELETE CASCADE,
    agent_name      TEXT NOT NULL,
    deviation_type  TEXT NOT NULL,
    action          TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    blast_radius    TEXT NOT NULL DEFAULT 'medium',
    reversible      BOOLEAN NOT NULL DEFAULT FALSE,
    requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    suggested_reviewer TEXT NOT NULL DEFAULT 'operator',
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS self_guardian_fix_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id     UUID NOT NULL REFERENCES self_guardian_fix_proposals(id) ON DELETE CASCADE,
    success         BOOLEAN NOT NULL DEFAULT FALSE,
    outcome         TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    rollback_action TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fix_proposals_status ON self_guardian_fix_proposals(status);
CREATE INDEX IF NOT EXISTS idx_fix_proposals_alert ON self_guardian_fix_proposals(alert_id);
CREATE INDEX IF NOT EXISTS idx_fix_results_proposal ON self_guardian_fix_results(proposal_id);
