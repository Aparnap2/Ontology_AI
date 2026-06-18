package workflow

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"iterateswarm-core/internal/agents"
	"iterateswarm-core/internal/events"
	"iterateswarm-core/internal/logging"
	"iterateswarm-core/internal/memory"
	"iterateswarm-core/internal/retry"

	"github.com/bwmarrin/discordgo"

	// gRPC imports for Python agent communication
	aiv1 "github.com/Aparnap2/iterate_swarm/gen/go/ai/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// Activities contains the workflow activities.
type Activities struct {
	logger   *logging.Logger
	aiClient *grpc.ClientConn
	db       *sql.DB
}

// NewActivities creates a new Activities instance.
func NewActivities(aiClient *grpc.ClientConn) *Activities {
	return &Activities{
		logger:   logging.NewLogger("workflow"),
		aiClient: aiClient,
	}
}

// SetDB sets the database connection for DLQ and persistence activities.
// Optional — if not set, DLQ operations fall back to logging only.
func (a *Activities) SetDB(db *sql.DB) {
	a.db = db
}

// AnalyzeFeedbackInput is the input for the AnalyzeFeedback activity.
type AnalyzeFeedbackInput struct {
	Text      string
	Source    string
	UserID    string
	ChannelID string
}

// AnalyzeFeedback analyzes feedback using Go-based AI agents (replaces Python gRPC).
func (a *Activities) AnalyzeFeedback(ctx context.Context, input AnalyzeFeedbackInput) (*AnalyzeFeedbackOutput, error) {
	startTime := time.Now()
	a.logger.Info("analyzing feedback",
		"source", input.Source,
		"user_id", input.UserID,
		"text_length", len(input.Text),
	)

	// Step 1: Check for duplicates using Qdrant
	qdrantClient, err := memory.NewQdrantClientFromEnv()
	if err != nil {
		a.logger.Error("failed to create qdrant client", err)
		return nil, fmt.Errorf("failed to create qdrant client: %w", err)
	}

	if err := qdrantClient.EnsureCollection(ctx); err != nil {
		a.logger.Error("failed to ensure qdrant collection", err)
		return nil, fmt.Errorf("failed to ensure collection: %w", err)
	}

	isDuplicate, _, err := qdrantClient.CheckDuplicate(ctx, input.Text)
	if err != nil {
		a.logger.Error("duplicate check failed", err)
		return nil, fmt.Errorf("duplicate check failed: %w", err)
	}

	if isDuplicate {
		a.logger.Info("feedback is duplicate, skipping analysis")
		return &AnalyzeFeedbackOutput{
			IsDuplicate: true,
		}, nil
	}

	// Step 2: Triage (classify and determine severity)
	// P1-2 FIX: Add nil check and validation before using agent
	triageAgent := agents.NewTriageAgentFromEnv()
	if triageAgent == nil {
		a.logger.Error("triage agent is nil", fmt.Errorf("failed to create triage agent - check AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT environment variables"))
		return nil, fmt.Errorf("triage agent unavailable: AI service not configured")
	}

	triageResult, err := triageAgent.Classify(ctx, input.UserID, input.Text, input.Source)
	if err != nil {
		a.logger.Error("triage failed", err)
		return nil, fmt.Errorf("triage failed: %w", err)
	}

	// Step 3: Generate spec
	// P1-2 FIX: Add nil check before using agent
	specAgent := agents.NewSpecAgentFromEnv()
	if specAgent == nil {
		a.logger.Error("spec agent is nil", fmt.Errorf("failed to create spec agent - check AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT environment variables"))
		return nil, fmt.Errorf("spec agent unavailable: AI service not configured")
	}

	specResult, err := specAgent.GenerateSpec(
		ctx,
		input.UserID,
		input.Text,
		input.Source,
		triageResult.Classification,
		triageResult.Severity,
		triageResult.Reasoning,
		triageResult.Confidence,
	)
	if err != nil {
		a.logger.Error("spec generation failed", err)
		return nil, fmt.Errorf("spec generation failed: %w", err)
	}

	// Step 4: Index for future duplicate detection
	metadata := map[string]interface{}{
		"user_id":        input.UserID,
		"classification": triageResult.Classification,
		"severity":       triageResult.Severity,
		"confidence":     triageResult.Confidence,
	}
	if err := qdrantClient.IndexFeedback(ctx, input.UserID, input.Text, metadata); err != nil {
		a.logger.Error("failed to index feedback", err)
		// Don't fail if indexing fails
	}

	// Build description from spec
	description := buildDescription(specResult)

	// P3-1 FIX: Include confidence from AI response (not hardcoded)
	output := &AnalyzeFeedbackOutput{
		IsDuplicate: false,
		Title:       specResult.Title,
		Description: description,
		Labels:      specResult.Labels,
		Severity:    triageResult.Severity,
		IssueType:   triageResult.Classification,
		Confidence:  triageResult.Confidence, // Real confidence from Azure AI
	}

	duration := time.Since(startTime)
	a.logger.LogActivity(ctx, "AnalyzeFeedback", duration, true,
		"is_duplicate", output.IsDuplicate,
		"issue_type", output.IssueType,
		"severity", output.Severity,
	)

	return output, nil
}

