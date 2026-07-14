package web

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

func TestLLMOpsDashboard_ReturnsHTMXPartialOnHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/llmops", h.APILLMOpsDashboard)

	req := httptest.NewRequest("GET", "/api/htmx/llmops", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if !strings.Contains(bodyStr, "<div") && !strings.Contains(bodyStr, "grid") {
		t.Errorf("FAIL: Expected HTMX partial, got: %q", bodyStr)
	}
}

func TestLLMOpsDashboard_ShowsEvalScores(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/llmops", h.APILLMOpsDashboard)

	req := httptest.NewRequest("GET", "/api/htmx/llmops", nil)
	req.Header.Set("HX-Request", "true")
	resp, _ := app.Test(req)

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.ToLower(string(body))

	hasMetrics := strings.Contains(bodyStr, "score") ||
		strings.Contains(bodyStr, "quality") ||
		strings.Contains(bodyStr, "eval")

	if !hasMetrics {
		t.Errorf("FAIL: Expected eval metrics, got: %q", bodyStr)
	}
}

func TestLLMOpsDashboard_ShowsAcknowledgementRate(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/llmops", h.APILLMOpsDashboard)

	// Need HX-Request header to get metrics
	req := httptest.NewRequest("GET", "/api/htmx/llmops", nil)
	req.Header.Set("HX-Request", "true")
	resp, _ := app.Test(req)

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.ToLower(string(body))

	hasAck := strings.Contains(bodyStr, "ack") ||
		strings.Contains(bodyStr, "rate") ||
		strings.Contains(bodyStr, "quality")

	if !hasAck {
		t.Errorf("FAIL: Expected acknowledgement metrics, got: %q", bodyStr)
	}
}
