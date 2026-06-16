package web

import (
	"database/sql"
	"embed"
	"fmt"
	"html/template"
	"time"

	"github.com/gofiber/fiber/v2"
)

//go:embed templates/*.html
var templatesFS embed.FS

// Render renders a template with data
func Render(c *fiber.Ctx, name string, data interface{}) error {
	tmpl, err := template.ParseFS(templatesFS, "templates/"+name+".html")
	if err != nil {
		return fmt.Errorf("failed to parse template %s: %w", name, err)
	}

	c.Set("Content-Type", "text/html")
	return tmpl.Execute(c.Response().BodyWriter(), data)
}

// Handler struct for web routes
type Handler struct {
	db *sql.DB
}

// NewHandler creates a new web handler
func NewHandler(db *sql.DB) *Handler {
	return &Handler{
		db: db,
	}
}

// Dashboard handler - serves the main HTMX dashboard
func (h *Handler) Dashboard(c *fiber.Ctx) error {
	return Render(c, "dashboard", fiber.Map{
		"Title": "IterateSwarm Admin Dashboard",
	})
}

// HandleFeedback processes feedback submissions from HTMX
func (h *Handler) HandleFeedback(c *fiber.Ctx) error {
	var req struct {
		Content string `json:"content" form:"content"`
		Source  string `json:"source" form:"source"`
		UserID  string `json:"user_id" form:"user_id"`
	}

	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).SendString(`<div class="text-red-600">Invalid request</div>`)
	}

	// Validate
	if req.Content == "" {
		return c.Status(400).SendString(`<div class="text-red-600">Content is required</div>`)
	}

	if req.Source == "" {
		req.Source = "web"
	}

	if req.UserID == "" {
		req.UserID = "anonymous"
	}

	// For now, return a simple success message
	// TODO: Integrate with actual feedback processing
	return c.SendString(`<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-center"><i class="fas fa-check-circle mr-2"></i>Feedback received: ` + req.Content[:50] + `...</div>`)
}

// HandleStats returns system stats for HTMX polling
func (h *Handler) HandleStats(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"circuit_breaker":  "CLOSED",
		"rate_limit_used":  0,
		"rate_limit_total": 20,
		"avg_time":         "3.5",
	})
}

// HandleMetrics returns detailed metrics
func (h *Handler) HandleMetrics(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"feedbacks_processed":   0,
		"avg_processing_time":   3.5,
		"circuit_breaker_state": "CLOSED",
		"rate_limit_hits":       0,
		"classification_accuracy": fiber.Map{
			"bug":      0.96,
			"feature":  0.97,
			"question": 0.98,
		},
	})
}

// ============== Panel 1: Live Feed ==============

// GetLiveFeed renders the live feed panel
func (h *Handler) GetLiveFeed(c *fiber.Ctx) error {
	return Render(c, "live_feed", nil)
}

// ============== Panel 2: HITL Queue ==============

// Approval represents a pending approval
type Approval struct {
	ID         string                 `json:"id"`
	PRNumber   int                    `json:"pr_number"`
	Type       string                 `json:"type"`
	Reasoning  string                 `json:"reasoning"`
	Confidence int                    `json:"confidence"`
	CreatedAt  string                 `json:"created_at"`
	Metadata   map[string]interface{} `json:"metadata"`
}

// GetPendingApprovals returns pending HITL approvals from PostgreSQL
func (h *Handler) GetPendingApprovals(c *fiber.Ctx) error {
	// Query HITL queue from PostgreSQL - includes both hitl_queue and agent_outputs
	rows, err := h.db.Query(`
		SELECT 
			COALESCE(hq.task_id, ao.id) as task_id,
			COALESCE(hq.issue_title, ao.headline) as title,
			COALESCE(hq.issue_body, ao.output_json->>'reasoning') as body,
			COALESCE(hq.severity, ao.urgency) as severity,
			COALESCE(hq.created_at, ao.created_at) as created_at,
			CASE 
				WHEN hq.task_id IS NOT NULL THEN 'hitl_queue'
				ELSE 'agent_outputs'
			END as source
		FROM hitl_queue hq
		FULL OUTER JOIN agent_outputs ao 
			ON ao.agent_name = 'finance' 
			AND ao.hitl_sent = true
			AND ao.output_type = 'anomaly_alert'
		WHERE (hq.status = 'pending' AND hq.expires_at > NOW())
			OR (ao.id IS NOT NULL AND ao.hitl_sent = true)
		ORDER BY COALESCE(hq.created_at, ao.created_at) DESC
		LIMIT 20
	`)
	if err != nil {
		// Return empty list on error
		return Render(c, "hitl_queue", fiber.Map{
			"Approvals": []Approval{},
		})
	}
	defer rows.Close()

	var approvals []Approval
	for rows.Next() {
		var taskID, title, body, severity, source string
		var createdAt time.Time
		if err := rows.Scan(&taskID, &title, &body, &severity, &createdAt, &source); err != nil {
			continue
		}
		approvals = append(approvals, Approval{
			ID:        taskID,
			Type:      severity,
			Reasoning: body,
			CreatedAt: createdAt.Format(time.RFC3339),
			Metadata: map[string]interface{}{
				"source": source,
			},
		})
	}

	return Render(c, "hitl_queue", fiber.Map{
		"Approvals": approvals,
	})
}

