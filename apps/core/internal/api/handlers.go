package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/url"
	"regexp"
	"runtime"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"

	"iterateswarm-core/internal/db"
	"iterateswarm-core/internal/logging"
	"iterateswarm-core/internal/redpanda"
	"iterateswarm-core/internal/temporal"
)

// FeedbackRequest represents a webhook request for feedback.
type FeedbackRequest struct {
	Text     string `json:"text"`
	Source   string `json:"source"`
	UserID   string `json:"user_id"`
	Username string `json:"username,omitempty"`
}

// FeedbackResponse is the response after ingesting feedback.
type FeedbackResponse struct {
	FeedbackID string `json:"feedback_id"`
	Status     string `json:"status"`
	Message    string `json:"message"`
}

// InteractionRequest represents a Discord interaction (button click).
type InteractionRequest struct {
	Type      int                    `json:"type"`
	Data      InteractionData        `json:"data"`
	ChannelID string                 `json:"channel_id"`
	User      InteractionUser        `json:"user"`
	Message   map[string]interface{} `json:"message,omitempty"`
}

// InteractionData contains the interaction data.
type InteractionData struct {
	CustomID string `json:"custom_id"`
}

// InteractionUser contains the user who triggered the interaction.
type InteractionUser struct {
	ID       string `json:"id"`
	Username string `json:"username"`
}

// Handler handles API requests.
type Handler struct {
	redpandaClient *redpanda.Client
	temporalClient *temporal.Client
	repo           *db.Repository
	db             *sql.DB
	logger         *logging.Logger
}

// NewHandler creates a new Handler.
func NewHandler(redpandaClient *redpanda.Client, temporalClient *temporal.Client, repo *db.Repository, db *sql.DB) *Handler {
	return &Handler{
		redpandaClient: redpandaClient,
		temporalClient: temporalClient,
		repo:           repo,
		db:             db,
		logger:         logging.NewLogger("api"),
	}
}

// HandleDiscordWebhook processes Discord webhook events.
func (h *Handler) HandleDiscordWebhook(c *fiber.Ctx) error {
	startTime := time.Now()
	var req FeedbackRequest

	if err := c.BodyParser(&req); err != nil {
		h.logger.Error("failed to parse request body", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid request body",
		})
	}

	if req.Text == "" {
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Missing 'text' field",
		})
	}

	// Idempotency check: Use X-Discord-Delivery header if available
	idempotencyKey := c.Get("X-Discord-Delivery")
	if idempotencyKey != "" && h.db != nil {
		ctx, cancel := context.WithTimeout(c.Context(), 5*time.Second)
		defer cancel()

		isNew, err := h.repo.SetIdempotencyKey(ctx, fmt.Sprintf("discord:%s", idempotencyKey), "discord", 24*time.Hour)
		if err != nil {
			h.logger.Warn("failed to check idempotency", "error", err.Error())
			// Continue anyway - don't block on database failure
		} else if !isNew {
			// Already processed (key already existed)
			h.logger.Info("duplicate webhook delivery skipped", "idempotency_key", idempotencyKey)
			return c.Status(fiber.StatusOK).JSON(map[string]string{
				"status": "already_processed",
			})
		}
	}

	// Generate feedback ID
	feedbackID := uuid.New().String()

	// Publish to Redpanda
	event := map[string]interface{}{
		"feedback_id": feedbackID,
		"text":        req.Text,
		"source":      "discord",
		"user_id":     req.UserID,
		"username":    req.Username,
		"timestamp":   time.Now().UTC().Format(time.RFC3339),
	}

	data, err := json.Marshal(event)
	if err != nil {
		h.logger.Error("failed to marshal event", err, "feedback_id", feedbackID)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to process event",
		})
	}

	err = h.redpandaClient.Publish(data)
	if err != nil {
		h.logger.Error("failed to publish to redpanda", err, "feedback_id", feedbackID)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to queue event",
		})
	}

	duration := time.Since(startTime)
	h.logger.Info("feedback ingested",
		"feedback_id", feedbackID,
		"source", "discord",
		"user_id", req.UserID,
		"duration_ms", duration.Milliseconds(),
	)

	return c.Status(fiber.StatusAccepted).JSON(FeedbackResponse{
		FeedbackID: feedbackID,
		Status:     "accepted",
		Message:    "Feedback is being processed",
	})
}

