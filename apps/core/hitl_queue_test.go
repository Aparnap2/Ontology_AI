package main

import (
	"database/sql"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
	"iterateswarm-core/internal/web"
)

func setupTestAppWithRealHandlers(db *sql.DB) *fiber.App {
	app := fiber.New()
	h := web.NewHandler(db)

	apiGroup := app.Group("/api")
	apiGroup.Get("/hitl/count", h.APIPendingHITL)
	apiGroup.Get("/hitl/queue", h.APIHITLQueue)
	apiGroup.Post("/hitl/:id/approve", h.APIHITLApprove)
	apiGroup.Post("/hitl/:id/reject", h.APIHITLReject)

	// NEW: HTMX screens - will fail until implemented
	apiGroup.Get("/htmx/onboarding", h.APIOnboardingStatus)
	apiGroup.Get("/htmx/watchlist", h.APIWatchlist)
	apiGroup.Get("/htmx/llmops", h.APILLMOpsDashboard)

	return app
}

func readBody(resp *http.Response) string {
	body, _ := io.ReadAll(resp.Body)
	return strings.TrimSpace(string(body))
}

func TestPendingQueueReturnsHTMXPartialOnHXRequest(t *testing.T) {
	app := setupTestAppWithRealHandlers(nil)

	req := httptest.NewRequest("GET", "/api/hitl/queue", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body := readBody(resp)

	if !strings.Contains(body, "HITL-001") {
		t.Errorf("FAIL: Expected HTMX partial with HITL row, got: %q", body)
	}
}

func TestApproveEndpointReturnsPartialForHTMX(t *testing.T) {
	app := setupTestAppWithRealHandlers(nil)

	req := httptest.NewRequest("POST", "/api/hitl/1/approve", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body := readBody(resp)

	if body != "" {
		t.Errorf("FAIL: Expected empty partial for HTMX, got: %q", body)
	}
}

func TestRejectEndpointReturnsPartialForHTMX(t *testing.T) {
	app := setupTestAppWithRealHandlers(nil)

	req := httptest.NewRequest("POST", "/api/hitl/1/reject", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body := readBody(resp)

	if body != "" {
		t.Errorf("FAIL: Expected empty partial for HTMX, got: %q", body)
	}
}

// NEW: HTMX Screen Tests - TDD approach

func TestOnboardingStatusReturnsHTMXPartial(t *testing.T) {
	app := setupTestAppWithRealHandlers(nil)

	req := httptest.NewRequest("GET", "/api/htmx/onboarding", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body := readBody(resp)
	bodyLower := strings.ToLower(body)

	if !strings.Contains(bodyLower, "slack") || !strings.Contains(bodyLower, "connected") {
		t.Errorf("FAIL: Expected onboarding partial with integration status, got: %q", body)
	}
}

func TestWatchlistReturnsHTMXPartial(t *testing.T) {
	app := setupTestAppWithRealHandlers(nil)

	req := httptest.NewRequest("GET", "/api/htmx/watchlist", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body := readBody(resp)
	bodyLower := strings.ToLower(body)

	if !strings.Contains(bodyLower, "alert") || !strings.Contains(bodyLower, "threshold") {
		t.Errorf("FAIL: Expected watchlist partial with alerts, got: %q", body)
	}
}

func TestLLMOpsDashboardReturnsHTMXPartial(t *testing.T) {
	app := setupTestAppWithRealHandlers(nil)

	req := httptest.NewRequest("GET", "/api/htmx/llmops", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body := readBody(resp)
	bodyLower := strings.ToLower(body)

	// Should contain any of these metrics-related keywords
	hasMetric := strings.Contains(bodyLower, "score") || strings.Contains(bodyLower, "rate") || strings.Contains(bodyLower, "quality")
	if !hasMetric {
		t.Errorf("FAIL: Expected llmops partial with metrics, got: %q", body)
	}
}
