package web

import (
	"context"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
)

// OntologySetupStep represents a step in the ontology setup wizard.
type OntologySetupStep struct {
	Number      int    `json:"number"`
	Name        string `json:"name"`
	Title       string `json:"title"`
	Description string `json:"description"`
}

// OntologySetupProgress tracks a user's progress through the setup wizard.
type OntologySetupProgress struct {
	EngagementID string                 `json:"engagement_id"`
	CurrentStep  int                    `json:"current_step"`
	Completed    bool                   `json:"completed"`
	StartedAt    string                 `json:"started_at"`
	UpdatedAt    string                 `json:"updated_at"`
	Data         map[string]interface{} `json:"data"`
}

// The 5 steps of the ontology setup wizard (V5.1 Pydantic-model aligned).
var ontologySetupSteps = []OntologySetupStep{
	{Number: 1, Name: "problem_framing", Title: "Problem Framing", Description: "Define business context, scope, and stakeholders"},
	{Number: 2, Name: "evidence_intake", Title: "Evidence Intake", Description: "Gather source documents, data sources, and notes"},
	{Number: 3, Name: "candidate_review", Title: "Candidate Review", Description: "Review proposed object types and relationships"},
	{Number: 4, Name: "relationship_review", Title: "Relationship Review", Description: "Define object relationships and cardinality"},
	{Number: 5, Name: "approval", Title: "Approval & Launch", Description: "Review and launch the ontology discovery process"},
}

// Step name -> number mapping for string-based route params.
var ontologyStepNameToNumber = map[string]int{
	"problem_framing":     1,
	"evidence_intake":     2,
	"candidate_review":    3,
	"relationship_review": 4,
	"approval":            5,
}

// Step number -> name mapping.
var ontologyStepNumberToName = map[int]string{
	1: "problem_framing",
	2: "evidence_intake",
	3: "candidate_review",
	4: "relationship_review",
	5: "approval",
}

// In-memory progress store (replace with DB in production).
var ontologySetupProgress = make(map[string]*OntologySetupProgress)

// APIOntologySetupStart returns the wizard start page for an engagement.
func (h *Handler) APIOntologySetupStart(c *fiber.Ctx) error {
	engagementID := c.Params("engagement_id")
	if engagementID == "" {
		return c.Status(400).SendString("engagement_id is required")
	}

	// Initialize or retrieve progress
	progress, exists := ontologySetupProgress[engagementID]
	if !exists {
		progress = &OntologySetupProgress{
			EngagementID: engagementID,
			CurrentStep:  1,
			Completed:    false,
			StartedAt:    time.Now().Format(time.RFC3339),
			UpdatedAt:    time.Now().Format(time.RFC3339),
			Data:         make(map[string]interface{}),
		}
		ontologySetupProgress[engagementID] = progress
	}

	if c.Get("HX-Request") != "true" {
		return c.JSON(fiber.Map{
			"engagement_id": engagementID,
			"current_step":  progress.CurrentStep,
			"completed":     progress.Completed,
		})
	}

	return Render(c, "partials/ontology_setup_start", fiber.Map{
		"EngagementID": engagementID,
		"CurrentStep":  progress.CurrentStep,
		"TotalSteps":   len(ontologySetupSteps),
		"Steps":        ontologySetupSteps,
		"Completed":    progress.Completed,
	})
}

// parseStepParam converts a step route parameter (string name or number) to
// a 1-based step index. Returns 0 if invalid.
func parseStepParam(stepStr string) int {
	// Try string-based step name first (Pydantic model names).
	if n, ok := ontologyStepNameToNumber[stepStr]; ok {
		return n
	}
	// Fall back to integer parsing (legacy support).
	n := 0
	for _, c := range stepStr {
		if c >= '0' && c <= '9' {
			n = n*10 + int(c-'0')
		} else {
			return 0
		}
	}
	return n
}

// resolveStepPartial returns the step-specific partial template name for a step name.
// Falls back to the generic step template.
func resolveStepPartial(stepName string) string {
	stepSpecific := map[string]string{
		"problem_framing":     "partials/ontology_setup_problem_framing",
		"evidence_intake":     "partials/ontology_setup_evidence_intake",
		"candidate_review":    "partials/ontology_setup_candidate_review",
		"relationship_review": "partials/ontology_setup_relationship_review",
		"approval":            "partials/ontology_setup_approval",
	}
	if tpl, ok := stepSpecific[stepName]; ok {
		return tpl
	}
	return "partials/ontology_setup_step"
}

// APIOntologySetupStep returns a specific step partial.
func (h *Handler) APIOntologySetupStep(c *fiber.Ctx) error {
	engagementID := c.Params("engagement_id")
	stepStr := c.Params("step")

	if engagementID == "" {
		return c.Status(400).SendString("engagement_id is required")
	}

	step := parseStepParam(stepStr)
	if step < 1 || step > len(ontologySetupSteps) {
		return c.Status(400).SendString(fmt.Sprintf("Invalid step: %s", stepStr))
	}

	progress, exists := ontologySetupProgress[engagementID]
	if !exists {
		return c.Status(404).SendString("Engagement not found; start the wizard first")
	}

	// Validate step transition: can't skip ahead by more than 1
	if step > progress.CurrentStep+1 {
		return c.Status(400).SendString(fmt.Sprintf(
			"Cannot skip to step %d; current step is %d",
			step, progress.CurrentStep,
		))
	}

	stepInfo := ontologySetupSteps[step-1]
	partial := resolveStepPartial(stepInfo.Name)

	return Render(c, partial, fiber.Map{
		"EngagementID": engagementID,
		"Step":         stepInfo,
		"TotalSteps":   len(ontologySetupSteps),
		"Progress":     progress,
	})
}

