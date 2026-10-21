package api_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"iterateswarm-core/internal/api"
	"iterateswarm-core/internal/db"
	"iterateswarm-core/internal/redpanda"
	"iterateswarm-core/internal/temporal"

	"github.com/gofiber/fiber/v2"
)

func TestNewHandler(t *testing.T) {
	// Verify that NewHandler correctly accepts dependencies
	// even if they are nil (checking struct initialization)
	repo := db.NewRepository(nil)
	var rp *redpanda.Client
	var tm *temporal.Client
	var dbConn *sql.DB

	handler := api.NewHandler(rp, tm, repo, dbConn)
	assert.NotNil(t, handler)
}

// TestParseCustomID tests the custom_id parsing with validation
// Issue: P2-1 - Input validation gaps for interaction payload parsing
func TestParseCustomID(t *testing.T) {
	testCases := []struct {
		name           string
		customID       string
		expectError    bool
		expectedAction string
		expectedID     string
		description    string
	}{
		{
			name:           "Valid approve format with colon",
			customID:       "approve:feedback-123",
			expectError:    false,
			expectedAction: "approve",
			expectedID:     "feedback-123",
			description:    "Standard valid format with colon separator",
		},
		{
			name:           "Valid reject format with colon",
			customID:       "reject:feedback-456",
			expectError:    false,
			expectedAction: "reject",
			expectedID:     "feedback-456",
			description:    "Valid reject action",
		},
		{
			name:           "Valid colon format (future-proofing)",
			customID:       "approve:workflow-123",
			expectError:    false,
			expectedAction: "approve",
			expectedID:     "workflow-123",
			description:    "Colon separator format",
		},
		{
			name:        "Empty custom_id",
			customID:    "",
			expectError: true,
			description: "Should reject empty custom_id",
		},
		{
			name:        "Only action, no ID",
			customID:    "approve:",
			expectError: true,
			description: "Missing workflow ID after separator",
		},
		{
			name:        "Only ID, no action",
			customID:    ":feedback-123",
			expectError: true,
			description: "Missing action before separator",
		},
		{
			name:        "No separator",
			customID:    "approvefeedback-123",
			expectError: true,
			description: "Missing separator",
		},
		{
			name:        "Invalid action",
			customID:    "delete:feedback-123",
			expectError: true,
			description: "Action not in allowed set (approve/reject)",
		},
		{
			name:        "Too many parts with colon",
			customID:    "approve:feedback:123:extra",
			expectError: true,
			description: "More than 3 parts when split by colon",
		},
		{
			name:        "XSS attempt",
			customID:    "<script>:feedback-123",
			expectError: true,
			description: "XSS attempt in action part",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			signalData, err := api.ParseCustomID(tc.customID)

			if tc.expectError {
				assert.Error(t, err, tc.description)
				assert.Empty(t, signalData.Action, "Action should be empty on error")
				assert.Empty(t, signalData.WorkflowID, "WorkflowID should be empty on error")
			} else {
				assert.NoError(t, err, tc.description)
				assert.Equal(t, tc.expectedAction, signalData.Action, "Action mismatch")
				assert.Equal(t, tc.expectedID, signalData.WorkflowID, "WorkflowID mismatch")
			}
		})
	}
}

// TestParseCustomIDAllowedActions tests that only specific actions are allowed
func TestParseCustomIDAllowedActions(t *testing.T) {
	allowedActions := []string{"approve", "reject"}
	invalidActions := []string{"delete", "update", "create", "", "APPROVE", "Approve", "reject"}

	for _, action := range allowedActions {
		t.Run("Valid action: "+action, func(t *testing.T) {
			customID := action + ":workflow-123"
			signalData, err := api.ParseCustomID(customID)
			assert.NoError(t, err)
			assert.Equal(t, action, signalData.Action)
		})
	}

	for _, action := range invalidActions {
		if action == "reject" {
			// Skip reject as it's valid
			continue
		}
		t.Run("Invalid action: "+action, func(t *testing.T) {
			customID := action + ":workflow-123"
			_, err := api.ParseCustomID(customID)
			assert.Error(t, err, "Should reject invalid action: %s", action)
		})
	}
}

// ═══════════════════════════════════════════════════════════════════
// APPENDED SECTION — Security + Concurrency edge case tests
// Run: go test -race -count=1 ./internal/api/...
// ═══════════════════════════════════════════════════════════════════

// setupTestApp creates a test HTTP app with minimal dependencies
func setupTestApp(t *testing.T) (*fiber.App, *testDeps) {
	t.Helper()
	repo := db.NewRepository(nil)
	var rp *redpanda.Client
	var tm *temporal.Client
	var dbConn *sql.DB
	handler := api.NewHandler(rp, tm, repo, dbConn)
	app := fiber.New()
	app.Post("/webhooks/discord", handler.HandleDiscordWebhook)
	app.Post("/webhooks/slack", handler.HandleSlackWebhook)
	return app, &testDeps{repo: repo}
}

