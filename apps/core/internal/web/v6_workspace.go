package web

import (
	"bufio"
	"context"
	"database/sql"
	"fmt"
	"html"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"

	"iterateswarm-core/internal/v6"
)

// ── Milestone #5 — Operational Workspace ─────────────────────────────────────
//
// Founder Workspace panels backed by the V6 domain tables (012_v6_domain.sql)
// and the compiled mission_state snapshot. Boundary (frozen in
// v6_system_architecture.md §1.4): presentation and human-input collection
// only. These handlers read from stores and render HTMX partials; they never
// contain business logic.
//
// SSE wiring reuses the existing SSEHub (per-tenant Subscribe/Publish with
// buffered channels) and the SetBodyStreamWriter pattern from
// command_center_chat.go / mission_workspace.go. Frames are re-emitted with
// the raw HTML fragment on the `data:` line so HTMX `sse-swap` renders them
// directly (see parseMissionMessage).

// ── Frozen workspace vocabulary ──────────────────────────────────────────────

// workspaceStatusLabel maps the missions table status to the frozen Mission
// Runtime workspace verb (ACTIVE / WAITING / INVESTIGATING / AWAITING_APPROVAL
// / EXECUTING / MONITORING / COMPLETED / FAILED / PAUSED). Statuses that have
// no frozen verb mapping (e.g. archived) fall back to the DB status uppercased.
func workspaceStatusLabel(status string) string {
	switch status {
	case "pending":
		return "WAITING"
	case "active":
		return "ACTIVE"
	case "stalled":
		return "INVESTIGATING"
	case "completed":
		return "COMPLETED"
	case "failed":
		return "FAILED"
	default:
		return strings.ToUpper(status)
	}
}

// workspaceStatusPill maps a missions table status to a pill colour class.
func workspaceStatusPill(status string) string {
	switch status {
	case "active":
		return "bg-blue-900/30 text-blue-400"
	case "pending":
		return "bg-yellow-900/30 text-yellow-400"
	case "stalled":
		return "bg-purple-900/30 text-purple-400"
	case "completed":
		return "bg-green-900/30 text-green-400"
	case "failed":
		return "bg-red-900/30 text-red-400"
	default:
		return "bg-gray-700/30 text-gray-400"
	}
}

// workspacePriorityPill maps a missions priority to a pill colour class.
func workspacePriorityPill(priority string) string {
	switch priority {
	case "urgent":
		return "bg-red-900/30 text-red-400"
	case "high":
		return "bg-orange-900/30 text-orange-400"
	case "medium":
		return "bg-yellow-900/30 text-yellow-400"
	default:
		return "bg-gray-700/30 text-gray-400"
	}
}

// missionEventToSSEEventName maps a mission_events.event_type to the frozen
// MISSION_* SSE event name (e.g. "created" → "MISSION_CREATED",
// "confidence_changed" → "MISSION_CONFIDENCE_CHANGED").
func missionEventToSSEEventName(eventType string) string {
	return "MISSION_" + strings.ToUpper(strings.ReplaceAll(eventType, "-", "_"))
}

// missionEventTypes is the frozen mission_events.event_type vocabulary from
// 012_v6_domain.sql (the append-only MISSION_* timeline).
var missionEventTypes = []string{
	"created", "started", "reviewed", "paused", "resumed", "replanned",
	"redirected", "approved", "rejected", "executed", "confidence_changed",
	"status_changed", "priority_changed", "evidence_added",
	"recommendation_updated", "completed", "archived",
}

// missionSSEEventNames returns every MISSION_* SSE event name for the frozen
// vocabulary. Used by the timeline SSE subscription so external publishers can
// push any mission event.
func missionSSEEventNames() []string {
	out := make([]string, len(missionEventTypes))
	for i, t := range missionEventTypes {
		out[i] = missionEventToSSEEventName(t)
	}
	return out
}

// ── Frozen workspace lifecycle SSE vocabulary (issue #61) ────────────────────
//
// Exactly these six events form the Founder Workspace live-update contract.
// They are emitted where the backend lifecycle produces them and consumed via
// the existing hx-ext="sse" declarative pattern (see timeline_panel.html
// sse-swap). Do not extend without updating the timeline partial and the
// subscription helpers below.
var workspaceLifecycleEvents = []string{
	"MISSION_UPDATED",
	"ACTION_PROPOSED",
	"ACTION_APPROVED",
	"ACTION_EXECUTED",
	"ACTION_VERIFIED",
	"MISSION_REPLANNED",
}

