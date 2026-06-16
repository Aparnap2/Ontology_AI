package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"iterateswarm-core/internal/logging"
)

// telegramAPIBase returns the Telegram API base URL format string.
// Reads from TELEGRAM_API_BASE env var for mock support.
// Falls back to real Telegram API in production.
func telegramAPIBase() string {
	if base := os.Getenv("TELEGRAM_API_BASE"); base != "" {
		// Mock mode: http://localhost:8081 (tg-mock format: bot<TOKEN>/method)
		return base + "/bot%s/%s"
	}
	// Production: https://api.telegram.org
	return "https://api.telegram.org/bot%s/%s"
}

// TelegramDB defines the database interface for Telegram handler
type TelegramDB interface {
	WriteHITLResponse(ctx context.Context, userID int64, action, contextID string) error
}

// RedpandaProducer defines the interface for publishing events
type RedpandaProducer interface {
	Publish(topic string, event map[string]string) error
}

// HTTPClient defines the interface for HTTP requests (for testing)
type HTTPClient interface {
	Do(req *http.Request) (*http.Response, error)
}

// InlineButton represents a Telegram inline keyboard button
type InlineButton struct {
	Text         string `json:"text"`
	CallbackData string `json:"callback_data"`
}

// TelegramHandler handles Telegram bot webhook events
type TelegramHandler struct {
	botToken   string
	db         TelegramDB
	redpanda   RedpandaProducer
	httpClient HTTPClient
	logger     *logging.Logger
}

// NewTelegramHandler creates a new TelegramHandler
func NewTelegramHandler(db TelegramDB, rp RedpandaProducer) *TelegramHandler {
	return &TelegramHandler{
		botToken:   os.Getenv("TELEGRAM_BOT_TOKEN"),
		db:         db,
		redpanda:   rp,
		httpClient: &http.Client{Timeout: 10 * time.Second},
		logger:     logging.NewLogger("telegram"),
	}
}

// SetHTTPClient sets the HTTP client (for testing)
func (h *TelegramHandler) SetHTTPClient(client HTTPClient) {
	h.httpClient = client
}