// buildDescription creates a GitHub issue description from the spec result.
func buildDescription(spec *agents.SpecResult) string {
	var parts []string

	if len(spec.ReproductionSteps) > 0 {
		parts = append(parts, "## Reproduction Steps")
		for i, step := range spec.ReproductionSteps {
			parts = append(parts, fmt.Sprintf("%d. %s", i+1, step))
		}
		parts = append(parts, "")
	}

	if len(spec.AffectedComponents) > 0 {
		parts = append(parts, "## Affected Components")
		for _, comp := range spec.AffectedComponents {
			parts = append(parts, fmt.Sprintf("- %s", comp))
		}
		parts = append(parts, "")
	}

	if len(spec.AcceptanceCriteria) > 0 {
		parts = append(parts, "## Acceptance Criteria")
		for _, criteria := range spec.AcceptanceCriteria {
			parts = append(parts, fmt.Sprintf("- [ ] %s", criteria))
		}
		parts = append(parts, "")
	}

	return strings.Join(parts, "\n")
}

// severityColor maps severity levels to Discord embed colors.
var severityColor = map[string]int{
	"critical":    0xff0000,
	"high":        0xff6600,
	"medium":      0xffff00,
	"low":         0x00ff00,
	"unspecified": 0x808080,
}

// issueTypeEmoji maps issue types to emojis.
var issueTypeEmoji = map[string]string{
	"bug":         "🐛",
	"feature":     "✨",
	"question":    "❓",
	"unspecified": "📝",
}

// SendDiscordApproval sends an approval request to Discord with Approve/Reject buttons.
func (a *Activities) SendDiscordApproval(ctx context.Context, input SendDiscordApprovalInput) error {
	startTime := time.Now()
	a.logger.Info("sending discord approval request",
		"channel_id", input.ChannelID,
		"issue_title", input.IssueTitle,
		"workflow_id", input.WorkflowID,
	)

	// Get Discord bot token from environment
	discordToken := os.Getenv("DISCORD_BOT_TOKEN")
	if discordToken == "" {
		a.logger.Warn("discord token not configured, skipping notification")
		return nil
	}

	// Create Discord session with retry
	var dg *discordgo.Session
	err := retry.SimpleRetry(func() error {
		var createErr error
		dg, createErr = discordgo.New("Bot " + discordToken)
		return createErr
	})
	if err != nil {
		a.logger.Error("failed to create discord session", err)
		return fmt.Errorf("failed to create Discord session: %w", err)
	}

	// Get color for severity
	color := severityColor[strings.ToLower(input.Severity)]
	if color == 0 {
		color = severityColor["unspecified"]
	}

	// Get emoji for issue type
	emoji := issueTypeEmoji[strings.ToLower(input.IssueType)]
	if emoji == "" {
		emoji = issueTypeEmoji["unspecified"]
	}

	// Create embed for the issue proposal
	embed := &discordgo.MessageEmbed{
		Title:       fmt.Sprintf("%s New Issue Proposed: %s", emoji, input.IssueTitle),
		Description: truncateString(input.IssueBody, 4000),
		Color:       color,
		Fields: []*discordgo.MessageEmbedField{
			{
				Name:   "Severity",
				Value:  strings.ToUpper(input.Severity),
				Inline: true,
			},
			{
				Name:   "Type",
				Value:  strings.ToUpper(input.IssueType),
				Inline: true,
			},
			{
				Name:   "Labels",
				Value:  strings.Join(input.IssueLabels, ", "),
				Inline: true,
			},
			{
				Name:   "Workflow ID",
				Value:  input.WorkflowID,
				Inline: false,
			},
		},
		Footer: &discordgo.MessageEmbedFooter{
			Text: "IterateSwarm AI ChatOps",
		},
		Timestamp: time.Now().Format(time.RFC3339),
	}

	// P1-1 FIX: Use WorkflowID in custom_id format: "action:workflow_id"
	// This ensures precise signal routing back to the specific workflow
	customIDFormat := input.WorkflowID

	approveBtn := discordgo.Button{
		Label:    "Approve",
		Style:    discordgo.SuccessButton,
		CustomID: fmt.Sprintf("approve:%s", customIDFormat),
	}

	rejectBtn := discordgo.Button{
		Label:    "Reject",
		Style:    discordgo.DangerButton,
		CustomID: fmt.Sprintf("reject:%s", customIDFormat),
	}

	// Get channel info and send message with retry
	var channel *discordgo.Channel
	err = retry.SimpleRetry(func() error {
		var channelErr error
		channel, channelErr = dg.Channel(input.ChannelID)
		return channelErr
	})
	if err != nil {
		a.logger.Error("failed to get discord channel", err, "channel_id", input.ChannelID)
		return fmt.Errorf("failed to get Discord channel: %w", err)
	}

	a.logger.Info("sending to discord channel", "channel_name", channel.Name)

	var msg *discordgo.Message
	err = retry.SimpleRetry(func() error {
		var sendErr error
		msg, sendErr = dg.ChannelMessageSendComplex(input.ChannelID, &discordgo.MessageSend{
			Embeds:     []*discordgo.MessageEmbed{embed},
			Components: []discordgo.MessageComponent{discordgo.ActionsRow{Components: []discordgo.MessageComponent{approveBtn, rejectBtn}}},
		})
		return sendErr
	})
	if err != nil {
		a.logger.Error("failed to send discord message", err, "channel_id", input.ChannelID)
		return fmt.Errorf("failed to send Discord message: %w", err)
	}

	duration := time.Since(startTime)
	a.logger.LogActivity(ctx, "SendDiscordApproval", duration, true,
		"message_id", msg.ID,
		"channel_id", input.ChannelID,
	)

	return nil
}

