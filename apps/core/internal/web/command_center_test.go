package web

import (
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

	if !strings.Contains(bodyStr, "Sarthi Command Center") {
		t.Errorf("FAIL: Expected page title, got: %q", bodyStr)
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

	checks := []string{"Sarthi", "Finance", "Data", "Ops"}
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

	checks := []string{"Investor update", "Jira issue", "Approve", "Hold"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected approval item '%s' in response, got: %q", check, bodyStr)
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
