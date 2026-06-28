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

// SSEHub manages fan-out subscriptions for Server-Sent Events
type SSEHub struct {
	mu          sync.RWMutex
	subscribers map[string]map[string]chan []byte
}

// NewSSEHub creates a new SSEHub
func NewSSEHub() *SSEHub {
	return &SSEHub{
		subscribers: make(map[string]map[string]chan []byte),
	}
}

// Subscribe creates a new subscription for a tenant and returns the sub ID and channel
func (h *SSEHub) Subscribe(tenantID string) (string, chan []byte) {
	h.mu.Lock()
	defer h.mu.Unlock()
	subID := uuid.New().String()
	ch := make(chan []byte, 64)
	if h.subscribers[tenantID] == nil {
		h.subscribers[tenantID] = make(map[string]chan []byte)
	}
	h.subscribers[tenantID][subID] = ch
	return subID, ch
}

// Unsubscribe removes a subscription
func (h *SSEHub) Unsubscribe(tenantID, subID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if subs, ok := h.subscribers[tenantID]; ok {
		if ch, ok := subs[subID]; ok {
			close(ch)
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
	for _, ch := range h.subscribers[tenantID] {
		select {
		case ch <- []byte(msg):
		default:
		}
	}
}