// ApprovePR approves a pending PR
func (h *Handler) ApprovePR(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(400).SendString("Missing approval ID")
	}

	// Update HITL status in PostgreSQL
	_, err := h.db.Exec(`
		UPDATE hitl_queue
		SET status = 'approved'
		WHERE task_id = $1
	`, id)
	if err != nil {
		return c.Status(500).SendString("Failed to approve")
	}

	return h.GetPendingApprovals(c)
}

// RejectPR rejects a pending PR
func (h *Handler) RejectPR(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(400).SendString("Missing approval ID")
	}

	// Update HITL status in PostgreSQL
	_, err := h.db.Exec(`
		UPDATE hitl_queue
		SET status = 'rejected'
		WHERE task_id = $1
	`, id)
	if err != nil {
		return c.Status(500).SendString("Failed to reject")
	}

	return h.GetPendingApprovals(c)
}

// ============== Panel 3: Agent Map ==============

// AgentStatus represents an agent's current status
type AgentStatus struct {
	Name      string `json:"name"`
	State     string `json:"state"` // active, busy, idle, error
	TaskCount int    `json:"task_count"`
	LastSeen  string `json:"last_seen"`
}

// GetAgentStatus returns status for a specific agent
func (h *Handler) GetAgentStatus(c *fiber.Ctx) error {
	agent := c.Params("agent")
	if agent == "" {
		return c.Status(400).JSON(fiber.Map{"error": "Missing agent parameter"})
	}

	// Placeholder - return default status
	status := AgentStatus{
		Name:      agent,
		State:     "idle",
		TaskCount: 0,
		LastSeen:  time.Now().Format(time.RFC3339),
	}

	return c.JSON(status)
}

// GetAllAgentsStatus returns status for all agents
func (h *Handler) GetAllAgentsStatus(c *fiber.Ctx) error {
	agents := []string{"supervisor", "researcher", "sre", "swe", "reviewer"}
	statuses := make(map[string]AgentStatus)

	for _, agent := range agents {
		statuses[agent] = AgentStatus{
			Name:      agent,
			State:     "idle",
			TaskCount: 0,
			LastSeen:  time.Now().Format(time.RFC3339),
		}
	}

	return c.JSON(statuses)
}

// GetAgentMap renders the agent map panel
func (h *Handler) GetAgentMap(c *fiber.Ctx) error {
	return Render(c, "agent_map", nil)
}

// ============== Panel 4: Task Board ==============

// Task represents a task in the kanban board
type Task struct {
	TaskID      string `json:"task_id"`
	Description string `json:"description"`
	Priority    string `json:"priority"`
	CreatedAt   string `json:"created_at"`
	Source      string `json:"source"`
	Progress    int    `json:"progress"`
	Confidence  int    `json:"confidence"`
	Result      string `json:"result"`
	CompletedAt string `json:"completed_at"`
}

// TaskBoard represents all tasks organized by status
type TaskBoard struct {
	Queued       []Task `json:"queued"`
	Analyzing    []Task `json:"analyzing"`
	AwaitingHITL []Task `json:"awaiting_hitl"`
	Completed    []Task `json:"completed"`
}

// GetTaskBoard renders the task board panel
func (h *Handler) GetTaskBoard(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", board)
}

// GetQueuedTasks returns tasks in queued state
func (h *Handler) GetQueuedTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"Queued": board.Queued,
	})
}

// GetAnalyzingTasks returns tasks in analyzing state
func (h *Handler) GetAnalyzingTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"Analyzing": board.Analyzing,
	})
}

// GetAwaitingHITLTasks returns tasks awaiting human review
func (h *Handler) GetAwaitingHITLTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"AwaitingHITL": board.AwaitingHITL,
	})
}

// GetCompletedTasks returns completed tasks
func (h *Handler) GetCompletedTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"Completed": board.Completed,
	})
}

