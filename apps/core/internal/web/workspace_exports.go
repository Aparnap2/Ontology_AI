package web

import (
	"github.com/gofiber/fiber/v2"
)

// ArtifactExportResult is the shape returned by export endpoints.
type ArtifactExportResult struct {
	ArtifactType string         `json:"artifact_type"`
	EngagementID string         `json:"engagement_id"`
	Content      map[string]any `json:"content"`
	GeneratedAt  string         `json:"generated_at"`
}

// exportShapes returns the mock content for a given export type.
func exportShapes(exportType string) (fiber.Map, bool) {
	shapes := map[string]fiber.Map{
		"truth-map": {
			"artifact_type": "truth_map",
			"engagement_id": "default",
			"findings":      []any{},
			"generated_at":  nil,
		},
		"ontology-snapshot": {
			"artifact_type": "ontology_snapshot",
			"engagement_id": "default",
			"objects": map[string]any{
				"Party":         []any{},
				"Engagement":    []any{},
				"MoneyEvent":    []any{},
				"Issue":         []any{},
				"Message":       []any{},
				"PlannedAction": []any{},
			},
			"links":        []any{},
			"generated_at": nil,
		},
		"workflow-pack": {
			"artifact_type": "workflow_pack",
			"engagement_id": "default",
			"specs":         []any{},
			"generated_at":  nil,
		},
		"sop-pack": {
			"artifact_type": "sop_pack",
			"engagement_id": "default",
			"sops":          []any{},
			"generated_at":  nil,
		},
		"action-register": {
			"artifact_type": "action_register",
			"engagement_id": "default",
			"actions":       []any{},
			"generated_at":  nil,
		},
		"executable-draft": {
			"artifact_type": "executable_workflow_draft",
			"engagement_id": "default",
			"draft":         nil,
			"generated_at":  nil,
		},
	}
	shape, ok := shapes[exportType]
	return shape, ok
}

// APIExportGet returns a single artifact export by type.
// Supported types: truth-map, ontology-snapshot, workflow-pack,
//
//	sop-pack, action-register, executable-draft.
func (h *Handler) APIExportGet(c *fiber.Ctx) error {
	exportType := c.Params("type")
	shape, ok := exportShapes(exportType)
	if !ok {
		return c.Status(404).JSON(fiber.Map{"error": "unknown export type"})
	}
	return c.JSON(shape)
}

// APIExportsList returns the list of available export types with their names.
func (h *Handler) APIExportsList(c *fiber.Ctx) error {
	exportTypes := []fiber.Map{
		{"type": "truth-map", "name": "Truth Map"},
		{"type": "ontology-snapshot", "name": "Ontology Snapshot"},
		{"type": "workflow-pack", "name": "Workflow Pack"},
		{"type": "sop-pack", "name": "SOP Pack"},
		{"type": "action-register", "name": "Action Register"},
		{"type": "executable-draft", "name": "Executable Draft"},
	}
	return c.JSON(fiber.Map{"export_types": exportTypes})
}
