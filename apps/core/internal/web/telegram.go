package web

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"

	"iterateswarm-core/internal/db"
	"iterateswarm-core/internal/events"
	"iterateswarm-core/internal/redpanda"
)

// TelegramHandler handles Telegram webhook events
type TelegramHandler struct {
	store    db.RawEventStore
	producer redpanda.Producer
	dict     *events.EventDictionary
}

// NewTelegramHandler creates a new Telegram webhook handler
func NewTelegramHandler(store db.RawEventStore, producer redpanda.Producer) *TelegramHandler {
	d := events.NewEventDictionary()
	return &TelegramHandler{
		store:    store,
		producer: producer,
		dict:     d,
	}
}

// TelegramUpdate represents incoming Telegram webhook payload
type TelegramUpdate struct {
	UpdateID int64            `json:"update_id"`
	Message  *TelegramMessage `json:"message,omitempty"`
}

// TelegramMessage represents a Telegram message
type TelegramMessage struct {
	MessageID int64             `json:"message_id"`
	From      *TelegramUser     `json:"from,omitempty"`
	Chat      *TelegramChat     `json:"chat,omitempty"`
	Text      string            `json:"text,omitempty"`
	Document  *TelegramDocument `json:"document,omitempty"`
	Photo     []TelegramPhoto   `json:"photo,omitempty"`
	Caption   string            `json:"caption,omitempty"`
}

// TelegramUser represents a Telegram user
type TelegramUser struct {
	ID        int64  `json:"id"`
	FirstName string `json:"first_name,omitempty"`
}

// TelegramChat represents a Telegram chat
type TelegramChat struct {
	ID   int64  `json:"id"`
	Type string `json:"type"`
}

// TelegramDocument represents a Telegram document attachment
type TelegramDocument struct {
	FileName string `json:"file_name"`
	MimeType string `json:"mime_type"`
	FileID   string `json:"file_id"`
}

// TelegramPhoto represents a Telegram photo attachment
type TelegramPhoto struct {
	FileID   string `json:"file_id"`
	FileSize int64  `json:"file_size"`
}

// Handle processes incoming Telegram webhook requests
func (h *TelegramHandler) Handle(c *fiber.Ctx) error {
	// 1. Parse Telegram update
	var update TelegramUpdate
	if err := json.Unmarshal(c.Body(), &update); err != nil {
		return c.Status(400).JSON(fiber.Map{
			"error":   "invalid_json",
			"details": err.Error(),
		})
	}

	// 2. Validate update structure
	if update.Message == nil {
		return c.Status(400).JSON(fiber.Map{
			"error":   "invalid_update",
			"details": "message field required",
		})
	}
	msg := update.Message

	// 3. Classify message type and determine topic/SOP
	topic, _, eventType := h.classifyMessage(msg)

	// 4. Resolve via event dictionary to validate
	entry, err := h.dict.Resolve(events.SourceTelegram, eventType)
	if err != nil {
		// Unknown event type - send to DLQ
		h.store.InsertDLQ(c.Context(), eventType, "unknown_event", c.Body())
		return c.Status(200).JSON(fiber.Map{"status": "dlq_unknown_event"})
	}

	// Use resolved entry for topic (source of truth)
	topic = entry.Topic

	// 5. Persist raw event FIRST
	ikey := h.buildIdempotencyKey(update.UpdateID, msg.MessageID)
	rawEventID, err := h.store.InsertRawEvent(c.Context(), db.RawEvent{
		TenantID:       h.resolveFounder(msg.From.ID),
		Source:         "telegram",
		EventType:      eventType,
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

	// 6. Publish envelope (ref only, not raw payload)
	envelope := events.EventEnvelope{
		Source:         events.SourceTelegram,
		EventType:      eventType,
		PayloadRef:     "raw_events:" + rawEventID,
		PayloadHash:    h.computeHash(c.Body()),
		OccurredAt:     time.Now(),
		ReceivedAt:     time.Now(),
		IdempotencyKey: ikey,
	}
	if err := h.producer.PublishEnvelope(topic, envelope); err != nil {
		h.store.InsertDLQ(c.Context(), eventType, "publish_failed", c.Body())
		return c.Status(500).JSON(fiber.Map{"error": "publish_failed"})
	}

	return c.Status(200).JSON(fiber.Map{"status": "accepted"})
}

// classifyMessage determines the topic, SOP, and event type based on message content
func (h *TelegramHandler) classifyMessage(msg *TelegramMessage) (topic, sopName, eventType string) {
	// Document (PDF/CSV)
	if msg.Document != nil {
		fileName := strings.ToLower(msg.Document.FileName)
		mimeType := strings.ToLower(msg.Document.MimeType)

		if strings.Contains(fileName, "statement") || strings.Contains(mimeType, "pdf") {
			return "ingestion.pdf.bank_statement", "SOP_BANK_STATEMENT_INGEST", "pdf.bank_statement"
		}
		if strings.Contains(fileName, "invoice") || strings.Contains(fileName, "bill") {
			return "ingestion.pdf.invoice", "SOP_VENDOR_INVOICE_RECEIVED", "pdf.invoice"
		}
		if strings.Contains(fileName, "contract") || strings.Contains(fileName, "agreement") {
			return "ingestion.pdf.contract", "SOP_CONTRACT_INGESTED", "pdf.contract"
		}
		// Default document classification
		return "ingestion.file.csv", "SOP_FILE_INGESTION", "file.csv"
	}

	// Photo (receipts, whiteboards, etc.)
	if len(msg.Photo) > 0 {
		return "ingestion.image.receipt", "SOP_RECEIPT_INGESTED", "image.receipt"
	}

	// Text message
	if msg.Text != "" {
		text := strings.ToLower(msg.Text)

		// Check for decision signals
		if strings.Contains(text, "decided") || strings.Contains(text, "we're going with") ||
			strings.Contains(text, "final call") || strings.Contains(text, "agreed to") {
			return "ops.decision.logged", "SOP_DECISION_LOGGED", "decision.logged"
		}

		// Default to founder query
		return "ops.query.inbound", "SOP_FOUNDER_QUERY", "query.inbound"
	}

	// Fallback
	return "ops.query.inbound", "SOP_FOUNDER_QUERY", "query.inbound"
}

// buildIdempotencyKey constructs an idempotency key from the update and message IDs
func (h *TelegramHandler) buildIdempotencyKey(updateID, messageID int64) string {
	return "telegram:update:" + strconv.FormatInt(updateID, 10) + ":msg:" + strconv.FormatInt(messageID, 10) + ":v1"
}

// computeHash computes SHA-256 hash of the payload
func (h *TelegramHandler) computeHash(body []byte) string {
	hash := sha256.Sum256(body)
	return "sha256:" + hex.EncodeToString(hash[:])
}

// resolveFounder maps Telegram user ID to founder UUID in database
func (h *TelegramHandler) resolveFounder(telegramUserID int64) string {
	// TODO: Implement proper founder mapping from Telegram user ID
	// For now, return a default test founder
	return "00000000-0000-0000-0000-000000000000"
}
