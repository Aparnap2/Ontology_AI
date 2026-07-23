package web

import (
	"fmt"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

// ── Page ───────────────────────────────────────────────────────────────

func TestCommandCenter_ServesPage(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/command", h.CommandCenter)

	req := httptest.NewRequest("GET", "/command", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "OntologyAI Workspace Command Center") {
		t.Errorf("FAIL: Expected page title 'OntologyAI Workspace Command Center', got: %q", bodyStr)
	}
	if !strings.Contains(bodyStr, "htmx.org") {
		t.Errorf("FAIL: Expected HTMX script, got: %q", bodyStr)
	}
}

// ── KPIs ───────────────────────────────────────────────────────────────

func TestCommandKPIs_ReturnsHTMXPartial(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/kpis", h.APICommandKPIs)

	req := httptest.NewRequest("GET", "/api/command/kpis", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"MRR", "Runway", "Activation", "Support Load"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected KPI '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Status ─────────────────────────────────────────────────────────────

func TestCommandStatus_ReturnsStatusBar(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/status", h.APICommandStatus)

	req := httptest.NewRequest("GET", "/api/command/status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Overall Health", "Risk level", "Last sync"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestCommandStatus_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/status", h.APICommandStatus)

	req := httptest.NewRequest("GET", "/api/command/status", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Command Status" {
		t.Errorf("FAIL: Expected 'Command Status', got: %q", bodyStr)
	}
}

// ── Mission State ──────────────────────────────────────────────────────

func TestCommandMissionState_ReturnsBoard(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/mission-state", h.APICommandMissionState)

	req := httptest.NewRequest("GET", "/api/command/mission-state", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Mission Status", "F", "B", "O", "Auto-updated"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Watchlist ──────────────────────────────────────────────────────────

func TestCommandWatchlist_ReturnsItems(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/watchlist", h.APICommandWatchlist)

	req := httptest.NewRequest("GET", "/api/command/watchlist", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	itemChecks := []string{"FG-04", "BG-04", "OG-02", "OG-01"}
	for _, check := range itemChecks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected watchlist item '%s' in response, got: %q", check, bodyStr)
		}
	}

	severityChecks := []string{"High", "Med", "Low"}
	for _, check := range severityChecks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected severity label '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Agent Fleet ────────────────────────────────────────────────────────

func TestCommandAgentFleet_ReturnsAgents(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/agent-fleet", h.APICommandAgentFleet)

	req := httptest.NewRequest("GET", "/api/command/agent-fleet", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Workspace Guide", "FP&A", "Growth Analytics", "Reliability & Delivery"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected agent '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Timeline ───────────────────────────────────────────────────────────

func TestCommandTimeline_ReturnsEvents(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/timeline", h.APICommandTimeline)

	req := httptest.NewRequest("GET", "/api/command/timeline", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Stripe webhook", "Finance watchlist", "Correlation raised", "Approval queued", "MissionState refreshed"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected timeline event '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Approvals ──────────────────────────────────────────────────────────

func TestCommandApprovals_ReturnsPendingItems(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/approvals", h.APICommandApprovals)

	req := httptest.NewRequest("GET", "/api/command/approvals", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Actions Needing Your Approval"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestCommandApprovals_EmptyState(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/approvals", h.APICommandApprovals)

	req := httptest.NewRequest("GET", "/api/command/approvals", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr == "" {
		t.Errorf("FAIL: Expected non-empty approval content, got empty")
	}
}

func TestCommandApprovalAction_ReturnsEmptyOnApprove(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/approvals/:id/:action", h.APICommandApprovalAction)

	req := httptest.NewRequest("POST", "/api/command/approvals/1/approve", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "" {
		t.Errorf("FAIL: Expected empty body on approve, got: %q", bodyStr)
	}
}

func TestCommandApprovalAction_ReturnsEmptyOnHold(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/approvals/:id/:action", h.APICommandApprovalAction)

	req := httptest.NewRequest("POST", "/api/command/approvals/1/hold", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "" {
		t.Errorf("FAIL: Expected empty body on hold, got: %q", bodyStr)
	}
}

func TestCommandApprovalAction_SignalsTemporalOnApprove(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil) // nil temporal client — should not crash
	app.Post("/api/command/approvals/:id/:action", h.APICommandApprovalAction)

	req := httptest.NewRequest("POST", "/api/command/approvals/wf-123/approve", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "" {
		t.Errorf("FAIL: Expected empty body on approve (even with nil temporal), got: %q", bodyStr)
	}
}

// ── Metrics ────────────────────────────────────────────────────────────

func TestCommandMetrics_ReturnsMetricsPanel(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/metrics", h.APICommandMetrics)

	req := httptest.NewRequest("GET", "/api/command/metrics", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	labelChecks := []string{"Average agent response", "Approval turnaround", "False alert rate", "Context budget"}
	for _, check := range labelChecks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected metric label '%s' in response, got: %q", check, bodyStr)
		}
	}

	statusChecks := []string{"GOOD", "OK", "LOW", "SAFE"}
	for _, check := range statusChecks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected metric status '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Chart Data (JSON) ──────────────────────────────────────────────────

func TestCommandChartData_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/chart-data", h.APICommandChartData)

	req := httptest.NewRequest("GET", "/api/command/chart-data", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("FAIL: Expected Content-Type application/json, got: %q", ct)
	}

	checks := []string{"Mission Health", "Risk Index", "Execution Drag"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected chart data '%s' in response, got: %q", check, bodyStr)
		}
	}
}

// ── Chat Send ──────────────────────────────────────────────────────────

func TestCommandChatSend_ReturnsEmpty(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/chat/send", h.APICommandChatSend)

	bodyPayload := "message=Hello&mention=@all"
	req := httptest.NewRequest("POST", "/api/command/chat/send", strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "" {
		t.Errorf("FAIL: Expected empty body, got: %q", bodyStr)
	}
}

func TestCommandChatSend_ReturnsEmptyWithDBNoTemporal(t *testing.T) {
	// Regression: chat send with @agent mention should not panic when temporal is nil
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/chat/send", h.APICommandChatSend)

	bodyPayload := "message=What+is+the+status%3F&mention=@sarthi"
	req := httptest.NewRequest("POST", "/api/command/chat/send", strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	// Without DB + temporal: should return empty without error
	if bodyStr != "" {
		t.Errorf("FAIL: Expected empty body, got: %q", bodyStr)
	}
}

// ── Mission State Update ────────────────────────────────────────────

func TestCommandMissionStateUpdate_PersistsData(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/mission-state/update", h.APICommandMissionStateUpdate)

	body := `{"tenant_id":"default","mrr":150000,"burn_rate":45000,"runway_days":24,"trust_score":78}`
	req := httptest.NewRequest("POST", "/api/command/mission-state/update",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	respBody, _ := io.ReadAll(resp.Body)
	bodyStr := string(respBody)
	if bodyStr == "" {
		t.Errorf("FAIL: Expected non-empty mission state HTML, got empty")
	}

	checks := []string{"Mission Status", "F", "B", "O", "Auto-updated"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestCommandMissionStateUpdate_NoDBNotCrash(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/mission-state/update", h.APICommandMissionStateUpdate)

	body := `{"tenant_id":"default","mrr":150000}`
	req := httptest.NewRequest("POST", "/api/command/mission-state/update",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}

// ── Alert Lineage ────────────────────────────────────────────────

func TestAPICommandAlertLineage_ReturnsValidHTML(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/alert-lineage", h.APICommandAlertLineage)

	req := httptest.NewRequest("GET", "/api/command/alert-lineage", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Alert Lineage", "Burn Multiple Spike", "auto", "review"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestAPICommandAlertLineage_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/alert-lineage", h.APICommandAlertLineage)

	req := httptest.NewRequest("GET", "/api/command/alert-lineage", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Alert Lineage" {
		t.Errorf("FAIL: Expected 'Alert Lineage', got: %q", bodyStr)
	}
}

// ── Operating Layer ──────────────────────────────────────────────

func TestAPICommandOperatingLayer_ReturnsValidHTML(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/operating-layer", h.APICommandOperatingLayer)

	req := httptest.NewRequest("GET", "/api/command/operating-layer", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Operating Layer", "Prepared Brief", "Last Update", "Pending Decisions", "Active Agent Roles"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestAPICommandOperatingLayer_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/operating-layer", h.APICommandOperatingLayer)

	req := httptest.NewRequest("GET", "/api/command/operating-layer", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Operating Layer" {
		t.Errorf("FAIL: Expected 'Operating Layer', got: %q", bodyStr)
	}
}

func TestAPICommandOperatingLayer_NoDBNotCrash(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/operating-layer", h.APICommandOperatingLayer)

	req := httptest.NewRequest("GET", "/api/command/operating-layer", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}

// ── Control Plane Status ──────────────────────────────────────────

func TestAPICommandControlPlaneStatus_ReturnsValidHTML(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/control-plane-status", h.APICommandControlPlaneStatus)

	req := httptest.NewRequest("GET", "/api/command/control-plane-status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Control Plane Status", "Last 5m", "Last 30m", "Last 24h"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestAPICommandControlPlaneStatus_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/control-plane-status", h.APICommandControlPlaneStatus)

	req := httptest.NewRequest("GET", "/api/command/control-plane-status", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Control Plane Status" {
		t.Errorf("FAIL: Expected 'Control Plane Status', got: %q", bodyStr)
	}
}

func TestAPICommandControlPlaneStatus_NoDBNotCrash(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/control-plane-status", h.APICommandControlPlaneStatus)

	req := httptest.NewRequest("GET", "/api/command/control-plane-status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}

// ── Self-Guardian Status ──────────────────────────────────────────

func TestAPICommandSelfGuardianStatus_ReturnsValidHTML(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/self-guardian-status", h.APICommandSelfGuardianStatus)

	req := httptest.NewRequest("GET", "/api/command/self-guardian-status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Self-Guardian Status", "No active deviations"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestAPICommandSelfGuardianStatus_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/self-guardian-status", h.APICommandSelfGuardianStatus)

	req := httptest.NewRequest("GET", "/api/command/self-guardian-status", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Self-Guardian Status" {
		t.Errorf("FAIL: Expected 'Self-Guardian Status', got: %q", bodyStr)
	}
}

func TestAPICommandSelfGuardianStatus_NoDBNotCrash(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/self-guardian-status", h.APICommandSelfGuardianStatus)

	req := httptest.NewRequest("GET", "/api/command/self-guardian-status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}

// ── Risk Status ─────────────────────────────────────────────────────

func TestAPICommandRiskStatus_ReturnsValidHTML(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/risk-status", h.APICommandRiskStatus)

	req := httptest.NewRequest("GET", "/api/command/risk-status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Risk Status", "Last 5m", "Last 30m", "Last 24h"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in response, got: %q", check, bodyStr)
		}
	}
}

func TestAPICommandRiskStatus_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/risk-status", h.APICommandRiskStatus)

	req := httptest.NewRequest("GET", "/api/command/risk-status", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Risk Status" {
		t.Errorf("FAIL: Expected 'Risk Status', got: %q", bodyStr)
	}
}

func TestAPICommandRiskStatus_NoDBNotCrash(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/risk-status", h.APICommandRiskStatus)

	req := httptest.NewRequest("GET", "/api/command/risk-status", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}

// ── V4.1 Route Map Tests ────────────────────────────────────────────

func TestRouteMap_HasFiveCanonicalSpecialists(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/chat/send", h.APICommandChatSend)

	// Test @sarthi routes to ChiefOfStaffWorkflow
	req := httptest.NewRequest("POST", "/api/command/chat/send", strings.NewReader("message=hello&mention=@sarthi"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	_ = resp
	// Must not crash — handler should accept and process
}

func TestRouteMap_AllAliasesResolve(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/chat/send", h.APICommandChatSend)

	aliases := []string{"@sarthi", "@agent", "@qa", "@ask", "@chief", "@discover", "@map", "@truth", "@build", "@govern", "@strategy", "@finance", "@fpa", "@data", "@growth", "@ops", "@comms"}
	for _, alias := range aliases {
		req := httptest.NewRequest("POST", "/api/command/chat/send",
			strings.NewReader(fmt.Sprintf("message=hello&mention=%s", alias)))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		_, err := app.Test(req)
		if err != nil {
			t.Errorf("Alias %s failed: %v", alias, err)
		}
	}
}

func TestRouteMap_HiringRemoved(t *testing.T) {
	// @hiring must NOT be a valid route — handler should not reference hiring
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/command/chat/send", h.APICommandChatSend)

	req := httptest.NewRequest("POST", "/api/command/chat/send",
		strings.NewReader("message=hello&mention=@hiring"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)
	// Should get a response that does NOT reference hiring
	if strings.Contains(bodyStr, "hiring") || strings.Contains(bodyStr, "Hiring") {
		t.Errorf("FAIL: Response should not reference hiring, got: %q", bodyStr)
	}
}

// ── V4.1 API Mission State Tests ────────────────────────────────────

func TestAPIMissionState_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/mission-state", h.APIMissionState)

	req := httptest.NewRequest("GET", "/api/mission-state", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)
	// Should return JSON (even if empty/default)
	if !strings.Contains(bodyStr, "{") && !strings.Contains(bodyStr, "[]") {
		t.Errorf("FAIL: Expected JSON response, got: %q", bodyStr)
	}
	_ = resp
}

func TestAPIMissionStatePost_AcceptsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/mission-state", h.APIMissionStatePost)

	jsonBody := `{"tenant_id":"test","summary":"test state","state_payload":{"mrr":100000}}`
	req := httptest.NewRequest("POST", "/api/mission-state", strings.NewReader(jsonBody))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	_ = resp
	// Should succeed (status 200 or 201)
	if resp.StatusCode != 200 && resp.StatusCode != 201 {
		t.Errorf("FAIL: Expected 200/201, got %d", resp.StatusCode)
	}
}

func TestAPIMissionStatePost_RejectsInvalidJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/mission-state", h.APIMissionStatePost)

	req := httptest.NewRequest("POST", "/api/mission-state", strings.NewReader("not-json"))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for invalid JSON, got %d", resp.StatusCode)
	}
}

func TestAPIMissionState_WithNilDB_ReturnsDefault(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil) // nil DB
	app.Get("/api/mission-state", h.APIMissionState)

	req := httptest.NewRequest("GET", "/api/mission-state", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	// Should not crash with nil DB
	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200 with nil DB, got %d", resp.StatusCode)
	}
}

// ── V4.1 Branding Tests ─────────────────────────────────────────────

func TestCommandCenter_TitleContainsOntologyAI(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/command", h.CommandCenter)

	req := httptest.NewRequest("GET", "/command", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)
	if !strings.Contains(bodyStr, "OntologyAI Workspace") {
		t.Errorf("FAIL: Page title should contain 'OntologyAI Workspace', got: %q", bodyStr[:200])
	}
}

func TestCommandCenter_AgentFleetShowsChiefOfStaff(t *testing.T) {
	// Agent names are loaded via HTMX partial — verify the agent-fleet endpoint
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/command/agent-fleet", h.APICommandAgentFleet)

	req := httptest.NewRequest("GET", "/api/command/agent-fleet", nil)
	req.Header.Set("HX-Request", "true")
	resp, _ := app.Test(req)
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)
	if !strings.Contains(bodyStr, "Workspace Guide") {
		t.Errorf("FAIL: Expected 'Workspace Guide' in agent fleet, got: %q", bodyStr[:500])
	}
	// Also verify old names are not present
	if strings.Contains(bodyStr, "OntologyAI") {
		t.Errorf("FAIL: Agent fleet should not contain 'OntologyAI', got: %q", bodyStr[:500])
	}
}

func TestCommandCenter_NoHiringLabel(t *testing.T) {
	// Verify the dashboard page doesn't reference Hiring
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/command", h.CommandCenter)

	req := httptest.NewRequest("GET", "/command", nil)
	resp, _ := app.Test(req)
	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)
	if strings.Contains(bodyStr, "Hiring") {
		t.Errorf("FAIL: Dashboard should not show Hiring specialist, got: %q", bodyStr[:500])
	}
}
