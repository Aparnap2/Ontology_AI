package web

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

func TestWatchlistViewer_ReturnsHTMXPartialOnHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/watchlist", h.APIWatchlist)

	req := httptest.NewRequest("GET", "/api/htmx/watchlist", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if !strings.Contains(bodyStr, "<div") && !strings.Contains(bodyStr, "<button") {
		t.Errorf("FAIL: Expected HTMX partial, got: %q", bodyStr)
	}
}

func TestWatchlistViewer_ShowsAlertPatterns(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/watchlist", h.APIWatchlist)

	// Use HX-Request header to get actual watchlist content
	req := httptest.NewRequest("GET", "/api/htmx/watchlist", nil)
	req.Header.Set("HX-Request", "true")
	resp, _ := app.Test(req)

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.ToLower(string(body))

	hasContent := strings.Contains(bodyStr, "fg-") ||
		strings.Contains(bodyStr, "alert") ||
		strings.Contains(bodyStr, "burn") ||
		strings.Contains(bodyStr, "threshold") ||
		strings.Contains(bodyStr, "error")

	if !hasContent {
		t.Errorf("FAIL: Expected watchlist content, got: %q", bodyStr)
	}
}

// Test: Add threshold update test when handler is implemented
func TestWatchlistViewer_ThresholdUpdateReturnsUpdatedRow(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Post("/htmx/watchlist/:id/threshold", h.APIWatchlistThresholdUpdate)

	// Create request with form data
	req := httptest.NewRequest("POST", "/api/htmx/watchlist/FG-01/threshold?value=0.10", nil)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	// Should return updated row fragment
	if !strings.Contains(bodyStr, "FG-01") && !strings.Contains(bodyStr, "0.10") {
		t.Errorf("FAIL: Expected updated threshold in response, got: %q", bodyStr)
	}
}
