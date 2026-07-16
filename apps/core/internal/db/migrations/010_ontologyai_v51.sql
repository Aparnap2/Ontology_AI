-- ═══════════════════════════════════════════════════════════════════════
-- MIGRATION 010: OntologyAI V5.1 persistence layer
--
-- SCOPE (PRD §22, PLAN_V5.1 §4):
--   NEW tables (7):
--     1. engagement_states        — canonical write target (PRD §22.2)
--     2. executable_workflow_drafts (PRD §22.4)
--     3. workflow_specs            (PRD §22.3)
--     4. approvals                 (PRD §22.5)
--     5. session_messages          (PRD §22.1, distinct from legacy chat_messages)
--     6. artifact_exports          (PRD §22.6)
--     7. data_sources              (PRD §22.7)
--
--   ALTER (non-destructive) planned_actions:
--     Add engagement_id, target_type, target_id, requested_by,
--     approved_by, reason to match PRD §12.6 / handler.go reads.
--     Existing columns (actor, action_type, target_ref, risk_level,
--     requires_approval, status, temporal_workflow_id, created_at, ...) are
--     preserved — DO NOT drop or rename.
--
--   BRIDGE (preserved, untouched):
--     mission_states  — read-only bridge for one version (§8.1 decision 1)
--     chat_messages   — legacy, left unchanged (§8.1 decision 8)
--
-- All DDL is idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS) so the
-- migration can be re-applied on fresh or existing databases safely.
-- ═══════════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 1: engagement_states — canonical write target (PRD §22.2)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS engagement_states (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT UNIQUE NOT NULL,
    workspace_mode  TEXT,
    phase           TEXT,
    state           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engagement_states_tenant
    ON engagement_states(tenant_id);
CREATE INDEX IF NOT EXISTS idx_engagement_states_engagement
    ON engagement_states(engagement_id);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 2: executable_workflow_drafts (PRD §22.4)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS executable_workflow_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    runtime         TEXT,
    name            TEXT,
    status          TEXT,
    draft           JSONB NOT NULL,
    export_payload  JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ewd_tenant
    ON executable_workflow_drafts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ewd_engagement_status
    ON executable_workflow_drafts(engagement_id, status);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 3: workflow_specs (PRD §22.3)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS workflow_specs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    workflow_name   TEXT,
    spec            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_specs_tenant
    ON workflow_specs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflow_specs_engagement
    ON workflow_specs(engagement_id);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 4: approvals (PRD §22.5)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    target_type     TEXT,
    target_id       TEXT,
    status          TEXT,
    requested_by    TEXT,
    approved_by     TEXT NULL,
    reason          TEXT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_approvals_tenant
    ON approvals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_approvals_engagement_status
    ON approvals(engagement_id, status);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 5: session_messages — NEW, distinct from legacy chat_messages (PRD §22.1)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS session_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    role            TEXT,
    content         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_messages_tenant
    ON session_messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_session_messages_engagement
    ON session_messages(engagement_id);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 6: artifact_exports (PRD §22.6)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS artifact_exports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    artifact_type   TEXT,
    content         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifact_exports_tenant
    ON artifact_exports(tenant_id);
CREATE INDEX IF NOT EXISTS idx_artifact_exports_engagement
    ON artifact_exports(engagement_id);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 7: data_sources (PRD §22.7)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS data_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    source_type     TEXT,
    source_name     TEXT,
    status          TEXT,
    freshness       JSONB,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_sources_tenant
    ON data_sources(tenant_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_engagement
    ON data_sources(engagement_id);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 8: planned_actions — EXTEND (non-destructive ALTER, PRD §12.6)
-- ═══════════════════════════════════════════════════════════════════════
-- Existing columns (command_center.sql) preserved:
--   id, tenant_id, actor, action_type, target_ref, risk_level,
--   requires_approval, approval_reason, status, created_at,
--   executed_at, error, temporal_workflow_id (added in 003).
-- New columns below align the table with the V5.1 PlannedAction contract
-- and the engagement-scoped read/write path used by handler.go.
ALTER TABLE planned_actions
    ADD COLUMN IF NOT EXISTS engagement_id TEXT;
ALTER TABLE planned_actions
    ADD COLUMN IF NOT EXISTS target_type TEXT;
ALTER TABLE planned_actions
    ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE planned_actions
    ADD COLUMN IF NOT EXISTS requested_by TEXT;
ALTER TABLE planned_actions
    ADD COLUMN IF NOT EXISTS approved_by TEXT NULL;
ALTER TABLE planned_actions
    ADD COLUMN IF NOT EXISTS reason TEXT NULL;

-- Supporting indexes for the engagement-scoped approval queue (PLAN §4.3)
CREATE INDEX IF NOT EXISTS idx_planned_actions_engagement
    ON planned_actions(engagement_id);
CREATE INDEX IF NOT EXISTS idx_planned_actions_status_created
    ON planned_actions(status, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SUMMARY:
--   New tables: engagement_states, executable_workflow_drafts,
--     workflow_specs, approvals, session_messages, artifact_exports,
--     data_sources (7 total).
--   Altered: planned_actions (6 new nullable columns, no drops/renames).
--   Preserved (untouched): mission_states (bridge), chat_messages (legacy).
--   All DDL idempotent; safe to re-run on fresh or existing databases.
-- ═══════════════════════════════════════════════════════════════════════
