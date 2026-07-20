package web

import "github.com/gofiber/fiber/v2"

// APIWorkspaceTruthFindings returns the truth findings with mock empty data.
func (h *Handler) APIWorkspaceTruthFindings(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"findings":      []any{},
		"engagement_id": "default",
	})
}
