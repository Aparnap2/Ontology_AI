package web

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"

	"github.com/gofiber/fiber/v2"
)

// APIMissionState returns machine-readable JSON mission state (for Python/integrations)
func (h *Handler) APIMissionState(c *fiber.Ctx) error {
	if h.db != nil {
		var tenantID, summary string
		var statePayload sql.NullString
		err := h.db.QueryRow(`
			SELECT COALESCE(tenant_id, ''), COALESCE(summary, ''), COALESCE(state_payload::text, '')
			FROM mission_state
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&tenantID, &summary, &statePayload)
		if err == nil {
			var payload interface{}
			if statePayload.Valid && statePayload.String != "" {
				json.Unmarshal([]byte(statePayload.String), &payload)
			}
			return c.JSON(fiber.Map{
				"tenant_id":     tenantID,
				"summary":       summary,
				"state_payload": payload,
			})
		}
	}
	// Nil-DB or error fallback: return empty state
	return c.JSON(fiber.Map{"state": nil, "summary": "", "tenant_id": ""})
}

// APIMissionStatePost accepts validated JSON from Python and upserts into mission_state
func (h *Handler) APIMissionStatePost(c *fiber.Ctx) error {
	var payload struct {
		TenantID     string          `json:"tenant_id"`
		Summary      string          `json:"summary"`
		StatePayload json.RawMessage `json:"state_payload"`
	}
	if err := c.BodyParser(&payload); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "invalid JSON"})
	}
	if payload.TenantID == "" {
		return c.Status(400).JSON(fiber.Map{"error": "tenant_id required"})
	}
	if h.db != nil {
		_, err := h.db.Exec(`
			INSERT INTO mission_state (tenant_id, summary, state_payload)
			VALUES ($1, $2, $3::jsonb)
			ON CONFLICT (tenant_id) DO UPDATE SET
				summary = EXCLUDED.summary,
				state_payload = EXCLUDED.state_payload,
				updated_at = NOW()
		`, payload.TenantID, payload.Summary, string(payload.StatePayload))
		if err != nil {
			log.Printf("Failed to upsert mission state: %v", err)
		}
	}
	return c.Status(201).JSON(fiber.Map{"ok": true})
}

// APICommandControlPlaneStatus returns the control plane audit status panel
func (h *Handler) APICommandControlPlaneStatus(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Control Plane Status")
	}

	// Activity counts by time window
	recent5m := 0
	recent30m := 0
	recent24h := 0

	if h.db != nil {
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE created_at > NOW() - INTERVAL '5 minutes'`).Scan(&recent5m)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE created_at > NOW() - INTERVAL '30 minutes'`).Scan(&recent30m)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE created_at > NOW() - INTERVAL '24 hours'`).Scan(&recent24h)
	}

	// Agent summaries with outcome counts
	type AgentSummary struct {
		AgentName      string
		TotalActions   int
		FailedActions  int
		StatusDotClass string
	}

	agentSummaryMap := make(map[string]*AgentSummary)
	agentOrder := []string{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name, outcome, COUNT(*) as cnt
			FROM audit_log
			WHERE created_at > NOW() - INTERVAL '24 hours'
			GROUP BY agent_name, outcome
			ORDER BY agent_name
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var agent, outcome string
				var cnt int
				if err := rows.Scan(&agent, &outcome, &cnt); err != nil {
					continue
				}
				summary, exists := agentSummaryMap[agent]
				if !exists {
					summary = &AgentSummary{AgentName: agent}
					agentSummaryMap[agent] = summary
					agentOrder = append(agentOrder, agent)
				}
				summary.TotalActions += cnt
				if outcome == "failed" || outcome == "blocked" {
					summary.FailedActions += cnt
				}
			}
		}
	}

	agentSummaries := []AgentSummary{}
	for _, name := range agentOrder {
		s := agentSummaryMap[name]
		failRate := 0.0
		if s.TotalActions > 0 {
			failRate = float64(s.FailedActions) / float64(s.TotalActions) * 100
		}
		switch {
		case failRate > 20:
			s.StatusDotClass = "disconnected"
		case failRate > 5:
			s.StatusDotClass = "connecting"
		default:
			s.StatusDotClass = "connected"
		}
		agentSummaries = append(agentSummaries, *s)
	}

	if agentSummaries == nil {
		agentSummaries = []AgentSummary{}
	}

	// Recent audit events
	type AuditEvent struct {
		AgentName string
		Action    string
		ToolName  string
		Outcome   string
		TimeAgo   string
	}

	auditEvents := []AuditEvent{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name, action, COALESCE(tool_name, ''), outcome,
			       EXTRACT(EPOCH FROM NOW() - created_at) AS age_seconds
			FROM audit_log
			ORDER BY created_at DESC
			LIMIT 10
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var e AuditEvent
				var ageSeconds float64
				if err := rows.Scan(&e.AgentName, &e.Action, &e.ToolName, &e.Outcome, &ageSeconds); err != nil {
					continue
				}
				switch {
				case ageSeconds < 60:
					e.TimeAgo = "just now"
				case ageSeconds < 120:
					e.TimeAgo = "1m ago"
				case ageSeconds < 3600:
					e.TimeAgo = fmt.Sprintf("%dm ago", int(ageSeconds/60))
				default:
					e.TimeAgo = fmt.Sprintf("%dh ago", int(ageSeconds/3600))
				}
				auditEvents = append(auditEvents, e)
			}
		}
	}

	if auditEvents == nil {
		auditEvents = []AuditEvent{}
	}

	return Render(c, "partials/command_control_plane_status", fiber.Map{
		"Recent5m":       recent5m,
		"Recent30m":      recent30m,
		"Recent24h":      recent24h,
		"AgentSummaries": agentSummaries,
		"AuditEvents":    auditEvents,
	})
}

