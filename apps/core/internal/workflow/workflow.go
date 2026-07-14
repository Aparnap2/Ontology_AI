package workflow

import (
	"errors"
	"strings"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

// FeedbackInput is the input to the FeedbackWorkflow.
type FeedbackInput struct {
	Text      string
	Source    string
	UserID    string
	ChannelID string
	RepoOwner string
	RepoName  string
}

// AnalyzeFeedbackOutput contains the result of AI analysis.
type AnalyzeFeedbackOutput struct {
	IsDuplicate bool
	Title       string
	Description string
	Labels      []string
	Severity    string
	IssueType   string
	Confidence  float64 // P3-1: Added confidence field from AI response
}

// SendDiscordApprovalInput is input for sending Discord approval request.
// P1-1 FIX: Changed from WorkflowRunID to WorkflowID to fix signal routing
type SendDiscordApprovalInput struct {
	ChannelID   string
	IssueTitle  string
	IssueBody   string
	IssueLabels []string
	Severity    string
	IssueType   string
	WorkflowID  string // Was WorkflowRunID - now uses WorkflowID for correct signal routing
}

// CreateGitHubIssueInput is input for creating a GitHub issue.
type CreateGitHubIssueInput struct {
	Title     string
	Body      string
	Labels    []string
	RepoOwner string
	RepoName  string
	Assignee  string
}

// CleanupHITLRecordInput is input for cleaning up HITL records.
type CleanupHITLRecordInput struct {
	TaskID string
}

// NotifyHITLTimeoutInput is input for notifying about HITL timeout.
type NotifyHITLTimeoutInput struct {
	ChannelID  string
	IssueTitle string
	WorkflowID string
}

// SendToDLQInput is input for sending a task to the Dead Letter Queue.
type SendToDLQInput struct {
	TaskID   string
	Payload  map[string]interface{}
	ErrorMsg string
	Attempts int
}

// HITLTimeoutDuration is the timeout for human-in-the-loop approval (48 hours).
const HITLTimeoutDuration = 48 * time.Hour

// FeedbackWorkflow is the main workflow for processing feedback.
func FeedbackWorkflow(ctx workflow.Context, input FeedbackInput) error {
	// Set activity options with retry policy (MaximumAttempts: 5)
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 2 * time.Minute,
		HeartbeatTimeout:    30 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    time.Minute,
			MaximumAttempts:    5,
		},
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	// Channel for receiving signals (user approval)
	signalChan := workflow.GetSignalChannel(ctx, "user-action")

	var analyzeResult *AnalyzeFeedbackOutput

	// Step 1: Analyze feedback with AI (using activity function reference)
	err := workflow.ExecuteActivity(ctx, AnalyzeFeedback, AnalyzeFeedbackInput{
		Text:      input.Text,
		Source:    input.Source,
		UserID:    input.UserID,
		ChannelID: input.ChannelID,
	}).Get(ctx, &analyzeResult)
	if err != nil {
		// Check if we've exhausted retries and should send to DLQ
		if isRetryExhausted(err) {
			sendToDLQ(ctx, input, err, 5)
		}
		return err
	}

	// If duplicate, skip to end
	if analyzeResult.IsDuplicate {
		return nil
	}

	// Step 2: Send approval request to Discord
	// P1-1 FIX: Use WorkflowID instead of RunID for correct signal routing
	workflowInfo := workflow.GetInfo(ctx)
	err = workflow.ExecuteActivity(ctx, SendDiscordApproval, SendDiscordApprovalInput{
		ChannelID:   input.ChannelID,
		IssueTitle:  analyzeResult.Title,
		IssueBody:   analyzeResult.Description,
		IssueLabels: analyzeResult.Labels,
		Severity:    analyzeResult.Severity,
		IssueType:   analyzeResult.IssueType,
		WorkflowID:  workflowInfo.WorkflowExecution.ID, // Was RunID - now uses ID
	}).Get(ctx, nil)
	if err != nil {
		if isRetryExhausted(err) {
			sendToDLQ(ctx, input, err, 5)
		}
		return err
	}

	// Step 3: Wait for user approval with 48-hour timeout
	var signalValue interface{}
	signalReceived := false

	// Wait for signal with 48-hour timeout using AwaitWithTimeout
	timedOut, err := workflow.AwaitWithTimeout(ctx, HITLTimeoutDuration, func() bool {
		received := signalChan.ReceiveAsync(&signalValue)
		if received {
			signalReceived = true
			return true
		}
		return false
	})
	if err != nil {
		return err
	}

	// Check if we timed out
	if timedOut && !signalReceived {
		// HITL timed out - notify and cleanup
		_ = workflow.ExecuteActivity(ctx, NotifyHITLTimeout, NotifyHITLTimeoutInput{
			ChannelID:  input.ChannelID,
			IssueTitle: analyzeResult.Title,
			WorkflowID: workflowInfo.WorkflowExecution.ID,
		}).Get(ctx, nil)

		// Cleanup HITL record
		_ = workflow.ExecuteActivity(ctx, CleanupHITLRecord, CleanupHITLRecordInput{
			TaskID: workflowInfo.WorkflowExecution.ID,
		}).Get(ctx, nil)

		return nil
	}

	// Check if we received a signal or timed out
	approved := false
	if signalReceived {
		if s, ok := signalValue.(string); ok {
			approved = s == "approve"
		}
	}

	// Step 4: Handle approval/rejection
	if !approved {
		// Cleanup HITL record on rejection
		_ = workflow.ExecuteActivity(ctx, CleanupHITLRecord, CleanupHITLRecordInput{
			TaskID: workflowInfo.WorkflowExecution.ID,
		}).Get(ctx, nil)
		return nil
	}

	// Step 5: Create GitHub issue
	err = workflow.ExecuteActivity(ctx, CreateGitHubIssue, CreateGitHubIssueInput{
		Title:     analyzeResult.Title,
		Body:      analyzeResult.Description,
		Labels:    analyzeResult.Labels,
		RepoOwner: input.RepoOwner,
		RepoName:  input.RepoName,
	}).Get(ctx, nil)

	if err != nil {
		if isRetryExhausted(err) {
			sendToDLQ(ctx, input, err, 5)
		}
		return err
	}

	// Cleanup HITL record after successful issue creation
	_ = workflow.ExecuteActivity(ctx, CleanupHITLRecord, CleanupHITLRecordInput{
		TaskID: workflowInfo.WorkflowExecution.ID,
	}).Get(ctx, nil)

	return nil
}

