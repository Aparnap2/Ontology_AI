package db

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// ═══════════════════════════════════════════════════════════════════════
// OntologyAI V5.1 persistence accessors (PRD §22, PLAN §4).
//
// Typed structs + minimal query helpers for the 7 new V5.1 tables and the
// extended planned_actions read path. Uses database/sql with the existing
// *sql.DB held by Repository (consistent with repository.go). All helpers
// are context-first and return deterministic errors on scan failure.
//
// This file does NOT modify handler.go, templates, or any Python code.
// ═══════════════════════════════════════════════════════════════════════

// ── Typed structs ────────────────────────────────────────────────────────

// EngagementState is the canonical write target (PRD §22.2).
type EngagementState struct {
	ID            uuid.UUID       `json:"id"`
	TenantID      uuid.UUID       `json:"tenant_id"`
	EngagementID  string          `json:"engagement_id"`
	WorkspaceMode string          `json:"workspace_mode"`
	Phase         string          `json:"phase"`
	State         json.RawMessage `json:"state"`
	UpdatedAt     time.Time       `json:"updated_at"`
}

// ExecutableWorkflowDraft maps executable_workflow_drafts (PRD §22.4).
type ExecutableWorkflowDraft struct {
	ID            uuid.UUID       `json:"id"`
	TenantID      uuid.UUID       `json:"tenant_id"`
	EngagementID  string          `json:"engagement_id"`
	Runtime       string          `json:"runtime"`
	Name          string          `json:"name"`
	Status        string          `json:"status"`
	Draft         json.RawMessage `json:"draft"`
	ExportPayload json.RawMessage `json:"export_payload"`
	CreatedAt     time.Time       `json:"created_at"`
	UpdatedAt     time.Time       `json:"updated_at"`
}

