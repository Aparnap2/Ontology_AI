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