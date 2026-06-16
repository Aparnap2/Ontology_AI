package events

import "time"

// EventSource represents all event sources in TrackGuard.
type EventSource string

const (
	SourceRazorpay        EventSource = "razorpay"
	SourceZohoBooks       EventSource = "zoho_books"
	SourceGoogleWorkspace EventSource = "google_workspace"
	SourceESign           EventSource = "esign"
	SourceTelegram        EventSource = "telegram"
	SourceCron            EventSource = "cron"
	SourceAWSCost         EventSource = "aws_cost"
	SourceEmailForward    EventSource = "email_forward"
)

// EventEnvelope is the ONLY shape that flows through Redpanda and Temporal.
// PayloadRef points to raw_events table — NEVER contains raw JSON.
type EventEnvelope struct {
	// TenantID is the multi-tenant identifier (replaces FounderID)
	TenantID string `json:"tenant_id"`

	// EventType is the normalized event type (replaces EventName)
	// e.g. PAYMENT_SUCCESS, USER_SIGNED_UP, EMPLOYEE_CREATED
	EventType string `json:"event_type"`

	// Source is the event source (razorpay, stripe, intercom, etc.)
	Source EventSource `json:"source"`

	// PayloadRef is a storage reference ("raw_events:<uuid>" or "files:<path>")
	// NEVER contains raw JSON — store in PostgreSQL first
	PayloadRef string `json:"payload_ref"`

	// PayloadHash is the SHA-256 hash of raw payload
	PayloadHash string `json:"payload_hash"`

	// OccurredAt is when the event occurred (from source)
	OccurredAt time.Time `json:"occurred_at"`

	// ReceivedAt is when TrackGuard received the event
	ReceivedAt time.Time `json:"received_at"`

	// TraceID is the distributed tracing ID (for Langfuse)
	TraceID string `json:"trace_id"`

	// IdempotencyKey is the deduplication key (e.g., "razorpay:pay_abc:v1")
	IdempotencyKey string `json:"idempotency_key"`
}
