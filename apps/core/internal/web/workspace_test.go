package web

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

// ── Workspace Mode Toggle ────────────────────────────────────────────────

func TestWorkspaceMode_ToggleToWorkspace(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/mode", h.APIWorkspaceMode)

	req := httptest.NewRequest("POST", "/api/workspace/mode", strings.NewReader(`{"mode":"workspace"}`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"workspace_mode":"workspace"`) {
		t.Errorf("FAIL: Expected workspace_mode=workspace, got %q", string(body))
	}
}

func TestWorkspaceMode_ToggleToDashboard(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/mode", h.APIWorkspaceMode)

	req := httptest.NewRequest("POST", "/api/workspace/mode", strings.NewReader(`{"mode":"dashboard"}`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"workspace_mode":"dashboard"`) {
		t.Errorf("FAIL: Expected workspace_mode=dashboard, got %q", string(body))
	}
}

func TestWorkspaceMode_RejectsInvalidMode(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/mode", h.APIWorkspaceMode)

	req := httptest.NewRequest("POST", "/api/workspace/mode", strings.NewReader(`{"mode":"bogus"}`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for invalid mode, got %d", resp.StatusCode)
	}
}

func TestWorkspaceMode_RejectsBadJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/mode", h.APIWorkspaceMode)

	req := httptest.NewRequest("POST", "/api/workspace/mode", strings.NewReader(`not-json`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for bad JSON, got %d", resp.StatusCode)
	}
}

// ── Workspace State ──────────────────────────────────────────────────────

func TestWorkspaceState_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/state", h.APIWorkspaceState)

	req := httptest.NewRequest("GET", "/api/workspace/state", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "workspace_mode") {
		t.Errorf("FAIL: Expected workspace_mode in state, got %q", string(body))
	}
}

// ── Workspace Shell + Screens ────────────────────────────────────────────

func TestWorkspaceShell_RedirectsWhenNotInWorkspaceMode(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace", h.Workspace)

	req := httptest.NewRequest("GET", "/workspace", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	// Default mode is "dashboard" → should redirect (307) to /command
	if resp.StatusCode != fiber.StatusTemporaryRedirect {
		t.Errorf("FAIL: Expected 307 redirect, got %d", resp.StatusCode)
	}
}

func TestWorkspaceScreenPartial_ReturnsDashboard(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/dashboard", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Dashboard") {
		t.Errorf("FAIL: Expected Dashboard screen, got %q", string(body))
	}
}

func TestWorkspaceScreenPartial_ReturnsWorkflowBuilder(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/workflow-builder", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	checks := []string{"Workflow Builder", "Node Palette", "Export to n8n"}
	for _, c := range checks {
		if !strings.Contains(string(body), c) {
			t.Errorf("FAIL: Expected %q in workflow builder, got %q", c, string(body))
		}
	}
}

func TestWorkspaceScreenPartial_ReturnsAll16Screens(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	screens := []string{"dashboard", "conversations", "workflow-builder", "data-sources",
		"approvals", "agent-roster", "notifications", "analytics", "settings", "help",
		"mission", "credentials", "ontology", "truth-findings", "executable-drafts", "artifacts"}
	for _, s := range screens {
		req := httptest.NewRequest("GET", "/workspace/"+s, nil)
		resp, err := app.Test(req)
		if err != nil {
			t.Fatalf("Screen %s failed: %v", s, err)
		}
		if resp.StatusCode != 200 {
			t.Errorf("FAIL: Screen %s expected 200, got %d", s, resp.StatusCode)
		}
	}
}

func TestWorkspaceScreenPartial_UnknownScreen404(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/bogus", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 404 {
		t.Errorf("FAIL: Expected 404 for unknown screen, got %d", resp.StatusCode)
	}
}

// ── Workflow Drafts API ──────────────────────────────────────────────────