// WorkspaceLifecycleEvents returns a copy of the frozen six-event vocabulary.
func WorkspaceLifecycleEvents() []string {
	out := make([]string, len(workspaceLifecycleEvents))
	copy(out, workspaceLifecycleEvents)
	return out
}

// missionEventToLifecycleEvent maps a mission_events.event_type to the
// lifecycle contract: replanned → MISSION_REPLANNED, everything else →
// MISSION_UPDATED (generic mission refresh).
func missionEventToLifecycleEvent(eventType string) string {
	if eventType == "replanned" {
		return "MISSION_REPLANNED"
	}
	return "MISSION_UPDATED"
}

// actionStatusToLifecycleEvent maps an actions.status to the lifecycle
// contract: pending_approval → ACTION_PROPOSED, approved → ACTION_APPROVED,
// executing/completed → ACTION_EXECUTED. Statuses with no live-update contract
// (draft, rejected, failed) return "" and stay quiet.
func actionStatusToLifecycleEvent(status string) string {
	switch status {
	case "pending_approval":
		return "ACTION_PROPOSED"
	case "approved":
		return "ACTION_APPROVED"
	case "executing", "completed":
		return "ACTION_EXECUTED"
	default:
		return ""
	}
}

// v6MissionsSubscribedEvents is the SSEHub filter for the missions stream:
// the legacy "mission" refresh plus the mission-scoped lifecycle events.
func v6MissionsSubscribedEvents() []string {
	return []string{"mission", "MISSION_UPDATED", "MISSION_REPLANNED"}
}

// v6ApprovalsSubscribedEvents is the SSEHub filter for the approvals stream:
// the legacy "approval" refresh plus the action lifecycle events.
func v6ApprovalsSubscribedEvents() []string {
	return []string{"approval", "ACTION_PROPOSED", "ACTION_APPROVED", "ACTION_EXECUTED", "ACTION_VERIFIED"}
}

// v6TimelineSubscribedEvents is the SSEHub filter for the timeline stream:
// the generic refresh, every MISSION_* name, plus the six lifecycle events.
func v6TimelineSubscribedEvents() []string {
	out := append([]string{"timeline"}, missionSSEEventNames()...)
	return append(out, workspaceLifecycleEvents...)
}

// renderLifecycleFragment builds a minimal HTML fragment for a lifecycle
// event. Every caller-supplied field is escaped with html.EscapeString
// (project XSS rule); HTMX sse-swap renders the fragment directly.
func renderLifecycleFragment(eventName, summary, detail string) string {
	var b strings.Builder
	b.WriteString(`<div data-lifecycle-event="`)
	b.WriteString(html.EscapeString(eventName))
	b.WriteString(`"><span>`)
	b.WriteString(html.EscapeString(eventName))
	b.WriteString(`</span><span>`)
	b.WriteString(html.EscapeString(summary))
	b.WriteString(`</span>`)
	if detail != "" {
		b.WriteString(`<span>`)
		b.WriteString(html.EscapeString(detail))
		b.WriteString(`</span>`)
	}
	b.WriteString(`</div>`)
	return b.String()
}

// broadcastWorkspaceLifecycleEvent publishes a lifecycle event to a tenant's
// SSE subscribers. Payload HTML is escaped at construction.
func (h *Handler) broadcastWorkspaceLifecycleEvent(tenantID, eventName, summary, detail string) {
	if h.sseHub == nil {
		return
	}
	h.sseHub.Broadcast(tenantID, SSEEvent{
		Type:    eventName,
		Payload: renderLifecycleFragment(eventName, summary, detail),
	})
}

// missionEventSummary builds a short human summary for a timeline row.
func missionEventSummary(eventType, actor string) string {
	verb := strings.ReplaceAll(eventType, "_", " ")
	if actor != "" {
		return fmt.Sprintf("Mission %s · %s", verb, actor)
	}
	return "Mission " + verb
}

// ── Panel data types ─────────────────────────────────────────────────────────