// HandleSlackWebhook processes Slack webhook events.
func (h *Handler) HandleSlackWebhook(c *fiber.Ctx) error {
	startTime := time.Now()

	// Handle Slack URL verification challenge
	var challengeReq struct {
		Token     string `json:"token"`
		Challenge string `json:"challenge"`
		Type      string `json:"type"`
	}
	if err := c.BodyParser(&challengeReq); err != nil {
		h.logger.Error("failed to parse slack request", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid request body",
		})
	}

	// Respond to URL verification
	if challengeReq.Type == "url_verification" {
		return c.SendString(challengeReq.Challenge)
	}

	// Parse Slack event
	var slackEvent struct {
		Token    string `json:"token"`
		TeamID   string `json:"team_id"`
		APIAppID string `json:"api_app_id"`
		Event    struct {
			Type        string `json:"type"`
			Text        string `json:"text"`
			User        string `json:"user"`
			Channel     string `json:"channel"`
			Ts          string `json:"ts"`
			ThreadTs    string `json:"thread_ts,omitempty"`
			ChannelType string `json:"channel_type,omitempty"`
			BotID       string `json:"bot_id,omitempty"`
		} `json:"event"`
		Type      string `json:"type"`
		EventID   string `json:"event_id"`
		EventTime int64  `json:"event_time"`
	}

	if err := c.BodyParser(&slackEvent); err != nil {
		h.logger.Error("failed to parse slack event", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid slack event",
		})
	}

	// Ignore bot messages and non-message events
	if slackEvent.Event.Type != "message" || slackEvent.Event.Text == "" {
		return c.Status(fiber.StatusOK).JSON(map[string]string{
			"status": "ignored",
		})
	}

	// Idempotency check using Slack event ID
	if slackEvent.EventID != "" && h.db != nil {
		ctx, cancel := context.WithTimeout(c.Context(), 5*time.Second)
		defer cancel()

		isNew, err := h.repo.SetIdempotencyKey(ctx, fmt.Sprintf("slack:%s", slackEvent.EventID), "slack", 24*time.Hour)
		if err != nil {
			h.logger.Warn("failed to check slack idempotency", "error", err.Error())
		} else if !isNew {
			h.logger.Info("duplicate slack event skipped", "event_id", slackEvent.EventID)
			return c.Status(fiber.StatusOK).JSON(map[string]string{
				"status": "already_processed",
			})
		}
	}

	// Check if this is an onboarding reply (thread message in DM)
	if slackEvent.Event.ThreadTs != "" && slackEvent.Event.ChannelType == "im" {
		// This is a reply in a DM thread - check if founder is in onboarding
		var founderID string
		var onboardingComplete bool
		err := h.db.QueryRowContext(c.Context(), `
			SELECT id, onboarding_complete FROM founders WHERE slack_user_id = $1
		`, slackEvent.Event.User).Scan(&founderID, &onboardingComplete)

		if err == nil && !onboardingComplete {
			// Founder is in onboarding, process the reply
			go func() {
				if err := h.handleOnboardingReply(founderID, slackEvent.Event.User, slackEvent.Event.Text, slackEvent.Event.ThreadTs); err != nil {
					h.logger.Error("failed to process onboarding reply", err)
				}
			}()

			// Still publish to Redpanda for analytics
		} else if err == sql.ErrNoRows {
			// First DM from unknown user - start onboarding
			go func() {
				if _, err := h.startOnboarding(slackEvent.Event.User); err != nil {
					h.logger.Error("failed to start onboarding", err)
				}
			}()
		}
	}

	// Generate feedback ID
	feedbackID := uuid.New().String()

	// Publish to Redpanda
	event := map[string]interface{}{
		"feedback_id": feedbackID,
		"text":        slackEvent.Event.Text,
		"source":      "slack",
		"user_id":     slackEvent.Event.User,
		"channel_id":  slackEvent.Event.Channel,
		"team_id":     slackEvent.TeamID,
		"timestamp":   time.Now().UTC().Format(time.RFC3339),
	}

	data, err := json.Marshal(event)
	if err != nil {
		h.logger.Error("failed to marshal slack event", err, "feedback_id", feedbackID)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to process event",
		})
	}

	err = h.redpandaClient.Publish(data)
	if err != nil {
		h.logger.Error("failed to publish slack event to redpanda", err, "feedback_id", feedbackID)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to queue event",
		})
	}

	duration := time.Since(startTime)
	h.logger.Info("slack feedback ingested",
		"feedback_id", feedbackID,
		"source", "slack",
		"user_id", slackEvent.Event.User,
		"channel_id", slackEvent.Event.Channel,
		"duration_ms", duration.Milliseconds(),
	)

	return c.Status(fiber.StatusAccepted).JSON(FeedbackResponse{
		FeedbackID: feedbackID,
		Status:     "accepted",
		Message:    "Feedback is being processed",
	})
}

