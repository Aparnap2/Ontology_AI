package workflow

import (
	"fmt"
	"time"

	"go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
	"iterateswarm-core/internal/events"
)

// InternalOpsInput is the input to the InternalOpsWorkflow (v1.0 schema).
type InternalOpsInput struct {
	TenantID     string                 `json:"tenant_id"`
	EventType    string                 `json:"event_type"`
	EventPayload map[string]interface{} `json:"event_payload"`
	ChannelID    string                 `json:"channel_id,omitempty"`
}

// InternalOpsOutput contains the result of internal ops processing.
type InternalOpsOutput struct {
	DeskRouted   string                 `json:"desk_routed"`
	Result       map[string]interface{} `json:"result"`
	TasksCreated []string               `json:"tasks_created,omitempty"`
	AlertsSent   []string               `json:"alerts_sent,omitempty"`
}

// HITLClassification represents the human-in-the-loop classification level.
type HITLClassification string

const (
	HITLLow    HITLClassification = "LOW"
	HITLMedium HITLClassification = "MEDIUM"
	HITLHigh   HITLClassification = "HIGH"
)

// DeskType represents the type of desk handling the event.
type DeskType string

const (
	DeskFinance      DeskType = "finance"
	DeskPeople       DeskType = "people"
	DeskLegal        DeskType = "legal"
	DeskIntelligence DeskType = "intelligence"
	DeskIT           DeskType = "it"
	DeskAdmin        DeskType = "admin"
)

// InternalOpsWorkflow processes internal operations events through appropriate desks.
// This workflow handles all 6 desks: Finance, People, Legal, Intelligence, IT, Admin.
func InternalOpsWorkflow(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	// Set activity options with retry policy
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 5 * time.Minute,
		HeartbeatTimeout:    30 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    time.Minute,
			MaximumAttempts:    5,
		},
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	workflow.GetLogger(ctx).Info("starting internal ops workflow",
		"tenant_id", input.TenantID,
		"event_type", input.EventType,
	)

	// Step 1: Route event to appropriate desk
	var deskType DeskType
	var hitlLevel HITLClassification

	err := workflow.ExecuteActivity(ctx, RouteInternalEvent, RouteInternalEventInput{
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &RouteInternalEventOutput{
		DeskType:  &deskType,
		HITLLevel: &hitlLevel,
	})
	if err != nil {
		workflow.GetLogger(ctx).Error("failed to route event", "error", err)
		return nil, err
	}

	workflow.GetLogger(ctx).Info("event routed",
		"desk", deskType,
		"hitl_level", hitlLevel,
	)

	// Step 2: Process with appropriate desk based on routing
	var result *InternalOpsOutput

	switch deskType {
	case DeskFinance:
		result, err = processFinanceDesk(ctx, input)
	case DeskPeople:
		result, err = processPeopleDesk(ctx, input)
	case DeskLegal:
		result, err = processLegalDesk(ctx, input)
	case DeskIntelligence:
		result, err = processIntelligenceDesk(ctx, input)
	case DeskIT:
		result, err = processITDesk(ctx, input)
	case DeskAdmin:
		result, err = processAdminDesk(ctx, input)
	default:
		return nil, temporal.NewNonRetryableApplicationError("unknown desk type", "InvalidDesk", nil)
	}

	if err != nil {
		workflow.GetLogger(ctx).Error("desk processing failed",
			"desk", deskType,
			"error", err,
		)
		return nil, err
	}

	result.DeskRouted = string(deskType)

	// Step 3: Apply HITL gate if needed (MEDIUM/HIGH classification)
	if hitlLevel == HITLMedium || hitlLevel == HITLHigh {
		err := applyHITLGate(ctx, input, result, hitlLevel)
		if err != nil {
			workflow.GetLogger(ctx).Error("HITL gate failed", "error", err)
			return nil, err
		}
	}

	// Step 4: Persist result to database
	err = workflow.ExecuteActivity(ctx, PersistInternalOpsResult, PersistInternalOpsResultInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		DeskType:     string(deskType),
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		HITLLevel:    string(hitlLevel),
	}).Get(ctx, nil)

	if err != nil {
		workflow.GetLogger(ctx).Warn("failed to persist result", "error", err)
		// Don't fail workflow on persistence error
	}

	workflow.GetLogger(ctx).Info("internal ops workflow completed",
		"desk", deskType,
		"hitl_level", hitlLevel,
		"tasks_created", len(result.TasksCreated),
	)

	return result, nil
}