// WorkspaceMission is a mission row rendered in the /v6/missions feed.
type WorkspaceMission struct {
	ID           string
	Title        string
	Description  string
	Status       string // real DB status (missions.status)
	StatusLabel  string // frozen workspace verb badge
	StatusPill   string // CSS pill class
	Priority     string
	PriorityPill string
	Confidence   float64
	EmployeeRole string
	UpdatedAt    string // RFC3339 (for timeAgo)
}

// V6Approval is an action awaiting approval in the /v6/approvals queue.
type V6Approval struct {
	ID           string
	EmployeeRole string
	Capability   string
	RiskTier     string
	PolicyTier   string
	Reason       string
	Confidence   float64
	CreatedAt    string
}

// WorkspaceTimelineEvent is a mission_events row rendered in the /v6/timeline
// feed. SSEEvent carries the MISSION_* event name used by the SSE stream.
type WorkspaceTimelineEvent struct {
	ID        string
	MissionID string
	EventType string
	SSEEvent  string
	Actor     string
	Source    string
	Summary   string
	Time      string // HH:MM
}

// ── GET /v6/morning-brief ────────────────────────────────────────────────────

// V6MorningBrief renders the morning brief partial: active mission count,
// pending approvals count, system status (reuses /v6/status inventory), and
// KPI/process health summary. Counts come from the real stores; when the DB is
// unavailable the partial renders a clearly-marked empty state.
func (h *Handler) V6MorningBrief(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Morning Brief")
	}
	tenantID := c.Query("tenant_id", "default")

	activeMissions := 0
	pendingApprovals := 0
	processesMapped := 0
	trustScore := 0
	trustScoreValid := false
	burnAlert := false
	mrrTrend := ""
	activeAlerts := ""

	if h.db != nil {
		// Active missions = in-flight rows (pending/active/stalled).
		if err := h.db.QueryRow(
			`SELECT COUNT(*) FROM missions WHERE tenant_id = $1 AND status IN ('pending','active','stalled')`,
			tenantID,
		).Scan(&activeMissions); err != nil {
			activeMissions = 0
		}
		// Pending approvals = actions awaiting human approval.
		if err := h.db.QueryRow(
			`SELECT COUNT(*) FROM actions WHERE tenant_id = $1 AND status = 'pending_approval'`,
			tenantID,
		).Scan(&pendingApprovals); err != nil {
			pendingApprovals = 0
		}
		// Process health summary = mapped processes count.
		if err := h.db.QueryRow(
			`SELECT COUNT(*) FROM processes WHERE tenant_id = $1`,
			tenantID,
		).Scan(&processesMapped); err != nil {
			processesMapped = 0
		}
		// KPI summary from the latest compiled mission_state snapshot.
		var ts sql.NullInt64
		var ba sql.NullBool
		var trend, alerts sql.NullString
		if err := h.db.QueryRow(
			`SELECT COALESCE(trust_score, 0), COALESCE(burn_alert, FALSE),
			        COALESCE(mrr_trend, ''), COALESCE(active_alerts, '')
			 FROM mission_state WHERE tenant_id = $1 ORDER BY updated_at DESC LIMIT 1`,
			tenantID,
		).Scan(&ts, &ba, &trend, &alerts); err == nil {
			trustScore = int(ts.Int64)
			trustScoreValid = ts.Valid
			burnAlert = ba.Bool
			mrrTrend = trend.String
			activeAlerts = alerts.String
		}
	}

	routeTotal, routeImplemented, routeStubs := v6.RouteStatus()

	return Render(c, "partials/morning_brief", fiber.Map{
		"ActiveMissions":   activeMissions,
		"PendingApprovals": pendingApprovals,
		"ProcessesMapped":  processesMapped,
		"TrustScore":       trustScore,
		"TrustScoreValid":  trustScoreValid,
		"BurnAlert":        burnAlert,
		"MRRTrend":         mrrTrend,
		"ActiveAlerts":     activeAlerts,
		"SystemInventory":  v6.RuntimeInventory(),
		"RouteTotal":       routeTotal,
		"RouteImplemented": routeImplemented,
		"RouteStubs":       routeStubs,
		"Version":          6,
		"Branch":           v6.Branch(),
		"EmptyState":       h.db == nil,
	})
}

// ── GET /v6/missions ─────────────────────────────────────────────────────────