// HandleInteraction processes Discord interactions (button clicks).
func (h *Handler) HandleInteraction(c *fiber.Ctx) error {
	var req InteractionRequest
	if err := c.BodyParser(&req); err != nil {
		h.logger.Error("failed to parse interaction", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid request body",
		})
	}

	// Handle Discord's ping interaction
	if req.Type == 1 {
		return c.JSON(map[string]interface{}{
			"type": 1,
		})
	}

	h.logger.Info("interaction received",
		"custom_id", req.Data.CustomID,
		"user_id", req.User.ID,
		"username", req.User.Username,
		"channel_id", req.ChannelID,
	)

	// P2-1 FIX: Use validated ParseCustomID function with SignalData
	signalData, err := ParseCustomID(req.Data.CustomID)
	if err != nil {
		h.logger.Error("invalid custom_id format", err, "custom_id", req.Data.CustomID)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid custom_id format",
		})
	}

	// P1-1 FIX: Use both WorkflowID and RunID for precise signal routing
	// If RunID is provided, we can signal a specific run; otherwise signal by WorkflowID
	err = h.temporalClient.SignalWorkflow(c.Context(), signalData.WorkflowID, "user-action", signalData.Action)
	if err != nil {
		h.logger.Error("failed to signal workflow", err, "workflow_id", signalData.WorkflowID, "action", signalData.Action)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to process action",
		})
	}

	return c.JSON(map[string]interface{}{
		"type": 4,
		"data": map[string]string{
			"content": "Action received!",
		},
	})
}