// APIOntologySetupSubmit processes form data for a step and advances.
func (h *Handler) APIOntologySetupSubmit(c *fiber.Ctx) error {
	engagementID := c.Params("engagement_id")
	stepStr := c.Params("step")

	if engagementID == "" {
		return c.Status(400).SendString("engagement_id is required")
	}

	step := parseStepParam(stepStr)
	if step < 1 || step > len(ontologySetupSteps) {
		return c.Status(400).SendString(fmt.Sprintf("Invalid step: %s", stepStr))
	}

	progress, exists := ontologySetupProgress[engagementID]
	if !exists {
		return c.Status(404).SendString("Engagement not found; start the wizard first")
	}

	// Verify we're on the right step
	if step != progress.CurrentStep {
		return c.Status(400).SendString(fmt.Sprintf(
			"Expected step %d, got step %d",
			progress.CurrentStep, step,
		))
	}

	// Parse form data
	var formData map[string]interface{}
	if err := c.BodyParser(&formData); err != nil {
		formData = make(map[string]interface{})
	}

	// Store the submitted data
	progress.Data[fmt.Sprintf("step_%d", step)] = formData

	// Advance to next step
	if step < len(ontologySetupSteps) {
		progress.CurrentStep = step + 1
		progress.UpdatedAt = time.Now().Format(time.RFC3339)

		nextStep := ontologySetupSteps[step] // 0-indexed, step is 1-indexed
		nextPartial := resolveStepPartial(nextStep.Name)

		return Render(c, nextPartial, fiber.Map{
			"EngagementID": engagementID,
			"Step":         nextStep,
			"TotalSteps":   len(ontologySetupSteps),
			"Progress":     progress,
			"Success":      true,
		})
	}

	// Completed all 5 steps
	progress.CurrentStep = len(ontologySetupSteps)
	progress.Completed = true
	progress.UpdatedAt = time.Now().Format(time.RFC3339)

	// Trigger discovery workflow dispatch
	h.dispatchDiscoveryWorkflow(engagementID)

	return Render(c, "partials/ontology_setup_complete", fiber.Map{
		"EngagementID": engagementID,
		"Data":         progress.Data,
	})
}

// APIOntologySetupSummary returns the current wizard status for an engagement.
func (h *Handler) APIOntologySetupSummary(c *fiber.Ctx) error {
	engagementID := c.Params("engagement_id")
	if engagementID == "" {
		return c.Status(400).SendString("engagement_id is required")
	}

	progress, exists := ontologySetupProgress[engagementID]
	if !exists {
		return c.Status(404).SendString("No wizard progress found for this engagement")
	}

	if c.Get("HX-Request") == "true" {
		return Render(c, "partials/ontology_setup_approval", fiber.Map{
			"EngagementID": engagementID,
			"Data": fiber.Map{
				"BusinessGoalDisplay": fmt.Sprintf("Step %d of %d completed", progress.CurrentStep, len(ontologySetupSteps)),
				"ScopeDisplay":        "Review before launching",
			},
		})
	}

	return c.JSON(fiber.Map{
		"engagement_id": progress.EngagementID,
		"current_step":  progress.CurrentStep,
		"total_steps":   len(ontologySetupSteps),
		"completed":     progress.Completed,
	})
}

// APIOntologySetupLaunch triggers the ontology discovery workflow via
// ChiefOfStaff and returns a confirmation partial.
func (h *Handler) APIOntologySetupLaunch(c *fiber.Ctx) error {
	engagementID := c.Params("engagement_id")
	if engagementID == "" {
		return c.Status(400).SendString("engagement_id is required")
	}

	// Trigger discovery workflow dispatch
	h.dispatchDiscoveryWorkflow(engagementID)

	// Return the launch confirmation partial
	return Render(c, "partials/ontology_setup_launch", fiber.Map{
		"EngagementID": engagementID,
	})
}

// dispatchDiscoveryWorkflow starts the Discovery workflow via Temporal.
func (h *Handler) dispatchDiscoveryWorkflow(engagementID string) {
	if h.temporal == nil {
		// No Temporal client — just log (tests pass with nil)
		return
	}
	// Use context.Background() since this is fire-and-forget from an HTMX handler
	h.temporal.StartWorkflow(
		context.Background(),
		"discovery-"+engagementID,
		"",
		map[string]interface{}{
			"engagement_id": engagementID,
			"tenant_id":     "default",
		},
	)
}

// parseInt is a simple helper to parse integers from route params (legacy).
func parseInt(s string) int {
	n := 0
	for _, c := range s {
		if c >= '0' && c <= '9' {
			n = n*10 + int(c-'0')
		} else {
			return 0
		}
	}
	return n
}

// RegisterOntologySetupRoutes registers the ontology setup wizard routes.
func (h *Handler) RegisterOntologySetupRoutes(app *fiber.App) {
	// Pre-existing integer-based endpoints (also accept string step names)
	app.Get("/ontology-setup/:engagement_id", h.APIOntologySetupStart)
	app.Get("/ontology-setup/:engagement_id/step/:step", h.APIOntologySetupStep)
	app.Post("/ontology-setup/:engagement_id/step/:step", h.APIOntologySetupSubmit)
	app.Get("/ontology-setup/:engagement_id/status", h.APIOntologySetupSummary)

	// New V5.1 Pydantic-aligned endpoints
	app.Get("/ontology-setup/:engagement_id/summary", h.APIOntologySetupSummary)
	app.Post("/ontology-setup/:engagement_id/launch", h.APIOntologySetupLaunch)
}
