-- OntologyAI V6 — Virtual COO Domain Schema
-- Migration: 012
-- Date: 2026-08-10
-- This migration creates the V6 domain tables that back the Virtual COO
-- operating model: pillars, processes, SOPs, AI employees, missions,
-- governed actions, outcomes, and reviews.

-- =============================================
-- Updated-at trigger function (idempotent)
-- =============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- =============================================
-- 1. Business Pillars
-- =============================================
CREATE TABLE IF NOT EXISTS business_pillars (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL
        CHECK (name IN ('marketing', 'sales', 'operations', 'finance')),
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    description     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_business_pillars_tenant ON business_pillars(tenant_id);
CREATE INDEX IF NOT EXISTS idx_business_pillars_name ON business_pillars(name);

DROP TRIGGER IF EXISTS trg_business_pillars_updated_at ON business_pillars;
CREATE TRIGGER trg_business_pillars_updated_at
    BEFORE UPDATE ON business_pillars
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 2. Processes
-- =============================================
CREATE TABLE IF NOT EXISTS processes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    pillar          TEXT
        CHECK (pillar IN ('marketing', 'sales', 'operations', 'finance')),
    process_type    TEXT NOT NULL DEFAULT 'core'
        CHECK (process_type IN ('core', 'support', 'management')),
    status          TEXT NOT NULL DEFAULT 'mapped'
        CHECK (status IN ('mapped', 'analyzed', 'improved', 'retired')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    relationship_to_owner TEXT
        CHECK (relationship_to_owner IN ('owns', 'sponsors', 'operates', 'supports')),
    objective       TEXT,
    scope           TEXT,
    decision_rules  JSONB NOT NULL DEFAULT '[]'::jsonb,
    definition_of_done TEXT,
    kpi_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
    dependencies    JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    review_cadence  TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_processes_tenant ON processes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_processes_status ON processes(status);
CREATE INDEX IF NOT EXISTS idx_processes_pillar ON processes(pillar);
CREATE INDEX IF NOT EXISTS idx_processes_owner ON processes(owner_id);
CREATE INDEX IF NOT EXISTS idx_processes_gin_kpi_ids ON processes USING GIN(kpi_ids);

DROP TRIGGER IF EXISTS trg_processes_updated_at ON processes;
CREATE TRIGGER trg_processes_updated_at
    BEFORE UPDATE ON processes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 3. Process Steps
-- =============================================
CREATE TABLE IF NOT EXISTS process_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    process_id      UUID NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    order_index     INT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'deprecated')),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    description     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_process_steps_tenant ON process_steps(tenant_id);
CREATE INDEX IF NOT EXISTS idx_process_steps_process ON process_steps(process_id);
CREATE INDEX IF NOT EXISTS idx_process_steps_status ON process_steps(status);

DROP TRIGGER IF EXISTS trg_process_steps_updated_at ON process_steps;
CREATE TRIGGER trg_process_steps_updated_at
    BEFORE UPDATE ON process_steps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 4. SOPs
-- =============================================
CREATE TABLE IF NOT EXISTS sops (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    process_id      UUID REFERENCES processes(id) ON DELETE SET NULL,
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'archived')),
    current_version_id UUID,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_sops_tenant ON sops(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sops_process ON sops(process_id);
CREATE INDEX IF NOT EXISTS idx_sops_status ON sops(status);
CREATE INDEX IF NOT EXISTS idx_sops_owner ON sops(owner_id);

DROP TRIGGER IF EXISTS trg_sops_updated_at ON sops;
CREATE TRIGGER trg_sops_updated_at
    BEFORE UPDATE ON sops
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 5. SOP Versions
-- =============================================
CREATE TABLE IF NOT EXISTS sop_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    sop_id          UUID NOT NULL REFERENCES sops(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'current', 'superseded')),
    changes         TEXT,
    author          TEXT,
    supersedes_id   UUID REFERENCES sop_versions(id) ON DELETE SET NULL,
    body            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_sop_versions_tenant ON sop_versions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sop_versions_sop ON sop_versions(sop_id);
CREATE INDEX IF NOT EXISTS idx_sop_versions_status ON sop_versions(status);

DROP TRIGGER IF EXISTS trg_sop_versions_updated_at ON sop_versions;
CREATE TRIGGER trg_sop_versions_updated_at
    BEFORE UPDATE ON sop_versions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 6. AI Employees
-- =============================================
CREATE TABLE IF NOT EXISTS employees (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    role            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'paused')),
    goals           JSONB NOT NULL DEFAULT '[]'::jsonb,
    skills          JSONB NOT NULL DEFAULT '[]'::jsonb,
    capabilities    JSONB NOT NULL DEFAULT '[]'::jsonb,
    permissions     JSONB NOT NULL DEFAULT '[]'::jsonb,
    policies        JSONB NOT NULL DEFAULT '[]'::jsonb,
    authority       JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_threshold  TEXT NOT NULL DEFAULT 'MEDIUM'
        CHECK (risk_threshold IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    kpis            JSONB NOT NULL DEFAULT '[]'::jsonb,
    memory_namespace TEXT,
    mission_types   JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_employees_tenant ON employees(tenant_id);
CREATE INDEX IF NOT EXISTS idx_employees_role ON employees(role);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status);
CREATE INDEX IF NOT EXISTS idx_employees_gin_capabilities ON employees USING GIN(capabilities);