// CreateGitHubIssue creates a GitHub issue when approved.
// Uses SwarmRepo (GitHub-compatible API) when available, falls back to GitHub.
func (a *Activities) CreateGitHubIssue(ctx context.Context, input CreateGitHubIssueInput) (string, error) {
	startTime := time.Now()
	a.logger.Info("creating github issue",
		"title", input.Title,
		"repo_owner", input.RepoOwner,
		"repo_name", input.RepoName,
	)

	// Check if SwarmRepo is configured (via SWARM_REPO_URL env var)
	swarmRepoURL := os.Getenv("SWARM_REPO_URL")
	if swarmRepoURL == "" {
		swarmRepoURL = "http://localhost:4001" // Default to local SwarmRepo
	}

	// Get repository owner from environment if not provided
	owner := input.RepoOwner
	if owner == "" {
		owner = os.Getenv("GITHUB_OWNER")
	}
	if owner == "" {
		owner = "iterateswarm" // Default for SwarmRepo
	}

	// Get repository name from environment if not provided
	repo := input.RepoName
	if repo == "" {
		repo = os.Getenv("GITHUB_REPO")
	}
	if repo == "" {
		repo = "demo" // Default for SwarmRepo
	}

	// Prepare issue request body
	issueLabels := input.Labels
	if issueLabels == nil || len(issueLabels) == 0 {
		issueLabels = []string{"ai-generated"}
	}

	issueBody := map[string]interface{}{
		"title":  input.Title,
		"body":   input.Body,
		"labels": issueLabels,
	}

	jsonBody, err := json.Marshal(issueBody)
	if err != nil {
		return "", fmt.Errorf("failed to marshal issue body: %w", err)
	}

	// Execute request with retry - recreate request on each attempt
	client := &http.Client{Timeout: 30 * time.Second}
	var resp *http.Response
	err = retry.SimpleRetry(func() error {
		// Recreate request body on each retry (bytes.Buffer is single-use)
		url := fmt.Sprintf("%s/repos/%s/%s/issues", swarmRepoURL, owner, repo)
		req, reqErr := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBody))
		if reqErr != nil {
			return fmt.Errorf("failed to create request: %w", reqErr)
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/vnd.github.v3+json")

		var doErr error
		resp, doErr = client.Do(req)
		return doErr
	})
	if err != nil {
		a.logger.Error("failed to create issue in SwarmRepo", err)
		return "", fmt.Errorf("failed to create issue: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		a.logger.Error("SwarmRepo returned error", fmt.Errorf("status: %d", resp.StatusCode),
			"body", string(body),
		)
		return "", fmt.Errorf("SwarmRepo error: %s", resp.Status)
	}

	// Parse response
	var result struct {
		ID      int    `json:"number"`
		HTMLURL string `json:"html_url"`
		Title   string `json:"title"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("failed to parse response: %w", err)
	}

	duration := time.Since(startTime)
	a.logger.LogActivity(ctx, "CreateGitHubIssue", duration, true,
		"issue_url", result.HTMLURL,
		"issue_number", result.ID,
	)

	return result.HTMLURL, nil
}

// truncateString truncates a string to the specified max length.
func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

// StartSwarmInput is the input for the StartSwarm activity.
type StartSwarmInput struct {
	TaskID       string
	FeedbackText string
	Source       string
	UserID       string
	Config       SwarmConfig
}

// SwarmConfig controls which agents are enabled.
type SwarmConfig struct {
	EnableResearcher bool
	EnableSRE        bool
	EnableSWE        bool
	EnableReviewer   bool
}

// StartSwarmOutput contains the results from the multi-agent swarm.
type StartSwarmOutput struct {
	TaskID       string
	Status       string
	Results      []AgentResult
	PRURL        string
	ErrorMessage string
}

// AgentResult contains output from a single agent.
type AgentResult struct {
	AgentName    string
	Success      bool
	Output       string
	Confidence   float64
	ErrorMessage string
}

// StartSwarm calls the Python gRPC server to execute the multi-agent swarm.
func (a *Activities) StartSwarm(ctx context.Context, input StartSwarmInput) (*StartSwarmOutput, error) {
	startTime := time.Now()
	a.logger.Info("starting multi-agent swarm",
		"task_id", input.TaskID,
		"user_id", input.UserID,
		"source", input.Source,
	)

	// Get gRPC server address from environment
	grpcAddr := os.Getenv("AI_GRPC_ADDRESS")
	if grpcAddr == "" {
		grpcAddr = "localhost:50051" // Default address
	}

	// Create gRPC connection with timeout
	connCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(connCtx, grpcAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		a.logger.Error("failed to connect to AI gRPC server", err, "address", grpcAddr)
		return nil, fmt.Errorf("failed to connect to AI service: %w", err)
	}
	defer conn.Close()

	// Create gRPC client
	client := aiv1.NewAgentServiceClient(conn)

	// Build gRPC request
	req := &aiv1.StartSwarmRequest{
		TaskId:       input.TaskID,
		FeedbackText: input.FeedbackText,
		Source:       input.Source,
		UserId:       input.UserID,
		Config: &aiv1.SwarmConfig{
			EnableResearcher: input.Config.EnableResearcher,
			EnableSre:        input.Config.EnableSRE,
			EnableSwe:        input.Config.EnableSWE,
			EnableReviewer:   input.Config.EnableReviewer,
		},
	}

	// Call gRPC with timeout
	callCtx, callCancel := context.WithTimeout(ctx, 5*time.Minute)
	defer callCancel()

	resp, err := client.StartSwarm(callCtx, req)
	if err != nil {
		a.logger.Error("StartSwarm gRPC call failed", err, "task_id", input.TaskID)
		return nil, fmt.Errorf("swarm execution failed: %w", err)
	}

	// Map gRPC response to Go struct
	results := make([]AgentResult, len(resp.Results))
	for i, r := range resp.Results {
		results[i] = AgentResult{
			AgentName:    r.AgentName,
			Success:      r.Success,
			Output:       r.Output,
			Confidence:   float64(r.Confidence),
			ErrorMessage: r.ErrorMessage,
		}
	}

	// Map status
	status := "unknown"
	switch resp.Status {
	case aiv1.SwarmStatus_SWARM_STATUS_COMPLETED:
		status = "completed"
	case aiv1.SwarmStatus_SWARM_STATUS_FAILED:
		status = "failed"
	case aiv1.SwarmStatus_SWARM_STATUS_INTERRUPTED:
		status = "interrupted"
	case aiv1.SwarmStatus_SWARM_STATUS_PENDING:
		status = "pending"
	case aiv1.SwarmStatus_SWARM_STATUS_RUNNING:
		status = "running"
	}

	output := &StartSwarmOutput{
		TaskID:       resp.TaskId,
		Status:       status,
		Results:      results,
		PRURL:        resp.PrUrl,
		ErrorMessage: resp.ErrorMessage,
	}

	duration := time.Since(startTime)
	a.logger.LogActivity(ctx, "StartSwarm", duration, output.Status == "completed",
		"task_id", output.TaskID,
		"status", output.Status,
		"pr_url", output.PRURL,
	)

	return output, nil
}

// =============================================================================
// Standalone Activity Functions for Temporal Workflow Registration
// These wrapper functions allow activities to be called from workflows
// =============================================================================

// globalActivities is a singleton instance for standalone activity functions
var globalActivities = &Activities{
	logger:   logging.NewLogger("workflow"),
	aiClient: nil, // AI client not needed for Go-based agents
}

// AnalyzeFeedback is a standalone activity function for workflow use
func AnalyzeFeedback(ctx context.Context, input AnalyzeFeedbackInput) (*AnalyzeFeedbackOutput, error) {
	return globalActivities.AnalyzeFeedback(ctx, input)
}

// SendDiscordApproval is a standalone activity function for workflow use
func SendDiscordApproval(ctx context.Context, input SendDiscordApprovalInput) error {
	return globalActivities.SendDiscordApproval(ctx, input)
}

// CreateGitHubIssue is a standalone activity function for workflow use
func CreateGitHubIssue(ctx context.Context, input CreateGitHubIssueInput) (string, error) {
	return globalActivities.CreateGitHubIssue(ctx, input)
}

// CleanupHITLRecord removes a HITL record from the database after completion/timeout/rejection
func (a *Activities) CleanupHITLRecord(ctx context.Context, input CleanupHITLRecordInput) error {
	a.logger.Info("cleaning up HITL record", "task_id", input.TaskID)
	// TODO: Implement database cleanup logic
	// This would delete the record from hitl_queue table
	return nil
}

// CleanupHITLRecord is a standalone activity function for workflow use
func CleanupHITLRecord(ctx context.Context, input CleanupHITLRecordInput) error {
	return globalActivities.CleanupHITLRecord(ctx, input)
}

// NotifyHITLTimeout sends a notification when HITL approval times out
func (a *Activities) NotifyHITLTimeout(ctx context.Context, input NotifyHITLTimeoutInput) error {
	a.logger.Info("notifying HITL timeout",
		"channel_id", input.ChannelID,
		"issue_title", input.IssueTitle,
		"workflow_id", input.WorkflowID,
	)

	// Get Discord bot token from environment
	discordToken := os.Getenv("DISCORD_BOT_TOKEN")
	if discordToken == "" {
		a.logger.Warn("discord token not configured, skipping timeout notification")
		return nil
	}

	// Create Discord session with retry
	var dg *discordgo.Session
	err := retry.SimpleRetry(func() error {
		var createErr error
		dg, createErr = discordgo.New("Bot " + discordToken)
		return createErr
	})
	if err != nil {
		a.logger.Error("failed to create discord session", err)
		return fmt.Errorf("failed to create Discord session: %w", err)
	}

	// Send timeout notification
	_, err = dg.ChannelMessageSend(input.ChannelID, fmt.Sprintf(
		"⏰ **Approval timeout**: The issue proposal \"%s\" has timed out after 48 hours without approval.",
		input.IssueTitle,
	))
	if err != nil {
		a.logger.Error("failed to send timeout notification", err)
		return fmt.Errorf("failed to send timeout notification: %w", err)
	}

	return nil
}

// NotifyHITLTimeout is a standalone activity function for workflow use
func NotifyHITLTimeout(ctx context.Context, input NotifyHITLTimeoutInput) error {
	return globalActivities.NotifyHITLTimeout(ctx, input)
}

// SendToDLQ sends a failed task to the Dead Letter Queue
func (a *Activities) SendToDLQ(ctx context.Context, input SendToDLQInput) error {
	a.logger.Error("sending task to DLQ",
		errors.New(input.ErrorMsg),
		"task_id", input.TaskID,
		"attempts", input.Attempts,
	)

	payload, err := json.Marshal(input.Payload)
	if err != nil {
		a.logger.Error("failed to marshal DLQ payload", err, "task_id", input.TaskID)
		payload = []byte("{}")
	}

	if a.db != nil {
		_, err := a.db.ExecContext(ctx,
			`INSERT INTO dead_letter_queue (task_id, payload, error_msg, attempts)
			 VALUES ($1, $2, $3, $4)`,
			input.TaskID, payload, input.ErrorMsg, input.Attempts,
		)
		if err != nil {
			return fmt.Errorf("failed to insert into DLQ: %w", err)
		}
	} else {
		// Database not configured — log for debugging (safe fallback)
		a.logger.Info("DLQ (no DB): task_id=%s error=%s attempts=%d",
			input.TaskID, input.ErrorMsg, input.Attempts)
	}

	a.logger.Info("task sent to DLQ", "task_id", input.TaskID)
	return nil
}

// SendToDLQ is a standalone activity function for workflow use
func SendToDLQ(ctx context.Context, input SendToDLQInput) error {
	return globalActivities.SendToDLQ(ctx, input)
}

// =============================================================================
// Internal Ops Desk Activities
// =============================================================================

// RouteInternalEventInput is input for routing internal events to desks.
type RouteInternalEventInput struct {
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// RouteInternalEventOutput is output from event routing.
type RouteInternalEventOutput struct {
	DeskType  *DeskType           `json:"desk_type"`
	HITLLevel *HITLClassification `json:"hitl_level"`
}

// RouteInternalEvent routes events to appropriate internal ops desk.
// Uses deterministic routing based on event type.
func (a *Activities) RouteInternalEvent(ctx context.Context, input RouteInternalEventInput) (*RouteInternalEventOutput, error) {
	a.logger.Info("routing internal event", "event_type", input.EventType)

	// Deterministic routing map (mirrors Python CoS agent)
	routingMap := map[string]DeskType{
		// Finance Desk events
		"bank_statement":          DeskFinance,
		"transaction_categorized": DeskFinance,
		"invoice_overdue":         DeskFinance,
		"payment_received":        DeskFinance,
		"payroll_due":             DeskFinance,
		"reconciliation_needed":   DeskFinance,
		"ar_reminder":             DeskFinance,
		"ap_due":                  DeskFinance,
		"payroll_prep":            DeskFinance,

		// People Desk events
		"new_hire":            DeskPeople,
		"employee_onboarding": DeskPeople,
		"leave_request":       DeskPeople,
		"appraisal_due":       DeskPeople,
		"offboarding":         DeskPeople,
		"hiring_request":      DeskPeople,
		"interview_scheduled": DeskPeople,

		// Legal Desk events
		"contract_uploaded": DeskLegal,
		"contract_expiry":   DeskLegal,
		"compliance_due":    DeskLegal,
		"regulatory_filing": DeskLegal,
		"policy_update":     DeskLegal,

		// Intelligence Desk events
		"revenue_anomaly":        DeskIntelligence,
		"churn_detected":         DeskIntelligence,
		"unit_economics_review":  DeskIntelligence,
		"ops_anomaly":            DeskIntelligence,
		"policy_change_detected": DeskIntelligence,

		// IT Desk events
		"saas_subscription": DeskIT,
		"tool_unused":       DeskIT,
		"access_review_due": DeskIT,
		"security_audit":    DeskIT,
		"cost_optimization": DeskIT,

		// Admin Desk events
		"meeting_transcript":   DeskAdmin,
		"calendar_management":  DeskAdmin,
		"sop_extraction":       DeskAdmin,
		"documentation_update": DeskAdmin,
		"knowledge_capture":    DeskAdmin,
	}

	desk, exists := routingMap[input.EventType]
	if !exists {
		// Default to admin for unknown events
		desk = DeskAdmin
	}

	// Determine HITL level based on event type and payload
	hitlLevel := determineHITLLevel(input.EventType, input.EventPayload)

	a.logger.Info("event routed", "desk", desk, "hitl_level", hitlLevel)

	return &RouteInternalEventOutput{
		DeskType:  &desk,
		HITLLevel: &hitlLevel,
	}, nil
}

// determineHITLLevel determines the human-in-the-loop classification level.
func determineHITLLevel(eventType string, payload map[string]interface{}) HITLClassification {
	// HIGH: Financial transactions > threshold, legal contracts, security issues
	highEvents := map[string]bool{
		"bank_statement":    true,
		"contract_uploaded": true,
		"security_audit":    true,
		"compliance_due":    true,
		"regulatory_filing": true,
	}

	// MEDIUM: Payroll, hiring, anomalies
	mediumEvents := map[string]bool{
		"payroll_due":     true,
		"hiring_request":  true,
		"revenue_anomaly": true,
		"churn_detected":  true,
		"invoice_overdue": true,
		"contract_expiry": true,
	}

	if highEvents[eventType] {
		return HITLHigh
	}

	if mediumEvents[eventType] {
		return HITLMedium
	}

	return HITLLow
}

// ProcessFinanceOpsInput is input for Finance Desk processing (v1.0 schema).
type ProcessFinanceOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// ProcessFinanceOpsOutput is output from Finance Desk processing.
type ProcessFinanceOpsOutput struct {
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	AlertsSent   []string               `json:"alerts_sent"`
}

// ProcessFinanceOps processes events through Finance Desk (gRPC to Python).
func (a *Activities) ProcessFinanceOps(ctx context.Context, input ProcessFinanceOpsInput) (*ProcessFinanceOpsOutput, error) {
	a.logger.Info("processing finance ops",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// TODO: Call Python Finance Desk agent via gRPC when proto is updated
	// For now, return stub result
	return &ProcessFinanceOpsOutput{
		Result: map[string]interface{}{
			"status":  "processed",
			"desk":    "finance",
			"message": "Finance desk processing complete",
		},
		TasksCreated: []string{},
		AlertsSent:   []string{},
	}, nil
}

// ProcessPeopleOpsInput is input for People Desk processing.
type ProcessPeopleOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// ProcessPeopleOpsOutput is output from People Desk processing.
type ProcessPeopleOpsOutput struct {
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	AlertsSent   []string               `json:"alerts_sent"`
}

// ProcessPeopleOps processes events through People Desk (gRPC to Python).
func (a *Activities) ProcessPeopleOps(ctx context.Context, input ProcessPeopleOpsInput) (*ProcessPeopleOpsOutput, error) {
	a.logger.Info("processing people ops",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// TODO: Call Python People Desk agent via gRPC when proto is updated
	return &ProcessPeopleOpsOutput{
		Result: map[string]interface{}{
			"status":  "processed",
			"desk":    "people",
			"message": "People desk processing complete",
		},
		TasksCreated: []string{},
		AlertsSent:   []string{},
	}, nil
}

// ProcessLegalOps processes events through Legal Desk (gRPC to Python).
func (a *Activities) ProcessLegalOps(ctx context.Context, input ProcessLegalOpsInput) (*ProcessLegalOpsOutput, error) {
	a.logger.Info("processing legal ops",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// TODO: Call Python Legal Desk agent via gRPC when proto is updated
	return &ProcessLegalOpsOutput{
		Result: map[string]interface{}{
			"status":  "processed",
			"desk":    "legal",
			"message": "Legal desk processing complete",
		},
		TasksCreated: []string{},
		AlertsSent:   []string{},
	}, nil
}

// ProcessLegalOpsInput is input for Legal Desk processing.
type ProcessLegalOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// ProcessLegalOpsOutput is output from Legal Desk processing.
type ProcessLegalOpsOutput struct {
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	AlertsSent   []string               `json:"alerts_sent"`
}

// ProcessIntelligenceOps processes events through Intelligence Desk (gRPC to Python).
func (a *Activities) ProcessIntelligenceOps(ctx context.Context, input ProcessIntelligenceOpsInput) (*ProcessIntelligenceOpsOutput, error) {
	a.logger.Info("processing intelligence ops",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// TODO: Call Python Intelligence Desk agent via gRPC when proto is updated
	return &ProcessIntelligenceOpsOutput{
		Result: map[string]interface{}{
			"status":  "processed",
			"desk":    "intelligence",
			"message": "Intelligence desk processing complete",
		},
		TasksCreated: []string{},
		AlertsSent:   []string{},
	}, nil
}

// ProcessIntelligenceOpsInput is input for Intelligence Desk processing.
type ProcessIntelligenceOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// ProcessIntelligenceOpsOutput is output from Intelligence Desk processing.
type ProcessIntelligenceOpsOutput struct {
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	AlertsSent   []string               `json:"alerts_sent"`
}

// ProcessITOps processes events through IT Desk (gRPC to Python).
func (a *Activities) ProcessITOps(ctx context.Context, input ProcessITOpsInput) (*ProcessITOpsOutput, error) {
	a.logger.Info("processing IT ops",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// TODO: Call Python IT Desk agent via gRPC when proto is updated
	return &ProcessITOpsOutput{
		Result: map[string]interface{}{
			"status":  "processed",
			"desk":    "it",
			"message": "IT desk processing complete",
		},
		TasksCreated: []string{},
		AlertsSent:   []string{},
	}, nil
}

// ProcessITOpsInput is input for IT Desk processing.
type ProcessITOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// ProcessITOpsOutput is output from IT Desk processing.
type ProcessITOpsOutput struct {
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	AlertsSent   []string               `json:"alerts_sent"`
}

// ProcessAdminOps processes events through Admin Desk (gRPC to Python).
func (a *Activities) ProcessAdminOps(ctx context.Context, input ProcessAdminOpsInput) (*ProcessAdminOpsOutput, error) {
	a.logger.Info("processing admin ops",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// TODO: Call Python Admin Desk agent via gRPC when proto is updated
	return &ProcessAdminOpsOutput{
		Result: map[string]interface{}{
			"status":  "processed",
			"desk":    "admin",
			"message": "Admin desk processing complete",
		},
		TasksCreated: []string{},
		AlertsSent:   []string{},
	}, nil
}

// ProcessAdminOpsInput is input for Admin Desk processing.
type ProcessAdminOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
}

// ProcessAdminOpsOutput is output from Admin Desk processing.
type ProcessAdminOpsOutput struct {
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	AlertsSent   []string               `json:"alerts_sent"`
}

// callPythonDeskAgent calls Python desk agent via gRPC.
// TODO: Implement when proto is updated with ProcessDeskEvent method
func (a *Activities) callPythonDeskAgent(ctx context.Context, deskType string, input interface{}) (map[string]interface{}, error) {
	// Stub implementation - returns mock result
	return map[string]interface{}{
		"status":  "processed",
		"desk":    deskType,
		"message": "Desk processing complete (stub)",
	}, nil
}

// PersistInternalOpsResultInput is input for persisting internal ops results.
type PersistInternalOpsResultInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	DeskType     string                 `json:"desk_type"`
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created"`
	HITLLevel    string                 `json:"hitl_level"`
}

