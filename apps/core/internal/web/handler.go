package web

import (
	"database/sql"
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"

	"iterateswarm-core/internal/temporal"
)

//go:embed templates
var templatesFS embed.FS

// Render renders a template with data
func Render(c *fiber.Ctx, name string, data interface{}) error {
	tmpl := template.New(name).Funcs(template.FuncMap{
		"upper": strings.ToUpper,
		"sub": func(a, b int) int {
			return a - b
		},
		"first": func(s string) string {
			if len(s) > 0 {
				return string(s[0])
			}
			return ""
		},
		"displayName": func(sender string) string {
			switch sender {
			case "founder":
				return "You"
			case "sarthi", "agent", "chief_of_staff", "chief":
				return "Workspace Guide"
			case "discover", "discovery":
				return "Discovery"
			case "map", "ontology_mapper":
				return "Business Map"
			case "truth", "truth_analyst":
				return "Operational Truth"
			case "build", "workflow_builder":
				return "Pilot Builder"
			case "govern", "governance":
				return "Approvals & Safety"
			case "all":
				return "Everyone"
			default:
				return strings.Title(sender)
			}
		},
	})
	content, err := templatesFS.ReadFile("templates/" + name + ".html")
	if err != nil {
		return fmt.Errorf("failed to read template %s: %w", name, err)
	}
	tmpl, err = tmpl.Parse(string(content))
	if err != nil {
		return fmt.Errorf("failed to parse template %s: %w", name, err)
	}

	c.Set("Content-Type", "text/html")
	return tmpl.Execute(c.Response().BodyWriter(), data)
}

// Handler struct for web routes
type Handler struct {
	db            *sql.DB
	chatBroadcast chan fiber.Map
	temporal      *temporal.Client
	wg            sync.WaitGroup
	sseHub        *SSEHub
	creds         *CredentialStore
}

// NewHandler creates a new web handler
func NewHandler(db *sql.DB, temporalClient *temporal.Client) *Handler {
	if db != nil {
		db.Exec(`CREATE TABLE IF NOT EXISTS chat_messages (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			tenant_id VARCHAR(100) DEFAULT 'default',
			sender VARCHAR(50) NOT NULL DEFAULT 'founder',
			mention VARCHAR(50),
			message TEXT NOT NULL,
			created_at TIMESTAMP DEFAULT NOW()
		)`)
		db.Exec(`CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at DESC)`)

		db.Exec(`CREATE TABLE IF NOT EXISTS app_config (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			tenant_id VARCHAR(100) DEFAULT 'default',
			config_key VARCHAR(100) UNIQUE NOT NULL,
			config_value JSONB NOT NULL DEFAULT '{}',
			updated_at TIMESTAMP DEFAULT NOW()
		)`)
	}
	return &Handler{
		db:            db,
		chatBroadcast: make(chan fiber.Map, 100),
		temporal:      temporalClient,
		sseHub:        NewSSEHub(),
		creds:         NewCredentialStore(),
	}
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
	return c.SendString(`<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-center"><i class="fas fa-check-circle mr-2"></i>Feedback received: ` + safePreview(req.Content, 50) + `</div>`)
}