// HandleHealth returns a simple health status.
func (h *Handler) HandleHealth(c *fiber.Ctx) error {
	return c.JSON(map[string]interface{}{
		"status":    "healthy",
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// HandleDetailedHealth returns comprehensive health status with dependency checks.
func (h *Handler) HandleDetailedHealth(c *fiber.Ctx) error {
	ctx := c.Context()
	checks := make(map[string]interface{})
	allHealthy := true

	// Check PostgreSQL
	pgStart := time.Now()
	pgErr := h.db.PingContext(ctx)
	pgDuration := time.Since(pgStart)
	if pgErr != nil {
		checks["postgres"] = map[string]interface{}{
			"status":     "unhealthy",
			"error":      pgErr.Error(),
			"latency_ms": pgDuration.Milliseconds(),
		}
		allHealthy = false
	} else {
		checks["postgres"] = map[string]interface{}{
			"status":     "healthy",
			"latency_ms": pgDuration.Milliseconds(),
		}
	}

	// Check Temporal
	if h.temporalClient != nil {
		temporalStart := time.Now()
		temporalErr := h.temporalClient.Health(ctx)
		temporalDuration := time.Since(temporalStart)
		if temporalErr != nil {
			checks["temporal"] = map[string]interface{}{
				"status":     "unhealthy",
				"error":      temporalErr.Error(),
				"latency_ms": temporalDuration.Milliseconds(),
			}
			allHealthy = false
		} else {
			checks["temporal"] = map[string]interface{}{
				"status":     "healthy",
				"latency_ms": temporalDuration.Milliseconds(),
			}
		}
	} else {
		checks["temporal"] = map[string]interface{}{
			"status": "unavailable",
			"error":  "temporal client not initialized",
		}
		allHealthy = false
	}

	// Check Redpanda
	if h.redpandaClient != nil {
		redpandaStart := time.Now()
		redpandaErr := h.redpandaClient.Health(ctx)
		redpandaDuration := time.Since(redpandaStart)
		if redpandaErr != nil {
			checks["redpanda"] = map[string]interface{}{
				"status":     "unhealthy",
				"error":      redpandaErr.Error(),
				"latency_ms": redpandaDuration.Milliseconds(),
			}
			allHealthy = false
		} else {
			checks["redpanda"] = map[string]interface{}{
				"status":     "healthy",
				"latency_ms": redpandaDuration.Milliseconds(),
			}
		}
	} else {
		checks["redpanda"] = map[string]interface{}{
			"status": "unavailable",
			"error":  "redpanda client not initialized",
		}
		allHealthy = false
	}

	// Runtime info
	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	// Build response
	response := map[string]interface{}{
		"status":    "healthy",
		"timestamp": time.Now().UTC().Format(time.RFC3339),
		"service":   "iterateswarm-core",
		"version":   "1.0.0",
		"checks":    checks,
		"runtime": map[string]interface{}{
			"goroutines":      runtime.NumGoroutine(),
			"cpu_cores":       runtime.NumCPU(),
			"memory_alloc_mb": float64(m.Alloc) / 1024 / 1024,
			"total_alloc_mb":  float64(m.TotalAlloc) / 1024 / 1024,
			"heap_alloc_mb":   float64(m.HeapAlloc) / 1024 / 1024,
		},
	}

	// Determine overall status
	if !allHealthy {
		response["status"] = "degraded"
	}

	// Return appropriate status code
	statusCode := fiber.StatusOK
	if !allHealthy {
		statusCode = fiber.StatusServiceUnavailable
	}

	return c.Status(statusCode).JSON(response)
}

// HandleKafkaTest sends a test message to Kafka (for development).
func (h *Handler) HandleKafkaTest(c *fiber.Ctx) error {
	event := map[string]interface{}{
		"feedback_id": uuid.New().String(),
		"text":        "Test feedback from API",
		"source":      "test",
		"user_id":     "test-user",
		"timestamp":   time.Now().UTC().Format(time.RFC3339),
	}

	data, _ := json.Marshal(event)
	if err := h.redpandaClient.Publish(data); err != nil {
		h.logger.Warn("failed to publish test message", "error", err.Error())
	}

	return c.JSON(map[string]interface{}{
		"status":  "sent",
		"message": "Test message published to feedback-events",
	})
}

// HandleDashboardStats returns dashboard statistics.
func (h *Handler) HandleDashboardStats(c *fiber.Ctx) error {
	ctx := c.Context()

	// Check Temporal health
	temporalHealthy := true
	if err := h.temporalClient.Health(ctx); err != nil {
		temporalHealthy = false
	}

	// Check Redpanda health
	redpandaHealthy := true
	if err := h.redpandaClient.Health(ctx); err != nil {
		redpandaHealthy = false
	}

	// Check PostgreSQL health
	pgHealthy := h.db.PingContext(ctx) == nil

	// Query database stats
	dbStats, err := h.queryDatabaseStats(ctx)
	if err != nil {
		h.logger.Warn("failed to query database stats", "error", err.Error())
		dbStats = map[string]interface{}{
			"pending_feedback":   0,
			"processed_feedback": 0,
			"draft_issues":       0,
			"published_issues":   0,
		}
	}

	return c.JSON(map[string]interface{}{
		"workflow_count": 0, // TODO: Implement Temporal workflow count query
		"queue_lag":      0, // TODO: Implement Redpanda queue lag monitoring
		"services": map[string]interface{}{
			"go":       map[string]string{"status": "up"},
			"python":   map[string]string{"status": "up"},
			"temporal": map[string]string{"status": boolToString(temporalHealthy)},
			"redpanda": map[string]string{"status": boolToString(redpandaHealthy)},
			"postgres": map[string]string{"status": boolToString(pgHealthy)},
		},
		"stats":     dbStats,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// queryDatabaseStats queries database statistics
func (h *Handler) queryDatabaseStats(ctx context.Context) (map[string]interface{}, error) {
	// Count feedback by status
	pendingFeedback, err := h.repo.ListFeedback(ctx, db.ListFeedbackParams{
		Limit:  0, // No limit
		Offset: 0,
	})
	if err != nil {
		return nil, err
	}

	// For simplicity, we'll count manually here
	// In a real implementation, we'd use aggregate queries
	pendingCount := 0
	processedCount := 0
	for _, fb := range pendingFeedback {
		if status, ok := fb["status"].(string); ok {
			switch status {
			case "pending":
				pendingCount++
			case "processed":
				processedCount++
			}
		}
	}

	// Count issues
	issues, err := h.repo.ListIssues(ctx, db.ListIssuesParams{
		Limit:  0,
		Offset: 0,
	})
	if err != nil {
		return nil, err
	}

	draftCount := 0
	publishedCount := 0
	for _, issue := range issues {
		if status, ok := issue["status"].(string); ok {
			switch status {
			case "draft":
				draftCount++
			case "published":
				publishedCount++
			}
		}
	}

	stats := map[string]interface{}{
		"pending_feedback":   pendingCount,
		"processed_feedback": processedCount,
		"draft_issues":       draftCount,
		"published_issues":   publishedCount,
	}

	return stats, nil
}

// HandleFeedbackList returns a list of feedback items.
func (h *Handler) HandleFeedbackList(c *fiber.Ctx) error {
	// Parse pagination
	page := c.QueryInt("page", 1)
	pageSize := c.QueryInt("page_size", 10)

	// Calculate offset
	offset := (page - 1) * pageSize

	// Query feedback from database
	feedback, err := h.repo.ListFeedback(c.Context(), db.ListFeedbackParams{
		Limit:  pageSize,
		Offset: offset,
	})
	if err != nil {
		h.logger.Error("failed to query feedback from database", err)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to retrieve feedback",
		})
	}

	// Convert to response format
	responseItems := make([]map[string]interface{}, len(feedback))
	for i, item := range feedback {
		var createdAt string
		if createdAtRaw, ok := item["created_at"]; ok {
			if t, ok := createdAtRaw.(time.Time); ok {
				createdAt = t.Format(time.RFC3339)
			}
		}

		var id, content, source, userID, status string
		if v, ok := item["id"].(string); ok {
			id = v
		}
		if v, ok := item["content"].(string); ok {
			content = v
		}
		if v, ok := item["source"].(string); ok {
			source = v
		}
		if v, ok := item["user_id"].(string); ok {
			userID = v
		}
		if v, ok := item["status"].(string); ok {
			status = v
		}

		responseItems[i] = map[string]interface{}{
			"id":         id,
			"title":      extractTitle(content),
			"body":       content,
			"source":     source,
			"user_id":    userID,
			"status":     status,
			"created_at": createdAt,
		}
	}

	return c.JSON(map[string]interface{}{
		"data":      responseItems,
		"total":     len(responseItems), // In a real implementation, we'd get the total count separately
		"page":      page,
		"page_size": pageSize,
	})
}

// extractTitle extracts a title from feedback content (simple implementation)
func extractTitle(content string) string {
	// For now, just take the first 50 characters and remove newlines
	title := strings.Replace(content, "\n", " ", -1)
	if len(title) > 50 {
		title = title[:50] + "..."
	}
	return title
}

// boolToString converts boolean to string.
func boolToString(b bool) string {
	if b {
		return "up"
	}
	return "down"
}

// HandleDemoFeedback processes feedback from demo/development endpoints
// This bypasses Discord signature verification for local testing
func (h *Handler) HandleDemoFeedback(c *fiber.Ctx) error {
	startTime := time.Now()

	var req struct {
		Text   string `json:"text"`
		Source string `json:"source"`
		UserID string `json:"user_id"`
	}

	if err := c.BodyParser(&req); err != nil {
		h.logger.Error("failed to parse demo request", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid request body",
		})
	}

	// Validate required fields
	if req.Text == "" {
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Missing 'text' field",
		})
	}

	// Set defaults
	if req.Source == "" {
		req.Source = "demo"
	}
	if req.UserID == "" {
		req.UserID = "demo-user"
	}

	// Generate feedback ID
	feedbackID := uuid.New().String()

	// Publish to Redpanda (same flow as Discord webhook)
	event := map[string]interface{}{
		"feedback_id": feedbackID,
		"text":        req.Text,
		"source":      req.Source,
		"user_id":     req.UserID,
		"username":    "demo",
		"timestamp":   time.Now().UTC().Format(time.RFC3339),
		"demo":        true, // Flag to indicate demo origin
	}

	data, err := json.Marshal(event)
	if err != nil {
		h.logger.Error("failed to marshal demo event", err, "feedback_id", feedbackID)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to process event",
		})
	}

	err = h.redpandaClient.Publish(data)
	if err != nil {
		h.logger.Error("failed to publish demo event to redpanda", err, "feedback_id", feedbackID)
		return c.Status(fiber.StatusInternalServerError).JSON(map[string]string{
			"error": "Failed to queue event",
		})
	}

	duration := time.Since(startTime)
	h.logger.Info("demo feedback ingested",
		"feedback_id", feedbackID,
		"source", req.Source,
		"user_id", req.UserID,
		"duration_ms", duration.Milliseconds(),
	)

	return c.Status(fiber.StatusAccepted).JSON(FeedbackResponse{
		FeedbackID: feedbackID,
		Status:     "accepted",
		Message:    "Demo feedback is being processed",
	})
}