// APICommandRiskStatus returns the risk scan status panel
func (h *Handler) APICommandRiskStatus(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Risk Status")
	}

	// Scan counts by time window
	recent5m := 0
	recent30m := 0
	recent24h := 0
	blockCount := 0
	passCount := 0

	type RiskEvent struct {
		AgentName string
		Action    string
		Outcome   string
		TimeAgo   string
	}

	riskEvents := []RiskEvent{}

	if h.db != nil {
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE action IN ('prompt_risk_scan','output_risk_scan') AND created_at > NOW() - INTERVAL '5 minutes'`).Scan(&recent5m)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE action IN ('prompt_risk_scan','output_risk_scan') AND created_at > NOW() - INTERVAL '30 minutes'`).Scan(&recent30m)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE action IN ('prompt_risk_scan','output_risk_scan') AND created_at > NOW() - INTERVAL '24 hours'`).Scan(&recent24h)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE action IN ('prompt_risk_scan','output_risk_scan') AND outcome = 'blocked' AND created_at > NOW() - INTERVAL '24 hours'`).Scan(&blockCount)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM audit_log WHERE action IN ('prompt_risk_scan','output_risk_scan') AND outcome = 'completed' AND created_at > NOW() - INTERVAL '24 hours'`).Scan(&passCount)

		rows, err := h.db.Query(`
			SELECT agent_name, action, outcome,
			       EXTRACT(EPOCH FROM NOW() - created_at) AS age_seconds
			FROM audit_log
			WHERE action IN ('prompt_risk_scan','output_risk_scan')
			ORDER BY created_at DESC
			LIMIT 10
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var e RiskEvent
				var ageSeconds float64
				if err := rows.Scan(&e.AgentName, &e.Action, &e.Outcome, &ageSeconds); err != nil {
					continue
				}
				switch {
				case ageSeconds < 60:
					e.TimeAgo = "just now"
				case ageSeconds < 120:
					e.TimeAgo = "1m ago"
				case ageSeconds < 3600:
					e.TimeAgo = fmt.Sprintf("%dm ago", int(ageSeconds/60))
				default:
					e.TimeAgo = fmt.Sprintf("%dh ago", int(ageSeconds/3600))
				}
				riskEvents = append(riskEvents, e)
			}
		}
	}

	if riskEvents == nil {
		riskEvents = []RiskEvent{}
	}

	return Render(c, "partials/command_risk_status", fiber.Map{
		"Recent5m":   recent5m,
		"Recent30m":  recent30m,
		"Recent24h":  recent24h,
		"BlockCount": blockCount,
		"PassCount":  passCount,
		"RiskEvents": riskEvents,
	})
}
