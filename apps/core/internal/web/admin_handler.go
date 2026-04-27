package web

import (
	"bufio"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
	"iterateswarm-core/internal/api"
)

// AdminDashboard serves the main admin dashboard
func (h *Handler) AdminDashboard(c *fiber.Ctx) error {
	return Render(c, "admin-dashboard", fiber.Map{
		"Title":       "Admin Dashboard",
		"ActivePanel": "dashboard",
	})
}

// AdminLiveFeed serves the live feed panel
func (h *Handler) AdminLiveFeed(c *fiber.Ctx) error {
	return Render(c, "admin-live-feed", fiber.Map{
		"Title":       "Live Feed",
		"ActivePanel": "live-feed",
	})
}

// AdminTaskBoard serves the task board panel
func (h *Handler) AdminTaskBoard(c *fiber.Ctx) error {
	return Render(c, "admin-task-board", fiber.Map{
		"Title":       "Task Board",
		"ActivePanel": "task-board",
	})
}

// AdminAgentMap serves the agent map panel
func (h *Handler) AdminAgentMap(c *fiber.Ctx) error {
	return Render(c, "admin-agent-map", fiber.Map{
		"Title":       "Agent Map",
		"ActivePanel": "agent-map",
	})
}

// AdminHITLQueue serves the HITL queue panel
func (h *Handler) AdminHITLQueue(c *fiber.Ctx) error {
	return Render(c, "admin-hitl-queue", fiber.Map{
		"Title":       "HITL Queue",
		"ActivePanel": "hitl-queue",
	})
}

// AdminConfig serves the config panel
func (h *Handler) AdminConfig(c *fiber.Ctx) error {
	return Render(c, "admin-config", fiber.Map{
		"Title":       "Configuration",
		"ActivePanel": "config",
	})
}

// AdminTelemetry serves the telemetry panel
func (h *Handler) AdminTelemetry(c *fiber.Ctx) error {
	return Render(c, "admin-telemetry", fiber.Map{
		"Title":       "Telemetry",
		"ActivePanel": "telemetry",
	})
}

// API: Get active tasks count
func (h *Handler) APIActiveTasks(c *fiber.Ctx) error {
	// TODO: Get from Redis/Temporal
	return c.SendString("0")
}

// API: Get pending HITL count
func (h *Handler) APIPendingHITL(c *fiber.Ctx) error {
	// Check if HTMX request - return partial
	if c.Get("HX-Request") == "true" {
		// Return HTMX partial with count badge
		return c.SendString(`<span class="inline-flex items-center justify-center w-6 h-6 text-xs font-bold text-white bg-red-500 rounded-full">0</span>`)
	}
	// TODO: Get from Redis
	return c.SendString("0")
}

// API: Get completed tasks count
func (h *Handler) APICompletedTasks(c *fiber.Ctx) error {
	// TODO: Get from database
	return c.SendString("0")
}

// API: Get token usage
func (h *Handler) APITokenUsage(c *fiber.Ctx) error {
	// TODO: Get from TokenBudgetManager
	return c.SendString("0 / 100K")
}

// API: Get recent activity
func (h *Handler) APIRecentActivity(c *fiber.Ctx) error {
	// Return HTML for recent activity
	html := `<div class="p-4 text-center text-gray-500">No recent activity</div>`
	return c.SendString(html)
}

// API: SSE events endpoint
func (h *Handler) APIEvents(c *fiber.Ctx) error {
	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		// Send initial connection message
		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\"}\n\n")
		w.Flush()

		// Keep connection alive with heartbeat
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				w.Flush()
			case <-c.Context().Done():
				return
			}
		}
	})

	return nil
}

// API: Get tasks for task board
func (h *Handler) APITasks(c *fiber.Ctx) error {
	// Return HTML for task columns
	html := `
		<div class="space-y-3">
			<div class="bg-white p-3 rounded shadow cursor-pointer hover:shadow-md" onclick="showTaskDetail('task-1')">
				<p class="font-medium text-sm">Sample Task</p>
				<p class="text-xs text-gray-500 mt-1">Waiting for processing...</p>
			</div>
		</div>
	`
	return c.SendString(html)
}

