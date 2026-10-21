package v6

import "github.com/gofiber/fiber/v2"

// WorkspaceHandler is implemented by the Founder Workspace
// (apps/core/internal/web). It renders the Milestone #5 operational workspace
// panels and streams live updates over the existing SSEHub.
//
// Boundary (frozen in v6_system_architecture.md §1.4): the Founder Workspace
// is presentation and human-input collection only. These handlers read from
// stores (missions / mission_state / actions / mission_events) and render HTMX
// partials; they never contain business logic.
type WorkspaceHandler interface {
	// V6MorningBrief renders the morning brief partial: active mission count,
	// pending approvals count, system status (reuses /v6/status inventory),
	// and KPI/process health summary.
	V6MorningBrief(c *fiber.Ctx) error
	// V6Missions renders the mission feed/table partial with status badges.
	V6Missions(c *fiber.Ctx) error
	// V6Approvals renders the HITL approval queue partial.
	V6Approvals(c *fiber.Ctx) error
	// V6Timeline renders the append-only MISSION_* timeline partial.
	V6Timeline(c *fiber.Ctx) error

	// V6MissionsEvents streams mission events over SSE (event type "mission").
	V6MissionsEvents(c *fiber.Ctx) error
	// V6ApprovalsEvents streams approval events over SSE (event type "approval").
	V6ApprovalsEvents(c *fiber.Ctx) error
	// V6TimelineEvents streams MISSION_* timeline events over SSE.
	V6TimelineEvents(c *fiber.Ctx) error
}