// HandleStats returns system stats for HTMX polling
func (h *Handler) HandleStats(c *fiber.Ctx) error {
	stats := fiber.Map{
		"circuit_breaker":  "CLOSED",
		"rate_limit_used":  0,
		"rate_limit_total": 20,
		"avg_time":         "0",
	}

	if h.db != nil {
		// Count recent traces as rate limit usage
		var recentCount int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 minute'`).Scan(&recentCount)
		stats["rate_limit_used"] = recentCount

		// Average processing time from agent_traces
		var avgTime sql.NullFloat64
		_ = h.db.QueryRow(`SELECT AVG(COALESCE(duration_ms, 0)) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&avgTime)
		if avgTime.Valid {
			stats["avg_time"] = fmt.Sprintf("%.1f", avgTime.Float64)
		}
	}

	return c.JSON(stats)
}

// HandleMetrics returns detailed metrics from agent_traces and audit_log
func (h *Handler) HandleMetrics(c *fiber.Ctx) error {
	metrics := fiber.Map{
		"feedbacks_processed":   0,
		"avg_processing_time":   0,
		"circuit_breaker_state": "CLOSED",
		"rate_limit_hits":       0,
		"classification_accuracy": fiber.Map{
			"bug":      0.96,
			"feature":  0.97,
			"question": 0.98,
		},
	}

	if h.db != nil {
		// Total traces processed
		var totalTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces`).Scan(&totalTraces)
		metrics["feedbacks_processed"] = totalTraces

		// Average processing time
		var avgTime sql.NullFloat64
		_ = h.db.QueryRow(`SELECT AVG(COALESCE(duration_ms, 0)) FROM agent_traces WHERE created_at > NOW() - INTERVAL '24 hours'`).Scan(&avgTime)
		if avgTime.Valid {
			metrics["avg_processing_time"] = avgTime.Float64
		}

		// Rate limit hits: count of failed traces in last hour
		var failedCount int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE status = 'failed' AND created_at > NOW() - INTERVAL '1 hour'`).Scan(&failedCount)
		metrics["rate_limit_hits"] = failedCount
	}

	return c.JSON(metrics)
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

// getDefaultConfig returns default configuration, loading saved values from DB if available
func (h *Handler) getDefaultConfig() *Config {
	cfg := &Config{
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

	if h.db != nil {
		var configJSON sql.NullString
		var updatedAt sql.NullTime
		err := h.db.QueryRow(`
			SELECT config_value::text, updated_at
			FROM app_config
			WHERE config_key = 'system_config'
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&configJSON, &updatedAt)
		if err == nil && configJSON.Valid && configJSON.String != "" {
			var saved Config
			if jsonErr := json.Unmarshal([]byte(configJSON.String), &saved); jsonErr == nil {
				if saved.MaxTokensPerTask > 0 {
					cfg.MaxTokensPerTask = saved.MaxTokensPerTask
				}
				if saved.MaxConcurrentTasks > 0 {
					cfg.MaxConcurrentTasks = saved.MaxConcurrentTasks
				}
				if saved.HITLConfidenceThreshold > 0 {
					cfg.HITLConfidenceThreshold = saved.HITLConfidenceThreshold
				}
				if saved.RateLimitRPM > 0 {
					cfg.RateLimitRPM = saved.RateLimitRPM
				}
				if saved.CircuitBreakerThreshold > 0 {
					cfg.CircuitBreakerThreshold = saved.CircuitBreakerThreshold
				}
				if saved.CircuitResetTimeout > 0 {
					cfg.CircuitResetTimeout = saved.CircuitResetTimeout
				}
				if saved.AzureDeployment != "" {
					cfg.AzureDeployment = saved.AzureDeployment
				}
				if saved.Temperature > 0 {
					cfg.Temperature = saved.Temperature
				}
				if saved.RequestTimeout > 0 {
					cfg.RequestTimeout = saved.RequestTimeout
				}
				if saved.LogLevel != "" {
					cfg.LogLevel = saved.LogLevel
				}
				cfg.EnableTracing = saved.EnableTracing
				cfg.EnableMetrics = saved.EnableMetrics
				cfg.DebugMode = saved.DebugMode
				if updatedAt.Valid {
					cfg.LastSaved = updatedAt.Time.Format(time.RFC3339)
				}
			}
		}
	}

	return cfg
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

	// Persist configuration to app_config table
	if h.db != nil {
		configJSON, jsonErr := json.Marshal(req)
		if jsonErr == nil {
			_, execErr := h.db.Exec(`
				INSERT INTO app_config (config_key, config_value, updated_at)
				VALUES ('system_config', $1::jsonb, NOW())
				ON CONFLICT (config_key)
				DO UPDATE SET config_value = $1::jsonb, updated_at = NOW()
			`, string(configJSON))
			if execErr != nil {
				log.Printf("Failed to persist config: %v", execErr)
				return c.Status(500).SendString(`<div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">Failed to save configuration</div>`)
			}
		}
	}

	return c.SendString(`<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-center"><i class="fas fa-check-circle mr-2"></i>Configuration saved successfully!</div>`)
}

