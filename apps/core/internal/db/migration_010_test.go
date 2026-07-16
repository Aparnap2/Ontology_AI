package db_test

import (
	"database/sql"
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// skipIfNoDB returns a live DB connection, or skips the test when no
// PostgreSQL is reachable so the migration suite skips cleanly in CI
// environments without a database (consistent with the repo's
// "DB tests require PostgreSQL container" note).
func skipIfNoDB(t *testing.T) *sql.DB {
	t.Helper()

	connStr := os.Getenv("TEST_DATABASE_URL")
	if connStr == "" {
		connStr = os.Getenv("DATABASE_URL")
	}
	if connStr == "" {
		connStr = "postgres://iterateswarm:iterateswarm@localhost:5432/iterateswarm?sslmode=disable"
	}

	db, err := sql.Open("postgres", connStr)
	if err != nil {
		t.Skipf("skipping DB test, cannot open connection: %v", err)
		return nil
	}
	if err := db.Ping(); err != nil {
		db.Close()
		t.Skipf("skipping DB test, no live PostgreSQL reachable: %v", err)
		return nil
	}
	return db
}

// columnExists reports whether a column exists on a table.
func columnExists(t *testing.T, db *sql.DB, table, column string) bool {
	t.Helper()
	var exists bool
	err := db.QueryRow(`
		SELECT EXISTS (
			SELECT 1 FROM information_schema.columns
			WHERE table_name = $1 AND column_name = $2
		)`, table, column).Scan(&exists)
	require.NoError(t, err, "failed to check column %s.%s", table, column)
	return exists
}

// tableExists reports whether a table exists.
func tableExists(t *testing.T, db *sql.DB, table string) bool {
	t.Helper()
	var exists bool
	err := db.QueryRow(`
		SELECT EXISTS (
			SELECT 1 FROM information_schema.tables
			WHERE table_name = $1
		)`, table).Scan(&exists)
	require.NoError(t, err, "failed to check table %s", table)
	return exists
}

// TestMigration010NewTablesExist verifies all 7 V5.1 tables exist after migration.
func TestMigration010NewTablesExist(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	newTables := []string{
		"engagement_states",
		"executable_workflow_drafts",
		"workflow_specs",
		"approvals",
		"session_messages",
		"artifact_exports",
		"data_sources",
	}

	for _, table := range newTables {
		assert.True(t, tableExists(t, db, table), "table %q must exist after migration 010", table)
	}
}

// TestMigration010EngagementStatesColumns verifies engagement_states columns (PRD §22.2).
func TestMigration010EngagementStatesColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "workspace_mode",
		"phase", "state", "updated_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "engagement_states", col),
			"engagement_states.%s must exist", col)
	}
}

// TestMigration010ExecutableWorkflowDraftsColumns verifies executable_workflow_drafts columns (PRD §22.4).
func TestMigration010ExecutableWorkflowDraftsColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "runtime", "name",
		"status", "draft", "export_payload", "created_at", "updated_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "executable_workflow_drafts", col),
			"executable_workflow_drafts.%s must exist", col)
	}
}

// TestMigration010WorkflowSpecsColumns verifies workflow_specs columns (PRD §22.3).
func TestMigration010WorkflowSpecsColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "workflow_name",
		"spec", "created_at", "updated_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "workflow_specs", col),
			"workflow_specs.%s must exist", col)
	}
}

// TestMigration010ApprovalsColumns verifies approvals columns (PRD §22.5).
func TestMigration010ApprovalsColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "target_type", "target_id",
		"status", "requested_by", "approved_by", "reason",
		"created_at", "resolved_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "approvals", col),
			"approvals.%s must exist", col)
	}
}

// TestMigration010SessionMessagesColumns verifies session_messages columns (PRD §22.1).
func TestMigration010SessionMessagesColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "role", "content", "created_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "session_messages", col),
			"session_messages.%s must exist", col)
	}
}

// TestMigration010ArtifactExportsColumns verifies artifact_exports columns (PRD §22.6).
func TestMigration010ArtifactExportsColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "artifact_type", "content", "created_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "artifact_exports", col),
			"artifact_exports.%s must exist", col)
	}
}