// V6Missions renders the mission feed/table from the missions table with
// frozen-verb status badges. SSE-refreshed via the "mission" event.
func (h *Handler) V6Missions(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Missions")
	}
	tenantID := c.Query("tenant_id", "default")

	missions := []WorkspaceMission{}
	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT id, title, COALESCE(description, ''), status, priority,
			       COALESCE(confidence, 0), COALESCE(employee_role, ''), updated_at
			FROM missions
			WHERE tenant_id = $1
			ORDER BY updated_at DESC
			LIMIT 50
		`, tenantID)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var m WorkspaceMission
				var updatedAt time.Time
				if err := rows.Scan(&m.ID, &m.Title, &m.Description, &m.Status,
					&m.Priority, &m.Confidence, &m.EmployeeRole, &updatedAt); err != nil {
					continue
				}
				m.StatusLabel = workspaceStatusLabel(m.Status)
				m.StatusPill = workspaceStatusPill(m.Status)
				m.PriorityPill = workspacePriorityPill(m.Priority)
				m.UpdatedAt = updatedAt.Format(time.RFC3339)
				missions = append(missions, m)
			}
		}
	}

	return Render(c, "partials/missions_panel", fiber.Map{
		"Missions":   missions,
		"HasData":    h.db != nil && len(missions) > 0,
		"EmptyState": h.db == nil || len(missions) == 0,
	})
}

// ── GET /v6/approvals ────────────────────────────────────────────────────────

// V6Approvals renders the HITL approval queue from the actions table
// (status = 'pending_approval'). Approve/hold buttons post to the existing
// command-center approval action endpoint. SSE event type: "approval".
func (h *Handler) V6Approvals(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Approvals")
	}
	tenantID := c.Query("tenant_id", "default")

	approvals := []V6Approval{}
	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT id, employee_role, capability, risk_tier,
			       COALESCE(policy_tier, ''), COALESCE(reason, ''),
			       COALESCE(confidence, 0), created_at
			FROM actions
			WHERE tenant_id = $1 AND status = 'pending_approval'
			ORDER BY created_at DESC
			LIMIT 20
		`, tenantID)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var a V6Approval
				var createdAt time.Time
				if err := rows.Scan(&a.ID, &a.EmployeeRole, &a.Capability,
					&a.RiskTier, &a.PolicyTier, &a.Reason, &a.Confidence, &createdAt); err != nil {
					continue
				}
				a.CreatedAt = createdAt.Format(time.RFC3339)
				approvals = append(approvals, a)
			}
		}
	}

	return Render(c, "partials/approvals_panel", fiber.Map{
		"Approvals":  approvals,
		"HasData":    h.db != nil && len(approvals) > 0,
		"EmptyState": h.db == nil || len(approvals) == 0,
	})
}

// ── GET /v6/timeline ─────────────────────────────────────────────────────────