// PersistInternalOpsResult persists internal ops results to database.
func (a *Activities) PersistInternalOpsResult(ctx context.Context, input PersistInternalOpsResultInput) error {
	a.logger.Info("persisting internal ops result",
		"tenant_id", input.TenantID,
		"desk_type", input.DeskType,
	)

	// TODO: Implement database persistence
	// This would insert into appropriate desk table based on desk_type
	// - finance_ops, people_ops, legal_ops, it_assets, admin_events

	return nil
}

// CreateHITLRecordInput is input for creating HITL records.
type CreateHITLRecordInput struct {
	TenantID  string                 `json:"tenant_id"`
	EventType string                 `json:"event_type"`
	DeskType  string                 `json:"desk_type"`
	HITLLevel string                 `json:"hitl_level"`
	Result    map[string]interface{} `json:"result"`
	ChannelID string                 `json:"channel_id"`
}

// CreateHITLRecord creates a HITL approval record.
func (a *Activities) CreateHITLRecord(ctx context.Context, input CreateHITLRecordInput) error {
	a.logger.Info("creating HITL record",
		"tenant_id", input.TenantID,
		"desk_type", input.DeskType,
		"hitl_level", input.HITLLevel,
	)

	// TODO: Implement database insert for HITL record
	return nil
}