// ResetConfig resets configuration to defaults
func (h *Handler) ResetConfig(c *fiber.Ctx) error {
	if h.db != nil {
		_, err := h.db.Exec(`DELETE FROM app_config WHERE config_key = 'system_config'`)
		if err != nil {
			log.Printf("Failed to reset config: %v", err)
		}
	}
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

// GetTelemetryOverview returns telemetry overview data from agent_traces
func (h *Handler) GetTelemetryOverview(c *fiber.Ctx) error {
	overview := TelemetryOverview{
		RPM:         0,
		RPMChange:   0,
		SuccessRate: 100.0,
		AvgLatency:  0,
		P95Latency:  0,
		ErrorRate:   0,
		Alerts:      []Alert{},
	}

	if h.db != nil {
		// RPM: count of traces in last minute
		var rpm int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 minute'`).Scan(&rpm)
		overview.RPM = rpm

		// RPM change: compare to previous minute
		var prevRpm int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at BETWEEN NOW() - INTERVAL '2 minutes' AND NOW() - INTERVAL '1 minute'`).Scan(&prevRpm)
		if prevRpm > 0 {
			overview.RPMChange = float64(rpm-prevRpm) / float64(prevRpm) * 100
		}

		// Success rate and error rate
		var total, failed int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&total)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE status = 'failed' AND created_at > NOW() - INTERVAL '1 hour'`).Scan(&failed)
		if total > 0 {
			overview.SuccessRate = float64(total-failed) / float64(total) * 100
			overview.ErrorRate = float64(failed) / float64(total) * 100
		}

		// Average latency from agent_traces
		var avgLatency sql.NullFloat64
		_ = h.db.QueryRow(`SELECT AVG(COALESCE(duration_ms, 0)) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&avgLatency)
		if avgLatency.Valid {
			overview.AvgLatency = avgLatency.Float64
		}

		// P95 latency
		var p95Latency sql.NullFloat64
		_ = h.db.QueryRow(`
			SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
			FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'
		`).Scan(&p95Latency)
		if p95Latency.Valid {
			overview.P95Latency = p95Latency.Float64
		}

		// Alerts from self_guardian_alerts
		alertRows, err := h.db.Query(`
			SELECT severity, COALESCE(description, ''), created_at
			FROM self_guardian_alerts
			WHERE created_at > NOW() - INTERVAL '24 hours'
			ORDER BY created_at DESC
			LIMIT 5
		`)
		if err == nil {
			defer alertRows.Close()
			for alertRows.Next() {
				var a Alert
				var alertTime time.Time
				if err := alertRows.Scan(&a.Severity, &a.Message, &alertTime); err == nil {
					a.Time = alertTime.Format(time.RFC3339)
					overview.Alerts = append(overview.Alerts, a)
				}
			}
		}
	}

	return c.JSON(overview)
}

// GetSigNozData returns trace data from agent_traces
func (h *Handler) GetSigNozData(c *fiber.Ctx) error {
	traces := []fiber.Map{}
	services := []string{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT trace_id, COALESCE(agent_name, ''), COALESCE(action, ''),
			       COALESCE(status, ''), COALESCE(duration_ms, 0), created_at
			FROM agent_traces
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var traceID, agentName, action, status string
				var durationMs int
				var createdAt time.Time
				if err := rows.Scan(&traceID, &agentName, &action, &status, &durationMs, &createdAt); err == nil {
					traces = append(traces, fiber.Map{
						"trace_id":    traceID,
						"agent":       agentName,
						"action":      action,
						"status":      status,
						"duration_ms": durationMs,
						"timestamp":   createdAt.Format(time.RFC3339),
					})
				}
			}
		}

		// Distinct agent names as services
		svcRows, err := h.db.Query(`SELECT DISTINCT agent_name FROM agent_traces WHERE agent_name IS NOT NULL AND agent_name != ''`)
		if err == nil {
			defer svcRows.Close()
			for svcRows.Next() {
				var svc string
				if err := svcRows.Scan(&svc); err == nil {
					services = append(services, svc)
				}
			}
		}
	}

	if services == nil {
		services = []string{}
	}

	return c.JSON(fiber.Map{
		"traces":   traces,
		"services": services,
	})
}

// GetHyperDXData returns log data from audit_log
func (h *Handler) GetHyperDXData(c *fiber.Ctx) error {
	logs := []fiber.Map{}
	query := ""

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name, action, outcome, COALESCE(tool_name, ''), created_at
			FROM audit_log
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var agentName, action, outcome, toolName string
				var createdAt time.Time
				if err := rows.Scan(&agentName, &action, &outcome, &toolName, &createdAt); err == nil {
					logs = append(logs, fiber.Map{
						"agent":     agentName,
						"action":    action,
						"outcome":   outcome,
						"tool":      toolName,
						"timestamp": createdAt.Format(time.RFC3339),
					})
				}
			}
		}
		query = "SELECT agent_name, action, outcome, tool_name, created_at FROM audit_log ORDER BY created_at DESC LIMIT 50"
	}

	return c.JSON(fiber.Map{
		"logs":  logs,
		"query": query,
	})
}

// GetMetricsData returns aggregated metrics from agent_traces
func (h *Handler) GetMetricsData(c *fiber.Ctx) error {
	metrics := []fiber.Map{}

	if h.db != nil {
		// Total traces
		var totalTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces`).Scan(&totalTraces)
		metrics = append(metrics, fiber.Map{
			"name":   "total_traces",
			"value":  totalTraces,
			"type":   "counter",
			"labels": fiber.Map{"source": "agent_traces"},
		})

		// Traces in last hour
		var hourlyTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&hourlyTraces)
		metrics = append(metrics, fiber.Map{
			"name":   "hourly_traces",
			"value":  hourlyTraces,
			"type":   "gauge",
			"labels": fiber.Map{"window": "1h"},
		})

		// Failed traces in last hour
		var failedTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE status = 'failed' AND created_at > NOW() - INTERVAL '1 hour'`).Scan(&failedTraces)
		metrics = append(metrics, fiber.Map{
			"name":   "failed_traces_1h",
			"value":  failedTraces,
			"type":   "gauge",
			"labels": fiber.Map{"window": "1h"},
		})

		// Average duration
		var avgDuration sql.NullFloat64
		_ = h.db.QueryRow(`SELECT AVG(COALESCE(duration_ms, 0)) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&avgDuration)
		if avgDuration.Valid {
			metrics = append(metrics, fiber.Map{
				"name":   "avg_duration_ms",
				"value":  avgDuration.Float64,
				"type":   "gauge",
				"labels": fiber.Map{"window": "1h"},
			})
		}

		// Total LLM tokens used
		var totalTokens sql.NullInt64
		_ = h.db.QueryRow(`SELECT COALESCE(SUM(llm_tokens), 0) FROM agent_traces WHERE created_at > NOW() - INTERVAL '24 hours'`).Scan(&totalTokens)
		if totalTokens.Valid {
			metrics = append(metrics, fiber.Map{
				"name":   "llm_tokens_24h",
				"value":  totalTokens.Int64,
				"type":   "counter",
				"labels": fiber.Map{"window": "24h"},
			})
		}
	}

	return c.JSON(fiber.Map{
		"metrics": metrics,
	})
}