// API: Get agent status
func (h *Handler) APIAgentStatus(c *fiber.Ctx) error {
	agents := []struct {
		Name         string
		Status       string
		StatusColor  string
		CurrentTask  string
		LastActivity string
	}{
		{"Supervisor", "idle", "bg-green-100 text-green-800", "-", "2m ago"},
		{"Researcher", "idle", "bg-gray-100 text-gray-800", "-", "5m ago"},
		{"SRE", "idle", "bg-gray-100 text-gray-800", "-", "10m ago"},
		{"SWE", "idle", "bg-gray-100 text-gray-800", "-", "15m ago"},
		{"Reviewer", "idle", "bg-gray-100 text-gray-800", "-", "20m ago"},
	}

	html := ""
	for _, agent := range agents {
		html += fmt.Sprintf(`
			<tr>
				<td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">%s</td>
				<td class="px-6 py-4 whitespace-nowrap"><span class="px-2 py-1 text-xs rounded-full %s">%s</span></td>
				<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">%s</td>
				<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">%s</td>
				<td class="px-6 py-4 whitespace-nowrap text-sm">
					<button onclick="showAgentDetails('%s')" class="text-indigo-600 hover:text-indigo-900">Details</button>
				</td>
			</tr>
		`, agent.Name, agent.StatusColor, agent.Status, agent.CurrentTask, agent.LastActivity, agent.Name)
	}

	return c.SendString(html)
}

// API: Get HITL queue
func (h *Handler) APIHITLQueue(c *fiber.Ctx) error {
	// Check if HTMX request - return partial
	if c.Get("HX-Request") == "true" {
		// Return HTMX partial with table rows
		html := `<tr class="hover:bg-gray-50" hx-get="/api/hitl/1/details" hx-trigger="click" hx-target="#hitl-detail">
			<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">HITL-001</td>
			<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">Burn rate alert</td>
			<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">2h ago</td>
			<td class="px-6 py-4 whitespace-nowrap">
				<button hx-post="/api/hitl/1/approve" hx-target="closest tr" hx-swap="outerHTML swap:0.3s" class="text-green-600 hover:text-green-900 mr-3">Approve</button>
				<button hx-post="/api/hitl/1/reject" hx-target="closest tr" hx-swap="outerHTML swap:0.3s" class="text-red-600 hover:text-red-900">Dismiss</button>
			</td>
		</tr>`
		return c.SendString(html)
	}
	// Return full page for non-HTMX
	html := `<div class="p-8 text-center text-gray-500">No items awaiting approval</div>`
	return c.SendString(html)
}

// API: Approve HITL item
func (h *Handler) APIHITLApprove(c *fiber.Ctx) error {
	taskID := c.Params("id")
	// Check if HTMX request - return partial for swap
	if c.Get("HX-Request") == "true" {
		// Return empty to remove row from view
		return c.SendString("")
	}
	// Return full page for non-HTMX
	return c.SendString(fmt.Sprintf(`<div class="p-4 bg-green-50 text-green-800">Approved %s</div>`, taskID))
}

// API: Reject HITL item
func (h *Handler) APIHITLReject(c *fiber.Ctx) error {
	taskID := c.Params("id")
	// Check if HTMX request - return partial for swap
	if c.Get("HX-Request") == "true" {
		// Return empty to remove row from view
		return c.SendString("")
	}
	// Return full page for non-HTMX
	return c.SendString(fmt.Sprintf(`<div class="p-4 bg-red-50 text-red-800">Rejected %s</div>`, taskID))
}

