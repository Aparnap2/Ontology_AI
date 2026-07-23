package web

import (
	"bufio"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
)

// ── V5.1 Workspace (gated by EngagementState.workspace_mode) ──────────────

// WorkspaceScreen lists the 16 screens available in workspace mode.
var WorkspaceScreen = map[string]string{
	"dashboard":         "Dashboard",
	"conversations":     "Conversations",
	"data-sources":      "Data Sources",
	"approvals":         "Approvals",
	"agent-roster":      "Agent Roster",
	"notifications":     "Notifications",
	"analytics":         "Analytics",
	"settings":          "Settings",
	"help":              "Help",
	"mission":           "Mission",
	"ontology":          "Business Map",
	"truth-findings":    "Operational Truth",
	"workflow-builder":  "Pilot Builder",
	"executable-drafts": "Pilot Draft",
	"artifacts":         "Artifacts",
	"credentials":       "Credentials",
}

// EngagementState is the machine-readable state returned by /api/workspace/state.
type EngagementState struct {
	EngagementID  string          `json:"engagement_id"`
	WorkspaceMode string          `json:"workspace_mode"` // "dashboard" | "workspace"
	Phase         string          `json:"phase"`
	State         json.RawMessage `json:"state"`
	UpdatedAt     string          `json:"updated_at"`
}

