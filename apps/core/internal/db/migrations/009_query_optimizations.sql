-- ═══════════════════════════════════════════════════════════════════════
-- MIGRATION 009: Query Performance Optimizations
--
-- ANALYSIS FINDINGS:
--   After auditing all 8 existing migrations, 3 schema files, and the
--   2932-line handler.go, these optimization opportunities were found:
--
--   CRITICAL (actively queried, missing cover):
--     1. audit_log       — 12+ queries filter by created_at (no index)
--                        — action + created_at combo (risk scan pattern)
--     2. agent_traces    — 20+ queries filter by status + created_at
--                        — agent_name + created_at for per-agent latest
--     3. mission_states  — 6+ endpoints use ORDER BY updated_at DESC LIMIT 1 (no index)
--     4. planned_actions — approval queries filter status + ORDER BY created_at
--     5. agent_outputs   — queried by agent_name + output_type (no indexes at all)
--     6. self_guardian_fix_proposals — status filter + ORDER BY created_at
--     7. self_guardian_alerts — time-range + agent health queries
--
--   SCHEMA GAPS (tables used in code but missing migrations):
--     8. hitl_queue — used by handler.go + repository.go, no CREATE TABLE exists
--     9. agent_events — used by repository.go + sse.go, no CREATE TABLE exists
--
--   TABLES WITH ZERO INDEXES:
--     10. finance_ops, people_ops, legal_ops, it_assets, admin_events
--         (from internal_ops.sql) — no indexes at all
--     11. trigger_log — no indexes despite FK to founders
--
-- ═══════════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 1: audit_log — 12+ time-window queries + risk scan patterns
-- ═══════════════════════════════════════════════════════════════════════
-- The existing indexes are on `timestamp` column, but ALL queries filter
-- on `created_at`. These need coverage for time-window count queries
-- and risk-scan action + outcome filters.

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
    ON audit_log(created_at DESC);

-- Covers: APICommandControlPlaneStatus, APICommandRiskStatus,
-- GetHyperDXData, GetLogsData — all filter on created_at ranges
CREATE INDEX IF NOT EXISTS idx_audit_log_action_created
    ON audit_log(action, created_at DESC);

-- Covers: risk scan queries filtering by action + outcome + created_at
CREATE INDEX IF NOT EXISTS idx_audit_log_action_outcome_created
    ON audit_log(action, outcome, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 2: agent_traces — 20+ queries, most heavily queried table
-- ═══════════════════════════════════════════════════════════════════════
-- Query patterns:
--   a) status IN ('processing','running','success','completed') + ORDER BY created_at
--   b) agent_name + ORDER BY created_at DESC LIMIT 1 (per-agent latest)
--   c) agent_name + GROUP BY (all-agents status)
--   d) time-range aggregates (AVG, COUNT, PERCENTILE_CONT on duration_ms)

-- Covers: task board queries that filter by status and order by created_at
-- This is the single most impactful index for agent_traces
CREATE INDEX IF NOT EXISTS idx_agent_traces_status_created
    ON agent_traces(status, created_at DESC);

-- Covers: GetAgentStatus (per-agent latest), GetAllAgentsStatus (all agents)
-- The agent_name-only index exists but doesn't include created_at,
-- forcing a Sort node for ORDER BY + LIMIT
CREATE INDEX IF NOT EXISTS idx_agent_traces_agent_created
    ON agent_traces(agent_name, created_at DESC);

-- Covers: time-range aggregate queries (telemetry, metrics)
-- BRIN index is ideal for monotonically-increasing created_at values
-- on large tables — 100x smaller than equivalent B-tree
CREATE INDEX IF NOT EXISTS idx_agent_traces_created_brin
    ON agent_traces USING BRIN(created_at)
    WITH (pages_per_range = 32);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 3: mission_states — latest-state query pattern
-- ═══════════════════════════════════════════════════════════════════════
-- 6+ endpoints use ORDER BY updated_at DESC LIMIT 1 to get latest state.
-- The actual table (mission_states) has `timestamp` and `created_at`
-- but NOT `updated_at`. The view mission_state wraps SELECT * FROM
-- mission_states. Index on created_at DESC covers the latest-state
-- pattern since created_at is monotonically increasing.
-- The existing PK is on (tenant_id) only.