DROP TRIGGER IF EXISTS trg_employees_updated_at ON employees;
CREATE TRIGGER trg_employees_updated_at
    BEFORE UPDATE ON employees
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 7. Missions
-- =============================================
CREATE TABLE IF NOT EXISTS missions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'stalled', 'completed', 'failed', 'archived')),
    priority        TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    confidence      REAL CHECK (confidence >= 0 AND confidence <= 1),
    owner_id        UUID REFERENCES stakeholders(id) ON DELETE SET NULL,
    employee_role   TEXT,
    kpi_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    knowledge_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    process_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_missions_tenant ON missions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_priority ON missions(priority);
CREATE INDEX IF NOT EXISTS idx_missions_owner ON missions(owner_id);
CREATE INDEX IF NOT EXISTS idx_missions_gin_process_ids ON missions USING GIN(process_ids);

DROP TRIGGER IF EXISTS trg_missions_updated_at ON missions;
CREATE TRIGGER trg_missions_updated_at
    BEFORE UPDATE ON missions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 8. Mission Events (append-only timeline)
-- =============================================
CREATE TABLE IF NOT EXISTS mission_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    mission_id      UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL
        CHECK (event_type IN (
            'created', 'started', 'reviewed', 'paused', 'resumed', 'replanned',
            'redirected', 'approved', 'rejected', 'executed',
            'confidence_changed', 'status_changed', 'priority_changed',
            'evidence_added', 'recommendation_updated', 'completed', 'archived'
        )),
    version         INT NOT NULL DEFAULT 1,
    actor           TEXT,
    source          TEXT,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    causation_id    TEXT,
    correlation_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mission_events_tenant ON mission_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_mission_events_mission ON mission_events(mission_id);
CREATE INDEX IF NOT EXISTS idx_mission_events_type ON mission_events(event_type);
CREATE INDEX IF NOT EXISTS idx_mission_events_created ON mission_events(created_at);

-- =============================================
-- 9. Actions (governed, idempotent)
-- =============================================
CREATE TABLE IF NOT EXISTS actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    mission_id      UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    employee_role   TEXT NOT NULL,
    capability      TEXT NOT NULL,
    risk_tier       TEXT NOT NULL DEFAULT 'LOW'
        CHECK (risk_tier IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    policy_tier     TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft', 'pending_approval', 'approved', 'rejected',
            'executing', 'completed', 'failed'
        )),
    idempotency_key TEXT NOT NULL,
    evidence_refs   JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason          TEXT,
    confidence      REAL CHECK (confidence >= 0 AND confidence <= 1),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT,
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_actions_tenant ON actions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_actions_mission ON actions(mission_id);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);
CREATE INDEX IF NOT EXISTS idx_actions_risk ON actions(risk_tier);
CREATE INDEX IF NOT EXISTS idx_actions_idempotency ON actions(idempotency_key);

DROP TRIGGER IF EXISTS trg_actions_updated_at ON actions;
CREATE TRIGGER trg_actions_updated_at
    BEFORE UPDATE ON actions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 10. Action Results
-- =============================================
CREATE TABLE IF NOT EXISTS action_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    action_id       UUID NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    result_summary  TEXT,
    output_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    error           TEXT,
    rollback_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    verified        BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_action_results_tenant ON action_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_results_action ON action_results(action_id);
CREATE INDEX IF NOT EXISTS idx_action_results_verified ON action_results(verified);

DROP TRIGGER IF EXISTS trg_action_results_updated_at ON action_results;
CREATE TRIGGER trg_action_results_updated_at
    BEFORE UPDATE ON action_results
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 11. Outcomes
-- =============================================
CREATE TABLE IF NOT EXISTS outcomes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    mission_id      UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    result          TEXT NOT NULL DEFAULT 'na'
        CHECK (result IN ('success', 'partial', 'failure', 'na')),
    evidence_refs   JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary         TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_outcomes_tenant ON outcomes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_mission ON outcomes(mission_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_result ON outcomes(result);

DROP TRIGGER IF EXISTS trg_outcomes_updated_at ON outcomes;
CREATE TRIGGER trg_outcomes_updated_at
    BEFORE UPDATE ON outcomes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- 12. Reviews
-- =============================================
CREATE TABLE IF NOT EXISTS reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    target_id       UUID NOT NULL,
    reviewer        TEXT NOT NULL,
    cadence         TEXT,
    status          TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'in_progress', 'completed', 'skipped')),
    last_reviewed_at TIMESTAMPTZ,
    notes           TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_tenant ON reviews(tenant_id);
CREATE INDEX IF NOT EXISTS idx_reviews_target ON reviews(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews(reviewer);

DROP TRIGGER IF EXISTS trg_reviews_updated_at ON reviews;
CREATE TRIGGER trg_reviews_updated_at
    BEFORE UPDATE ON reviews
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();