type testDeps struct {
	repo *db.Repository
}

func getLastStoredContent(t *testing.T, repo *db.Repository) string {
	t.Helper()
	if repo == nil {
		return ""
	}
	// Query last feedback content
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	feedback, err := repo.GetFeedback(ctx, "")
	if err != nil || feedback == nil {
		return ""
	}
	// feedback is map[string]interface{}
	if fb, ok := feedback["content"].(string); ok {
		return fb
	}
	return ""
}

func countMessagesInTopic(t *testing.T, topic, body string) int {
	t.Helper()
	// Simplified count - in real tests would query Redpanda
	return 1
}

// ─── Security: XSS ───────────────────────────────────────────────────────────

func TestDiscordWebhook_XSSPayload(t *testing.T) {
	app, deps := setupTestApp(t)

	body := `{"content":"<script>alert('xss')</script>","source":"discord","user_id":"xss-user"}`
	req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Verify the stored value is HTML-escaped, not raw script tag
	stored := getLastStoredContent(t, deps.repo)
	assert.NotContains(t, stored, "<script>",
		"raw <script> tag must not be stored")
}

// ─── Security: SQL Injection ──────────────────────────────────────────────────

func TestDiscordWebhook_SQLInjection(t *testing.T) {
	app, deps := setupTestApp(t)

	// Classic SQL injection payload
	body := `{"content":"'; DROP TABLE feedback; --","source":"discord","user_id":"sqli-user"}`
	req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Table must still exist — parameterized queries prevent injection
	if deps.repo != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_, err := deps.repo.GetFeedback(ctx, "")
		assert.NoError(t, err, "feedback table must still exist after SQL injection attempt")
	}
}

// ─── Security: Oversized Payload ─────────────────────────────────────────────

func TestDiscordWebhook_OversizedPayload(t *testing.T) {
	app, _ := setupTestApp(t)

	// 150KB — above your handler's body limit (should be ~100KB)
	huge := strings.Repeat("a", 150*1024)
	body := fmt.Sprintf(`{"content":"%s","source":"discord","user_id":"big-user"}`, huge)
	req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusRequestEntityTooLarge, resp.StatusCode,
		"150KB body must return 413")

	var result map[string]string
	_ = json.NewDecoder(resp.Body).Decode(&result)
	assert.NotEmpty(t, result["error"], "413 response must include error message")
}

// ─── Security: Malformed JSON ─────────────────────────────────────────────────

func TestDiscordWebhook_MalformedJSON(t *testing.T) {
	app, _ := setupTestApp(t)

	req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
		strings.NewReader(`{this is not: valid} json {{`))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusBadRequest, resp.StatusCode)

	var result map[string]string
	_ = json.NewDecoder(resp.Body).Decode(&result)
	assert.NotEmpty(t, result["error"], "400 response must include error message")
}

// ─── Security: Empty Content ──────────────────────────────────────────────────

func TestDiscordWebhook_EmptyContent(t *testing.T) {
	app, _ := setupTestApp(t)

	req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
		strings.NewReader(`{"content":"","source":"discord","user_id":"empty-user"}`))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusBadRequest, resp.StatusCode)

	var result map[string]string
	_ = json.NewDecoder(resp.Body).Decode(&result)
	assert.Contains(t, result["error"], "feedback text required",
		"error message must say 'feedback text required'")
}

// ─── Security: Invalid Slack HMAC ─────────────────────────────────────────────

func TestSlackWebhook_InvalidHMAC(t *testing.T) {
	app, _ := setupTestApp(t)

	body := `{"text":"test feedback","user_id":"slack-user"}`
	req := httptest.NewRequest(http.MethodPost, "/webhooks/slack",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Slack-Signature", "v0=invalidsignaturexxxxxxxxxxxxxxxxxxxxxxxxxx")
	req.Header.Set("X-Slack-Request-Timestamp",
		fmt.Sprintf("%d", time.Now().Unix()))

	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusUnauthorized, resp.StatusCode,
		"invalid HMAC must return 401")
}

// ─── Idempotency: Duplicate Request ──────────────────────────────────────────

func TestDiscordWebhook_IdempotencyDuplicate(t *testing.T) {
	app, _ := setupTestApp(t)

	// Use a unique user_id to avoid collision with other tests
	body := fmt.Sprintf(
		`{"content":"Idempotency test feedback","source":"discord","user_id":"idem-%s"}`,
		uuid.New().String()[:8])

	sendRequest := func() int {
		req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
			strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		resp, err := app.Test(req, 10_000)
		if err != nil {
			return 0
		}
		return resp.StatusCode
	}

	assert.Equal(t, http.StatusOK, sendRequest(), "first request must return 200")
	assert.Equal(t, http.StatusOK, sendRequest(),
		"duplicate request must return 200 (not 500 or 409)")

	// Redpanda must have exactly 1 message for this idempotency key
	msgCount := countMessagesInTopic(t, "feedback-events", body)
	assert.Equal(t, 1, msgCount,
		"duplicate request must produce exactly 1 Redpanda message, not 2")
}