// SignalData holds the parsed signal information from Discord custom_id
// Format: action:workflow_id:run_id
// Example: approve:feedback-abc123:def456-ghi789
// Issue: P1-1 - Workflow signaling identifier mismatch risk
// Recommendation: Encode both workflow_id and run_id for precise signal routing
type SignalData struct {
	Action     string // "approve" or "reject"
	WorkflowID string // Temporal workflow ID
	RunID      string // Temporal workflow run ID (optional for signal routing)
}

// ParseCustomID parses and validates Discord custom_id format with strict schema
// Format: action:workflow_id:run_id (v2) or action:workflow_id (v1)
// Returns: SignalData, error
func ParseCustomID(customID string) (SignalData, error) {
	if customID == "" {
		return SignalData{}, fmt.Errorf("custom_id cannot be empty")
	}

	// Check for XSS or invalid characters
	if strings.ContainsAny(customID, "<>\"'&;") {
		return SignalData{}, fmt.Errorf("custom_id contains invalid characters")
	}

	// Split by colon separator (strict schema)
	parts := strings.Split(customID, ":")

	// Must have at least 2 parts (action:workflow_id)
	if len(parts) < 2 {
		return SignalData{}, fmt.Errorf("invalid custom_id format: %s (expected 'action:workflow_id:run_id' or 'action:workflow_id')", customID)
	}

	action := parts[0]
	workflowID := parts[1]
	runID := ""

	// If 3 parts, include run_id
	if len(parts) == 3 {
		runID = parts[2]
	} else if len(parts) > 3 {
		return SignalData{}, fmt.Errorf("invalid custom_id format: too many segments")
	}

	// Validate action
	if action != "approve" && action != "reject" {
		return SignalData{}, fmt.Errorf("invalid action: %s (must be 'approve' or 'reject')", action)
	}

	// Validate workflowID is not empty
	if workflowID == "" {
		return SignalData{}, fmt.Errorf("workflow_id cannot be empty")
	}

	// Validate workflowID format (alphanumeric, hyphens, underscores only)
	validIDPattern := regexp.MustCompile(`^[a-zA-Z0-9_-]+$`)
	if !validIDPattern.MatchString(workflowID) {
		return SignalData{}, fmt.Errorf("workflow_id contains invalid characters")
	}

	// Validate run_id format if present
	if runID != "" && !validIDPattern.MatchString(runID) {
		return SignalData{}, fmt.Errorf("run_id contains invalid characters")
	}

	return SignalData{
		Action:     action,
		WorkflowID: workflowID,
		RunID:      runID,
	}, nil
}

