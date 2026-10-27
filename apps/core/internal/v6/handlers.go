package v6

import (
	"os"

	"github.com/gofiber/fiber/v2"
)

// Dependencies holds the services that V6 handlers delegate to.
// These are wired in as milestones progress.
type Dependencies struct {
	GraphStore GraphStore

	// Workspace is the Founder Workspace implementation (Milestone #5). It
	// renders the operational workspace panels and streams live updates over
	// the existing SSEHub. Presentation only — handlers read from stores and
	// render HTMX partials; no business logic lives in the handlers.
	Workspace WorkspaceHandler
}

// routeEntry describes a single V6 API route registered under the /v6 group.
// Path is relative to the /v6 group (e.g. "/evidence").
type routeEntry struct {
	Method      string
	Path        string
	Implemented bool
}

// v6Routes is the single source of truth for the V6 API surface.
// RegisterRoutes iterates this registry; /v6/status reports its counts.
var v6Routes = []routeEntry{
	{Method: "POST", Path: "/evidence", Implemented: false},
	{Method: "POST", Path: "/evidence/batch", Implemented: false},

	{Method: "GET", Path: "/workspace/:id", Implemented: false},
	{Method: "GET", Path: "/workspace/:id/entities", Implemented: false},
	{Method: "GET", Path: "/workspace/:id/decisions", Implemented: false},
	{Method: "GET", Path: "/workspace/:id/artifacts", Implemented: false},

	{Method: "POST", Path: "/decision", Implemented: false},
	{Method: "GET", Path: "/decision/:id", Implemented: false},
	{Method: "POST", Path: "/decision/:id/score", Implemented: false},

	{Method: "GET", Path: "/artifact/:id", Implemented: false},
	{Method: "POST", Path: "/artifact/:id/validate", Implemented: false},
	{Method: "POST", Path: "/artifact/:id/publish", Implemented: false},

	{Method: "POST", Path: "/validation/run", Implemented: false},
	{Method: "GET", Path: "/validation/:id", Implemented: false},

	{Method: "POST", Path: "/graph/query", Implemented: false},
	{Method: "GET", Path: "/graph/entity/:id", Implemented: false},
	{Method: "GET", Path: "/graph/entity/:id/traverse", Implemented: false},

	// ── Milestone #5 — Operational Workspace (Founder Workspace panels) ──
	{Method: "GET", Path: "/morning-brief", Implemented: true},
	{Method: "GET", Path: "/missions", Implemented: true},
	{Method: "GET", Path: "/approvals", Implemented: true},
	{Method: "GET", Path: "/timeline", Implemented: true},

	{Method: "GET", Path: "/health", Implemented: true},
	{Method: "GET", Path: "/status", Implemented: true},
}

// RegisterRoutes registers V6 API endpoints on the given Fiber router.
func RegisterRoutes(app fiber.Router, deps *Dependencies) {
	g := app.Group("/v6")

	for _, r := range v6Routes {
		handler := deps.handlerFor(r.Path)
		switch r.Method {
		case "GET":
			g.Get(r.Path, handler)
		case "POST":
			g.Post(r.Path, handler)
		}
	}

	// Operational workspace SSE streams (Milestone #5). These are supporting
	// surfaces for the four panels above and are intentionally NOT counted in
	// the registry route_status (the registry tracks API endpoints only).
	if deps != nil && deps.Workspace != nil {
		g.Get("/missions/events", deps.Workspace.V6MissionsEvents)
		g.Get("/approvals/events", deps.Workspace.V6ApprovalsEvents)
		g.Get("/timeline/events", deps.Workspace.V6TimelineEvents)
	}
}

// handlerFor maps a registry path to its handler.
func (d *Dependencies) handlerFor(path string) fiber.Handler {
	switch path {
	case "/evidence":
		return d.IngestEvidence
	case "/evidence/batch":
		return d.IngestEvidenceBatch
	case "/workspace/:id":
		return d.GetWorkspace
	case "/workspace/:id/entities":
		return d.GetWorkspaceEntities
	case "/workspace/:id/decisions":
		return d.GetWorkspaceDecisions
	case "/workspace/:id/artifacts":
		return d.GetWorkspaceArtifacts
	case "/decision":
		return d.CreateDecision
	case "/decision/:id":
		return d.GetDecision
	case "/decision/:id/score":
		return d.ScoreDecision
	case "/artifact/:id":
		return d.GetArtifact
	case "/artifact/:id/validate":
		return d.ValidateArtifact
	case "/artifact/:id/publish":
		return d.PublishArtifact
	case "/validation/run":
		return d.RunValidation
	case "/validation/:id":
		return d.GetValidationResult
	case "/graph/query":
		return d.QueryGraph
	case "/graph/entity/:id":
		return d.GetEntityGraph
	case "/graph/entity/:id/traverse":
		return d.TraverseEntity
	case "/morning-brief":
		if d.Workspace == nil {
			return notImplemented
		}
		return d.Workspace.V6MorningBrief
	case "/missions":
		if d.Workspace == nil {
			return notImplemented
		}
		return d.Workspace.V6Missions
	case "/approvals":
		if d.Workspace == nil {
			return notImplemented
		}
		return d.Workspace.V6Approvals
	case "/timeline":
		if d.Workspace == nil {
			return notImplemented
		}
		return d.Workspace.V6Timeline
	case "/health":
		return d.Health
	case "/status":
		return d.Status
	default:
		return func(c *fiber.Ctx) error {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{"error": "not found"})
		}
	}
}