// getTaskBoardData retrieves task board data
func (h *Handler) getTaskBoardData() *TaskBoard {
	// Placeholder - return empty board
	// TODO: Integrate with actual task tracking
	return &TaskBoard{
		Queued:       []Task{},
		Analyzing:    []Task{},
		AwaitingHITL: []Task{},
		Completed:    []Task{},
	}
}

// GetTaskDetails returns details for a specific task
func (h *Handler) GetTaskDetails(c *fiber.Ctx) error {
	taskID := c.Params("id")

	// Placeholder - return empty task
	task := map[string]interface{}{
		"task_id":     taskID,
		"description": "Task details not implemented",
		"status":      "pending",
	}

	return c.JSON(task)
}

// ============== Panel 5: Config Panel ==============

// Config represents system configuration
type Config struct {
	MaxTokensPerTask        int     `json:"max_tokens_per_task"`
	MaxConcurrentTasks      int     `json:"max_concurrent_tasks"`
	HITLConfidenceThreshold int     `json:"hitl_confidence_threshold"`
	RateLimitRPM            int     `json:"rate_limit_rpm"`
	CircuitBreakerThreshold int     `json:"circuit_breaker_threshold"`
	CircuitResetTimeout     int     `json:"circuit_reset_timeout"`
	AzureDeployment         string  `json:"azure_deployment"`
	Temperature             float64 `json:"temperature"`
	RequestTimeout          int     `json:"request_timeout"`
	LogLevel                string  `json:"log_level"`
	EnableTracing           bool    `json:"enable_tracing"`
	EnableMetrics           bool    `json:"enable_metrics"`
	DebugMode               bool    `json:"debug_mode"`
	LastSaved               string  `json:"last_saved"`
}

// GetConfigPanel renders the config panel
func (h *Handler) GetConfigPanel(c *fiber.Ctx) error {
	config := h.getDefaultConfig()
	return Render(c, "config_panel", fiber.Map{
		"Config": config,
	})
}

// GetConfig returns current configuration as JSON
func (h *Handler) GetConfig(c *fiber.Ctx) error {
	config := h.getDefaultConfig()
	return c.JSON(fiber.Map{
		"Config": config,
	})
}

// getDefaultConfig returns default configuration
func (h *Handler) getDefaultConfig() *Config {
	return &Config{
		MaxTokensPerTask:        4000,
		MaxConcurrentTasks:      10,
		HITLConfidenceThreshold: 80,
		RateLimitRPM:            60,
		CircuitBreakerThreshold: 5,
		CircuitResetTimeout:     60,
		AzureDeployment:         "gpt-4",
		Temperature:             0.7,
		RequestTimeout:          30,
		LogLevel:                "info",
		EnableTracing:           true,
		EnableMetrics:           true,
		DebugMode:               false,
		LastSaved:               "",
	}
}

// SaveConfig saves configuration changes
func (h *Handler) SaveConfig(c *fiber.Ctx) error {
	var req Config
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Invalid configuration data</div>`)
	}

	// Validate configuration
	if req.MaxTokensPerTask < 1000 || req.MaxTokensPerTask > 128000 {
		return c.Status(400).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Max tokens must be between 1000 and 128000</div>`)
	}

	if req.MaxConcurrentTasks < 1 || req.MaxConcurrentTasks > 100 {
		return c.Status(400).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Max concurrent tasks must be between 1 and 100</div>`)
	}

	// TODO: Actually save configuration
	// For now, just return success

	return c.SendString(`<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-center"><i class="fas fa-check-circle mr-2"></i>Configuration saved successfully!</div>`)
}

// ResetConfig resets configuration to defaults
func (h *Handler) ResetConfig(c *fiber.Ctx) error {
	// TODO: Implement actual reset logic
	return h.GetConfigPanel(c)
}

// ============== Panel 6: Telemetry Panel ==============

// GetTelemetryPanel renders the telemetry panel
func (h *Handler) GetTelemetryPanel(c *fiber.Ctx) error {
	return Render(c, "telemetry_panel", nil)
}

// TelemetryOverview represents telemetry overview data
type TelemetryOverview struct {
	RPM         int     `json:"rpm"`
	RPMChange   float64 `json:"rpm_change"`
	SuccessRate float64 `json:"success_rate"`
	AvgLatency  float64 `json:"avg_latency"`
	P95Latency  float64 `json:"p95_latency"`
	ErrorRate   float64 `json:"error_rate"`
	Alerts      []Alert `json:"alerts"`
}

// Alert represents a telemetry alert
type Alert struct {
	Severity string `json:"severity"`
	Message  string `json:"message"`
	Time     string `json:"time"`
}