// WorkflowSpec maps workflow_specs (PRD §22.3).
type WorkflowSpec struct {
	ID           uuid.UUID       `json:"id"`
	TenantID     uuid.UUID       `json:"tenant_id"`
	EngagementID string          `json:"engagement_id"`
	WorkflowName string          `json:"workflow_name"`
	Spec         json.RawMessage `json:"spec"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

// Approval maps approvals (PRD §22.5).
type Approval struct {
	ID           uuid.UUID `json:"id"`
	TenantID     uuid.UUID `json:"tenant_id"`
	EngagementID string    `json:"engagement_id"`
	TargetType   string    `json:"target_type"`
	TargetID     string    `json:"target_id"`
	Status       string    `json:"status"`
	RequestedBy  string    `json:"requested_by"`
	ApprovedBy   string    `json:"approved_by"`
	Reason       string    `json:"reason"`
	CreatedAt    time.Time `json:"created_at"`
	ResolvedAt   time.Time `json:"resolved_at"`
}

// SessionMessage maps session_messages (PRD §22.1).
type SessionMessage struct {
	ID           uuid.UUID `json:"id"`
	TenantID     uuid.UUID `json:"tenant_id"`
	EngagementID string    `json:"engagement_id"`
	Role         string    `json:"role"`
	Content      string    `json:"content"`
	CreatedAt    time.Time `json:"created_at"`
}

// ArtifactExport maps artifact_exports (PRD §22.6).
type ArtifactExport struct {
	ID           uuid.UUID       `json:"id"`
	TenantID     uuid.UUID       `json:"tenant_id"`
	EngagementID string          `json:"engagement_id"`
	ArtifactType string          `json:"artifact_type"`
	Content      json.RawMessage `json:"content"`
	CreatedAt    time.Time       `json:"created_at"`
}

// DataSource maps data_sources (PRD §22.7).
type DataSource struct {
	ID           uuid.UUID       `json:"id"`
	TenantID     uuid.UUID       `json:"tenant_id"`
	EngagementID string          `json:"engagement_id"`
	SourceType   string          `json:"source_type"`
	SourceName   string          `json:"source_name"`
	Status       string          `json:"status"`
	Freshness    json.RawMessage `json:"freshness"`
	Metadata     json.RawMessage `json:"metadata"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

// PlannedActionExtended is the V5.1-extended read shape of planned_actions.
// It preserves all legacy columns used by handler.go (Actor, ActionType,
// TargetRef, RiskLevel, RequiresApproval, Status, TemporalWorkflowID,
// CreatedAt, ExecutedAt, Error) and adds the new engagement-scoped fields.
type PlannedActionExtended struct {
	ID                 uuid.UUID `json:"id"`
	TenantID           string    `json:"tenant_id"`
	Actor              string    `json:"actor"`
	ActionType         string    `json:"action_type"`
	TargetRef          string    `json:"target_ref"`
	RiskLevel          string    `json:"risk_level"`
	RequiresApproval   bool      `json:"requires_approval"`
	ApprovalReason     string    `json:"approval_reason"`
	Status             string    `json:"status"`
	CreatedAt          time.Time `json:"created_at"`
	ExecutedAt         time.Time `json:"executed_at"`
	Error              string    `json:"error"`
	TemporalWorkflowID string    `json:"temporal_workflow_id"`
	EngagementID       string    `json:"engagement_id"`
	TargetType         string    `json:"target_type"`
	TargetID           string    `json:"target_id"`
	RequestedBy        string    `json:"requested_by"`
	ApprovedBy         string    `json:"approved_by"`
	Reason             string    `json:"reason"`
}

// ── engagement_states ─────────────────────────────────────────────────────

// UpsertEngagementState writes (insert or update) the canonical engagement state.
// engagement_id is UNIQUE, so this is idempotent per engagement.
func (r *Repository) UpsertEngagementState(ctx context.Context, es EngagementState) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO engagement_states
			(id, tenant_id, engagement_id, workspace_mode, phase, state, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, NOW())
		ON CONFLICT (engagement_id) DO UPDATE SET
			tenant_id = EXCLUDED.tenant_id,
			workspace_mode = EXCLUDED.workspace_mode,
			phase = EXCLUDED.phase,
			state = EXCLUDED.state,
			updated_at = NOW()
	`
	_, err := r.db.ExecContext(ctx, query,
		es.ID, es.TenantID, es.EngagementID, es.WorkspaceMode, es.Phase, es.State)
	if err != nil {
		return fmt.Errorf("failed to upsert engagement_state: %w", err)
	}
	return nil
}

// GetEngagementState reads the canonical state for an engagement.
func (r *Repository) GetEngagementState(ctx context.Context, engagementID string) (*EngagementState, error) {
	if r.db == nil {
		return nil, fmt.Errorf("no database connection configured")
	}
	query := `
		SELECT id, tenant_id, engagement_id, workspace_mode, phase, state, updated_at
		FROM engagement_states
		WHERE engagement_id = $1
	`
	var es EngagementState
	err := r.db.QueryRowContext(ctx, query, engagementID).Scan(
		&es.ID, &es.TenantID, &es.EngagementID, &es.WorkspaceMode, &es.Phase, &es.State, &es.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get engagement_state: %w", err)
	}
	return &es, nil
}

// ── executable_workflow_drafts ───────────────────────────────────────────

// InsertExecutableWorkflowDraft writes a new draft row.
func (r *Repository) InsertExecutableWorkflowDraft(ctx context.Context, d ExecutableWorkflowDraft) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO executable_workflow_drafts
			(id, tenant_id, engagement_id, runtime, name, status, draft, export_payload, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
	`
	_, err := r.db.ExecContext(ctx, query,
		d.ID, d.TenantID, d.EngagementID, d.Runtime, d.Name, d.Status, d.Draft, d.ExportPayload)
	if err != nil {
		return fmt.Errorf("failed to insert executable_workflow_draft: %w", err)
	}
	return nil
}