// processFinanceDesk processes events through Finance Desk
func processFinanceDesk(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	var result ProcessFinanceOpsOutput
	err := workflow.ExecuteActivity(ctx, ProcessFinanceOps, ProcessFinanceOpsInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &InternalOpsOutput{
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		AlertsSent:   result.AlertsSent,
	}, nil
}

// processPeopleDesk processes events through People Desk
func processPeopleDesk(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	var result ProcessPeopleOpsOutput
	err := workflow.ExecuteActivity(ctx, ProcessPeopleOps, ProcessPeopleOpsInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &InternalOpsOutput{
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		AlertsSent:   result.AlertsSent,
	}, nil
}

// processLegalDesk processes events through Legal Desk
func processLegalDesk(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	var result ProcessLegalOpsOutput
	err := workflow.ExecuteActivity(ctx, ProcessLegalOps, ProcessLegalOpsInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &InternalOpsOutput{
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		AlertsSent:   result.AlertsSent,
	}, nil
}

// processIntelligenceDesk processes events through Intelligence Desk
func processIntelligenceDesk(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	var result ProcessIntelligenceOpsOutput
	err := workflow.ExecuteActivity(ctx, ProcessIntelligenceOps, ProcessIntelligenceOpsInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &InternalOpsOutput{
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		AlertsSent:   result.AlertsSent,
	}, nil
}

// processITDesk processes events through IT Desk
func processITDesk(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	var result ProcessITOpsOutput
	err := workflow.ExecuteActivity(ctx, ProcessITOps, ProcessITOpsInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &InternalOpsOutput{
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		AlertsSent:   result.AlertsSent,
	}, nil
}

// processAdminDesk processes events through Admin Desk
func processAdminDesk(ctx workflow.Context, input InternalOpsInput) (*InternalOpsOutput, error) {
	var result ProcessAdminOpsOutput
	err := workflow.ExecuteActivity(ctx, ProcessAdminOps, ProcessAdminOpsInput{
		TenantID:     input.TenantID,
		EventType:    input.EventType,
		EventPayload: input.EventPayload,
	}).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &InternalOpsOutput{
		Result:       result.Result,
		TasksCreated: result.TasksCreated,
		AlertsSent:   result.AlertsSent,
	}, nil
}

// applyHITLGate applies human-in-the-loop approval gate for MEDIUM/HIGH classification
func applyHITLGate(ctx workflow.Context, input InternalOpsInput, result *InternalOpsOutput, hitlLevel HITLClassification) error {
	// Create HITL record
	err := workflow.ExecuteActivity(ctx, CreateHITLRecord, CreateHITLRecordInput{
		TenantID:  input.TenantID,
		EventType: input.EventType,
		DeskType:  result.DeskRouted,
		HITLLevel: string(hitlLevel),
		Result:    result.Result,
		ChannelID: input.ChannelID,
	}).Get(ctx, nil)

	if err != nil {
		return err
	}

	// Wait for approval signal
	signalChan := workflow.GetSignalChannel(ctx, "hitl-approval")
	var approved bool

	// Wait for signal with 48-hour timeout
	timedOut, err := workflow.AwaitWithTimeout(ctx, 48*time.Hour, func() bool {
		return signalChan.ReceiveAsync(&approved)
	})

	if err != nil {
		return err
	}

	if timedOut {
		workflow.GetLogger(ctx).Warn("HITL approval timed out")
		// Notify timeout
		_ = workflow.ExecuteActivity(ctx, NotifyHITLTimeout, NotifyHITLTimeoutInput{
			ChannelID:  input.ChannelID,
			IssueTitle: input.EventType,
			WorkflowID: input.TenantID,
		}).Get(ctx, nil)
		return nil
	}

	if !approved {
		workflow.GetLogger(ctx).Info("HITL approval rejected")
		return nil
	}

	workflow.GetLogger(ctx).Info("HITL approval received")
	return nil
}

// =============================================================================
// BusinessOS Workflow — Parent Router for SOP Execution
// =============================================================================

const (
	// ContinueAsNewThreshold — fire CAN before hitting Temporal's 51,200 hard limit
	ContinueAsNewThreshold = 5000

	// Default task queue for AI activities
	AITaskQueue = "AI_TASK_QUEUE"
)

// BusinessOSState tracks workflow state across Continue-As-New cycles (v1.0 schema)
type BusinessOSState struct {
	TenantID        string          `json:"tenant_id"`
	EventsProcessed int             `json:"events_processed"`
	SeenKeys        map[string]bool `json:"seen_keys"`
}

// BusinessOSWorkflow is the parent router — spawns child workflows, never executes SOP logic
// It receives events via signals and spawns agent workflows for each unique event.
// Accepts BusinessOSState to preserve SeenKeys across Continue-As-New cycles.
func BusinessOSWorkflow(ctx workflow.Context, st BusinessOSState) error {
	if st.SeenKeys == nil {
		st.SeenKeys = make(map[string]bool)
	}

	// Get signal channel for incoming events
	signalChan := workflow.GetSignalChannel(ctx, "ontology_ai.events")

	for {
		// ── Guard: Continue-As-New before hitting Temporal history limits
		if st.EventsProcessed >= ContinueAsNewThreshold {
			workflow.GetLogger(ctx).Info(
				"Triggering Continue-As-New",
				"events_processed", st.EventsProcessed,
				"tenant_id", st.TenantID,
				"seen_keys", len(st.SeenKeys),
			)
			return workflow.NewContinueAsNewError(ctx, BusinessOSWorkflow, st)
		}

		// ── Receive next event
		var envelope events.EventEnvelope
		if !signalChan.ReceiveAsync(&envelope) {
			// No events pending — wait for next signal
			signalChan.Receive(ctx, &envelope)
		}

		// ── Idempotency: skip duplicates
		if st.SeenKeys[envelope.IdempotencyKey] {
			workflow.GetLogger(ctx).Info(
				"Skipping duplicate event",
				"idempotency_key", envelope.IdempotencyKey,
				"event_type", envelope.EventType,
			)
			continue
		}
		st.SeenKeys[envelope.IdempotencyKey] = true
		st.EventsProcessed++

		// ── Spawn child workflow: parent NEVER executes SOP logic
		// v1.0: AgentName determines which agent handles the event
		childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
			WorkflowID:        fmt.Sprintf("agent:%s:%s", envelope.EventType, envelope.TenantID),
			TaskQueue:         AITaskQueue,
			ParentClosePolicy: enums.PARENT_CLOSE_POLICY_ABANDON, // Child continues if parent dies
		})

		// Fire-and-forget: don't wait for SOP completion
		_ = workflow.ExecuteChildWorkflow(childCtx, SOPExecutorWorkflow, envelope)

		workflow.GetLogger(ctx).Info(
			"Spawned agent workflow",
			"event_type", envelope.EventType,
			"tenant_id", envelope.TenantID,
		)
	}
}

// SOPExecutorWorkflow executes a single SOP via Python gRPC activity (v1.0)
func SOPExecutorWorkflow(ctx workflow.Context, envelope events.EventEnvelope) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("Starting agent execution", "event_type", envelope.EventType, "tenant_id", envelope.TenantID)

	// Set activity options with retry policy
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 30 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    10 * time.Second,
			MaximumAttempts:    3,
		},
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	// Execute Python activity via gRPC
	var result SOPActivityResult
	err := workflow.ExecuteActivity(ctx, ExecuteSOPActivity, envelope).Get(ctx, &result)

	if err != nil {
		logger.Error("SOP execution failed", "error", err)
		return err
	}

	logger.Info("SOP execution completed", "success", result.Success)

	// Fire alert if needed
	if result.FireAlert {
		logger.Info("Alert should be fired", "message", result.Message)
		// TODO: Implement alert firing activity
	}

	return nil
}

// SOPActivityResult is the result from Python SOP execution
type SOPActivityResult struct {
	Success   bool   `json:"success"`
	Message   string `json:"message"`
	FireAlert bool   `json:"fire_alert"`
}