// Standalone activity functions for Temporal registration
func RouteInternalEvent(ctx context.Context, input RouteInternalEventInput) (*RouteInternalEventOutput, error) {
	return globalActivities.RouteInternalEvent(ctx, input)
}

func ProcessFinanceOps(ctx context.Context, input ProcessFinanceOpsInput) (*ProcessFinanceOpsOutput, error) {
	return globalActivities.ProcessFinanceOps(ctx, input)
}

func ProcessPeopleOps(ctx context.Context, input ProcessPeopleOpsInput) (*ProcessPeopleOpsOutput, error) {
	return globalActivities.ProcessPeopleOps(ctx, input)
}

func ProcessLegalOps(ctx context.Context, input ProcessLegalOpsInput) (*ProcessLegalOpsOutput, error) {
	return globalActivities.ProcessLegalOps(ctx, input)
}

func ProcessIntelligenceOps(ctx context.Context, input ProcessIntelligenceOpsInput) (*ProcessIntelligenceOpsOutput, error) {
	return globalActivities.ProcessIntelligenceOps(ctx, input)
}

func ProcessITOps(ctx context.Context, input ProcessITOpsInput) (*ProcessITOpsOutput, error) {
	return globalActivities.ProcessITOps(ctx, input)
}

func ProcessAdminOps(ctx context.Context, input ProcessAdminOpsInput) (*ProcessAdminOpsOutput, error) {
	return globalActivities.ProcessAdminOps(ctx, input)
}