// SendMessage sends a Telegram message with optional inline keyboard
func (h *TelegramHandler) SendMessage(chatID, text string, buttons [][]InlineButton) error {
	body := map[string]interface{}{
		"chat_id":    chatID,
		"text":       text,
		"parse_mode": "Markdown",
	}

	if len(buttons) > 0 {
		body["reply_markup"] = map[string]interface{}{
			"inline_keyboard": buttons,
		}
	}

	payload, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	url := fmt.Sprintf(telegramAPIBase(), h.botToken, "sendMessage")
	req, err := http.NewRequest("POST", url, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("telegram send failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("telegram send failed: status=%d, body=%s", resp.StatusCode, string(respBody))
	}

	h.logger.Info("telegram message sent", "chat_id", chatID, "text_length", len(text))
	return nil
}

// HandleCallback receives inline keyboard button presses from Telegram
// POST /webhooks/telegram/callback
func (h *TelegramHandler) HandleCallback(c *fiber.Ctx) error {
	var update struct {
		CallbackQuery struct {
			ID   string `json:"id"`
			Data string `json:"data"`
			From struct {
				ID int64 `json:"id"`
			} `json:"from"`
			Message struct {
				Chat struct {
					ID int64 `json:"id"`
				} `json:"chat"`
			} `json:"message"`
		} `json:"callback_query"`
	}

	if err := c.BodyParser(&update); err != nil {
		h.logger.Error("failed to parse callback", err)
		return c.Status(fiber.StatusBadRequest).SendString("bad request")
	}

	cq := update.CallbackQuery

	// Empty callback query - just acknowledge
	if cq.ID == "" {
		return c.SendStatus(fiber.StatusOK)
	}

	// Parse action from callback data: "action:context_id"
	action, contextID := ParseCallbackData(cq.Data)

	userID := cq.From.ID
	if userID == 0 {
		userID = cq.Message.Chat.ID
	}

	h.logger.Info("telegram callback received",
		"callback_id", cq.ID,
		"action", action,
		"context_id", contextID,
		"user_id", userID,
	)

	// Write to hitl_actions table (always log the response)
	if h.db != nil {
		ctx, cancel := context.WithTimeout(c.Context(), 5*time.Second)
		defer cancel()
		if err := h.db.WriteHITLResponse(ctx, userID, action, contextID); err != nil {
			h.logger.Error("failed to write HITL response", err)
			// Continue anyway - don't block user feedback
		}
	}

	// Route actions - emit events for specific actions
	switch action {
	case "pay_now":
		h.emitEvent("FOUNDER_APPROVED_PAYMENT", contextID)
	case "send_reminder":
		h.emitEvent("FOUNDER_SEND_REMINDER", contextID)
	case "mark_ok":
		// Silent - just logged in DB
		h.logger.Info("mark_ok action logged", "context_id", contextID)
	case "investigate":
		// No action - logged for CoS context
		h.logger.Info("investigate action logged", "context_id", contextID)
	default:
		h.logger.Warn("unknown telegram action", "action", action, "context_id", contextID)
	}

	// Acknowledge callback to Telegram (required within 10s)
	h.answerCallback(cq.ID)

	return c.SendStatus(fiber.StatusOK)
}

// ParseCallbackData extracts action and context from callback data
// Format: "action:context_id" or just "action"
func ParseCallbackData(data string) (action, contextID string) {
	if data == "" {
		return "", ""
	}

	parts := strings.SplitN(data, ":", 2)
	action = parts[0]

	if len(parts) > 1 {
		contextID = parts[1]
	}

	return action, contextID
}

// emitEvent publishes an event to Redpanda
func (h *TelegramHandler) emitEvent(eventType, contextID string) {
	if h.redpanda == nil {
		h.logger.Warn("redpanda client not configured, skipping event emission")
		return
	}

	event := map[string]string{
		"event_type": eventType,
		"context_id": contextID,
		"source":     "telegram",
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}

	go func() {
		if err := h.redpanda.Publish("trackguard.events.raw", event); err != nil {
			h.logger.Error("failed to publish telegram event", err, "event_type", eventType)
		} else {
			h.logger.Info("telegram event published", "event_type", eventType, "context_id", contextID)
		}
	}()
}

// answerCallback acknowledges a callback query to Telegram
func (h *TelegramHandler) answerCallback(callbackID string) {
	if callbackID == "" {
		return
	}

	url := fmt.Sprintf(telegramAPIBase(), h.botToken, "answerCallbackQuery")
	body := map[string]string{
		"callback_query_id": callbackID,
	}

	payload, err := json.Marshal(body)
	if err != nil {
		h.logger.Error("failed to marshal answerCallbackQuery body", err)
		return
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(payload))
	if err != nil {
		h.logger.Error("failed to create answerCallbackQuery request", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := h.httpClient.Do(req)
	if err != nil {
		h.logger.Error("failed to answer callback query", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		h.logger.Warn("answerCallbackQuery returned non-200", "status", resp.StatusCode)
	}
}

// HandleWebhook processes incoming Telegram webhook updates
// POST /webhooks/telegram
func (h *TelegramHandler) HandleWebhook(c *fiber.Ctx) error {
	var update struct {
		UpdateID int64 `json:"update_id"`
		Message  *struct {
			MessageID int64  `json:"message_id"`
			From      *struct {
				ID        int64  `json:"id"`
				IsBot     bool   `json:"is_bot"`
				FirstName string `json:"first_name"`
				Username  string `json:"username"`
			} `json:"from"`
			Chat struct {
				ID   int64  `json:"id"`
				Type string `json:"type"`
			} `json:"chat"`
			Text string `json:"text"`
		} `json:"message"`
		CallbackQuery *struct {
			ID      string `json:"id"`
			From    *struct {
				ID int64 `json:"id"`
			} `json:"from"`
			Message *struct {
				Chat struct {
					ID int64 `json:"id"`
				} `json:"chat"`
			} `json:"message"`
			Data string `json:"data"`
		} `json:"callback_query"`
	}

	if err := c.BodyParser(&update); err != nil {
		h.logger.Error("failed to parse telegram webhook", err)
		return c.Status(fiber.StatusBadRequest).SendString("bad request")
	}

	// Handle callback queries
	if update.CallbackQuery != nil {
		// Delegate to HandleCallback for processing
		callbackBody := map[string]interface{}{
			"callback_query": update.CallbackQuery,
		}
		c.BodyParser(&callbackBody)
		return h.HandleCallback(c)
	}

	// Handle regular messages
	if update.Message != nil && update.Message.Text != "" {
		h.logger.Info("telegram message received",
			"update_id", update.UpdateID,
			"from", update.Message.From.Username,
			"chat_id", update.Message.Chat.ID,
			"text", update.Message.Text,
		)

		// TODO: Process message through TrackGuard NLP pipeline
		// For now, just acknowledge
		return c.SendStatus(fiber.StatusOK)
	}

	// Unknown update type
	h.logger.Warn("unknown telegram update type", "update_id", update.UpdateID)
	return c.SendStatus(fiber.StatusOK)
}