// getEngagementState reads the current engagement state from the DB (or default).
func (h *Handler) getEngagementState() EngagementState {
	state := EngagementState{
		EngagementID:  "default",
		WorkspaceMode: "dashboard",
		Phase:         "discovery",
		State:         json.RawMessage(`{}`),
		UpdatedAt:     time.Now().Format(time.RFC3339),
	}
	if h.db != nil {
		var mode, phase, statePayload sql.NullString
		err := h.db.QueryRow(`
			SELECT workspace_mode, phase, COALESCE(state::text, '{}')
			FROM engagement_states
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&mode, &phase, &statePayload)
		if err == nil {
			if mode.Valid && mode.String != "" {
				state.WorkspaceMode = mode.String
			}
			if phase.Valid && phase.String != "" {
				state.Phase = phase.String
			}
			state.State = json.RawMessage(statePayload.String)
		}
	}
	return state
}

// Workspace serves the main 15-screen workspace shell (gated by workspace_mode).
func (h *Handler) Workspace(c *fiber.Ctx) error {
	state := h.getEngagementState()
	if state.WorkspaceMode != "workspace" {
		// Not in workspace mode — redirect to the dashboard shell.
		return c.Redirect("/command", fiber.StatusTemporaryRedirect)
	}
	return Render(c, "workspace", fiber.Map{
		"Title":   "IterateSwarm Workspace",
		"Screens": WorkspaceScreen,
		"State":   state,
	})
}

// WorkspaceScreenPartial renders a single workspace screen partial.
func (h *Handler) WorkspaceScreenPartial(c *fiber.Ctx) error {
	screen := c.Params("screen")
	name, ok := WorkspaceScreen[screen]
	if !ok {
		return c.Status(404).SendString(`<div class="text-red-400 text-sm">Unknown screen</div>`)
	}
	// All screens are server-rendered fragments; the workflow-builder is the live canvas.
	return Render(c, "partials/workspace_"+screen, fiber.Map{
		"Screen": name,
		"State":  h.getEngagementState(),
	})
}

// APIWorkspaceState returns the EngagementState (incl. workspace_mode) as JSON.
func (h *Handler) APIWorkspaceState(c *fiber.Ctx) error {
	return c.JSON(h.getEngagementState())
}

// APIWorkspaceMode toggles workspace_mode between "dashboard" and "workspace".
func (h *Handler) APIWorkspaceMode(c *fiber.Ctx) error {
	var req struct {
		Mode string `json:"mode"`
	}
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "invalid JSON"})
	}
	if req.Mode != "dashboard" && req.Mode != "workspace" {
		return c.Status(400).JSON(fiber.Map{"error": "mode must be 'dashboard' or 'workspace'"})
	}

	if h.db != nil {
		// Upsert the canonical engagement state row.
		_, err := h.db.Exec(`
			INSERT INTO engagement_states (engagement_id, workspace_mode, phase, state)
			VALUES ('default', $1, 'discovery', '{}'::jsonb)
			ON CONFLICT (engagement_id)
			DO UPDATE SET workspace_mode = EXCLUDED.workspace_mode, updated_at = NOW()
		`, req.Mode)
		if err != nil {
			log.Printf("Failed to persist workspace_mode: %v", err)
		}
	}

	// Broadcast mode change over SSE for live UI updates.
	if h.sseHub != nil {
		h.sseHub.Broadcast("default", SSEEvent{
			Type:    "workspace-mode",
			Payload: req.Mode,
		})
	}

	return c.JSON(fiber.Map{"ok": true, "workspace_mode": req.Mode})
}

// ── Workflow Drafts (executable_workflow_drafts) ──────────────────────────

// WorkflowDraft is the API representation of an executable_workflow_drafts row.
type WorkflowDraft struct {
	ID            string          `json:"id"`
	Runtime       string          `json:"runtime"`
	Name          string          `json:"name"`
	Status        string          `json:"status"`
	Draft         json.RawMessage `json:"draft"`
	ExportPayload json.RawMessage `json:"export_payload,omitempty"`
	CreatedAt     string          `json:"created_at"`
	UpdatedAt     string          `json:"updated_at"`
}

// APIWorkflowDraftsList lists drafts from executable_workflow_drafts.
func (h *Handler) APIWorkflowDraftsList(c *fiber.Ctx) error {
	drafts := []WorkflowDraft{}
	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT id, COALESCE(runtime, ''), COALESCE(name, ''), COALESCE(status, ''),
			       draft::text, COALESCE(export_payload::text, ''),
			       created_at, updated_at
			FROM executable_workflow_drafts
			ORDER BY updated_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var d WorkflowDraft
				var draftJSON, exportJSON sql.NullString
				var createdAt, updatedAt time.Time
				if err := rows.Scan(&d.ID, &d.Runtime, &d.Name, &d.Status,
					&draftJSON, &exportJSON, &createdAt, &updatedAt); err != nil {
					continue
				}
				d.Draft = json.RawMessage(draftJSON.String)
				if exportJSON.Valid && exportJSON.String != "" {
					d.ExportPayload = json.RawMessage(exportJSON.String)
				}
				d.CreatedAt = createdAt.Format(time.RFC3339)
				d.UpdatedAt = updatedAt.Format(time.RFC3339)
				drafts = append(drafts, d)
			}
		}
	}
	if drafts == nil {
		drafts = []WorkflowDraft{}
	}
	return c.JSON(fiber.Map{"drafts": drafts})
}

// APIWorkflowDraftCreate creates a new draft.
func (h *Handler) APIWorkflowDraftCreate(c *fiber.Ctx) error {
	var req struct {
		Runtime string          `json:"runtime"`
		Name    string          `json:"name"`
		Draft   json.RawMessage `json:"draft"`
	}
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "invalid JSON"})
	}
	if req.Name == "" {
		return c.Status(400).JSON(fiber.Map{"error": "name required"})
	}
	if len(req.Draft) == 0 {
		req.Draft = json.RawMessage(`{}`)
	}
	if req.Runtime == "" {
		req.Runtime = "n8n"
	}

	var id string
	var createdAt time.Time
	if h.db != nil {
		err := h.db.QueryRow(`
			INSERT INTO executable_workflow_drafts (tenant_id, engagement_id, runtime, name, status, draft)
			VALUES ('default', 'default', $1, $2, 'draft', $3::jsonb)
			RETURNING id, created_at
		`, req.Runtime, req.Name, string(req.Draft)).Scan(&id, &createdAt)
		if err != nil {
			log.Printf("Failed to create workflow draft: %v", err)
			return c.Status(500).JSON(fiber.Map{"error": "failed to create draft"})
		}
	} else {
		id = "draft-" + fmt.Sprintf("%d", time.Now().UnixNano())
		createdAt = time.Now()
	}

	return c.Status(201).JSON(WorkflowDraft{
		ID:        id,
		Runtime:   req.Runtime,
		Name:      req.Name,
		Status:    "draft",
		Draft:     req.Draft,
		CreatedAt: createdAt.Format(time.RFC3339),
		UpdatedAt: createdAt.Format(time.RFC3339),
	})
}

// APIWorkflowDraftGet returns a single draft.
func (h *Handler) APIWorkflowDraftGet(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(400).JSON(fiber.Map{"error": "id required"})
	}
	if h.db != nil {
		var d WorkflowDraft
		var draftJSON, exportJSON sql.NullString
		var createdAt, updatedAt time.Time
		err := h.db.QueryRow(`
			SELECT id, COALESCE(runtime, ''), COALESCE(name, ''), COALESCE(status, ''),
			       draft::text, COALESCE(export_payload::text, ''), created_at, updated_at
			FROM executable_workflow_drafts WHERE id = $1
		`, id).Scan(&d.ID, &d.Runtime, &d.Name, &d.Status,
			&draftJSON, &exportJSON, &createdAt, &updatedAt)
		if err == nil {
			d.Draft = json.RawMessage(draftJSON.String)
			if exportJSON.Valid && exportJSON.String != "" {
				d.ExportPayload = json.RawMessage(exportJSON.String)
			}
			d.CreatedAt = createdAt.Format(time.RFC3339)
			d.UpdatedAt = updatedAt.Format(time.RFC3339)
			return c.JSON(d)
		}
	}
	return c.Status(404).JSON(fiber.Map{"error": "draft not found"})
}

// APIWorkflowDraftUpdate updates an existing draft.
func (h *Handler) APIWorkflowDraftUpdate(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(400).JSON(fiber.Map{"error": "id required"})
	}
	var req struct {
		Name   string          `json:"name"`
		Status string          `json:"status"`
		Draft  json.RawMessage `json:"draft"`
	}
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "invalid JSON"})
	}
	if h.db != nil {
		_, err := h.db.Exec(`
			UPDATE executable_workflow_drafts
			SET name = COALESCE(NULLIF($2, ''), name),
			    status = COALESCE(NULLIF($3, ''), status),
			    draft = COALESCE($4::jsonb, draft),
			    updated_at = NOW()
			WHERE id = $1
		`, id, req.Name, req.Status, string(req.Draft))
		if err != nil {
			log.Printf("Failed to update workflow draft: %v", err)
			return c.Status(500).JSON(fiber.Map{"error": "failed to update draft"})
		}
	}
	return c.JSON(fiber.Map{"ok": true, "id": id})
}

// APIWorkflowDraftCompile stubs the n8n compile trigger. Real compile is a
// Python activity — here we just queue and return 202.
func (h *Handler) APIWorkflowDraftCompile(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(400).JSON(fiber.Map{"error": "id required"})
	}
	if h.db != nil {
		_, err := h.db.Exec(`
			UPDATE executable_workflow_drafts
			SET status = 'compiling', updated_at = NOW()
			WHERE id = $1
		`, id)
		if err != nil {
			log.Printf("Failed to mark draft compiling: %v", err)
		}
	}
	// Broadcast a queued event over SSE for live UI feedback.
	if h.sseHub != nil {
		h.sseHub.Broadcast("default", SSEEvent{
			Type:    "workflow-compile",
			Payload: id,
		})
	}
	return c.Status(202).JSON(fiber.Map{
		"ok":      true,
		"status":  "queued",
		"message": "Compile queued — n8n export will be produced by the Python compile activity.",
		"draft":   id,
	})
}

// ── Data Sources (data_sources) ───────────────────────────────────────────

// DataSource is the API representation of a data_sources row.
type DataSource struct {
	ID         string          `json:"id"`
	SourceType string          `json:"source_type"`
	SourceName string          `json:"source_name"`
	Status     string          `json:"status"`
	Metadata   json.RawMessage `json:"metadata,omitempty"`
	CreatedAt  string          `json:"created_at"`
	UpdatedAt  string          `json:"updated_at"`
}

// APIDataSourcesList lists data sources.
func (h *Handler) APIDataSourcesList(c *fiber.Ctx) error {
	sources := []DataSource{}
	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT id, COALESCE(source_type, ''), COALESCE(source_name, ''), COALESCE(status, ''),
			       COALESCE(metadata::text, ''), created_at, updated_at
			FROM data_sources
			ORDER BY updated_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var s DataSource
				var metaJSON sql.NullString
				var createdAt, updatedAt time.Time
				if err := rows.Scan(&s.ID, &s.SourceType, &s.SourceName, &s.Status,
					&metaJSON, &createdAt, &updatedAt); err != nil {
					continue
				}
				if metaJSON.Valid && metaJSON.String != "" {
					s.Metadata = json.RawMessage(metaJSON.String)
				}
				s.CreatedAt = createdAt.Format(time.RFC3339)
				s.UpdatedAt = updatedAt.Format(time.RFC3339)
				sources = append(sources, s)
			}
		}
	}
	if sources == nil {
		sources = []DataSource{}
	}
	return c.JSON(fiber.Map{"data_sources": sources})
}

// ── Approvals (approvals) ─────────────────────────────────────────────────

// WorkspaceApproval is the API representation of an approvals row.
type WorkspaceApproval struct {
	ID          string `json:"id"`
	TargetType  string `json:"target_type"`
	TargetID    string `json:"target_id"`
	Status      string `json:"status"`
	RequestedBy string `json:"requested_by"`
	Reason      string `json:"reason"`
	CreatedAt   string `json:"created_at"`
}

// APIApprovalsList lists pending approvals from the approvals table.
func (h *Handler) APIApprovalsList(c *fiber.Ctx) error {
	approvals := []WorkspaceApproval{}
	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT id, COALESCE(target_type, ''), COALESCE(target_id, ''), COALESCE(status, ''),
			       COALESCE(requested_by, ''), COALESCE(reason, ''), created_at
			FROM approvals
			WHERE status = 'pending'
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var a WorkspaceApproval
				var createdAt time.Time
				if err := rows.Scan(&a.ID, &a.TargetType, &a.TargetID, &a.Status,
					&a.RequestedBy, &a.Reason, &createdAt); err != nil {
					continue
				}
				a.CreatedAt = createdAt.Format(time.RFC3339)
				approvals = append(approvals, a)
			}
		}
	}
	if approvals == nil {
		approvals = []WorkspaceApproval{}
	}
	return c.JSON(fiber.Map{"approvals": approvals})
}

// APIApprovalAction approves or holds an approval from the approvals table.
func (h *Handler) APIApprovalAction(c *fiber.Ctx) error {
	id := c.Params("id")
	action := c.Params("action")
	if id == "" {
		return c.Status(400).JSON(fiber.Map{"error": "id required"})
	}
	newStatus := "held"
	if action == "approve" {
		newStatus = "approved"
	}
	if h.db != nil {
		_, err := h.db.Exec(`
			UPDATE approvals
			SET status = $2, resolved_at = NOW()
			WHERE id = $1
		`, id, newStatus)
		if err != nil {
			log.Printf("Failed to update approval: %v", err)
		}
	}
	if h.sseHub != nil {
		h.sseHub.Broadcast("default", SSEEvent{
			Type:    "approval-" + newStatus,
			Payload: id,
		})
	}
	return c.JSON(fiber.Map{"ok": true, "id": id, "status": newStatus})
}

// ── Workspace SSE (live updates) ───────────────────────────────────────────

// APIWorkspaceEvents is the SSE endpoint for workspace live updates
// (event types: "workspace-mode", "workflow-compile", "approval-*").
func (h *Handler) APIWorkspaceEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, "workspace-mode", "workflow-compile", "approval-approved", "approval-held")
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, _ = fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				_, _ = fmt.Fprintf(w, "%s", msgBytes)
				w.Flush()
			case <-done:
				return
			}
		}
	})
	return nil
}

// RegisterWorkspaceRoutes registers the V5.1 workspace routes.
func (h *Handler) RegisterWorkspaceRoutes(app *fiber.App) {
	// Shell + screen partials (gated by workspace_mode)
	app.Get("/workspace", h.Workspace)
	app.Get("/workspace/:screen", h.WorkspaceScreenPartial)

	// Engagement state + mode toggle
	app.Get("/api/workspace/state", h.APIWorkspaceState)
	app.Post("/api/workspace/mode", h.APIWorkspaceMode)

	// Workflow drafts CRUD + compile stub
	app.Get("/api/workspace/workflow-drafts", h.APIWorkflowDraftsList)
	app.Post("/api/workspace/workflow-drafts", h.APIWorkflowDraftCreate)
	app.Get("/api/workspace/workflow-drafts/:id", h.APIWorkflowDraftGet)
	app.Put("/api/workspace/workflow-drafts/:id", h.APIWorkflowDraftUpdate)
	app.Post("/api/workspace/workflow-drafts/:id/compile", h.APIWorkflowDraftCompile)

	// Data sources
	app.Get("/api/workspace/data-sources", h.APIDataSourcesList)

	// Approvals
	app.Get("/api/workspace/approvals", h.APIApprovalsList)
	app.Post("/api/workspace/approvals/:id/:action", h.APIApprovalAction)

	// Credentials (V5.1 credential collection)
	app.Get("/api/workspace/credentials", h.APICredentialsList)
	app.Get("/api/workspace/credentials/add", h.APICredentialsAddForm)
	app.Post("/api/workspace/credentials", h.APICredentialsCreate)
	app.Delete("/api/workspace/credentials/:id", h.APICredentialsDelete)

	// Ontology viewer
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	// Executable drafts
	app.Get("/api/workspace/executable-drafts", h.APIWorkflowDraftsList)

	// Exports
	app.Get("/api/workspace/exports", h.APIExportsList)
	app.Get("/api/workspace/exports/:type", h.APIExportGet)

	// Truth findings
	app.Get("/api/workspace/truth-findings", h.APIWorkspaceTruthFindings)

	// Live SSE
	app.Get("/api/workspace/events", h.APIWorkspaceEvents)
}

// ensure strings import is used (defensive for future palette helpers)
var _ = strings.TrimSpace