// ListExecutableWorkflowDrafts returns drafts for an engagement (optionally filtered by status).
func (r *Repository) ListExecutableWorkflowDrafts(ctx context.Context, engagementID, status string) ([]ExecutableWorkflowDraft, error) {
	if r.db == nil {
		return nil, fmt.Errorf("no database connection configured")
	}
	query := `
		SELECT id, tenant_id, engagement_id, runtime, name, status, draft, export_payload, created_at, updated_at
		FROM executable_workflow_drafts
		WHERE engagement_id = $1
	`
	args := []interface{}{engagementID}
	if status != "" {
		query += " AND status = $2"
		args = append(args, status)
	}
	query += " ORDER BY created_at DESC"

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list executable_workflow_drafts: %w", err)
	}
	defer rows.Close()

	var out []ExecutableWorkflowDraft
	for rows.Next() {
		var d ExecutableWorkflowDraft
		if err := rows.Scan(&d.ID, &d.TenantID, &d.EngagementID, &d.Runtime, &d.Name,
			&d.Status, &d.Draft, &d.ExportPayload, &d.CreatedAt, &d.UpdatedAt); err != nil {
			return nil, fmt.Errorf("failed to scan executable_workflow_draft: %w", err)
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

// ── workflow_specs ────────────────────────────────────────────────────────

// InsertWorkflowSpec writes a new workflow spec row.
func (r *Repository) InsertWorkflowSpec(ctx context.Context, s WorkflowSpec) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO workflow_specs
			(id, tenant_id, engagement_id, workflow_name, spec, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
	`
	_, err := r.db.ExecContext(ctx, query,
		s.ID, s.TenantID, s.EngagementID, s.WorkflowName, s.Spec)
	if err != nil {
		return fmt.Errorf("failed to insert workflow_spec: %w", err)
	}
	return nil
}

// ── approvals ─────────────────────────────────────────────────────────────

// InsertApproval writes a new approval request row.
func (r *Repository) InsertApproval(ctx context.Context, a Approval) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO approvals
			(id, tenant_id, engagement_id, target_type, target_id, status, requested_by, approved_by, reason, created_at, resolved_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, NULLIF($8, ''), NULLIF($9, ''), NOW(), NULL)
	`
	_, err := r.db.ExecContext(ctx, query,
		a.ID, a.TenantID, a.EngagementID, a.TargetType, a.TargetID, a.Status, a.RequestedBy, a.ApprovedBy, a.Reason)
	if err != nil {
		return fmt.Errorf("failed to insert approval: %w", err)
	}
	return nil
}

// ListApprovals returns approvals for an engagement (optionally filtered by status).
func (r *Repository) ListApprovals(ctx context.Context, engagementID, status string) ([]Approval, error) {
	if r.db == nil {
		return nil, fmt.Errorf("no database connection configured")
	}
	query := `
		SELECT id, tenant_id, engagement_id, target_type, target_id, status, requested_by, approved_by, reason, created_at, resolved_at
		FROM approvals
		WHERE engagement_id = $1
	`
	args := []interface{}{engagementID}
	if status != "" {
		query += " AND status = $2"
		args = append(args, status)
	}
	query += " ORDER BY created_at DESC"

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list approvals: %w", err)
	}
	defer rows.Close()

	var out []Approval
	for rows.Next() {
		var a Approval
		var approvedBy, reason sql.NullString
		var resolvedAt sql.NullTime
		if err := rows.Scan(&a.ID, &a.TenantID, &a.EngagementID, &a.TargetType, &a.TargetID,
			&a.Status, &a.RequestedBy, &approvedBy, &reason, &a.CreatedAt, &resolvedAt); err != nil {
			return nil, fmt.Errorf("failed to scan approval: %w", err)
		}
		a.ApprovedBy = approvedBy.String
		a.Reason = reason.String
		a.ResolvedAt = resolvedAt.Time
		out = append(out, a)
	}
	return out, rows.Err()
}

// ── session_messages ──────────────────────────────────────────────────────

// InsertSessionMessage writes a new session message (distinct from legacy chat_messages).
func (r *Repository) InsertSessionMessage(ctx context.Context, m SessionMessage) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO session_messages
			(id, tenant_id, engagement_id, role, content, created_at)
		VALUES ($1, $2, $3, $4, $5, NOW())
	`
	_, err := r.db.ExecContext(ctx, query,
		m.ID, m.TenantID, m.EngagementID, m.Role, m.Content)
	if err != nil {
		return fmt.Errorf("failed to insert session_message: %w", err)
	}
	return nil
}

// ListSessionMessages returns messages for an engagement ordered oldest-first.
func (r *Repository) ListSessionMessages(ctx context.Context, engagementID string, limit int) ([]SessionMessage, error) {
	if r.db == nil {
		return nil, fmt.Errorf("no database connection configured")
	}
	if limit <= 0 || limit > 1000 {
		limit = 200
	}
	query := `
		SELECT id, tenant_id, engagement_id, role, content, created_at
		FROM session_messages
		WHERE engagement_id = $1
		ORDER BY created_at ASC
		LIMIT $2
	`
	rows, err := r.db.QueryContext(ctx, query, engagementID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list session_messages: %w", err)
	}
	defer rows.Close()

	var out []SessionMessage
	for rows.Next() {
		var m SessionMessage
		if err := rows.Scan(&m.ID, &m.TenantID, &m.EngagementID, &m.Role, &m.Content, &m.CreatedAt); err != nil {
			return nil, fmt.Errorf("failed to scan session_message: %w", err)
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// ── artifact_exports ──────────────────────────────────────────────────────

// InsertArtifactExport writes a new artifact export row.
func (r *Repository) InsertArtifactExport(ctx context.Context, a ArtifactExport) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO artifact_exports
			(id, tenant_id, engagement_id, artifact_type, content, created_at)
		VALUES ($1, $2, $3, $4, $5, NOW())
	`
	_, err := r.db.ExecContext(ctx, query,
		a.ID, a.TenantID, a.EngagementID, a.ArtifactType, a.Content)
	if err != nil {
		return fmt.Errorf("failed to insert artifact_export: %w", err)
	}
	return nil
}

