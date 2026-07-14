package workflow

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
	"iterateswarm-core/internal/events"
)

// dlqDB is a package-level database connection for Dead Letter Queue operations.
// Initialized via InitDLQDatabase before starting the worker.
var dlqDB *sql.DB

// InitDLQDatabase sets the database connection used by SendToDLQActivity.
// Must be called before starting the Temporal worker.
func InitDLQDatabase(db *sql.DB) {
	dlqDB = db
}

// WorkflowRouterContinueAsNewThreshold is the number of events before triggering Continue-As-New in WorkflowRouter
const WorkflowRouterContinueAsNewThreshold = 1000

// WorkflowRouterState tracks workflow state across Continue-As-New cycles
type WorkflowRouterState struct {
	TenantID        string          `json:"tenant_id"`
	EventsProcessed int             `json:"events_processed"`
	SeenKeys        map[string]bool `json:"seen_keys"`
}

// EventRoutingTable maps event types to workflow names
type EventRoutingTable map[string][]string

// GetRoutingTable returns the event routing configuration
// This is the central routing logic for OntologyAI v1.0
func GetRoutingTable() EventRoutingTable {
	return EventRoutingTable{
		// ==================== REVENUE TRACKER ====================
		// Payment & Subscription events from Razorpay
		"PAYMENT_SUCCESS":       {"RevenueWorkflow"},
		"SUBSCRIPTION_CREATED":  {"RevenueWorkflow"},
		"SUBSCRIPTION_UPDATED":  {"RevenueWorkflow"},
		"SUBSCRIPTION_CANCELED": {"RevenueWorkflow"},
		"PAYMENT_FAILED":        {"RevenueWorkflow"},
		"INVOICE_PAID":          {"RevenueWorkflow"},
		"INVOICE_EXPIRED":       {"RevenueWorkflow"},
		"REFUND_CREATED":        {"RevenueWorkflow"},

		// CRM & Sales events
		"CRM_DEAL_CREATED": {"RevenueWorkflow"},
		"CRM_DEAL_UPDATED": {"RevenueWorkflow"},
		"CRM_DEAL_WON":     {"RevenueWorkflow"},
		"CRM_DEAL_LOST":    {"RevenueWorkflow"},

		// Weekly tick for revenue review
		"TIME_TICK_WEEKLY": {"RevenueWorkflow", "ChiefOfStaffWorkflow"}, // Multi-route

		// ==================== CS AGENT ====================
		// User lifecycle events
		"USER_SIGNED_UP":       {"CSWorkflow"},
		"USER_LOGGED_IN":       {"CSWorkflow"},
		"USER_LOGGED_OUT":      {"CSWorkflow"},
		"USER_PROFILE_UPDATED": {"CSWorkflow"},

		// Support events
		"SUPPORT_TICKET_CREATED":  {"CSWorkflow"},
		"SUPPORT_TICKET_UPDATED":  {"CSWorkflow"},
		"SUPPORT_TICKET_RESOLVED": {"CSWorkflow"},

		// Day-based ticks for CS follow-ups
		"TIME_TICK_D1": {"CSWorkflow"}, // Day 1 check-in
		"TIME_TICK_D3": {"CSWorkflow"}, // Day 3 follow-up
		"TIME_TICK_D7": {"CSWorkflow"}, // Day 7 retention check

		// ==================== PEOPLE COORDINATOR ====================
		// Employee lifecycle
		"EMPLOYEE_CREATED":    {"PeopleWorkflow"},
		"EMPLOYEE_UPDATED":    {"PeopleWorkflow"},
		"EMPLOYEE_TERMINATED": {"PeopleWorkflow"},

		// Checklist & onboarding
		"CHECKLIST_ITEM_CONFIRMED": {"PeopleWorkflow"},
		"CHECKLIST_ITEM_COMPLETED": {"PeopleWorkflow"},
		"ONBOARDING_STARTED":       {"PeopleWorkflow"},
		"ONBOARDING_COMPLETED":     {"PeopleWorkflow"},

		// ==================== FP&A MONITOR ====================
		// Expense & accounting
		"EXPENSE_RECORDED": {"FPAWorkflow"},
		"EXPENSE_APPROVED": {"FPAWorkflow"},
		"EXPENSE_REJECTED": {"FPAWorkflow"},

		// Bank & payment processing
		"BANK_WEBHOOK":            {"FPAWorkflow"},
		"BANK_TRANSACTION":        {"FPAWorkflow"},
		"VENDOR_INVOICE_RECEIVED": {"FPAWorkflow"},
		"VENDOR_INVOICE_PAID":     {"FPAWorkflow"},

		// Daily finance review
		"TIME_TICK_DAILY": {"FPAWorkflow"},

		// ==================== CHIEF OF STAFF ====================
		// Monthly executive review
		"TIME_TICK_MONTHLY": {"ChiefOfStaffWorkflow"},

		// Agent outputs require CoS attention
		"AGENT_OUTPUT": {"ChiefOfStaffWorkflow"},

		// Strategic decisions
		"DECISION_LOGGED": {"ChiefOfStaffWorkflow"},
		"POLICY_CHANGE":   {"ChiefOfStaffWorkflow"},
	}
}

