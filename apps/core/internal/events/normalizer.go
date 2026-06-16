package events

import (
	"fmt"
)

// EventType represents the normalized event types in TrackGuard v1.0.
// These replace the v4.3.0-alpha SOP/Topic pattern.
type EventType string

const (
	// Payment events
	EventTypePaymentSuccess       EventType = "PAYMENT_SUCCESS"
	EventTypePaymentFailed        EventType = "PAYMENT_FAILED"
	EventTypeSubscriptionActive   EventType = "SUBSCRIPTION_ACTIVATED"
	EventTypeSubscriptionCanceled EventType = "SUBSCRIPTION_CANCELED"

	// User events
	EventTypeUserSignedUp EventType = "USER_SIGNED_UP"

	// Support events
	EventTypeSupportTicketCreated EventType = "SUPPORT_TICKET_CREATED"

	// HR/People events
	EventTypeEmployeeCreated    EventType = "EMPLOYEE_CREATED"
	EventTypeEmployeeTerminated EventType = "EMPLOYEE_TERMINATED"

	// Finance events
	EventTypeBankWebhook    EventType = "BANK_WEBHOOK"
	EventTypeExpenseCreated EventType = "EXPENSE_CREATED"

	// Time-based events
	EventTypeTimeTickWeekly  EventType = "TIME_TICK_WEEKLY"
	EventTypeTimeTickDaily   EventType = "TIME_TICK_DAILY"
	EventTypeTimeTickMonthly EventType = "TIME_TICK_MONTHLY"

	// Agent output events
	EventTypeAgentOutput EventType = "AGENT_OUTPUT"
)

// EventTypeFromString converts a string to EventType
func EventTypeFromString(s string) EventType {
	return EventType(s)
}

// String returns the string representation of EventType
func (e EventType) String() string {
	return string(e)
}

// Normalizer maps raw source + event name to normalized EventType.
// This replaces the v4.3.0-alpha SOP/Topic routing with a simpler v1.0 pattern.
type Normalizer struct{}

// NewNormalizer creates a new EventNormalizer
func NewNormalizer() *Normalizer {
	return &Normalizer{}
}

// Normalize converts a raw event (source + rawEventName) to a normalized EventType.
// Returns an error if no mapping exists.
func (n *Normalizer) Normalize(source EventSource, rawEventName string) (EventType, error) {
	key := fmt.Sprintf("%s::%s", source, rawEventName)
	eventType, ok := normalizerIndex[key]
	if !ok {
		return "", fmt.Errorf("no normalization mapping for source=%q event=%q", source, rawEventName)
	}
	return eventType, nil
}

// NormalizeOrUnknown returns the EventType or a default "unknown" type if no mapping exists
func (n *Normalizer) NormalizeOrUnknown(source EventSource, rawEventName string) EventType {
	eventType, err := n.Normalize(source, rawEventName)
	if err != nil {
		return EventType("UNKNOWN")
	}
	return eventType
}

// normalizerIndex maps source::rawEventName -> EventType
var normalizerIndex map[string]EventType

func init() {
	normalizerIndex = make(map[string]EventType)

	// RAZORPAY mappings (2)
	normalizerIndex["razorpay::payment.captured"] = EventTypePaymentSuccess
	normalizerIndex["razorpay::subscription.cancelled"] = EventTypeSubscriptionCanceled
	normalizerIndex["razorpay::payment.failed"] = EventTypePaymentFailed
	normalizerIndex["razorpay::subscription.activated"] = EventTypeSubscriptionActive

	// STRIPE mappings (1)
	normalizerIndex["stripe::invoice.paid"] = EventTypePaymentSuccess
	normalizerIndex["stripe::payment_intent.succeeded"] = EventTypePaymentSuccess

	// INTERCOM mappings (2)
	normalizerIndex["intercom::user.created"] = EventTypeUserSignedUp
	normalizerIndex["intercom::conversation.created"] = EventTypeSupportTicketCreated

	// CRISP mappings (1)
	normalizerIndex["crisp::user.created"] = EventTypeUserSignedUp
	normalizerIndex["crisp::conversation.created"] = EventTypeSupportTicketCreated

	// KEKA mappings (2)
	normalizerIndex["keka::employee.created"] = EventTypeEmployeeCreated
	normalizerIndex["keka::employee.terminated"] = EventTypeEmployeeTerminated

	// DARWINBOX mappings (2) - same as Keka
	normalizerIndex["darwinbox::employee.created"] = EventTypeEmployeeCreated
	normalizerIndex["darwinbox::employee.terminated"] = EventTypeEmployeeTerminated

	// BANK mappings (1)
	normalizerIndex["bank::transaction"] = EventTypeBankWebhook

	// CRON mappings (3)
	normalizerIndex["cron::cron.weekly"] = EventTypeTimeTickWeekly
	normalizerIndex["cron::cron.daily"] = EventTypeTimeTickDaily
	normalizerIndex["cron::cron.monthly"] = EventTypeTimeTickMonthly

	// Additional common mappings
	normalizerIndex["zoho_books::expense.created"] = EventTypeExpenseCreated
	normalizerIndex["zoho_books::invoice.created"] = EventTypeExpenseCreated
}

// MappingCount returns the total number of normalization mappings
func MappingCount() int {
	return len(normalizerIndex)
}
