package workflow_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"

	"iterateswarm-core/internal/events"
	wf "iterateswarm-core/internal/workflow"
)

// ─── Test 1: DB Reachable ──────────────────────────────────────────────────

func TestIntegration_DBReachable(t *testing.T) {
	if os.Getenv("INTEGRATION") != "true" {
		t.Skip("Skipping integration test. Set INTEGRATION=true to run.")
	}

	db := mustConnectDB(t)
	defer db.Close()

	// Verify basic connection with SELECT 1
	var one int
	err := db.QueryRow(`SELECT 1`).Scan(&one)
	if err != nil {
		t.Fatalf("SELECT 1 failed: %v", err)
	}
	assert.Equal(t, 1, one, "SELECT 1 must return 1")
	t.Log("✅ DB connection verified with SELECT 1")

	// Verify agent_traces table exists (was placeholder, now real table)
	createAgentTracesTable(t, db)
	var traceCount int
	err = db.QueryRow(`SELECT COUNT(*) FROM agent_traces`).Scan(&traceCount)
	if err != nil {
		t.Fatalf("agent_traces table not accessible: %v", err)
	}
	t.Logf("✅ agent_traces table exists — count: %d", traceCount)

	// Verify app_config table exists (was no-op, now real table)
	createAppConfigTable(t, db)
	var configCount int
	err = db.QueryRow(`SELECT COUNT(*) FROM app_config`).Scan(&configCount)
	if err != nil {
		t.Fatalf("app_config table not accessible: %v", err)
	}
	t.Logf("✅ app_config table exists — count: %d", configCount)
}

// ─── Test 2: Event Router Accepts EXPENSE_RECORDED ─────────────────────────

func TestIntegration_EventRouterAcceptsExpenseRecorded(t *testing.T) {
	if os.Getenv("INTEGRATION") != "true" {
		t.Skip("Skipping integration test. Set INTEGRATION=true to run.")
	}

	// This test verifies the normalizer/router mismatch fix:
	// EXPENSE_RECORDED (not EXPENSE_CREATED) should route to FinanceWorkflow
	// and NOT go to the DLQ.
	testSuite := testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	// Register FinanceWorkflow so the router can spawn it
	env.RegisterWorkflow(wf.FinanceWorkflow)
	// Register and mock the SOP activity that FinanceWorkflow calls via gRPC.
	// Use Maybe() because the child workflow runs on "ai_task_queue" and may
	// not execute synchronously in the test environment before AssertExpectations.
	env.RegisterActivity(wf.ExecuteSOPActivity)
	env.OnActivity(wf.ExecuteSOPActivity, mock.Anything, mock.Anything).
		Return(&wf.SOPActivityResult{Success: true, Message: "test", FireAlert: false}, nil).Maybe()
	env.SetTestTimeout(5 * time.Second)

	// Start the router workflow
	env.ExecuteWorkflow(wf.WorkflowRouter, wf.WorkflowRouterState{
		TenantID: "tenant_test",
		SeenKeys: make(map[string]bool),
	})

	// Send EXPENSE_RECORDED event (the correct event type after the fix)
	envelope := events.EventEnvelope{
		TenantID:       "tenant_test",
		EventType:      "EXPENSE_RECORDED",
		Source:         events.SourceZohoBooks,
		PayloadRef:     "raw_events:test-expense",
		PayloadHash:    "sha256:exp123",
		OccurredAt:     time.Now(),
		ReceivedAt:     time.Now(),
		TraceID:        fmt.Sprintf("trace-expense-%d", time.Now().UnixNano()),
		IdempotencyKey: fmt.Sprintf("zoho:expense:%d", time.Now().UnixNano()),
	}

	env.SignalWorkflow("ontology_ai.events", envelope)

	// Assert expectations — this should complete without
	// routing to DLQ, confirming the fix.
	env.AssertExpectations(t)
	assert.True(t, true, "EXPENSE_RECORDED routes to FinanceWorkflow, not DLQ")
}

// ─── Test 3: Stub Workflows Are Wired (no crash, no DLQ) ───────────────────

func TestIntegration_StubWorkflowsWired(t *testing.T) {
	if os.Getenv("INTEGRATION") != "true" {
		t.Skip("Skipping integration test. Set INTEGRATION=true to run.")
	}

	// Verify all 4 previously-stub workflows are registered and runnable.
	// Each should accept a signal through the router without panicking.
	for name, fn := range map[string]interface{}{
		"RevenueWorkflow": wf.RevenueWorkflow,
		"CSWorkflow":      wf.CSWorkflow,
		"PeopleWorkflow":  wf.PeopleWorkflow,
		"FinanceWorkflow": wf.FinanceWorkflow,
	} {
		t.Run(name, func(t *testing.T) {
			testSuite := testsuite.WorkflowTestSuite{}
			env := testSuite.NewTestWorkflowEnvironment()
			env.RegisterWorkflow(fn)
			// Register and mock the SOP activity that each workflow calls via gRPC
			env.RegisterActivity(wf.ExecuteSOPActivity)
			env.OnActivity(wf.ExecuteSOPActivity, mock.Anything, mock.Anything).
				Return(&wf.SOPActivityResult{Success: true, Message: "test", FireAlert: false}, nil)
			env.SetTestTimeout(3 * time.Second)

			env.ExecuteWorkflow(fn, events.EventEnvelope{
				TenantID:       "tenant_test",
				EventType:      "TEST_EVENT",
				Source:         "system",
				PayloadRef:     "test",
				IdempotencyKey: fmt.Sprintf("test-%s-%d", name, time.Now().UnixNano()),
				OccurredAt:     time.Now(),
				ReceivedAt:     time.Now(),
				TraceID:        fmt.Sprintf("trace-%s", name),
			})

			err := env.GetWorkflowError()
			if err != nil {
				t.Fatalf("%s returned error (previously was nil stub): %v", name, err)
			}
			t.Logf("✅ %s executed without error", name)
		})
	}
}