// V6Timeline renders the append-only MISSION_* timeline from mission_events.
// Live rows stream in via SSE with event names matching the MISSION_* verbs.
func (h *Handler) V6Timeline(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Timeline")
	}
	tenantID := c.Query("tenant_id", "default")

	events := []WorkspaceTimelineEvent{}
	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT id, mission_id, event_type, COALESCE(actor, ''),
			       COALESCE(source, ''), created_at
			FROM mission_events
			WHERE tenant_id = $1
			ORDER BY created_at DESC
			LIMIT 50
		`, tenantID)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var e WorkspaceTimelineEvent
				var createdAt time.Time
				if err := rows.Scan(&e.ID, &e.MissionID, &e.EventType,
					&e.Actor, &e.Source, &createdAt); err != nil {
					continue
				}
				e.SSEEvent = missionEventToSSEEventName(e.EventType)
				e.Summary = missionEventSummary(e.EventType, e.Actor)
				e.Time = createdAt.Format("15:04")
				events = append(events, e)
			}
		}
	}

	return Render(c, "partials/timeline_panel", fiber.Map{
		"Events":     events,
		"HasData":    h.db != nil && len(events) > 0,
		"EmptyState": h.db == nil || len(events) == 0,
		"TenantID":   tenantID,
	})
}

// ── SSE streams ──────────────────────────────────────────────────────────────

// V6MissionsEvents streams mission events over SSE. It subscribes to the
// legacy "mission" refresh plus the mission-scoped lifecycle events
// (MISSION_UPDATED, MISSION_REPLANNED) so hx-ext="sse" consumers stay live.
func (h *Handler) V6MissionsEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, v6MissionsSubscribedEvents()...)
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)
	return h.streamSSE(c, sub)
}

// V6ApprovalsEvents streams approval events over SSE. It subscribes to the
// legacy "approval" refresh plus the ACTION_* lifecycle events, and polls the
// actions / action_results tables so real DB lifecycle transitions broadcast.
func (h *Handler) V6ApprovalsEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, v6ApprovalsSubscribedEvents()...)
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go h.pollActionLifecycle(ctx, tenantID)

	return h.streamSSE(c, sub)
}

// V6TimelineEvents streams MISSION_* timeline events over SSE. It subscribes
// to "timeline" plus every MISSION_* event name plus the six lifecycle events
// so external publishers can push either a generic refresh, a specific mission
// event, or a lifecycle transition, and it polls mission_events for new rows
// so the feed is live with real data.
func (h *Handler) V6TimelineEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, v6TimelineSubscribedEvents()...)
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go h.pollMissionTimeline(ctx, tenantID)

	return h.streamSSE(c, sub)
}

// streamSSE writes an SSE stream that forwards hub frames to the client. The
// hub frame's data line carries a JSON SSEEvent envelope; we re-emit it with
// the raw HTML payload on the data line so HTMX sse-swap renders it directly.
func (h *Handler) streamSSE(c *fiber.Ctx, sub *Subscription) error {
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
				_, err := fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				if err != nil {
					return
				}
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				evt, err := parseMissionMessage(msgBytes)
				if err != nil {
					continue
				}
				_, err = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", evt.Type, evt.Payload)
				if err != nil {
					return
				}
				w.Flush()
			case <-done:
				return
			}
		}
	})

	return nil
}

// pollMissionTimeline polls mission_events for new rows every 3 seconds and
// broadcasts rendered MISSION_* fragments through the SSEHub so every
// connected timeline stream receives them. It is append-only: a watermark plus
// a recently-seen id set prevents replays and duplicate frames.
func (h *Handler) pollMissionTimeline(ctx context.Context, tenantID string) {
	if h.db == nil {
		return
	}
	watermark := time.Time{}
	seen := map[string]bool{}
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}

		rows, err := h.db.QueryContext(ctx, `
			SELECT id, mission_id, event_type, COALESCE(actor, ''),
			       COALESCE(source, ''), created_at
			FROM mission_events
			WHERE tenant_id = $1 AND created_at >= $2
			ORDER BY created_at ASC, id ASC
		`, tenantID, watermark.Add(-2*time.Second))
		if err != nil {
			continue
		}

		var maxTS time.Time
		for rows.Next() {
			var e WorkspaceTimelineEvent
			var createdAt time.Time
			if err := rows.Scan(&e.ID, &e.MissionID, &e.EventType,
				&e.Actor, &e.Source, &createdAt); err != nil {
				continue
			}
			if seen[e.ID] {
				continue
			}
			if createdAt.After(maxTS) {
				maxTS = createdAt
			}
			e.SSEEvent = missionEventToSSEEventName(e.EventType)
			e.Summary = missionEventSummary(e.EventType, e.Actor)
			e.Time = createdAt.Format("15:04")

			h.sseHub.Broadcast(tenantID, SSEEvent{
				Type:    e.SSEEvent,
				Payload: renderTimelineRowHTML(e),
			})

			// Lifecycle contract (issue #61): every mission_events row also
			// produces the mapped lifecycle event (replanned →
			// MISSION_REPLANNED, all others → MISSION_UPDATED) with the same
			// escaped row fragment, so hx-ext="sse" consumers of the six-event
			// vocabulary stay live off real DB reads.
			h.sseHub.Broadcast(tenantID, SSEEvent{
				Type:    missionEventToLifecycleEvent(e.EventType),
				Payload: renderTimelineRowHTML(e),
			})

			if len(seen) > 200 {
				seen = map[string]bool{}
			}
			seen[e.ID] = true
		}
		rows.Close()
		if maxTS.After(watermark) {
			watermark = maxTS
		}
	}
}

// pollActionLifecycle polls the actions table for lifecycle transitions and
// the action_results table for verifications, broadcasting the mapped
// ACTION_* lifecycle events through the SSEHub. It mirrors pollMissionTimeline:
// a recent-update window plus a last-broadcast map prevents replays. Only
// statuses with a lifecycle contract broadcast (see
// actionStatusToLifecycleEvent).
func (h *Handler) pollActionLifecycle(ctx context.Context, tenantID string) {
	if h.db == nil {
		return
	}
	lastBroadcast := map[string]string{}
	seenVerified := map[string]bool{}
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}

		rows, err := h.db.QueryContext(ctx, `
			SELECT id, status, COALESCE(employee_role, ''), COALESCE(capability, '')
			FROM actions
			WHERE tenant_id = $1 AND updated_at >= NOW() - INTERVAL '30 seconds'
			ORDER BY updated_at ASC
			LIMIT 20
		`, tenantID)
		if err != nil {
			continue
		}
		for rows.Next() {
			var id, status, role, capability string
			if err := rows.Scan(&id, &status, &role, &capability); err != nil {
				continue
			}
			evt := actionStatusToLifecycleEvent(status)
			if evt == "" {
				continue
			}
			if lastBroadcast[id] == evt {
				continue
			}
			if len(lastBroadcast) > 500 {
				lastBroadcast = map[string]string{}
			}
			lastBroadcast[id] = evt
			summary := "Action " + strings.ToLower(strings.TrimPrefix(evt, "ACTION_")) + " · " + capability
			if role != "" {
				summary += " · " + role
			}
			h.broadcastWorkspaceLifecycleEvent(tenantID, evt, summary, id)
		}
		rows.Close()

		vrows, err := h.db.QueryContext(ctx, `
			SELECT action_id
			FROM action_results
			WHERE tenant_id = $1 AND verified = TRUE AND updated_at >= NOW() - INTERVAL '30 seconds'
			ORDER BY updated_at ASC
			LIMIT 20
		`, tenantID)
		if err != nil {
			continue
		}
		for vrows.Next() {
			var actionID string
			if err := vrows.Scan(&actionID); err != nil {
				continue
			}
			if seenVerified[actionID] {
				continue
			}
			if len(seenVerified) > 500 {
				seenVerified = map[string]bool{}
			}
			seenVerified[actionID] = true
			h.broadcastWorkspaceLifecycleEvent(tenantID, "ACTION_VERIFIED", "Action verified", actionID)
		}
		vrows.Close()
	}
}

// renderTimelineRowHTML builds the HTML fragment for a single timeline row.
// It is hand-built (not a template) so every user/LLM-derived field is escaped
// with html.EscapeString (project XSS rule). Keep in sync with the row markup
// in partials/timeline_panel.html.
func renderTimelineRowHTML(e WorkspaceTimelineEvent) string {
	var b strings.Builder
	b.WriteString(`<div class="flex items-start gap-3 py-2.5 px-2 rounded-lg transition-colors duration-150 hover:bg-white/[0.02]" style="border-bottom:1px solid rgba(255,255,255,0.04)">`)
	b.WriteString(`<span class="text-[11px] font-mono flex-shrink-0 w-10 pt-0.5" style="color:var(--text-muted)">`)
	b.WriteString(html.EscapeString(e.Time))
	b.WriteString(`</span>`)
	b.WriteString(`<div class="flex-1 min-w-0">`)
	b.WriteString(`<div class="flex items-center gap-2 flex-wrap">`)
	b.WriteString(`<span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap" style="background:rgba(125,211,252,0.12);color:#bae6fd">`)
	b.WriteString(html.EscapeString(e.SSEEvent))
	b.WriteString(`</span>`)
	b.WriteString(`<span class="text-xs font-medium" style="color:var(--text)">`)
	b.WriteString(html.EscapeString(e.Summary))
	b.WriteString(`</span>`)
	b.WriteString(`</div>`)
	if e.Actor != "" {
		b.WriteString(`<p class="text-xs mt-0.5 truncate" style="color:var(--text-secondary)">actor: `)
		b.WriteString(html.EscapeString(e.Actor))
		b.WriteString(`</p>`)
	}
	b.WriteString(`</div>`)
	b.WriteString(`<span class="w-2 h-2 rounded-full flex-shrink-0 mt-1.5" style="background:var(--accent-blue);box-shadow:0 0 6px rgba(125,211,252,0.4)"></span>`)
	b.WriteString(`</div>`)
	return b.String()
}