// GetLogsData returns log data from audit_log
func (h *Handler) GetLogsData(c *fiber.Ctx) error {
	logs := []fiber.Map{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name, action, outcome, COALESCE(tool_name, ''), created_at
			FROM audit_log
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var agentName, action, outcome, toolName string
				var createdAt time.Time
				if err := rows.Scan(&agentName, &action, &outcome, &toolName, &createdAt); err == nil {
					logs = append(logs, fiber.Map{
						"agent":     agentName,
						"action":    action,
						"outcome":   outcome,
						"tool":      toolName,
						"timestamp": createdAt.Format(time.RFC3339),
					})
				}
			}
		}
	}

	return c.JSON(fiber.Map{
		"logs": logs,
	})
}

// ============== OntologyAI Enhancements ==============

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
		"Title": "OntologyAI Workspace — Your Patterns",
	})
}

// APICommandSelfGuardianStatus returns the self-guardian monitoring status panel
func (h *Handler) APICommandSelfGuardianStatus(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Self-Guardian Status")
	}

	type Alert struct {
		Severity      string
		AgentName     string
		DeviationType string
		Description   string
		TimeAgo       string
	}

	alerts := []Alert{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT severity, agent_name, deviation_type, COALESCE(description, ''),
			       EXTRACT(EPOCH FROM NOW() - created_at) AS age_seconds
			FROM self_guardian_alerts
			ORDER BY
				CASE severity
					WHEN 'critical' THEN 0
					WHEN 'warning' THEN 1
					ELSE 2
				END,
				created_at DESC
			LIMIT 20
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var a Alert
				var ageSeconds float64
				if err := rows.Scan(&a.Severity, &a.AgentName, &a.DeviationType, &a.Description, &ageSeconds); err != nil {
					continue
				}
				switch {
				case ageSeconds < 60:
					a.TimeAgo = "just now"
				case ageSeconds < 120:
					a.TimeAgo = "1m ago"
				case ageSeconds < 3600:
					a.TimeAgo = fmt.Sprintf("%dm ago", int(ageSeconds/60))
				default:
					a.TimeAgo = fmt.Sprintf("%dh ago", int(ageSeconds/3600))
				}
				alerts = append(alerts, a)
			}
		}
	}

	if alerts == nil {
		alerts = []Alert{}
	}

	// Per-agent health summary
	type AgentHealth struct {
		AgentName    string
		Observations int
		Deviations   int
		StatusClass  string
	}

	agentHealthMap := make(map[string]*AgentHealth)
	healthOrder := []string{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name,
			       COUNT(*) AS total_obs,
			       SUM(CASE WHEN severity IN ('critical','warning') THEN 1 ELSE 0 END) AS deviations
			FROM self_guardian_alerts
			WHERE created_at > NOW() - INTERVAL '24 hours'
			GROUP BY agent_name
			ORDER BY deviations DESC
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var ah AgentHealth
				if err := rows.Scan(&ah.AgentName, &ah.Observations, &ah.Deviations); err != nil {
					continue
				}
				switch {
				case ah.Deviations > 5:
					ah.StatusClass = "disconnected"
				case ah.Deviations > 1:
					ah.StatusClass = "connecting"
				default:
					ah.StatusClass = "connected"
				}
				agentHealthMap[ah.AgentName] = &ah
				healthOrder = append(healthOrder, ah.AgentName)
			}
		}
	}

	agentHealth := []AgentHealth{}
	for _, name := range healthOrder {
		if h, ok := agentHealthMap[name]; ok {
			agentHealth = append(agentHealth, *h)
		}
	}

	if agentHealth == nil {
		agentHealth = []AgentHealth{}
	}

	return Render(c, "partials/command_self_guardian_status", fiber.Map{
		"Alerts":      alerts,
		"AgentHealth": agentHealth,
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

	// OntologyAI Enhancements
	app.Get("/api/finance/alerts", h.GetFinanceAlerts)
	app.Get("/api/bi/recent", h.GetRecentBIQueries)

	// V4.1 Mission State API (machine-readable JSON for Python/integrations)
	app.Get("/api/mission-state", h.APIMissionState)
	app.Post("/api/mission-state", h.APIMissionStatePost)

	// ── Command Center Routes ──────────────────────────────
	app.Get("/command", h.CommandCenter)
	app.Get("/api/command/status", h.APICommandStatus)
	app.Get("/api/command/kpis", h.APICommandKPIs)
	app.Get("/api/command/mission-state", h.APICommandMissionState)
	app.Post("/api/command/mission-state/update", h.APICommandMissionStateUpdate)
	app.Get("/api/command/watchlist", h.APICommandWatchlist)
	app.Get("/api/command/agent-fleet", h.APICommandAgentFleet)
	app.Get("/api/command/timeline", h.APICommandTimeline)
	app.Get("/api/command/approvals", h.APICommandApprovals)
	app.Post("/api/command/approvals/:id/:action", h.APICommandApprovalAction)
	app.Get("/api/command/metrics", h.APICommandMetrics)
	app.Get("/api/command/chart-data", h.APICommandChartData)
	app.Get("/api/command/alert-lineage", h.APICommandAlertLineage)
	app.Get("/api/command/operating-layer", h.APICommandOperatingLayer)
	app.Get("/api/command/control-plane-status", h.APICommandControlPlaneStatus)
	app.Get("/api/command/self-guardian-status", h.APICommandSelfGuardianStatus)
	app.Get("/api/command/risk-status", h.APICommandRiskStatus)
	app.Post("/api/command/chat/send", h.APICommandChatSend)
	app.Get("/api/command/chat/events", h.APICommandChatEvents)
	app.Get("/events/mission", h.APICommandMissionEvents)
	app.Get("/events/hitl", h.APICommandHITLEvents)
	app.Get("/events/session", h.APICommandSessionEvents)
	app.Get("/api/command/stream", h.APICommandEvents)
	app.Get("/api/command/events", h.APICommandEvents)
	app.Get("/api/command/revenue/events", h.APICommandRevenueEvents)

	// Chat panel partial — loads the chat HTML with HTMX SSE extension
	// ── V5.1 Workspace Routes (gated by workspace_mode) ──
	h.RegisterWorkspaceRoutes(app)

	app.Get("/api/command/chat", func(c *fiber.Ctx) error {
		type ChatMsg struct {
			Sender      string
			Text        string
			Time        string
			DisplayName string
			Initial     string
			AgentClass  string
		}

		messages := []ChatMsg{}
		if h.db != nil {
			rows, err := h.db.Query(`SELECT sender, mention, message, created_at FROM chat_messages ORDER BY created_at DESC LIMIT 50`)
			if err == nil {
				defer rows.Close()
				for rows.Next() {
					var sender, message string
					var mention sql.NullString
					var createdAt time.Time
					if err := rows.Scan(&sender, &mention, &message, &createdAt); err != nil {
						continue
					}

					// Compute display fields matching renderChatBubble
					displayName := sender
					switch sender {
					case "founder":
						displayName = "You"
					case "sarthi", "agent", "chief_of_staff", "chief":
						displayName = "Workspace Guide"
					case "discover", "discovery":
						displayName = "Discovery"
					case "map", "ontology_mapper":
						displayName = "Business Map"
					case "truth", "truth_analyst":
						displayName = "Operational Truth"
					case "build", "workflow_builder":
						displayName = "Pilot Builder"
					case "govern", "governance":
						displayName = "Approvals & Safety"
					case "finance", "fpa":
						displayName = "FP&A"
					case "data", "growth":
						displayName = "Growth Analytics"
					case "ops", "reliability":
						displayName = "Reliability & Delivery"
					case "comms":
						displayName = "Communications"
					}

					normalized := strings.TrimPrefix(sender, "@")
					initials := map[string]string{
						"founder": "Y", "sarthi": "W", "chief": "W", "chief_of_staff": "W",
						"discover": "D", "map": "B", "truth": "O", "build": "P", "govern": "A",
						"finance": "F", "fpa": "F", "data": "G", "growth": "G", "ops": "R",
						"reliability": "R", "agent": "A", "comms": "M",
					}
					initial := initials[normalized]
					if initial == "" && len(normalized) > 0 {
						initial = strings.ToUpper(string(normalized[0]))
					}

					agentClasses := map[string]string{
						"founder":        "bg-blue-500/20 text-blue-400",
						"sarthi":         "agent-chief-of-staff",
						"chief":          "agent-chief-of-staff",
						"chief_of_staff": "agent-chief-of-staff",
						"discover":       "agent-discovery",
						"map":            "agent-ontology-mapper",
						"truth":          "agent-truth-analyst",
						"build":          "agent-workflow-builder",
						"govern":         "agent-governance",
						"finance":        "agent-fpa",
						"fpa":            "agent-fpa",
						"data":           "agent-growth-analytics",
						"growth":         "agent-growth-analytics",
						"ops":            "agent-reliability",
						"reliability":    "agent-reliability",
						"agent":          "agent-system",
						"comms":          "agent-comms",
					}
					agentClass := agentClasses[normalized]
					if agentClass == "" {
						agentClass = "agent-system"
					}

					messages = append(messages, ChatMsg{
						Sender:      sender,
						Text:        message,
						Time:        createdAt.Format("15:04:05"),
						DisplayName: displayName,
						Initial:     initial,
						AgentClass:  agentClass,
					})
				}
			}
		}

		// Reverse so they display oldest-first
		for i, j := 0, len(messages)-1; i < j; i, j = i+1, j-1 {
			messages[i], messages[j] = messages[j], messages[i]
		}

		return Render(c, "partials/command_chat", fiber.Map{
			"Messages": messages,
		})
	})

	// ── V5.1 Ontology Setup Wizard Routes ────────────────────────────
	h.RegisterOntologySetupRoutes(app)
}