// WorkflowRouter is the parent router that spawns child workflows based on event type.
// It implements the router pattern with Continue-As-New at 1000 events to prevent
// Temporal history size bloat.
// Accepts WorkflowRouterState to preserve SeenKeys across Continue-As-New cycles.
func WorkflowRouter(ctx workflow.Context, st WorkflowRouterState) error {
	if st.SeenKeys == nil {
		st.SeenKeys = make(map[string]bool)
	}

	routingTable := GetRoutingTable()

	// Get signal channel for incoming events
	signalChan := workflow.GetSignalChannel(ctx, "ontology_ai.events")

	for {
		// Guard: Continue-As-New before hitting Temporal history limits
		// This is critical for long-running workflows to prevent history size errors
		if st.EventsProcessed >= WorkflowRouterContinueAsNewThreshold {
			workflow.GetLogger(ctx).Info(
				"Triggering Continue-As-New",
				"events_processed", st.EventsProcessed,
				"tenant_id", st.TenantID,
				"seen_keys", len(st.SeenKeys),
			)
			return workflow.NewContinueAsNewError(ctx, WorkflowRouter, st)
		}

		// Receive next event from signal channel
		var envelope events.EventEnvelope
		signalChan.Receive(ctx, &envelope)

		// Idempotency: skip duplicate events based on idempotency key
		// This prevents double-processing of retried events
		if st.SeenKeys[envelope.IdempotencyKey] {
			workflow.GetLogger(ctx).Info(
				"Skipping duplicate event",
				"idempotency_key", envelope.IdempotencyKey,
				"event_type", envelope.EventType,
				"event_id", envelope.TraceID,
			)
			continue
		}
		st.SeenKeys[envelope.IdempotencyKey] = true
		st.EventsProcessed++

		// Route to appropriate workflows based on event type
		workflowNames, exists := routingTable[envelope.EventType]
		if !exists {
			// Unknown event - send to Dead Letter Queue for manual inspection
			workflow.GetLogger(ctx).Warn(
				"Unknown event type, sending to DLQ",
				"event_type", envelope.EventType,
				"source", envelope.Source,
				"tenant_id", envelope.TenantID,
			)

			// Execute DLQ activity with timeout
			ao := workflow.ActivityOptions{
				StartToCloseTimeout: 5 * time.Second,
				RetryPolicy: &temporal.RetryPolicy{
					InitialInterval:    time.Second,
					BackoffCoefficient: 2.0,
					MaximumAttempts:    3,
				},
			}
			ctxWithAO := workflow.WithActivityOptions(ctx, ao)
			workflow.ExecuteActivity(ctxWithAO, SendToDLQActivity, envelope)
			continue
		}

		// Spawn child workflows for each target workflow
		// Multi-route events (like TIME_TICK_WEEKLY) will spawn multiple children
		for _, workflowName := range workflowNames {
			var childWorkflow interface{}
			switch workflowName {
			case "RevenueWorkflow":
				childWorkflow = RevenueWorkflow
			case "CSWorkflow":
				childWorkflow = CSWorkflow
			case "PeopleWorkflow":
				childWorkflow = PeopleWorkflow
			case "FinanceWorkflow":
				childWorkflow = FinanceWorkflow
			case "ChiefOfStaffWorkflow":
				childWorkflow = ChiefOfStaffWorkflow
			default:
				workflow.GetLogger(ctx).Error(
					"Unknown workflow name in routing table",
					"workflow_name", workflowName,
					"event_type", envelope.EventType,
				)
				continue
			}

			// Create child workflow context with fire-and-forget semantics
			// ParentClosePolicyAbandon ensures child continues even if parent stops
			childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
				WorkflowID:        fmt.Sprintf("child:%s:%s:%s", workflowName, envelope.TenantID, envelope.TraceID),
				TaskQueue:         "ai_task_queue",
				ParentClosePolicy: 1, // PARENT_CLOSE_POLICY_ABANDON
				RetryPolicy: &temporal.RetryPolicy{
					InitialInterval:    time.Second,
					BackoffCoefficient: 2.0,
					MaximumAttempts:    3,
				},
			})

			// Fire-and-forget: do NOT wait for child completion
			// This allows the router to continue processing events immediately
			_ = workflow.ExecuteChildWorkflow(childCtx, childWorkflow, envelope)

			workflow.GetLogger(ctx).Info(
				"Spawned child workflow",
				"event_type", envelope.EventType,
				"workflow_name", workflowName,
				"tenant_id", envelope.TenantID,
				"trace_id", envelope.TraceID,
			)
		}
	}
}