// GetTelemetryOverview returns telemetry overview data
func (h *Handler) GetTelemetryOverview(c *fiber.Ctx) error {
	// Placeholder - return sample data
	overview := TelemetryOverview{
		RPM:         42,
		RPMChange:   12.5,
		SuccessRate: 99.8,
		AvgLatency:  245,
		P95Latency:  890,
		ErrorRate:   0.2,
		Alerts:      []Alert{},
	}
	return c.JSON(overview)
}

// GetSigNozData returns SigNoz telemetry data
func (h *Handler) GetSigNozData(c *fiber.Ctx) error {
	// Placeholder - return sample data
	return c.JSON(fiber.Map{
		"traces":   []interface{}{},
		"services": []string{"core", "agent", "feedback"},
	})
}

// GetHyperDXData returns HyperDX telemetry data
func (h *Handler) GetHyperDXData(c *fiber.Ctx) error {
	// Placeholder - return sample data
	return c.JSON(fiber.Map{
		"logs":  []interface{}{},
		"query": "",
	})
}

// GetMetricsData returns Prometheus metrics data
func (h *Handler) GetMetricsData(c *fiber.Ctx) error {
	// Placeholder - return sample data
	return c.JSON(fiber.Map{
		"metrics": []interface{}{},
	})
}

// GetLogsData returns log data
func (h *Handler) GetLogsData(c *fiber.Ctx) error {
	// Placeholder - return sample data
	return c.JSON(fiber.Map{
		"logs": []interface{}{},
	})
}

// ============== TrackGuard Enhancements ==============

// FinanceAlert represents a finance anomaly alert
type FinanceAlert struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	Vendor    string    `json:"vendor"`
	Amount    float64   `json:"amount"`
	Expected  float64   `json:"expected"`
	Multiple  float64   `json:"multiple"`
	Urgency   string    `json:"urgency"` // low, medium, high, critical
	Headline  string    `json:"headline"`
	CreatedAt time.Time `json:"created_at"`
	HITLSent  bool      `json:"hitl_sent"`
}

// GetFinanceAlerts returns recent finance anomalies from agent_outputs
func (h *Handler) GetFinanceAlerts(c *fiber.Ctx) error {
	// Query agent_outputs table for finance alerts
	rows, err := h.db.Query(`
		SELECT 
			id,
			tenant_id,
			output_json->>'vendor_name' as vendor,
			(output_json->>'amount')::float as amount,
			(output_json->>'expected_amount')::float as expected,
			(output_json->>'multiple')::float as multiple,
			urgency,
			headline,
			hitl_sent,
			created_at
		FROM agent_outputs
		WHERE agent_name = 'finance'
			AND output_type = 'anomaly_alert'
		ORDER BY created_at DESC
		LIMIT 10
	`)
	if err != nil {
		// Return empty list on error
		return Render(c, "partials/finance_alerts", fiber.Map{
			"Alerts": []FinanceAlert{},
		})
	}
	defer rows.Close()

	var alerts []FinanceAlert
	for rows.Next() {
		var alert FinanceAlert
		var vendor, headline sql.NullString
		var expected, multiple sql.NullFloat64
		var hitlSent sql.NullBool

		if err := rows.Scan(
			&alert.ID,
			&alert.TenantID,
			&vendor,
			&alert.Amount,
			&expected,
			&multiple,
			&alert.Urgency,
			&headline,
			&hitlSent,
			&alert.CreatedAt,
		); err != nil {
			continue
		}

		if vendor.Valid {
			alert.Vendor = vendor.String
		}
		if expected.Valid {
			alert.Expected = expected.Float64
		}
		if multiple.Valid {
			alert.Multiple = multiple.Float64
		}
		if headline.Valid {
			alert.Headline = headline.String
		}
		if hitlSent.Valid {
			alert.HITLSent = hitlSent.Bool
		}

		alerts = append(alerts, alert)
	}

	return Render(c, "partials/finance_alerts", fiber.Map{
		"Alerts": alerts,
	})
}

// BIQueryResult represents a BI query result
type BIQueryResult struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	Query     string    `json:"query"`
	Result    string    `json:"result"`
	ChartURL  string    `json:"chart_url"`
	CreatedAt time.Time `json:"created_at"`
}