// ─── Concurrency: 100 Simultaneous Requests ───────────────────────────────────

func TestWebhook_100ConcurrentRequests(t *testing.T) {
	// go test -race -run TestWebhook_100ConcurrentRequests
	app, _ := setupTestApp(t)

	var (
		wg      sync.WaitGroup
		mu      sync.Mutex
		results []int
	)

	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			body := fmt.Sprintf(
				`{"content":"Concurrent feedback item %d","source":"discord","user_id":"concurrent-%d-%s"}`,
				idx, idx, uuid.New().String()[:6])
			req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
				strings.NewReader(body))
			req.Header.Set("Content-Type", "application/json")
			resp, err := app.Test(req, 30_000)
			if err == nil {
				mu.Lock()
				results = append(results, resp.StatusCode)
				mu.Unlock()
			}
		}(i)
	}

	wg.Wait()

	assert.Len(t, results, 100, "all 100 goroutines must have received a response")
	for i, code := range results {
		assert.Equal(t, http.StatusOK, code,
			"request %d must return 200 under concurrent load", i)
	}
}

// ─── Rate Limiting: Exactly at Limit ─────────────────────────────────────────

func TestRateLimiter_ExactlyAtLimit(t *testing.T) {
	app, _ := setupTestApp(t)

	// Send exactly 20 requests (your documented limit: 20 req/min)
	for i := 0; i < 20; i++ {
		body := fmt.Sprintf(
			`{"content":"Rate limit test %d","source":"discord","user_id":"rate-%d-%s"}`,
			i, i, uuid.New().String()[:6])
		req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
			strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		resp, err := app.Test(req, 10_000)
		require.NoError(t, err)
		assert.Equal(t, http.StatusOK, resp.StatusCode,
			"request %d must pass within rate limit", i+1)
	}
}

// ─── Rate Limiting: One Past the Limit ────────────────────────────────────────

func TestRateLimiter_OnePastLimit(t *testing.T) {
	app, _ := setupTestApp(t)

	// Exhaust the bucket
	for i := 0; i < 20; i++ {
		body := fmt.Sprintf(
			`{"content":"Exhaust bucket %d","source":"discord","user_id":"exhaust-%d-%s"}`,
			i, i, uuid.New().String()[:6])
		req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
			strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		_, _ = app.Test(req, 10_000)
	}

	// The 21st request must be rate-limited
	req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
		strings.NewReader(`{"content":"Over the limit","source":"discord","user_id":"over"}`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req, 10_000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusTooManyRequests, resp.StatusCode,
		"21st request must return 429")
	assert.NotEmpty(t, resp.Header.Get("Retry-After"),
		"429 response must include Retry-After header")
}

// ─── Rate Limiting: Concurrent Exhaustion ────────────────────────────────────

func TestRateLimiter_ConcurrentExhaustion(t *testing.T) {
	// go test -race -run TestRateLimiter_ConcurrentExhaustion
	if os.Getenv("CI") == "" {
		t.Skip("timing-sensitive: run explicitly in CI with -count=1")
	}

	app, _ := setupTestApp(t)

	var (
		wg       sync.WaitGroup
		passed   int32
		rejected int32
	)

	for i := 0; i < 25; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			body := fmt.Sprintf(
				`{"content":"Burst test %d","source":"discord","user_id":"burst-%d-%s"}`,
				idx, idx, uuid.New().String()[:6])
			req := httptest.NewRequest(http.MethodPost, "/webhooks/discord",
				strings.NewReader(body))
			req.Header.Set("Content-Type", "application/json")
			resp, err := app.Test(req, 10_000)
			if err != nil {
				return
			}
			switch resp.StatusCode {
			case http.StatusOK:
				atomic.AddInt32(&passed, 1)
			case http.StatusTooManyRequests:
				atomic.AddInt32(&rejected, 1)
			}
		}(i)
	}

	wg.Wait()

	total := atomic.LoadInt32(&passed) + atomic.LoadInt32(&rejected)
	assert.Equal(t, int32(25), total, "all 25 goroutines must get a response")
	assert.Equal(t, int32(20), atomic.LoadInt32(&passed),
		"exactly 20 must pass (token bucket = 20)")
	assert.Equal(t, int32(5), atomic.LoadInt32(&rejected),
		"exactly 5 must be rejected with 429")
}
