package web

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

func TestOnboardingStatus_ReturnsHTMXPartialOnHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/onboarding", h.APIOnboardingStatus)

	req := httptest.NewRequest("GET", "/api/htmx/onboarding", nil)
	req.Header.Set("HX-Request", "true")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed to test request: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	// Should return <div> fragment with integration cards when HX-Request is true
	if !strings.Contains(bodyStr, "<div") {
		t.Errorf("FAIL: Expected HTMX partial with div, got: %q", bodyStr)
	}

	// Should show integration cards (Slack, Razorpay, etc.)
	if !strings.Contains(bodyStr, "Slack") {
		t.Errorf("FAIL: Expected integration cards, got: %q", bodyStr)
	}
}

func TestOnboardingStatus_ShowsConnectedIntegrations(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/onboarding", h.APIOnboardingStatus)

	// Request WITH HX-Request to get integration cards
	req := httptest.NewRequest("GET", "/api/htmx/onboarding", nil)
	req.Header.Set("HX-Request", "true")
	resp, _ := app.Test(req)

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.ToLower(string(body))

	// Should show Slack as connected (green)
	if !strings.Contains(bodyStr, "slack") {
		t.Error("FAIL: Should show Slack integration status")
	}

	// Should show Razorpay as connected (green)
	if !strings.Contains(bodyStr, "razorpay") {
		t.Error("FAIL: Should show Razorpay integration status")
	}
}

func TestOnboardingStatus_ShowsFirstAlertGate(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)

	apiGroup := app.Group("/api")
	apiGroup.Get("/htmx/onboarding", h.APIOnboardingStatus)

	// Request without HX-Request header
	req := httptest.NewRequest("GET", "/api/htmx/onboarding", nil)
	resp, _ := app.Test(req)

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.ToLower(string(body))

	// With no alerts fired, should show appropriate onboarding content
	// (not the empty "onboarding status" fallback)
	if bodyStr == "onboarding status" {
		t.Errorf("FAIL: Expected onboarding content, got: %q", bodyStr)
	}
}
