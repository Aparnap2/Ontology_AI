package db_test

import (
	"fmt"
	"testing"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// newUniqueID generates a unique ID for test data to avoid conflicts
func newUniqueID(prefix string) string {
	return fmt.Sprintf("%s_%s", prefix, uuid.New().String()[:8])
}

// newUniqueTenantID generates a unique tenant ID for test data
func newUniqueTenantID() string {
	return newUniqueID("tenant")
}

// expectedTables lists all tables introduced in Migration 002 (TrackGuard v1.0)
var expectedTables = []string{
	"founders",
	"raw_events",
	"transactions",
	"pipeline_deals",
	"cs_customers",
	"employees",
	"finance_snapshots",
	"vendor_baselines",
	"agent_outputs",
	"hitl_actions",
}

// TestMigration002TablesExist verifies all 10 v1.0 tables exist after migration
func TestMigration002TablesExist(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	for _, table := range expectedTables {
		var exists bool
		err := db.QueryRow(`
			SELECT EXISTS (
				SELECT 1 FROM information_schema.tables
				WHERE table_name = $1
			)`, table).Scan(&exists)
		require.NoError(t, err, "Failed to check existence of table %q", table)
		assert.True(t, exists, "table %q must exist after migration 002", table)
	}
}

// TestMigration002IdempotencyKeyUnique tests the unique constraint on raw_events.idempotency_key
func TestMigration002IdempotencyKeyUnique(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	ikey := newUniqueID("idempotency")
	insert := func() error {
		_, err := db.Exec(`
			INSERT INTO raw_events
				(tenant_id, source, event_type, payload_hash,
				 payload_body, idempotency_key)
			VALUES ($1,$2,$3,$4,$5,$6)`,
			newUniqueTenantID(), "razorpay", "PAYMENT_SUCCESS",
			"sha256:abc", `{"amount":5000}`, ikey)
		return err
	}

	// First insert should succeed
	require.NoError(t, insert(), "First insert should succeed")

	// Second insert with same idempotency_key must fail on UNIQUE constraint
	err := insert()
	assert.Error(t, err, "duplicate idempotency_key must be rejected")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002FoundersCRUD tests basic CRUD operations on founders table
// Note: founders table uses slack_user_id as unique key (from migration 001)
// Migration 002 adds telegram_user_id support for multi-tenant scenarios
func TestMigration002FoundersCRUD(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	slackUserID := newUniqueID("slack")
	telegramUserID := newUniqueID("tg")

	// CREATE: Insert a founder with telegram_user_id (migration 002 field)
	_, err := db.Exec(`
		INSERT INTO founders (slack_user_id, telegram_user_id, name, stage)
		VALUES ($1, $2, $3, $4)`,
		slackUserID, telegramUserID, "Test Founder", "prerevenue")
	require.NoError(t, err, "Failed to insert founder")

	// READ: Verify founder was created with telegram_user_id
	var name string
	var stage string
	var retTelegramID string
	err = db.QueryRow(`SELECT name, stage, telegram_user_id FROM founders WHERE slack_user_id = $1`, slackUserID).Scan(&name, &stage, &retTelegramID)
	require.NoError(t, err, "Failed to read founder")
	assert.Equal(t, "Test Founder", name, "Founder name should match")
	assert.Equal(t, "prerevenue", stage, "Founder stage should match")
	assert.Equal(t, telegramUserID, retTelegramID, "Telegram user ID should match")

	// UPDATE: Update founder stage
	var updatedStage string
	err = db.QueryRow(`
		UPDATE founders SET stage = $2 WHERE slack_user_id = $1 RETURNING stage`,
		slackUserID, "building").Scan(&updatedStage)
	require.NoError(t, err, "Failed to update founder")
	assert.Equal(t, "building", updatedStage, "Updated stage should match")

	// UNIQUE slack_user_id constraint: Duplicate slack_user_id should fail
	_, err = db.Exec(`
		INSERT INTO founders (slack_user_id, telegram_user_id, name, stage)
		VALUES ($1, $2, $3, $4)`,
		slackUserID, newUniqueID("tg"), "Duplicate Founder", "prerevenue")
	assert.Error(t, err, "Duplicate slack_user_id should fail unique constraint")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002TransactionsCRUD tests CRUD operations on transactions table
func TestMigration002TransactionsCRUD(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()
	externalID := newUniqueID("txn")

	// CREATE
	_, err := db.Exec(`
		INSERT INTO transactions
			(tenant_id, txn_date, description, debit, credit, category, external_id)
		VALUES ($1, NOW(), $2, $3, $4, $5, $6)`,
		tenantID, "Test transaction", 100.00, 0.00, "revenue", externalID)
	require.NoError(t, err, "Failed to insert transaction")

	// READ
	var debit, credit float64
	err = db.QueryRow(`SELECT debit, credit FROM transactions WHERE tenant_id = $1 AND external_id = $2`, tenantID, externalID).Scan(&debit, &credit)
	require.NoError(t, err, "Failed to read transaction")
	assert.Equal(t, 100.00, debit, "Debit should match")
	assert.Equal(t, 0.00, credit, "Credit should match")

	// UNIQUE constraint on tenant_id + external_id
	_, err = db.Exec(`
		INSERT INTO transactions
			(tenant_id, txn_date, description, debit, credit, external_id)
		VALUES ($1, NOW(), $2, $3, $4, $5)`,
		tenantID, "Duplicate transaction", 200.00, 0.00, externalID)
	assert.Error(t, err, "Duplicate tenant_id + external_id should fail")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002PipelineDealsUnique tests unique constraint on pipeline_deals
func TestMigration002PipelineDealsUnique(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()
	dealID := newUniqueID("deal")

	// First insert should succeed
	_, err := db.Exec(`
		INSERT INTO pipeline_deals (tenant_id, deal_id, name, amount, stage)
		VALUES ($1, $2, $3, $4, $5)`,
		tenantID, dealID, "Test Deal", 50000.00, "qualified")
	require.NoError(t, err, "First insert should succeed")

	// Duplicate tenant_id + deal_id must fail
	_, err = db.Exec(`
		INSERT INTO pipeline_deals (tenant_id, deal_id, name, amount, stage)
		VALUES ($1, $2, $3, $4, $5)`,
		tenantID, dealID, "Duplicate Deal", 60000.00, "proposal")
	assert.Error(t, err, "Duplicate tenant_id + deal_id should fail")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002CsCustomersUnique tests unique constraint on cs_customers
func TestMigration002CsCustomersUnique(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()
	customerID := newUniqueID("customer")

	// First insert should succeed
	_, err := db.Exec(`
		INSERT INTO cs_customers (tenant_id, customer_id, telegram_id, onboarding_stage)
		VALUES ($1, $2, $3, $4)`,
		tenantID, customerID, "tg_123", "WELCOME")
	require.NoError(t, err, "First insert should succeed")

	// Duplicate tenant_id + customer_id must fail
	_, err = db.Exec(`
		INSERT INTO cs_customers (tenant_id, customer_id, telegram_id, onboarding_stage)
		VALUES ($1, $2, $3, $4)`,
		tenantID, customerID, "tg_456", "ONBOARDED")
	assert.Error(t, err, "Duplicate tenant_id + customer_id should fail")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002EmployeesUnique tests unique constraint on employees
func TestMigration002EmployeesUnique(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()
	employeeID := newUniqueID("emp")

	// First insert should succeed
	_, err := db.Exec(`
		INSERT INTO employees (tenant_id, employee_id, name, role_function, status)
		VALUES ($1, $2, $3, $4, $5)`,
		tenantID, employeeID, "John Doe", "engineering", "ONBOARDING")
	require.NoError(t, err, "First insert should succeed")

	// Duplicate tenant_id + employee_id must fail
	_, err = db.Exec(`
		INSERT INTO employees (tenant_id, employee_id, name, role_function, status)
		VALUES ($1, $2, $3, $4, $5)`,
		tenantID, employeeID, "Jane Doe", "sales", "ACTIVE")
	assert.Error(t, err, "Duplicate tenant_id + employee_id should fail")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002VendorBaselinesUnique tests unique constraint on vendor_baselines
func TestMigration002VendorBaselinesUnique(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()
	vendorName := newUniqueID("vendor")

	// First insert should succeed
	_, err := db.Exec(`
		INSERT INTO vendor_baselines (tenant_id, vendor_name, avg_monthly, stddev_monthly)
		VALUES ($1, $2, $3, $4)`,
		tenantID, vendorName, 1000.00, 100.00)
	require.NoError(t, err, "First insert should succeed")

	// Duplicate tenant_id + vendor_name must fail
	_, err = db.Exec(`
		INSERT INTO vendor_baselines (tenant_id, vendor_name, avg_monthly, stddev_monthly)
		VALUES ($1, $2, $3, $4)`,
		tenantID, vendorName, 2000.00, 200.00)
	assert.Error(t, err, "Duplicate tenant_id + vendor_name should fail")
	assert.Contains(t, err.Error(), "duplicate key", "Error should mention duplicate key violation")
}

// TestMigration002RawEventsIndex verifies index on raw_events table
func TestMigration002RawEventsIndex(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	var exists bool
	err := db.QueryRow(`
		SELECT EXISTS (
			SELECT 1 FROM pg_indexes
			WHERE tablename = 'raw_events'
			AND indexname = 'idx_raw_events_tenant_type'
		)`).Scan(&exists)
	require.NoError(t, err, "Failed to check index existence")
	assert.True(t, exists, "idx_raw_events_tenant_type index must exist")
}

// TestMigration002AgentOutputsInsert tests insert into agent_outputs table
func TestMigration002AgentOutputsInsert(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()

	_, err := db.Exec(`
		INSERT INTO agent_outputs
			(tenant_id, agent_name, output_type, headline, urgency, output_json)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		tenantID, "triage_agent", "alert", "Payment anomaly detected", "high", `{"payment_id": "pay_123"}`)
	require.NoError(t, err, "Failed to insert agent output")

	// Verify insert
	var headline string
	var urgency string
	err = db.QueryRow(`SELECT headline, urgency FROM agent_outputs WHERE tenant_id = $1`, tenantID).Scan(&headline, &urgency)
	require.NoError(t, err, "Failed to read agent output")
	assert.Equal(t, "Payment anomaly detected", headline, "Headline should match")
	assert.Equal(t, "high", urgency, "Urgency should match")
}

// TestMigration002HitlActionsInsert tests insert into hitl_actions table
func TestMigration002HitlActionsInsert(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()

	_, err := db.Exec(`
		INSERT INTO hitl_actions
			(tenant_id, agent_name, message_sent, founder_response)
		VALUES ($1, $2, $3, $4)`,
		tenantID, "triage_agent", "Approve this transaction?", "approved")
	require.NoError(t, err, "Failed to insert HITL action")

	// Verify insert
	var messageSent string
	var founderResponse string
	err = db.QueryRow(`SELECT message_sent, founder_response FROM hitl_actions WHERE tenant_id = $1`, tenantID).Scan(&messageSent, &founderResponse)
	require.NoError(t, err, "Failed to read HITL action")
	assert.Equal(t, "Approve this transaction?", messageSent, "Message should match")
	assert.Equal(t, "approved", founderResponse, "Response should match")
}

// TestMigration002FinanceSnapshotsInsert tests insert into finance_snapshots table
func TestMigration002FinanceSnapshotsInsert(t *testing.T) {
	db := getTestDB(t)
	defer db.Close()

	tenantID := newUniqueTenantID()

	_, err := db.Exec(`
		INSERT INTO finance_snapshots
			(tenant_id, snapshot_date, monthly_revenue, monthly_expense, burn_rate, runway_months)
		VALUES ($1, CURRENT_DATE, $2, $3, $4, $5)`,
		tenantID, 50000.00, 30000.00, 20000.00, 6.5)
	require.NoError(t, err, "Failed to insert finance snapshot")

	// Verify insert
	var revenue, expense, burnRate float64
	var runway float64
	err = db.QueryRow(`SELECT monthly_revenue, monthly_expense, burn_rate, runway_months FROM finance_snapshots WHERE tenant_id = $1`, tenantID).Scan(&revenue, &expense, &burnRate, &runway)
	require.NoError(t, err, "Failed to read finance snapshot")
	assert.Equal(t, 50000.00, revenue, "Revenue should match")
	assert.Equal(t, 30000.00, expense, "Expense should match")
	assert.Equal(t, 20000.00, burnRate, "Burn rate should match")
	assert.Equal(t, 6.5, runway, "Runway months should match")
}