func PersistInternalOpsResult(ctx context.Context, input PersistInternalOpsResultInput) error {
	return globalActivities.PersistInternalOpsResult(ctx, input)
}

func CreateHITLRecord(ctx context.Context, input CreateHITLRecordInput) error {
	return globalActivities.CreateHITLRecord(ctx, input)
}

// =============================================================================
// Chief of Staff Workflow Activities
// =============================================================================

// GetRecentAlertsInput is input for getting recent alerts.
type GetRecentAlertsInput struct {
	TenantID string `json:"tenant_id"`
	Days     int    `json:"days"`
}

// GetRecentAlertsOutput is output from getting recent alerts.
type GetRecentAlertsOutput struct {
	Alerts []map[string]interface{} `json:"alerts"`
}

// GetRecentAlerts retrieves recent alerts for a tenant.
func (a *Activities) GetRecentAlerts(ctx context.Context, input GetRecentAlertsInput) (*GetRecentAlertsOutput, error) {
	a.logger.Info("getting recent alerts", "tenant_id", input.TenantID, "days", input.Days)

	// TODO: Implement database query for recent alerts
	// This would query the alerts table for the last N days

	return &GetRecentAlertsOutput{
		Alerts: []map[string]interface{}{}, // Stub: return empty for now
	}, nil
}