// RevenueWorkflow handles all revenue-related events (payments, subscriptions, CRM deals).
// It routes the event to the Python Revenue agent via gRPC for processing.
func RevenueWorkflow(ctx workflow.Context, envelope events.EventEnvelope) error {
	logger := workflow.GetLogger(ctx)
	logger.Info(
		"RevenueWorkflow started",
		"event_type", envelope.EventType,
		"tenant_id", envelope.TenantID,
		"trace_id", envelope.TraceID,
	)

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

	// Execute Python revenue agent via gRPC
	var result SOPActivityResult
	err := workflow.ExecuteActivity(ctx, ExecuteSOPActivity, envelope).Get(ctx, &result)
	if err != nil {
		logger.Error("RevenueWorkflow: SOP execution failed", "error", err)
		return err
	}

	logger.Info("RevenueWorkflow completed",
		"success", result.Success,
		"message", result.Message,
	)

	// Fire alert if the agent detected an issue requiring attention
	if result.FireAlert {
		logger.Info("RevenueWorkflow: alert flagged", "message", result.Message)
	}

	return nil
}

// CSWorkflow handles customer success events (signups, support tickets, engagement ticks).
// It routes the event to the Python CS agent via gRPC for processing.
func CSWorkflow(ctx workflow.Context, envelope events.EventEnvelope) error {
	logger := workflow.GetLogger(ctx)
	logger.Info(
		"CSWorkflow started",
		"event_type", envelope.EventType,
		"tenant_id", envelope.TenantID,
		"trace_id", envelope.TraceID,
	)

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

	// Execute Python CS agent via gRPC
	var result SOPActivityResult
	err := workflow.ExecuteActivity(ctx, ExecuteSOPActivity, envelope).Get(ctx, &result)
	if err != nil {
		logger.Error("CSWorkflow: SOP execution failed", "error", err)
		return err
	}

	logger.Info("CSWorkflow completed",
		"success", result.Success,
		"message", result.Message,
	)

	// Fire alert if the agent detected an issue requiring attention
	if result.FireAlert {
		logger.Info("CSWorkflow: alert flagged", "message", result.Message)
	}

	return nil
}

