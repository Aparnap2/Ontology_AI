package web

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/gofiber/fiber/v2"
)

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

// APICommandApprovals returns approval items from planned_actions table
func (h *Handler) APICommandApprovals(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Approvals")
	}

	items := []fiber.Map{}
	remediationItems := []fiber.Map{}

	if h.db != nil {
		// 1. Planned actions (original approval items)
		rows, err := h.db.Query(`
			SELECT
				id,
				COALESCE(actor, ''),
				COALESCE(action_type, ''),
				COALESCE(target_ref, ''),
				COALESCE(risk_level, 'low'),
				COALESCE(approval_reason, ''),
				created_at
			FROM planned_actions
			WHERE status = 'planned'
			ORDER BY created_at DESC
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var id, actor, actionType, targetRef, riskLevel, reason string
				var createdAt time.Time
				if err := rows.Scan(&id, &actor, &actionType, &targetRef, &riskLevel, &reason, &createdAt); err != nil {
					continue
				}
				title := actor + " proposes " + actionType
				if targetRef != "" {
					title = actor + " proposes " + actionType + " on " + targetRef
				}
				if len(title) > 60 {
					title = title[:60] + "..."
				}
				desc := reason
				if len(desc) > 100 {
					desc = desc[:100] + "..."
				}
				items = append(items, fiber.Map{
					"ID": id, "Title": title, "Description": desc, "Type": "action",
				})
			}
		}

		// 2. Fix proposals from self-guardian (remediation items)
		fixRows, err := h.db.Query(`
			SELECT
				id,
				COALESCE(agent_name, ''),
				COALESCE(action, ''),
				COALESCE(description, ''),
				COALESCE(blast_radius, 'medium'),
				COALESCE(deviation_type, ''),
				created_at
			FROM self_guardian_fix_proposals
			WHERE status = 'pending'
			ORDER BY created_at DESC
		`)
		if err == nil {
			defer fixRows.Close()
			for fixRows.Next() {
				var id, agentName, action, description, blastRadius, deviationType string
				var createdAt time.Time
				if err := fixRows.Scan(&id, &agentName, &action, &description, &blastRadius, &deviationType, &createdAt); err != nil {
					continue
				}
				title := "Self-correction: " + agentName + " - " + action
				if len(title) > 60 {
					title = title[:60] + "..."
				}
				desc := description
				if len(desc) > 120 {
					desc = desc[:120] + "..."
				}
				items = append(items, fiber.Map{
					"ID":          id,
					"Title":       title,
					"Description": desc,
					"Type":        "remediation",
					"BlastRadius": blastRadius,
				})
			}
		}
	} else {
		// Fallback hardcoded items for development/testing when no DB is connected
		items = append(items, fiber.Map{
			"ID":          "investor-update-1",
			"Title":       "Investor update",
			"Description": "Quarterly investor update for Q2 2026 is ready for review",
			"Type":        "action",
		})
		items = append(items, fiber.Map{
			"ID":          "jira-issue-1",
			"Title":       "Jira issue",
			"Description": "New feature request requires prioritization approval",
			"Type":        "action",
		})
	}

	if items == nil {
		items = []fiber.Map{}
	}

	return Render(c, "partials/command_approvals", fiber.Map{
		"Items":            items,
		"RemediationItems": remediationItems,
	})
}

// APICommandApprovalAction approves or holds an approval item from planned_actions
func (h *Handler) APICommandApprovalAction(c *fiber.Ctx) error {
	id := c.Params("id")
	action := c.Params("action")

	// Look up the Temporal workflow ID from the planned_actions table
	workflowID := id // fallback to the URL param
	if h.db != nil {
		var temporalWorkflowID string
		err := h.db.QueryRow(
			`SELECT temporal_workflow_id FROM planned_actions WHERE id = $1`,
			id,
		).Scan(&temporalWorkflowID)
		if err == nil && temporalWorkflowID != "" {
			workflowID = temporalWorkflowID
		}
	}

	// Signal Temporal workflow on approval to unblock HITL gate
	if action == "approve" && h.temporal != nil && h.temporal.Client != nil {
		sigCtx, sigCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer sigCancel()
		if err := h.temporal.SignalWorkflow(sigCtx, workflowID, "hitl-approval", true); err != nil {
			log.Printf("ERROR: Failed to signal workflow %s for approval: %v", workflowID, err)
		}
	}

	if h.db != nil {
		var newStatus string
		switch action {
		case "approve":
			newStatus = "approved"
		case "hold":
			newStatus = "held"
		default:
			newStatus = "held"
		}
		_, err := h.db.Exec(`UPDATE planned_actions SET status = $1 WHERE id = $2`, newStatus, id)
		if err != nil {
			// Log error, but still return empty for HTMX swap removal
		}
	}

	// Workspace lifecycle contract (issue #61): an approval at this HITL gate
	// produces ACTION_APPROVED for the tenant's SSE subscribers.
	if action == "approve" {
		h.broadcastWorkspaceLifecycleEvent(c.Query("tenant_id", "default"), "ACTION_APPROVED", "Action approved", id)
	}

	if c.Get("HX-Request") == "true" {
		return c.SendString("")
	}
	return c.SendString(fmt.Sprintf("%s %s", action, id))
}