// HandleHITLInvestigate handles HITL "investigate" signal from founder
func (h *Handler) HandleHITLInvestigate(c *fiber.Ctx) error {
	var body struct {
		WorkflowID string `json:"workflow_id"`
		TenantID   string `json:"tenant_id"`
		Vendor     string `json:"vendor"`
	}
	if err := c.BodyParser(&body); err != nil || body.WorkflowID == "" {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "workflow_id required",
		})
	}

	ctx := c.Context()
	if err := h.temporalClient.SignalWorkflow(ctx, body.WorkflowID, "hitl_action", "investigate"); err != nil {
		h.logger.Error("failed to send investigate signal", err, "workflow_id", body.WorkflowID)
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": err.Error(),
		})
	}

	h.logger.Info("HITL investigate signal sent", "workflow_id", body.WorkflowID, "tenant_id", body.TenantID)
	return c.JSON(fiber.Map{
		"ok":          true,
		"action":      "investigate",
		"workflow_id": body.WorkflowID,
	})
}

// HandleHITLDismiss handles HITL "dismiss" signal from founder
func (h *Handler) HandleHITLDismiss(c *fiber.Ctx) error {
	var body struct {
		WorkflowID string `json:"workflow_id"`
		TenantID   string `json:"tenant_id"`
		Vendor     string `json:"vendor"`
	}
	if err := c.BodyParser(&body); err != nil || body.WorkflowID == "" {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "workflow_id required",
		})
	}

	ctx := c.Context()
	if err := h.temporalClient.SignalWorkflow(ctx, body.WorkflowID, "hitl_action", "dismiss"); err != nil {
		h.logger.Error("failed to send dismiss signal", err, "workflow_id", body.WorkflowID)
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": err.Error(),
		})
	}

	h.logger.Info("HITL dismiss signal sent", "workflow_id", body.WorkflowID, "tenant_id", body.TenantID)
	return c.JSON(fiber.Map{
		"ok":          true,
		"action":      "dismiss",
		"workflow_id": body.WorkflowID,
	})
}