// PeopleWorkflow handles HR/people operations (employee lifecycle, onboarding, checklists).
// It routes the event to the Python People agent via gRPC for processing.
func PeopleWorkflow(ctx workflow.Context, envelope events.EventEnvelope) error {
	logger := workflow.GetLogger(ctx)
	logger.Info(
		"PeopleWorkflow started",
		"event_type", envelope.EventType,
		"tenant_id", envelope.TenantID,
		"trace_id", envelope.TraceID,
	)

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

	// Execute Python people agent via gRPC
	var result SOPActivityResult
	err := workflow.ExecuteActivity(ctx, ExecuteSOPActivity, envelope).Get(ctx, &result)
	if err != nil {
		logger.Error("PeopleWorkflow: SOP execution failed", "error", err)
		return err
	}

	logger.Info("PeopleWorkflow completed",
		"success", result.Success,
		"message", result.Message,
	)

	// Fire alert if the agent detected an issue requiring attention
	if result.FireAlert {
		logger.Info("PeopleWorkflow: alert flagged", "message", result.Message)
	}

	return nil
}

// FinanceWorkflow handles finance operations (expenses, bank webhooks, vendor invoices).
// It routes the event to the Python Finance agent via gRPC for processing.
func FinanceWorkflow(ctx workflow.Context, envelope events.EventEnvelope) error {
	logger := workflow.GetLogger(ctx)
	logger.Info(
		"FinanceWorkflow started",
		"event_type", envelope.EventType,
		"tenant_id", envelope.TenantID,
		"trace_id", envelope.TraceID,
	)

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

	// Execute Python finance agent via gRPC
	var result SOPActivityResult
	err := workflow.ExecuteActivity(ctx, ExecuteSOPActivity, envelope).Get(ctx, &result)
	if err != nil {
		logger.Error("FinanceWorkflow: SOP execution failed", "error", err)
		return err
	}

	logger.Info("FinanceWorkflow completed",
		"success", result.Success,
		"message", result.Message,
	)

	// Fire alert if the agent detected an issue requiring attention
	if result.FireAlert {
		logger.Info("FinanceWorkflow: alert flagged", "message", result.Message)
	}

	return nil
}

// ChiefOfStaffWorkflow handles executive-level events (weekly synthesis, agent outputs, decisions).
func ChiefOfStaffWorkflow(ctx workflow.Context, envelope events.EventEnvelope) error {
	logger := workflow.GetLogger(ctx)
	logger.Info(
		"ChiefOfStaffWorkflow started",
		"event_type", envelope.EventType,
		"tenant_id", envelope.TenantID,
		"trace_id", envelope.TraceID,
	)

	// Activity options
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 5 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumAttempts:    3,
		},
	}
	ctxWithAO := workflow.WithActivityOptions(ctx, ao)

	// Get recent alerts (last 7 days)
	alertsResult := &GetRecentAlertsOutput{}
	err := workflow.ExecuteActivity(ctxWithAO, GetRecentAlerts, GetRecentAlertsInput{
		TenantID: envelope.TenantID,
		Days:     7,
	}).Get(ctx, alertsResult)
	if err != nil {
		logger.Error("Failed to get recent alerts", err)
		// Continue with empty alerts
		alertsResult = &GetRecentAlertsOutput{Alerts: []map[string]interface{}{}}
	}

	// Get recent decisions (last 7 days)
	decisionsResult := &GetRecentDecisionsOutput{}
	err = workflow.ExecuteActivity(ctxWithAO, GetRecentDecisions, GetRecentDecisionsInput{
		TenantID: envelope.TenantID,
		Days:     7,
	}).Get(ctx, decisionsResult)
	if err != nil {
		logger.Error("Failed to get recent decisions", err)
		// Continue with empty decisions
		decisionsResult = &GetRecentDecisionsOutput{Decisions: []map[string]interface{}{}}
	}

	// Get current metrics snapshot
	metricsResult := &GetCurrentMetricsSnapshotOutput{}
	err = workflow.ExecuteActivity(ctxWithAO, GetCurrentMetricsSnapshot, GetCurrentMetricsSnapshotInput{
		TenantID: envelope.TenantID,
	}).Get(ctx, metricsResult)
	if err != nil {
		logger.Error("Failed to get current metrics", err)
		// Continue with empty metrics
		metricsResult = &GetCurrentMetricsSnapshotOutput{Metrics: map[string]interface{}{}}
	}

	// Get investor relationship health
	investorResult := &GetInvestorRelationshipHealthOutput{}
	err = workflow.ExecuteActivity(ctxWithAO, GetInvestorRelationshipHealth, GetInvestorRelationshipHealthInput{
		TenantID: envelope.TenantID,
	}).Get(ctx, investorResult)
	if err != nil {
		logger.Error("Failed to get investor relationship health", err)
		// Continue with empty investor status
		investorResult = &GetInvestorRelationshipHealthOutput{Health: map[string]interface{}{}}
	}

	// Synthesize weekly brief
	briefResult := &SynthesizeWeeklyBriefOutput{}
	err = workflow.ExecuteActivity(ctxWithAO, SynthesizeWeeklyBrief, SynthesizeWeeklyBriefInput{
		TenantID:       envelope.TenantID,
		Alerts:         alertsResult.Alerts,
		Decisions:      decisionsResult.Decisions,
		Metrics:        metricsResult.Metrics,
		InvestorStatus: investorResult.Health,
		FounderName:    "Founder", // TODO: Get from tenant config
		CompanyName:    "Company", // TODO: Get from tenant config
	}).Get(ctx, briefResult)
	if err != nil {
		logger.Error("Failed to synthesize weekly brief", err)
		return err
	}

	// Deliver weekly brief
	deliverResult := &DeliverWeeklyBriefOutput{}
	err = workflow.ExecuteActivity(ctxWithAO, DeliverWeeklyBrief, DeliverWeeklyBriefInput{
		TenantID: envelope.TenantID,
		Brief:    briefResult.Brief,
	}).Get(ctx, deliverResult)
	if err != nil {
		logger.Error("Failed to deliver weekly brief", err)
		return err
	}

	logger.Info("ChiefOfStaffWorkflow completed successfully",
		"delivered", deliverResult.Delivered,
		"brief_length", len(briefResult.Brief),
	)

	return nil
}