// ── data_sources ──────────────────────────────────────────────────────────

// UpsertDataSource writes (insert or update) a data source row by (engagement_id, source_name).
func (r *Repository) UpsertDataSource(ctx context.Context, d DataSource) error {
	if r.db == nil {
		return fmt.Errorf("no database connection configured")
	}
	query := `
		INSERT INTO data_sources
			(id, tenant_id, engagement_id, source_type, source_name, status, freshness, metadata, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
		ON CONFLICT (id) DO UPDATE SET
			tenant_id = EXCLUDED.tenant_id,
			engagement_id = EXCLUDED.engagement_id,
			source_type = EXCLUDED.source_type,
			source_name = EXCLUDED.source_name,
			status = EXCLUDED.status,
			freshness = EXCLUDED.freshness,
			metadata = EXCLUDED.metadata,
			updated_at = NOW()
	`
	_, err := r.db.ExecContext(ctx, query,
		d.ID, d.TenantID, d.EngagementID, d.SourceType, d.SourceName, d.Status, d.Freshness, d.Metadata)
	if err != nil {
		return fmt.Errorf("failed to upsert data_source: %w", err)
	}
	return nil
}

// ── planned_actions (extended read) ──────────────────────────────────────

// GetPlannedActionExtended reads the V5.1-extended planned_actions row by ID.
// Preserves all legacy columns and surfaces the new engagement-scoped fields.
func (r *Repository) GetPlannedActionExtended(ctx context.Context, id uuid.UUID) (*PlannedActionExtended, error) {
	if r.db == nil {
		return nil, fmt.Errorf("no database connection configured")
	}
	query := `
		SELECT id, tenant_id, actor, action_type, target_ref, risk_level,
		       requires_approval, approval_reason, status, created_at, executed_at, error,
		       temporal_workflow_id, engagement_id, target_type, target_id,
		       requested_by, approved_by, reason
		FROM planned_actions
		WHERE id = $1
	`
	var pa PlannedActionExtended
	var tenantID sql.NullString
	var actor, actionType, targetRef, riskLevel, approvalReason, status, errorStr, twID sql.NullString
	var requiresApproval sql.NullBool
	var createdAt, executedAt sql.NullTime
	var engagementID, targetType, targetID, requestedBy, approvedBy, reason sql.NullString

	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&pa.ID, &tenantID, &actor, &actionType, &targetRef, &riskLevel,
		&requiresApproval, &approvalReason, &status, &createdAt, &executedAt, &errorStr,
		&twID, &engagementID, &targetType, &targetID, &requestedBy, &approvedBy, &reason)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get planned_action: %w", err)
	}

	pa.TenantID = tenantID.String
	pa.Actor = actor.String
	pa.ActionType = actionType.String
	pa.TargetRef = targetRef.String
	pa.RiskLevel = riskLevel.String
	pa.RequiresApproval = requiresApproval.Bool
	pa.ApprovalReason = approvalReason.String
	pa.Status = status.String
	pa.CreatedAt = createdAt.Time
	pa.ExecutedAt = executedAt.Time
	pa.Error = errorStr.String
	pa.TemporalWorkflowID = twID.String
	pa.EngagementID = engagementID.String
	pa.TargetType = targetType.String
	pa.TargetID = targetID.String
	pa.RequestedBy = requestedBy.String
	pa.ApprovedBy = approvedBy.String
	pa.Reason = reason.String
	return &pa, nil
}