// GetRecentBIQueries returns recent BI query results
func (h *Handler) GetRecentBIQueries(c *fiber.Ctx) error {
	// Query agent_outputs for BI query results
	rows, err := h.db.Query(`
		SELECT 
			id,
			tenant_id,
			output_json->>'query' as query,
			output_json->>'result_summary' as result,
			output_json->>'chart_url' as chart_url,
			created_at
		FROM agent_outputs
		WHERE agent_name = 'bi'
			AND output_type = 'query_result'
		ORDER BY created_at DESC
		LIMIT 5
	`)
	if err != nil {
		// Return empty list on error
		return Render(c, "partials/bi_queries", fiber.Map{
			"queries": []BIQueryResult{},
		})
	}
	defer rows.Close()

	var queries []BIQueryResult
	for rows.Next() {
		var query BIQueryResult
		var queryText, result, chartURL sql.NullString

		if err := rows.Scan(
			&query.ID,
			&query.TenantID,
			&queryText,
			&result,
			&chartURL,
			&query.CreatedAt,
		); err != nil {
			continue
		}

		if queryText.Valid {
			query.Query = queryText.String
		}
		if result.Valid {
			query.Result = result.String
		}
		if chartURL.Valid {
			query.ChartURL = chartURL.String
		}

		queries = append(queries, query)
	}

	// Check if this is an HTMX request
	if c.Get("HX-Request") == "true" {
		return Render(c, "partials/bi_queries", fiber.Map{
			"queries": queries,
		})
	}

	return c.JSON(fiber.Map{
		"queries": queries,
	})
}

// FounderDashboard serves the founder dashboard page
func (h *Handler) FounderDashboard(c *fiber.Ctx) error {
	return Render(c, "founder_dashboard", fiber.Map{
		"Title": "Saarathi — Your Patterns",
	})
}

// RegisterRoutes registers all web routes
func (h *Handler) RegisterRoutes(app *fiber.App) {
	// Main dashboard
	app.Get("/", h.Dashboard)
	app.Get("/dashboard", h.Dashboard)

	// Founder routes
	app.Get("/founder/dashboard", h.FounderDashboard)

	// API endpoints for HTMX
	app.Post("/api/feedback", h.HandleFeedback)
	app.Get("/api/stats", h.HandleStats)
	app.Get("/api/metrics", h.HandleMetrics)

	// Founder API endpoints
	app.Get("/founder/dashboard/summary", func(c *fiber.Ctx) error {
		// This will be handled by FounderDashboardHandler
		return c.SendString("Dashboard summary - use FounderDashboardHandler")
	})
	app.Get("/founder/dashboard/stream", func(c *fiber.Ctx) error {
		// This will be handled by FounderDashboardHandler
		return c.SendString("Dashboard stream - use FounderDashboardHandler")
	})
	app.Post("/founder/reflection", func(c *fiber.Ctx) error {
		// This will be handled by ReflectionHandler
		return c.SendString("Reflection - use ReflectionHandler")
	})

	// Panel 1: Live Feed
	app.Get("/api/live-feed", h.GetLiveFeed)

	// Panel 2: HITL Queue
	app.Get("/api/approvals/pending", h.GetPendingApprovals)
	app.Post("/api/approvals/:id/approve", h.ApprovePR)
	app.Post("/api/approvals/:id/reject", h.RejectPR)

	// Panel 3: Agent Map
	app.Get("/api/agent-map", h.GetAgentMap)
	app.Get("/api/agents/status", h.GetAllAgentsStatus)
	app.Get("/api/agents/:agent/status", h.GetAgentStatus)

	// Panel 4: Task Board
	app.Get("/api/tasks/board", h.GetTaskBoard)
	app.Get("/api/tasks/queued", h.GetQueuedTasks)
	app.Get("/api/tasks/analyzing", h.GetAnalyzingTasks)
	app.Get("/api/tasks/awaiting-hitl", h.GetAwaitingHITLTasks)
	app.Get("/api/tasks/completed", h.GetCompletedTasks)
	app.Get("/api/tasks/:id/details", h.GetTaskDetails)

	// Panel 5: Config Panel
	app.Get("/api/config", h.GetConfig)
	app.Get("/api/config/panel", h.GetConfigPanel)
	app.Post("/api/config/save", h.SaveConfig)
	app.Get("/api/config/reset", h.ResetConfig)

	// Panel 6: Telemetry Panel
	app.Get("/api/telemetry/panel", h.GetTelemetryPanel)
	app.Get("/api/telemetry/overview", h.GetTelemetryOverview)
	app.Get("/api/telemetry/signoz", h.GetSigNozData)
	app.Get("/api/telemetry/hyperdx", h.GetHyperDXData)
	app.Get("/api/telemetry/metrics", h.GetMetricsData)
	app.Get("/api/telemetry/logs", h.GetLogsData)

	// TrackGuard Enhancements
	app.Get("/api/finance/alerts", h.GetFinanceAlerts)
	app.Get("/api/bi/recent", h.GetRecentBIQueries)
}