// HTMX Screen 1: Tenant Onboarding Status
func (h *Handler) APIOnboardingStatus(c *fiber.Ctx) error {
	if c.Get("HX-Request") == "true" {
		html := `
		<div class="grid grid-cols-2 gap-4" hx-get="/api/htmx/onboarding" hx-trigger="every 30s">
			<div class="p-4 bg-green-50 rounded-lg">
				<h3 class="font-semibold text-green-800">Slack</h3>
				<p class="text-sm text-green-600">Connected</p>
			</div>
			<div class="p-4 bg-green-50 rounded-lg">
				<h3 class="font-semibold text-green-800">Razorpay</h3>
				<p class="text-sm text-green-600">Connected</p>
			</div>
			<div class="p-4 bg-yellow-50 rounded-lg">
				<h3 class="font-semibold text-yellow-800">Telegram</h3>
				<p class="text-sm text-yellow-600">Pending setup</p>
			</div>
			<div class="p-4 bg-gray-50 rounded-lg">
				<h3 class="font-semibold text-gray-800">PostgreSQL</h3>
				<p class="text-sm text-gray-600">Not configured</p>
			</div>
		</div>`
		return c.SendString(html)
	}
	return c.SendString(`<div class="p-8">Onboarding status</div>`)
}

// HTMX Screen 2: Guardian Watchlist Viewer
func (h *Handler) APIWatchlist(c *fiber.Ctx) error {
	if c.Get("HX-Request") == "true" {
		html := `
		<div class="space-y-2" hx-get="/api/htmx/watchlist" hx-trigger="every 30s">
			<div class="flex items-center justify-between p-3 bg-white border rounded">
				<div>
					<p class="font-medium">FG-01: Burn rate alert</p>
					<p class="text-sm text-gray-500">Threshold: >5% weekly</p>
				</div>
				<button class="px-3 py-1 text-sm bg-red-100 text-red-800 rounded">Edit</button>
			</div>
			<div class="flex items-center justify-between p-3 bg-white border rounded">
				<div>
					<p class="font-medium">BG-02: Error spike alert</p>
					<p class="text-sm text-gray-500">Threshold: >10 errors/min</p>
				</div>
				<button class="px-3 py-1 text-sm bg-red-100 text-red-800 rounded">Edit</button>
			</div>
			<div class="flex items-center justify-between p-3 bg-white border rounded">
				<div>
					<p class="font-medium">OG-01: Deployment failure</p>
					<p class="text-sm text-gray-500">Threshold: any failure</p>
				</div>
				<button class="px-3 py-1 text-sm bg-red-100 text-red-800 rounded">Edit</button>
			</div>
		</div>`
		return c.SendString(html)
	}
	return c.SendString(`<div class="p-8">Watchlist</div>`)
}

// HTMX Screen 3: LLMOps Dashboard
func (h *Handler) APILLMOpsDashboard(c *fiber.Ctx) error {
	if c.Get("HX-Request") == "true" {
		html := `
		<div class="grid grid-cols-3 gap-4" hx-get="/api/htmx/llmops" hx-trigger="every 30s">
			<div class="p-4 bg-blue-50 rounded-lg">
				<p class="text-2xl font-bold">94%</p>
				<p class="text-sm text-blue-600">Alert quality score</p>
			</div>
			<div class="p-4 bg-green-50 rounded-lg">
				<p class="text-2xl font-bold">87%</p>
				<p class="text-sm text-green-600">Acknowledge rate</p>
			</div>
			<div class="p-4 bg-purple-50 rounded-lg">
				<p class="text-2xl font-bold">0.82</p>
				<p class="text-sm text-purple-600">Eval score</p>
			</div>
		</div>`
		return c.SendString(html)
	}
	return c.SendString(`<div class="p-8">LLMOps dashboard</div>`)
}

// API: Save agent config
func (h *Handler) APIConfigAgents(c *fiber.Ctx) error {
	return c.SendString(`<div class="p-3 bg-green-50 text-green-800 rounded">Agent settings saved</div>`)
}

// API: Save budget config
func (h *Handler) APIConfigBudget(c *fiber.Ctx) error {
	return c.SendString(`<div class="p-3 bg-green-50 text-green-800 rounded">Budget settings saved</div>`)
}

// API: Get telemetry stats
func (h *Handler) APITelemetryStats(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"error_rate":   "0.1%",
		"avg_response": "245ms",
		"traces_min":   "120",
		"log_volume":   "5.2K/min",
	})
}