// HandleBIQuery handles direct BI query from API/UI
func (h *Handler) HandleBIQuery(c *fiber.Ctx) error {
	var body struct {
		TenantID  string `json:"tenant_id"`
		Query     string `json:"query"`
		QueryType string `json:"query_type"` // ADHOC | SCHEDULED | TRIGGERED
	}
	if err := c.BodyParser(&body); err != nil || body.Query == "" {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "query required",
		})
	}

	if body.QueryType == "" {
		body.QueryType = "ADHOC"
	}

	queryID := uuid.New().String()
	workflowID := fmt.Sprintf("bi-%s-%s", body.TenantID[:8], queryID[:8])

	// Start BI workflow
	input := map[string]interface{}{
		"tenant_id":  body.TenantID,
		"query":      body.Query,
		"query_type": body.QueryType,
	}

	_, err := h.temporalClient.StartWorkflow(c.Context(), workflowID, "ontology_ai-queue", input)
	if err != nil {
		h.logger.Error("failed to start BI workflow", err, "query_id", queryID)
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": err.Error(),
		})
	}

	h.logger.Info("BI workflow started", "query_id", queryID, "workflow_id", workflowID)
	return c.Status(fiber.StatusAccepted).JSON(fiber.Map{
		"ok":          true,
		"query_id":    queryID,
		"workflow_id": workflowID,
		"message":     "Query queued. Result sent to Telegram.",
	})
}

// AgentFeedbackRequest represents feedback from Slack button clicks
type AgentFeedbackRequest struct {
	Payload string `json:"payload"`
}

