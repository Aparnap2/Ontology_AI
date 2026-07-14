package db_test

import (
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"testing"
)

// TestMigration003_BiQueriesTableExists verifies bi_queries table was created
func TestMigration003_BiQueriesTableExists(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	var exists bool
	err := db.QueryRow(`
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'bi_queries'
        )
    `).Scan(&exists)

	require.NoError(t, err)
	assert.True(t, exists, "bi_queries table should exist after migration 003")
}

// TestMigration003_VendorBaselinesColumns verifies new columns were added
func TestMigration003_VendorBaselinesColumns(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	// Test avg_30d column
	var avg30dExists bool
	err := db.QueryRow(`
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'vendor_baselines' 
            AND column_name = 'avg_30d'
        )
    `).Scan(&avg30dExists)
	require.NoError(t, err)
	assert.True(t, avg30dExists, "vendor_baselines.avg_30d should exist")

	// Test avg_90d column
	var avg90dExists bool
	err = db.QueryRow(`
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'vendor_baselines' 
            AND column_name = 'avg_90d'
        )
    `).Scan(&avg90dExists)
	require.NoError(t, err)
	assert.True(t, avg90dExists, "vendor_baselines.avg_90d should exist")

	// Test transaction_count column
	var txCountExists bool
	err = db.QueryRow(`
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'vendor_baselines' 
            AND column_name = 'transaction_count'
        )
    `).Scan(&txCountExists)
	require.NoError(t, err)
	assert.True(t, txCountExists, "vendor_baselines.transaction_count should exist")
}

// TestMigration003_AgentOutputsColumns verifies langfuse_trace and anomaly_score were added
func TestMigration003_AgentOutputsColumns(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	var langfuseTraceExists bool
	err := db.QueryRow(`
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'agent_outputs' 
            AND column_name = 'langfuse_trace'
        )
    `).Scan(&langfuseTraceExists)
	require.NoError(t, err)
	assert.True(t, langfuseTraceExists, "agent_outputs.langfuse_trace should exist")

	var anomalyScoreExists bool
	err = db.QueryRow(`
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'agent_outputs' 
            AND column_name = 'anomaly_score'
        )
    `).Scan(&anomalyScoreExists)
	require.NoError(t, err)
	assert.True(t, anomalyScoreExists, "agent_outputs.anomaly_score should exist")
}

// TestMigration003_IndexesCreated verifies performance indexes exist
func TestMigration003_IndexesCreated(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	indexes := []string{
		"idx_bi_queries_tenant",
		"idx_vendor_baselines_tenant_vendor_name",
		"idx_agent_outputs_tenant_agent_name",
	}

	for _, idxName := range indexes {
		var exists bool
		err := db.QueryRow(`
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = $1
            )
        `, idxName).Scan(&exists)

		require.NoError(t, err)
		assert.True(t, exists, "Index %s should exist", idxName)
	}
}

// TestMigration003_InsertBiQuery verifies bi_queries table is writable
func TestMigration003_InsertBiQuery(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	// Generate a UUID for tenant_id
	tenantID := "550e8400-e29b-41d4-a716-446655440000"

	_, err := db.Exec(`
        INSERT INTO bi_queries (tenant_id, query_text, generated_sql, row_count, narrative)
        VALUES ($1, $2, $3, $4, $5)
    `, tenantID, "What was MRR?", "SELECT SUM(amount)...", 1, "MRR was $50k")

	require.NoError(t, err, "Should be able to insert into bi_queries")
}

// TestMigration003_UpdateVendorBaseline verifies vendor_baselines new columns are writable
func TestMigration003_UpdateVendorBaseline(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	// First insert a test row
	_, err := db.Exec(`
        INSERT INTO vendor_baselines (tenant_id, vendor_name, avg_30d, avg_90d, transaction_count)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (tenant_id, vendor_name) DO UPDATE SET
            avg_30d = $3, avg_90d = $4, transaction_count = $5
    `, "test-tenant", "AWS", 18000.0, 18500.0, 12)

	require.NoError(t, err, "Should be able to insert/update vendor_baselines with new columns")

	// Verify the values were stored
	var avg30d, avg90d float64
	var txCount int
	err = db.QueryRow(`
        SELECT avg_30d, avg_90d, transaction_count 
        FROM vendor_baselines 
        WHERE tenant_id = 'test-tenant' AND vendor_name = 'AWS'
    `).Scan(&avg30d, &avg90d, &txCount)

	require.NoError(t, err)
	assert.Equal(t, 18000.0, avg30d)
	assert.Equal(t, 18500.0, avg90d)
	assert.Equal(t, 12, txCount)
}