// RegisterAdminRoutes registers all admin routes
func (h *Handler) RegisterAdminRoutes(app *fiber.App) {
	// Admin pages - require auth
	admin := app.Group("/admin", api.RequireAuth())
	admin.Get("/", h.AdminDashboard)
	admin.Get("/live-feed", h.AdminLiveFeed)
	admin.Get("/task-board", h.AdminTaskBoard)
	admin.Get("/agent-map", h.AdminAgentMap)
	admin.Get("/hitl-queue", h.AdminHITLQueue)
	admin.Get("/config", h.AdminConfig)
	admin.Get("/telemetry", h.AdminTelemetry)

	// API endpoints - require auth
	apiGroup := app.Group("/api/admin", api.RequireAuth())

	// Dashboard stats
	apiGroup.Get("/stats/active-tasks", h.APIActiveTasks)
	apiGroup.Get("/stats/pending-hitl", h.APIPendingHITL)
	apiGroup.Get("/stats/completed", h.APICompletedTasks)
	apiGroup.Get("/stats/tokens", h.APITokenUsage)
	apiGroup.Get("/recent-activity", h.APIRecentActivity)

	// Live feed
	apiGroup.Get("/events", h.APIEvents)
	apiGroup.Get("/event-stats", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"supervisor": 0,
			"researcher": 0,
			"sre":        0,
			"swe":        0,
			"reviewer":   0,
		})
	})

	// Task board
	apiGroup.Get("/tasks", h.APITasks)
	apiGroup.Get("/tasks/:id", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-4">Task details for ` + c.Params("id") + `</div>`)
	})

	// Agent map
	apiGroup.Get("/agent-status", h.APIAgentStatus)
	apiGroup.Get("/agent-topology", func(c *fiber.Ctx) error {
		return c.SendString("") // SVG updated via HTMX
	})
	apiGroup.Get("/agents/:agent/details", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-4">Details for ` + c.Params("agent") + `</div>`)
	})

	// HITL queue
	apiGroup.Get("/hitl/count", h.APIPendingHITL)
	apiGroup.Get("/hitl/queue", h.APIHITLQueue)
	apiGroup.Get("/hitl/history", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-4 text-center text-gray-500">No history</div>`)
	})
	apiGroup.Get("/hitl/:id/details", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-4">Details for ` + c.Params("id") + `</div>`)
	})
	apiGroup.Post("/hitl/:id/approve", h.APIHITLApprove)
	apiGroup.Post("/hitl/:id/reject", h.APIHITLReject)
	apiGroup.Post("/hitl/approve-all", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-4 bg-green-50 text-green-800">All items approved</div>`)
	})

	// Config
	apiGroup.Post("/config/agents", h.APIConfigAgents)
	apiGroup.Post("/config/budget", h.APIConfigBudget)
	apiGroup.Post("/config/reload", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-3 bg-green-50 text-green-800 rounded">Configuration reloaded</div>`)
	})
	apiGroup.Get("/config/llm-status", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"calls":   42,
			"tokens":  "15.2K",
			"latency": "180ms",
		})
	})

	// Telemetry
	apiGroup.Get("/telemetry/stats", h.APITelemetryStats)
	apiGroup.Get("/telemetry/signoz-summary", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"services": 5,
			"errors":   2,
			"p99":      "320ms",
		})
	})
	apiGroup.Get("/telemetry/hyperdx-summary", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="p-3 bg-gray-50 rounded text-sm font-mono">No recent logs</div>`)
	})
	apiGroup.Get("/telemetry/agent-chart", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="text-gray-400">Chart data loading...</div>`)
	})
	apiGroup.Get("/telemetry/token-usage", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="text-gray-400">Loading token usage...</div>`)
	})
	apiGroup.Get("/telemetry/task-distribution", func(c *fiber.Ctx) error {
		return c.SendString(`<div class="text-gray-400">Loading distribution...</div>`)
	})

	// HTMX Screen 1: Tenant Onboarding Status
	apiGroup.Get("/htmx/onboarding", h.APIOnboardingStatus)

	// HTMX Screen 2: Guardian Watchlist Viewer
	apiGroup.Get("/htmx/watchlist", h.APIWatchlist)

	// HTMX Screen 3: LLMOps Dashboard
	apiGroup.Get("/htmx/llmops", h.APILLMOpsDashboard)
}
