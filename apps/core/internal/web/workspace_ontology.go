package web

import "github.com/gofiber/fiber/v2"

// V5_1_CANONICAL_OBJECT_TYPES lists the 6 canonical ontology entity types
// defined in the V5.1 product contract (PRD §14). Artifact / Decision / Metric
// are V6 BABOK view-model categories, not canonical ontology types.
var V5_1_CANONICAL_OBJECT_TYPES = []string{
	"Party",
	"Engagement",
	"MoneyEvent",
	"Issue",
	"Message",
	"PlannedAction",
	"Shipment",
}

// V5_1_CANONICAL_LINK_TYPES lists the 9 canonical directed relation types
// between the 6 canonical object types. Links referencing ExecutableWorkflowDraft
// or Workflow (shared-state / UI categories) are excluded from this API.
var V5_1_CANONICAL_LINK_TYPES = []string{
	"party_engagement",
	"engagement_money_event",
	"engagement_issue",
	"message_party",
	"message_engagement",
	"issue_planned_action",
	"money_event_planned_action",
	"party_planned_action",
	"engagement_planned_action",
	"order_shipment",
}

// APIWorkspaceOntology returns the V5.1 canonical ontology schema (PRD §14).
//
// The return type was increased from 6/5 to 9/11 briefly during implementation
// but was corrected back to the locked V5.1 contract of exactly 6 object types
// and 9 link types. The extra 3 object types (Artifact, Decision, Metric) are
// V6 BABOK view-model categories, not V5.1 canonical ontology types.
func (h *Handler) APIWorkspaceOntology(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"object_types": V5_1_CANONICAL_OBJECT_TYPES,
		"link_types":   V5_1_CANONICAL_LINK_TYPES,
		"objects":      []any{},
		"links":        []any{},
	})
}
