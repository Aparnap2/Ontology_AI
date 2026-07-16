-- OntologyAI V5.1 schema source for sqlc (PRD §22, PLAN §4).
-- Mirrors migrations/010_ontologyai_v51.sql. Kept separate from the v1.0
-- command_center.sql to avoid disturbing legacy schema definitions.
-- All DDL is idempotent; sqlc only reads this for type inference.

-- engagement_states — canonical write target (PRD §22.2)
CREATE TABLE IF NOT EXISTS engagement_states (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT UNIQUE NOT NULL,
    workspace_mode  TEXT,
    phase           TEXT,
    state           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- executable_workflow_drafts (PRD §22.4)
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

-- workflow_specs (PRD §22.3)
CREATE TABLE IF NOT EXISTS workflow_specs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    workflow_name   TEXT,
    spec            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- approvals (PRD §22.5)
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

-- session_messages — NEW, distinct from legacy chat_messages (PRD §22.1)
CREATE TABLE IF NOT EXISTS session_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    role            TEXT,
    content         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- artifact_exports (PRD §22.6)
CREATE TABLE IF NOT EXISTS artifact_exports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID,
    engagement_id   TEXT,
    artifact_type   TEXT,
    content         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- data_sources (PRD §22.7)
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
