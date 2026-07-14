package web

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"time"

	"github.com/gofiber/fiber/v2"

	"iterateswarm-core/internal/db"
	"iterateswarm-core/internal/events"
	"iterateswarm-core/internal/redpanda"
)

// RazorpayHandler handles Razorpay webhook events
type RazorpayHandler struct {
	secret   string
	store    db.RawEventStore
	producer redpanda.Producer
	dict     *events.EventDictionary
}

// NewRazorpayHandler creates a new Razorpay webhook handler
func NewRazorpayHandler(secret string, store db.RawEventStore, producer redpanda.Producer) *RazorpayHandler {
	d := events.NewEventDictionary()
	return &RazorpayHandler{
		secret:   secret,
		store:    store,
		producer: producer,
		dict:     d,
	}
}

// Handle processes incoming Razorpay webhook requests
func (h *RazorpayHandler) Handle(c *fiber.Ctx) error {
	// 1. Parse event name from body FIRST — handle JSON parse errors before signature check
	var raw map[string]interface{}
	if err := json.Unmarshal(c.Body(), &raw); err != nil {
		return c.Status(400).JSON(fiber.Map{
			"error":   "invalid_json",
			"details": err.Error(),
		})
	}

	// 2. Verify HMAC-SHA256 signature
	sig := c.Get("X-Razorpay-Signature")
	if !h.verifySignature(c.Body(), sig) {
		return c.Status(401).JSON(fiber.Map{"error": "invalid_signature"})
	}

	eventName, ok := raw["event"].(string)
	if !ok || eventName == "" {
		h.store.InsertDLQ(c.Context(), "unknown", "missing_event_name", c.Body())
		return c.Status(200).JSON(fiber.Map{"status": "dlq_missing_event_name"})
	}

	// 3. Resolve via event dictionary
	entry, err := h.dict.Resolve(events.SourceRazorpay, eventName)
	if err != nil {
		h.store.InsertDLQ(c.Context(), eventName, "unknown_event", c.Body())
		return c.Status(200).JSON(fiber.Map{"status": "unknown_event_dlq"})
	}

	// 4. Persist raw event FIRST
	ikey := h.buildIdempotencyKey(eventName, raw)
	rawEventID, err := h.store.InsertRawEvent(c.Context(), db.RawEvent{
		TenantID:       h.resolveFounder(c),
		Source:         "razorpay",
		EventType:      eventName,
		PayloadHash:    h.computeHash(c.Body()),
		PayloadBody:    c.Body(),
		IdempotencyKey: ikey,
	})
	if err != nil {
		if isDuplicateKey(err) {
			return c.Status(200).JSON(fiber.Map{"status": "duplicate"})
		}
		return c.Status(500).JSON(fiber.Map{"error": "storage_failed"})
	}

	// 5. Publish envelope (ref only, not raw payload)
	envelope := events.EventEnvelope{
		Source:         events.SourceRazorpay,
		EventType:      eventName,
		PayloadRef:     "raw_events:" + rawEventID,
		PayloadHash:    h.computeHash(c.Body()),
		OccurredAt:     time.Now(),
		ReceivedAt:     time.Now(),
		IdempotencyKey: ikey,
	}
	if err := h.producer.PublishEnvelope(entry.Topic, envelope); err != nil {
		h.store.InsertDLQ(c.Context(), eventName, "publish_failed", c.Body())
		return c.Status(500).JSON(fiber.Map{"error": "publish_failed"})
	}

	return c.Status(200).JSON(fiber.Map{"status": "accepted"})
}

// verifySignature verifies the HMAC-SHA256 signature from Razorpay
func (h *RazorpayHandler) verifySignature(body []byte, sig string) bool {
	mac := hmac.New(sha256.New, []byte(h.secret))
	mac.Write(body)
	expected := hex.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(expected), []byte(sig))
}

// buildIdempotencyKey constructs an idempotency key from the event data
func (h *RazorpayHandler) buildIdempotencyKey(eventName string, raw map[string]interface{}) string {
	// Extract payment ID or other unique identifier from payload
	if payload, ok := raw["payload"].(map[string]interface{}); ok {
		if payment, ok := payload["payment"].(map[string]interface{}); ok {
			if entity, ok := payment["entity"].(map[string]interface{}); ok {
				if id, ok := entity["id"].(string); ok {
					return "razorpay:" + eventName + ":" + id + ":v1"
				}
			}
		}
	}
	return "razorpay:" + eventName + ":unknown:v1"
}

// computeHash computes SHA-256 hash of the payload
func (h *RazorpayHandler) computeHash(body []byte) string {
	hash := sha256.Sum256(body)
	return "sha256:" + hex.EncodeToString(hash[:])
}

// resolveFounder extracts founder ID from context or headers
func (h *RazorpayHandler) resolveFounder(c *fiber.Ctx) string {
	// Extract founder ID from API key or JWT in header
	// For now, return a default test founder
	// TODO: Implement proper founder extraction from JWT/API key
	return "00000000-0000-0000-0000-000000000000"
}

// isDuplicateKey checks if an error is a duplicate key violation
func isDuplicateKey(err error) bool {
	if err == nil {
		return false
	}
	// Check if error is PostgreSQL unique constraint violation
	errStr := err.Error()
	return errStr == "duplicate_key" ||
		errStr == "UNIQUE constraint failed" ||
		errStr == "duplicate key value violates unique constraint" ||
		contains(errStr, "duplicate key") ||
		contains(errStr, "unique constraint")
}

// contains is a helper to check if a string contains a substring
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > len(substr) && findSubstring(s, substr))
}

// findSubstring checks if s contains substr
func findSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