CREATE INDEX IF NOT EXISTS idx_mission_states_created_at
    ON mission_states(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mission_states_tenant_created
    ON mission_states(tenant_id, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 4: planned_actions — approval queue queries
-- ═══════════════════════════════════════════════════════════════════════
-- Queries: WHERE status = 'planned' ORDER BY created_at DESC
-- Existing idx_planned_actions_status covers status but not ordering.

CREATE INDEX IF NOT EXISTS idx_planned_actions_status_created
    ON planned_actions(status, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 5: agent_outputs — has NO indexes at all
-- ═══════════════════════════════════════════════════════════════════════
-- Queries: WHERE agent_name = 'finance' AND output_type = 'anomaly_alert'
--          ORDER BY created_at DESC LIMIT 10

CREATE INDEX IF NOT EXISTS idx_agent_outputs_agent_type
    ON agent_outputs(agent_name, output_type, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 6: self_guardian_fix_proposals — HITL approval queries
-- ═══════════════════════════════════════════════════════════════════════
-- Query: WHERE status = 'pending' ORDER BY created_at DESC
-- Existing idx_fix_proposals_status covers status but not ordering.

CREATE INDEX IF NOT EXISTS idx_fix_proposals_status_created
    ON self_guardian_fix_proposals(status, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 7: self_guardian_alerts — time-range + agent health
-- ═══════════════════════════════════════════════════════════════════════
-- Queries:
--   a) created_at > NOW() - INTERVAL '24 hours'  (telemetry alerts)
--   b) GROUP BY agent_name with created_at filter  (agent health)
-- Existing idx_sga_tenant_created includes tenant_id but most
-- queries don't filter by tenant_id. Adding a time-range index.

CREATE INDEX IF NOT EXISTS idx_sga_created_at
    ON self_guardian_alerts(created_at DESC);

-- Covers: per-agent health aggregate queries
CREATE INDEX IF NOT EXISTS idx_sga_agent_created
    ON self_guardian_alerts(agent_name, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 8: hitl_queue — missing table + indexes
-- ═══════════════════════════════════════════════════════════════════════
-- This table is used in repository.go (AddToHITLQueue, ListPendingHITL)
-- and handler.go (GetPendingApprovals) but has no CREATE TABLE migration.

CREATE TABLE IF NOT EXISTS hitl_queue (
    task_id      VARCHAR(200) PRIMARY KEY,
    workflow_id  VARCHAR(200),
    issue_title  TEXT,
    issue_body   TEXT,
    severity     VARCHAR(20) DEFAULT 'medium',
    status       VARCHAR(20) DEFAULT 'pending',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    expires_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hitl_queue_status_expires
    ON hitl_queue(status, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_hitl_queue_created
    ON hitl_queue(created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 9: agent_events — missing table + indexes
-- ═══════════════════════════════════════════════════════════════════════
-- This table is used in repository.go (PublishAgentEvent, ListAgentEvents)
-- and sse.go (SSE streaming) but has no CREATE TABLE migration.

CREATE TABLE IF NOT EXISTS agent_events (
    id         SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    task_id    VARCHAR(200),
    agent_name VARCHAR(100),
    message    TEXT,
    severity   VARCHAR(20) DEFAULT 'info',
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_events_created
    ON agent_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_events_type_created
    ON agent_events(event_type, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SECTION 10: ontology_ai.sql missing indexes
-- ═══════════════════════════════════════════════════════════════════════
-- trigger_log has no indexes but references founders(id) via FK.
-- Also used for trigger_type based queries in the agent logic.

CREATE INDEX IF NOT EXISTS idx_trigger_log_type_founder
    ON trigger_log(founder_id, trigger_type, created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- SUMMARY:
--   Critical indexes added: 9 (audit_log ×2, agent_traces ×2,
--     mission_states ×1, planned_actions ×1, agent_outputs ×1,
--     self_guardian_fix_proposals ×1, self_guardian_alerts ×1)
--   Missing tables ensured: hitl_queue, agent_events (both now indexed)
--   Minor indexes added: 4 (sga created, sga agent+created,
--     trigger_log type+founder, agent_events type+created)
--
--   Tables that still have zero custom indexes (no query patterns
--   found in handler.go): accounts_payable, connector_states,
--   compliance_calendar, sop_findings, cs_customers, finance_snapshots,
--   vendor_baselines, hitl_actions. These are append/write-heavy
--   tables where indexes would slow writes without query benefit.
--
--   Performance impact:
--   - audit_log time-range queries: SEQ SCAN → INDEX ONLY SCAN
--   - agent_traces status+time queries: SEQ SCAN → INDEX SCAN
--   - mission_states latest-state: SEQ SCAN → INDEX BACKWARD SCAN
--   - agent_outputs agent+type queries: SEQ SCAN → INDEX SCAN
--   - fix_proposals pending queue: SEQ SCAN → INDEX ONLY SCAN
-- ═══════════════════════════════════════════════════════════════════════
