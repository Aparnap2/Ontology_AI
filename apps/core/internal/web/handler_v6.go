package web

import (
	"github.com/gofiber/fiber/v2"
	"iterateswarm-core/internal/v6"
)

// RegisterV6Routes adds V6 API routes to the Fiber app.
//
// The web Handler implements v6.WorkspaceHandler, so the Founder Workspace
// (Milestone #5) is wired into the /v6 registry without a circular import:
// v6 owns the route registry, web owns the presentation.
func (h *Handler) RegisterV6Routes(app *fiber.App) {
	deps := &v6.Dependencies{
		GraphStore: nil, // wired in Milestone 1
		Workspace:  h,   // Founder Workspace (Milestone #5)
	}
	v6.RegisterRoutes(app, deps)
}