// TestMigration010DataSourcesColumns verifies data_sources columns (PRD §22.7).
func TestMigration010DataSourcesColumns(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	expected := []string{
		"id", "tenant_id", "engagement_id", "source_type", "source_name",
		"status", "freshness", "metadata", "created_at", "updated_at",
	}
	for _, col := range expected {
		assert.True(t, columnExists(t, db, "data_sources", col),
			"data_sources.%s must exist", col)
	}
}

// TestMigration010PlannedActionsExtended verifies planned_actions gained the new
// V5.1 columns WITHOUT losing the legacy columns used by handler.go.
func TestMigration010PlannedActionsExtended(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	// New V5.1 columns (PRD §12.6 / PLAN §4).
	newCols := []string{
		"engagement_id", "target_type", "target_id",
		"requested_by", "approved_by", "reason",
	}
	for _, col := range newCols {
		assert.True(t, columnExists(t, db, "planned_actions", col),
			"planned_actions.%s must exist after extension", col)
	}

	// Legacy columns that MUST be preserved (handler.go reads these).
	// Reflects the actual planned_actions schema in this repo (009 + 010).
	legacyCols := []string{
		"id", "tenant_id", "action_type", "target_id", "target_type",
		"status", "action_data", "requested_by", "approved_by", "reason",
		"engagement_id", "created_at", "updated_at", "temporal_workflow_id",
	}
	for _, col := range legacyCols {
		assert.True(t, columnExists(t, db, "planned_actions", col),
			"planned_actions.%s must be preserved (legacy)", col)
	}
}

// TestMigration010BridgeAndLegacyPreserved verifies mission_states (bridge) and
// chat_messages (legacy) still exist and were not dropped or altered away.
func TestMigration010BridgeAndLegacyPreserved(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	assert.True(t, tableExists(t, db, "mission_states"),
		"mission_states bridge table must still exist")
	assert.True(t, tableExists(t, db, "chat_messages"),
		"chat_messages legacy table must still exist")

	// mission_states must retain its read path columns.
	for _, col := range []string{"tenant_id", "created_at", "timestamp"} {
		assert.True(t, columnExists(t, db, "mission_states", col),
			"mission_states.%s must be preserved", col)
	}
	// chat_messages must retain its legacy columns.
	for _, col := range []string{"id", "tenant_id", "sender", "message", "created_at"} {
		assert.True(t, columnExists(t, db, "chat_messages", col),
			"chat_messages.%s must be preserved", col)
	}
}

// TestMigration010IndexesExist verifies the key V5.1 indexes were created.
func TestMigration010IndexesExist(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	indexes := []string{
		"idx_engagement_states_tenant",
		"idx_engagement_states_engagement",
		"idx_ewd_engagement_status",
		"idx_approvals_engagement_status",
		"idx_planned_actions_engagement",
		"idx_planned_actions_status_created",
	}
	for _, idx := range indexes {
		var exists bool
		err := db.QueryRow(`SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = $1)`, idx).Scan(&exists)
		require.NoError(t, err)
		assert.True(t, exists, "index %s must exist", idx)
	}
}

// TestMigration010EngagementStateRoundTrip verifies the canonical write target is writable.
func TestMigration010EngagementStateRoundTrip(t *testing.T) {
	db := skipIfNoDB(t)
	defer db.Close()

	engagementID := newUniqueID("eng")
	state := `{"phase":"discovery","workspace_mode":"fde_assisted"}`

	_, err := db.Exec(`
		INSERT INTO engagement_states (tenant_id, engagement_id, workspace_mode, phase, state, updated_at)
		VALUES ($1, $2, $3, $4, $5, NOW())
		ON CONFLICT (engagement_id) DO UPDATE SET state = EXCLUDED.state, updated_at = NOW()
	`, "00000000-0000-0000-0000-000000000001", engagementID, "fde_assisted", "discovery", state)
	require.NoError(t, err, "should be able to write engagement_states")

	var gotPhase, gotMode, gotState string
	err = db.QueryRow(`SELECT phase, workspace_mode, state FROM engagement_states WHERE engagement_id = $1`, engagementID).
		Scan(&gotPhase, &gotMode, &gotState)
	require.NoError(t, err)
	assert.Equal(t, "discovery", gotPhase)
	assert.Equal(t, "fde_assisted", gotMode)
	assert.Contains(t, gotState, "workspace_mode")

	// Cleanup
	_, _ = db.Exec(`DELETE FROM engagement_states WHERE engagement_id = $1`, engagementID)
}

// ensure os import is referenced (skip guard may be the only consumer path).
var _ = os.Getenv