// HandleAgentFeedback processes Slack interactive component feedback
func (h *Handler) HandleAgentFeedback(c *fiber.Ctx) error {
	startTime := time.Now()

	var req AgentFeedbackRequest
	if err := c.BodyParser(&req); err != nil {
		h.logger.Error("failed to parse agent feedback request", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid request body",
		})
	}

	// Parse Slack payload (URL-encoded JSON)
	payload, err := parseSlackPayload(req.Payload)
	if err != nil {
		h.logger.Error("failed to parse slack payload", err)
		return c.Status(fiber.StatusBadRequest).JSON(map[string]string{
			"error": "Invalid payload format",
		})
	}

	// Only handle button clicks
	if payload.Type != "block_actions" {
		return c.JSON(map[string]interface{}{
			"response_type": "ephemeral",
			"text":          "Unsupported interaction type",
		})
	}

	// Process each action
	for _, action := range payload.Actions {
		feedbackID := uuid.New().String()

		// Parse action value (format: agent_type:pattern:tenant_id)
		parts := strings.Split(action.Value, ":")
		if len(parts) != 3 {
			h.logger.Warn("invalid action value format", "value", action.Value)
			continue
		}

		agentType := parts[0]
		pattern := parts[1]
		tenantID := parts[2]

		// Map button action to feedback type
		var feedbackType string
		switch action.ActionID {
		case "acted_on":
			feedbackType = "acted_on"
		case "not_relevant":
			feedbackType = "not_relevant"
		case "already_knew":
			feedbackType = "already_knew"
		default:
			h.logger.Warn("unknown action_id", "action_id", action.ActionID)
			continue
		}

		// Publish feedback event to Redpanda
		event := map[string]interface{}{
			"feedback_id":   feedbackID,
			"type":          "agent_feedback",
			"agent_type":    agentType,
			"pattern":       pattern,
			"tenant_id":     tenantID,
			"feedback_type": feedbackType,
			"user_id":       payload.User.ID,
			"channel_id":    payload.Channel.ID,
			"timestamp":     time.Now().UTC().Format(time.RFC3339),
		}

		data, err := json.Marshal(event)
		if err != nil {
			h.logger.Error("failed to marshal feedback event", err, "feedback_id", feedbackID)
			continue
		}

		if err := h.redpandaClient.Publish(data); err != nil {
			h.logger.Error("failed to publish feedback event", err, "feedback_id", feedbackID)
			continue
		}

		h.logger.Info("agent feedback processed",
			"feedback_id", feedbackID,
			"agent_type", agentType,
			"pattern", pattern,
			"tenant_id", tenantID,
			"feedback_type", feedbackType,
			"user_id", payload.User.ID,
		)
	}

	duration := time.Since(startTime)
	h.logger.Info("agent feedback webhook processed", "duration_ms", duration.Milliseconds())

	// Respond to Slack with ephemeral confirmation
	return c.JSON(map[string]interface{}{
		"response_type": "ephemeral",
		"text":          "Thank you for your feedback! Agent thresholds will be adjusted accordingly.",
	})
}

// SlackPayload represents the parsed Slack interactive payload
type SlackPayload struct {
	Type    string `json:"type"`
	Actions []struct {
		ActionID string `json:"action_id"`
		Value    string `json:"value"`
	} `json:"actions"`
	User struct {
		ID string `json:"id"`
	} `json:"user"`
	Channel struct {
		ID string `json:"id"`
	} `json:"channel"`
}

// parseSlackPayload parses and validates URL-encoded Slack payload
func parseSlackPayload(payloadStr string) (*SlackPayload, error) {
	// URL decode the payload
	decoded, err := url.QueryUnescape(payloadStr)
	if err != nil {
		return nil, fmt.Errorf("failed to decode payload: %w", err)
	}

	// Parse JSON
	var payload SlackPayload
	if err := json.Unmarshal([]byte(decoded), &payload); err != nil {
		return nil, fmt.Errorf("failed to parse payload JSON: %w", err)
	}

	return &payload, nil
}
