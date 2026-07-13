package web

import (
	"encoding/json"
	"fmt"
	"sync"

	"github.com/google/uuid"
)

// SSEEvent represents a server-sent event
type SSEEvent struct {
	Type    string `json:"type"`
	Payload string `json:"payload"`
}

// Subscription represents a single SSE subscription
type Subscription struct {
	ID      string
	Channel chan []byte
	filter  map[string]bool
}

// matches returns true if the subscription accepts the given event type.
// A subscription with no filter accepts all event types.
func (s *Subscription) matches(eventType string) bool {
	if len(s.filter) == 0 {
		return true
	}
	return s.filter[eventType]
}

// SSEHub manages fan-out subscriptions for Server-Sent Events
type SSEHub struct {
	mu          sync.RWMutex
	subscribers map[string]map[string]*Subscription
}

// NewSSEHub creates a new SSEHub
func NewSSEHub() *SSEHub {
	return &SSEHub{
		subscribers: make(map[string]map[string]*Subscription),
	}
}

// Subscribe creates a new subscription for a tenant with optional event-type filtering.
// If one or more eventTypes are provided, only those event types will be delivered.
func (h *SSEHub) Subscribe(tenantID string, eventTypes ...string) *Subscription {
	h.mu.Lock()
	defer h.mu.Unlock()
	filter := make(map[string]bool, len(eventTypes))
	for _, et := range eventTypes {
		filter[et] = true
	}
	sub := &Subscription{
		ID:      uuid.New().String(),
		Channel: make(chan []byte, 64),
		filter:  filter,
	}
	if h.subscribers[tenantID] == nil {
		h.subscribers[tenantID] = make(map[string]*Subscription)
	}
	h.subscribers[tenantID][sub.ID] = sub
	return sub
}

// Unsubscribe removes a subscription
func (h *SSEHub) Unsubscribe(tenantID, subID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if subs, ok := h.subscribers[tenantID]; ok {
		if sub, ok := subs[subID]; ok {
			close(sub.Channel)
			delete(subs, subID)
		}
	}
}

// Broadcast sends an event to all subscribers of a tenant (non-blocking)
func (h *SSEHub) Broadcast(tenantID string, event SSEEvent) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	data, _ := json.Marshal(event)
	msg := fmt.Sprintf("event: %s\ndata: %s\n\n", event.Type, string(data))
	for _, sub := range h.subscribers[tenantID] {
		if !sub.matches(event.Type) {
			continue
		}
		select {
		case sub.Channel <- []byte(msg):
		default:
		}
	}
}