// SendToDLQActivity writes unknown/unroutable events to the dead letter queue.
// This allows manual inspection and debugging of unexpected events.
// Uses the dead_letter_events table (migration 001).
func SendToDLQActivity(ctx context.Context, envelope events.EventEnvelope) error {
	// Build raw payload from envelope fields
	payload, err := json.Marshal(map[string]interface{}{
		"event_type":      envelope.EventType,
		"source":          string(envelope.Source),
		"tenant_id":       envelope.TenantID,
		"payload_ref":     envelope.PayloadRef,
		"payload_hash":    envelope.PayloadHash,
		"trace_id":        envelope.TraceID,
		"idempotency_key": envelope.IdempotencyKey,
		"occurred_at":     envelope.OccurredAt,
		"received_at":     envelope.ReceivedAt,
	})
	if err != nil {
		return fmt.Errorf("failed to marshal DLQ payload: %w", err)
	}

	reason := fmt.Sprintf("Unknown event type: %s (source: %s, trace: %s)",
		envelope.EventType, envelope.Source, envelope.TraceID)

	if dlqDB != nil {
		_, err := dlqDB.ExecContext(ctx,
			`INSERT INTO dead_letter_events
				(source, event_name, failure_reason, raw_payload)
			 VALUES ($1, $2, $3, $4)
			 ON CONFLICT DO NOTHING`,
			string(envelope.Source),
			envelope.EventType,
			reason,
			payload,
		)
		if err != nil {
			return fmt.Errorf("failed to insert into DLQ: %w", err)
		}
	} else {
		// Database not configured — log for debugging (safe fallback)
		log.Printf("DLQ (no DB): event_type=%q source=%q tenant=%q trace=%q reason=%q",
			envelope.EventType, envelope.Source, envelope.TenantID, envelope.TraceID, reason)
	}

	log.Printf("Event sent to DLQ: type=%s source=%s tenant=%s trace=%s",
		envelope.EventType, envelope.Source, envelope.TenantID, envelope.TraceID)
	return nil
}