func TestWorkspaceWorkflowDraftsList_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/workflow-drafts", h.APIWorkflowDraftsList)

	req := httptest.NewRequest("GET", "/api/workspace/workflow-drafts", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"drafts"`) {
		t.Errorf("FAIL: Expected drafts key, got %q", string(body))
	}
}

func TestWorkspaceWorkflowDraftCreate_Returns201(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/workflow-drafts", h.APIWorkflowDraftCreate)

	body := `{"name":"Test flow","runtime":"n8n","draft":{"nodes":[],"edges":[]}}`
	req := httptest.NewRequest("POST", "/api/workspace/workflow-drafts", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 201 {
		t.Errorf("FAIL: Expected 201, got %d", resp.StatusCode)
	}
}

func TestWorkspaceWorkflowDraftCreate_RejectsMissingName(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/workflow-drafts", h.APIWorkflowDraftCreate)

	req := httptest.NewRequest("POST", "/api/workspace/workflow-drafts", strings.NewReader(`{"runtime":"n8n"}`))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for missing name, got %d", resp.StatusCode)
	}
}

func TestWorkspaceWorkflowDraftCompile_Stubs202(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/workflow-drafts/:id/compile", h.APIWorkflowDraftCompile)

	req := httptest.NewRequest("POST", "/api/workspace/workflow-drafts/draft-1/compile", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 202 {
		t.Errorf("FAIL: Expected 202 (queued), got %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "queued") {
		t.Errorf("FAIL: Expected queued message, got %q", string(body))
	}
}

// ── Approvals + Data Sources API ─────────────────────────────────────────

func TestWorkspaceApprovalsList_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/approvals", h.APIApprovalsList)

	req := httptest.NewRequest("GET", "/api/workspace/approvals", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"approvals"`) {
		t.Errorf("FAIL: Expected approvals key, got %q", string(body))
	}
}

func TestWorkspaceDataSourcesList_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/data-sources", h.APIDataSourcesList)

	req := httptest.NewRequest("GET", "/api/workspace/data-sources", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"data_sources"`) {
		t.Errorf("FAIL: Expected data_sources key, got %q", string(body))
	}
}

// ── New V5.1 Workspace Screens ────────────────────────────────────────────

func TestWorkspaceScreenPartial_ReturnsOntology(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Ontology") {
		t.Errorf("FAIL: Expected Ontology screen, got %q", string(body))
	}
}

func TestWorkspaceScreenPartial_ReturnsTruthFindings(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/truth-findings", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Truth Findings") {
		t.Errorf("FAIL: Expected Truth Findings screen, got %q", string(body))
	}
}

func TestWorkspaceScreenPartial_ReturnsExecutableDrafts(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/executable-drafts", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Executable Drafts") {
		t.Errorf("FAIL: Expected Executable Drafts screen, got %q", string(body))
	}
}

func TestWorkspaceScreenPartial_ReturnsArtifacts(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	req := httptest.NewRequest("GET", "/workspace/artifacts", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "Artifacts") {
		t.Errorf("FAIL: Expected Artifacts screen, got %q", string(body))
	}
}

// ── Ontology API ──────────────────────────────────────────────────────────

func TestWorkspaceOntology_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	req := httptest.NewRequest("GET", "/api/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"object_types"`) {
		t.Errorf("FAIL: Expected object_types in response, got %q", string(body))
	}
}

// ── Exports API ───────────────────────────────────────────────────────────

func TestWorkspaceExport_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/exports/:type", h.APIExportGet)

	req := httptest.NewRequest("GET", "/api/workspace/exports/truth-map", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"artifact_type"`) {
		t.Errorf("FAIL: Expected artifact_type in response, got %q", string(body))
	}
}

func TestWorkspaceExport_UnknownType404(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/exports/:type", h.APIExportGet)

	req := httptest.NewRequest("GET", "/api/workspace/exports/bogus", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp.StatusCode != 404 {
		t.Errorf("FAIL: Expected 404 for unknown export type, got %d", resp.StatusCode)
	}
}

func TestWorkspaceExportsList_ReturnsJSON(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/exports", h.APIExportsList)

	req := httptest.NewRequest("GET", "/api/workspace/exports", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"export_types"`) {
		t.Errorf("FAIL: Expected export_types in response, got %q", string(body))
	}
}