// GetRecentDecisionsInput is input for getting recent decisions.
type GetRecentDecisionsInput struct {
	TenantID string `json:"tenant_id"`
	Days     int    `json:"days"`
}

// GetRecentDecisionsOutput is output from getting recent decisions.
type GetRecentDecisionsOutput struct {
	Decisions []map[string]interface{} `json:"decisions"`
}

// GetRecentDecisions retrieves recent decisions from the decision journal.
func (a *Activities) GetRecentDecisions(ctx context.Context, input GetRecentDecisionsInput) (*GetRecentDecisionsOutput, error) {
	a.logger.Info("getting recent decisions", "tenant_id", input.TenantID, "days", input.Days)

	// TODO: Implement database query for recent decisions
	// This would query the decisions table for the last N days

	return &GetRecentDecisionsOutput{
		Decisions: []map[string]interface{}{}, // Stub: return empty for now
	}, nil
}

// GetCurrentMetricsSnapshotInput is input for getting current metrics.
type GetCurrentMetricsSnapshotInput struct {
	TenantID string `json:"tenant_id"`
}

// GetCurrentMetricsSnapshotOutput is output from getting current metrics.
type GetCurrentMetricsSnapshotOutput struct {
	Metrics map[string]interface{} `json:"metrics"`
}

// GetCurrentMetricsSnapshot retrieves current business metrics snapshot.
func (a *Activities) GetCurrentMetricsSnapshot(ctx context.Context, input GetCurrentMetricsSnapshotInput) (*GetCurrentMetricsSnapshotOutput, error) {
	a.logger.Info("getting current metrics snapshot", "tenant_id", input.TenantID)

	// TODO: Implement metrics aggregation from various sources
	// This would aggregate MRR, churn, active customers, etc.

	return &GetCurrentMetricsSnapshotOutput{
		Metrics: map[string]interface{}{
			"mrr":              0.0,
			"arr":              0.0,
			"active_customers": 0,
			"churn_rate":       0.0,
			"growth_rate":      0.0,
		},
	}, nil
}

// GetInvestorRelationshipHealthInput is input for getting investor relationship health.
type GetInvestorRelationshipHealthInput struct {
	TenantID string `json:"tenant_id"`
}

// GetInvestorRelationshipHealthOutput is output from getting investor relationship health.
type GetInvestorRelationshipHealthOutput struct {
	Health map[string]interface{} `json:"health"`
}

// GetInvestorRelationshipHealth assesses investor relationship health.
func (a *Activities) GetInvestorRelationshipHealth(ctx context.Context, input GetInvestorRelationshipHealthInput) (*GetInvestorRelationshipHealthOutput, error) {
	a.logger.Info("getting investor relationship health", "tenant_id", input.TenantID)

	// TODO: Implement investor relationship analysis
	// This would check last contact dates, raise priorities, etc.

	return &GetInvestorRelationshipHealthOutput{
		Health: map[string]interface{}{
			"total_investors":      0,
			"warm_relationships":   0,
			"cold_relationships":   0,
			"high_priority_raises": 0,
		},
	}, nil
}