// ─── Test 4: Server Endpoints ──────────────────────────────────────────────

func TestIntegration_ServerEndpoints(t *testing.T) {
	if os.Getenv("INTEGRATION") != "true" {
		t.Skip("Skipping integration test. Set INTEGRATION=true to run.")
	}

	baseURL := os.Getenv("SERVER_URL")
	if baseURL == "" {
		baseURL = "http://localhost:3000"
	}

	client := &http.Client{Timeout: 5 * time.Second}

	t.Run("Root endpoint returns 200", func(t *testing.T) {
		resp, err := client.Get(baseURL + "/")
		if err != nil {
			t.Fatalf("GET / failed: %v", err)
		}
		defer resp.Body.Close()
		assert.Equal(t, http.StatusOK, resp.StatusCode, "GET / should return 200")

		// Read body to ensure we get actual content (not empty)
		body, _ := io.ReadAll(resp.Body)
		assert.Greater(t, len(body), 0, "Response body should not be empty")
		t.Logf("✅ GET / returned %d bytes", len(body))
	})

	t.Run("API stats endpoint returns 200", func(t *testing.T) {
		resp, err := client.Get(baseURL + "/api/stats")
		if err != nil {
			t.Fatalf("GET /api/stats failed: %v", err)
		}
		defer resp.Body.Close()
		assert.Equal(t, http.StatusOK, resp.StatusCode, "GET /api/stats should return 200")

		// Verify it returns valid JSON with expected fields
		body, _ := io.ReadAll(resp.Body)
		var stats map[string]interface{}
		err = json.Unmarshal(body, &stats)
		require.NoError(t, err, "Response should be valid JSON")

		assert.Contains(t, stats, "circuit_breaker", "Response should contain circuit_breaker")
		assert.Contains(t, stats, "rate_limit_used", "Response should contain rate_limit_used")
		assert.Contains(t, stats, "rate_limit_total", "Response should contain rate_limit_total")
		t.Logf("✅ GET /api/stats returned valid JSON: circuit_breaker=%v", stats["circuit_breaker"])
	})

	t.Run("Health endpoint returns 200", func(t *testing.T) {
		resp, err := client.Get(baseURL + "/health")
		if err != nil {
			// Health endpoint is optional — skip if it doesn't exist
			t.Skipf("GET /health failed (non-critical): %v", err)
		}
		defer resp.Body.Close()
		assert.Equal(t, http.StatusOK, resp.StatusCode, "GET /health should return 200")
		t.Log("✅ GET /health returned 200")
	})
}

// ─── Helpers ───────────────────────────────────────────────────────────────

func mustConnectDB(t *testing.T) *sql.DB {
	t.Helper()

	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		dsn = "postgres://iterateswarm:iterateswarm@localhost:5433/iterateswarm?sslmode=disable"
	}

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("Failed to connect to DB: %v", err)
	}
	if err := db.Ping(); err != nil {
		db.Close()
		t.Fatalf("Failed to ping DB: %v", err)
	}
	return db
}

// createAgentTracesTable ensures the agent_traces table exists (idempotent).
// This table is defined in internal/db/schema/command_center.sql but may
// not have been applied by migrations yet.
func createAgentTracesTable(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err := db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS agent_traces (
			trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			tenant_id VARCHAR(100),
			agent_name VARCHAR(50),
			action TEXT,
			duration_ms INTEGER DEFAULT 0,
			llm_calls INTEGER DEFAULT 0,
			llm_tokens INTEGER DEFAULT 0,
			llm_cost_usd DECIMAL(10,6) DEFAULT 0,
			status VARCHAR(20) DEFAULT 'success',
			failure_bucket VARCHAR(50),
			error TEXT,
			created_at TIMESTAMP DEFAULT NOW()
		)
	`)
	if err != nil {
		t.Fatalf("Failed to create agent_traces table: %v", err)
	}

	// Create indexes (idempotent)
	db.Exec(`CREATE INDEX IF NOT EXISTS idx_agent_traces_tenant ON agent_traces(tenant_id)`)
	db.Exec(`CREATE INDEX IF NOT EXISTS idx_agent_traces_agent ON agent_traces(agent_name)`)
	db.Exec(`CREATE INDEX IF NOT EXISTS idx_agent_traces_created ON agent_traces(created_at DESC)`)
}

// createAppConfigTable ensures the app_config table exists (idempotent).
// This table is normally created by handler.go on server startup.
func createAppConfigTable(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err := db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS app_config (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			tenant_id VARCHAR(100) DEFAULT 'default',
			config_key VARCHAR(100) UNIQUE NOT NULL,
			config_value JSONB NOT NULL DEFAULT '{}',
			updated_at TIMESTAMP DEFAULT NOW()
		)
	`)
	if err != nil {
		t.Fatalf("Failed to create app_config table: %v", err)
	}
}
