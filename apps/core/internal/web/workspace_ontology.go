package web

import "github.com/gofiber/fiber/v2"

// APIWorkspaceOntology returns the ontology schema with empty object/link lists.
func (h *Handler) APIWorkspaceOntology(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"object_types": []string{
			"Party", "Engagement", "MoneyEvent", "Issue", "Message", "PlannedAction",
		},
		"link_types": []string{
			"party_engagement",
			"engagement_issue",
			"engagement_money_event",
			"issue_message",
			"engagement_action",
		},
		"objects": []any{},
		"links":   []any{},
	})
}