// SynthesizeWeeklyBriefInput is input for synthesizing weekly brief.
type SynthesizeWeeklyBriefInput struct {
	TenantID           string                   `json:"tenant_id"`
	Alerts             []map[string]interface{} `json:"alerts"`
	Decisions          []map[string]interface{} `json:"decisions"`
	Metrics            map[string]interface{}   `json:"metrics"`
	InvestorStatus     map[string]interface{}   `json:"investor_status"`
	FounderName        string                   `json:"founder_name"`
	CompanyName        string                   `json:"company_name"`
}

// SynthesizeWeeklyBriefOutput is output from synthesizing weekly brief.
type SynthesizeWeeklyBriefOutput struct {
	Brief string `json:"brief"`
}

// SynthesizeWeeklyBrief synthesizes all data into a weekly brief.
func (a *Activities) SynthesizeWeeklyBrief(ctx context.Context, input SynthesizeWeeklyBriefInput) (*SynthesizeWeeklyBriefOutput, error) {
	a.logger.Info("synthesizing weekly brief", "tenant_id", input.TenantID)

	// TODO: Implement LLM call to synthesize brief
	// This would use the WEEKLY_SYNTHESIS_PROMPT from the task

	return &SynthesizeWeeklyBriefOutput{
		Brief: "🎯 ONE THING: Focus on customer acquisition\n\nWeekly Brief for " + input.FounderName + " at " + input.CompanyName + "...", // Stub
	}, nil
}

// DeliverWeeklyBriefInput is input for delivering weekly brief.
type DeliverWeeklyBriefInput struct {
	TenantID string `json:"tenant_id"`
	Brief    string `json:"brief"`
}

// DeliverWeeklyBriefOutput is output from delivering weekly brief.
type DeliverWeeklyBriefOutput struct {
	Delivered bool `json:"delivered"`
}

// DeliverWeeklyBrief delivers the weekly brief via Slack.
func (a *Activities) DeliverWeeklyBrief(ctx context.Context, input DeliverWeeklyBriefInput) (*DeliverWeeklyBriefOutput, error) {
	a.logger.Info("delivering weekly brief", "tenant_id", input.TenantID)

	// TODO: Implement Slack delivery
	// This would send the brief to Slack

	return &DeliverWeeklyBriefOutput{
		Delivered: true, // Stub: assume success
	}, nil
}

// Standalone activity functions for Chief of Staff workflow
func GetRecentAlerts(ctx context.Context, input GetRecentAlertsInput) (*GetRecentAlertsOutput, error) {
	return globalActivities.GetRecentAlerts(ctx, input)
}

func GetRecentDecisions(ctx context.Context, input GetRecentDecisionsInput) (*GetRecentDecisionsOutput, error) {
	return globalActivities.GetRecentDecisions(ctx, input)
}

func GetCurrentMetricsSnapshot(ctx context.Context, input GetCurrentMetricsSnapshotInput) (*GetCurrentMetricsSnapshotOutput, error) {
	return globalActivities.GetCurrentMetricsSnapshot(ctx, input)
}

func GetInvestorRelationshipHealth(ctx context.Context, input GetInvestorRelationshipHealthInput) (*GetInvestorRelationshipHealthOutput, error) {
	return globalActivities.GetInvestorRelationshipHealth(ctx, input)
}

func SynthesizeWeeklyBrief(ctx context.Context, input SynthesizeWeeklyBriefInput) (*SynthesizeWeeklyBriefOutput, error) {
	return globalActivities.SynthesizeWeeklyBrief(ctx, input)
}

func DeliverWeeklyBrief(ctx context.Context, input DeliverWeeklyBriefInput) (*DeliverWeeklyBriefOutput, error) {
	return globalActivities.DeliverWeeklyBrief(ctx, input)
}

// =============================================================================
// SOP Executor Activity
// =============================================================================

// ExecuteSOPActivity calls Python SOP executor via gRPC
func ExecuteSOPActivity(ctx context.Context, envelope events.EventEnvelope) (*SOPActivityResult, error) {
	// Get gRPC client from context
	client, ok := ctx.Value("grpc_client").(aiv1.SOPExecutorClient)
	if !ok {
		// Try to create a new client
		grpcAddr := "localhost:50051" // Default address
		conn, err := grpc.NewClient(
			grpcAddr,
			grpc.WithTransportCredentials(insecure.NewCredentials()),
		)
		if err != nil {
			return &SOPActivityResult{
				Success: false,
				Message: "gRPC client not available: " + err.Error(),
			}, nil
		}
		defer conn.Close()
		client = aiv1.NewSOPExecutorClient(conn)
	}

	// Convert envelope to protobuf (v1.0 schema)
	protoEnv := &aiv1.EventEnvelope{
		TenantId:       envelope.TenantID,
		EventType:      envelope.EventType,
		Source:         string(envelope.Source),
		PayloadRef:     envelope.PayloadRef,
		PayloadHash:    envelope.PayloadHash,
		OccurredAt:     envelope.OccurredAt.Unix(),
		ReceivedAt:     envelope.ReceivedAt.Unix(),
		TraceId:        envelope.TraceID,
		IdempotencyKey: envelope.IdempotencyKey,
	}

	// Call Python SOP executor with timeout
	callCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	resp, err := client.ExecuteSOP(callCtx, &aiv1.ExecuteSOPRequest{
		Envelope: protoEnv,
	})

	if err != nil {
		return &SOPActivityResult{
			Success: false,
			Message: err.Error(),
		}, err
	}

	return &SOPActivityResult{
		Success:   resp.Success,
		Message:   resp.Message,
		FireAlert: resp.FireAlert,
	}, nil
}