// notImplemented is the shared 501 stub handler used by workspace routes when
// the Workspace implementation is not wired in.
var notImplemented = func(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// routeCounts tallies the registry by implementation status.
func routeCounts() (total, implemented, stubs int) {
	total = len(v6Routes)
	for _, r := range v6Routes {
		if r.Implemented {
			implemented++
		} else {
			stubs++
		}
	}
	return total, implemented, stubs
}

// branch returns the current git branch, falling back to "unknown".
func branch() string {
	if b := os.Getenv("GIT_BRANCH"); b != "" {
		return b
	}
	return "unknown"
}

// Branch returns the current git branch, falling back to "unknown". Exported
// so the Founder Workspace morning brief can reuse the /v6/status inventory.
func Branch() string { return branch() }

// runtimeInventory is the canonical V6 runtime inventory list (single source
// of truth shared by /v6/status and the morning brief).
var runtimeInventory = []string{
	"evidence",
	"knowledge",
	"mission",
	"employee",
	"capability",
	"memory",
	"governance",
	"workspace",
	"orchestration",
}

// RuntimeInventory returns the canonical V6 runtime inventory list.
func RuntimeInventory() []string { return runtimeInventory }

// RouteStatus returns the V6 route registry tallies (total, implemented, stubs).
func RouteStatus() (total, implemented, stubs int) { return routeCounts() }

// IngestEvidence validates and accepts a single evidence record.
func (d *Dependencies) IngestEvidence(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// IngestEvidenceBatch accepts multiple evidence records in one request.
func (d *Dependencies) IngestEvidenceBatch(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspace returns workspace details by ID.
func (d *Dependencies) GetWorkspace(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspaceEntities lists entities linked to a workspace.
func (d *Dependencies) GetWorkspaceEntities(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspaceDecisions lists decisions in a workspace.
func (d *Dependencies) GetWorkspaceDecisions(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspaceArtifacts lists artifacts in a workspace.
func (d *Dependencies) GetWorkspaceArtifacts(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// CreateDecision creates a new decision with associated evidence.
func (d *Dependencies) CreateDecision(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetDecision returns a decision by ID.
func (d *Dependencies) GetDecision(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// ScoreDecision triggers feasibility scoring for a decision.
func (d *Dependencies) ScoreDecision(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetArtifact returns an artifact by ID.
func (d *Dependencies) GetArtifact(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// ValidateArtifact triggers validation for an artifact.
func (d *Dependencies) ValidateArtifact(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// PublishArtifact publishes a validated artifact.
func (d *Dependencies) PublishArtifact(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// RunValidation runs validation rules against a workspace or artifact.
func (d *Dependencies) RunValidation(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetValidationResult returns validation result by ID.
func (d *Dependencies) GetValidationResult(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// QueryGraph runs a Cypher query against Neo4j.
func (d *Dependencies) QueryGraph(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetEntityGraph returns the graph surrounding an entity.
func (d *Dependencies) GetEntityGraph(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// TraverseEntity traverses relationships from an entity up to maxHops.
func (d *Dependencies) TraverseEntity(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// Health returns V6 service health status.
func (d *Dependencies) Health(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"status":  "ok",
		"version": "0.6.0",
	})
}

// Status returns V6 runtime inventory and route registry status.
func (d *Dependencies) Status(c *fiber.Ctx) error {
	total, implemented, stubs := routeCounts()
	return c.JSON(fiber.Map{
		"version":           6,
		"branch":            branch(),
		"runtime_inventory": runtimeInventory,
		"route_status": fiber.Map{
			"total":       total,
			"implemented": implemented,
			"stubs":       stubs,
		},
	})
}