// isRetryExhausted checks if an error indicates retry exhaustion
// Returns true when Temporal's retry policy has been fully consumed:
//   - Non-retryable ApplicationErrors (Temporal refuses to retry)
//   - Timeout errors after all retry windows expired
//   - Errors containing retry-exhaustion strings (fallback)
func isRetryExhausted(err error) bool {
	if err == nil {
		return false
	}
	var applicationErr *temporal.ApplicationError
	if errors.As(err, &applicationErr) {
		return applicationErr.NonRetryable()
	}
	var timeoutErr *temporal.TimeoutError
	if errors.As(err, &timeoutErr) {
		return true
	}
	errMsg := err.Error()
	return temporal.IsApplicationError(err) ||
		(strings.Contains(errMsg, "retry") && strings.Contains(errMsg, "exhaust"))
}

// sendToDLQ sends a failed task to the Dead Letter Queue
func sendToDLQ(ctx workflow.Context, input FeedbackInput, err error, attempts int) {
	payload := map[string]interface{}{
		"text":       input.Text,
		"source":     input.Source,
		"user_id":    input.UserID,
		"channel_id": input.ChannelID,
		"repo_owner": input.RepoOwner,
		"repo_name":  input.RepoName,
	}

	_ = workflow.ExecuteActivity(ctx, SendToDLQ, SendToDLQInput{
		TaskID:   input.UserID + "-" + time.Now().String(),
		Payload:  payload,
		ErrorMsg: err.Error(),
		Attempts: attempts,
	}).Get(ctx, nil)
}
