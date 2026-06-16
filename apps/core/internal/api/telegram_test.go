package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"iterateswarm-core/internal/api"
)

// MockRedpandaProducer implements the RedpandaProducer interface for testing
type MockRedpandaProducer struct {
	PublishedEvents []map[string]string
	PublishFunc     func(topic string, event map[string]string) error
}

func (m *MockRedpandaProducer) Publish(topic string, event map[string]string) error {
	if m.PublishFunc != nil {
		return m.PublishFunc(topic, event)
	}
	m.PublishedEvents = append(m.PublishedEvents, event)
	return nil
}

// MockTelegramDB implements the TelegramDB interface for testing
type MockTelegramDB struct {
	WrittenResponses []HITLResponse
	WriteFunc        func(ctx context.Context, userID int64, action, contextID string) error
}

type HITLResponse struct {
	UserID     int64
	Action     string
	ContextID  string
	Timestamp  time.Time
}

func (m *MockTelegramDB) WriteHITLResponse(ctx context.Context, userID int64, action, contextID string) error {
	if m.WriteFunc != nil {
		return m.WriteFunc(ctx, userID, action, contextID)
	}
	m.WrittenResponses = append(m.WrittenResponses, HITLResponse{
		UserID:    userID,
		Action:    action,
		ContextID: contextID,
		Timestamp: time.Now(),
	})
	return nil
}

// MockHTTPClient wraps http.Client for testing Telegram API calls
type MockHTTPClient struct {
	DoFunc func(req *http.Request) (*http.Response, error)
}

func (m *MockHTTPClient) Do(req *http.Request) (*http.Response, error) {
	if m.DoFunc != nil {
		return m.DoFunc(req)
	}
	return &http.Response{
		StatusCode: 200,
		Body:       io.NopCloser(strings.NewReader(`{"ok": true}`)),
	}, nil
}

// TestTelegramSendMessage tests the SendMessage method with mock HTTP client
func TestTelegramSendMessage(t *testing.T) {
	t.Run("sends message without buttons", func(t *testing.T) {
		mockDB := &MockTelegramDB{}
		mockRP := &MockRedpandaProducer{}
		handler := api.NewTelegramHandler(mockDB, mockRP)

		// Override HTTP client with mock
		called := false
		handler.SetHTTPClient(&MockHTTPClient{
			DoFunc: func(req *http.Request) (*http.Response, error) {
				called = true
				assert.Equal(t, "POST", req.Method)
				assert.Contains(t, req.URL.Path, "sendMessage")
				
				// Read and verify body
				body, _ := io.ReadAll(req.Body)
				var payload map[string]interface{}
				err := json.Unmarshal(body, &payload)
				require.NoError(t, err)
				assert.Equal(t, "123456", payload["chat_id"])
				assert.Equal(t, "Hello from TrackGuard", payload["text"])
				assert.Equal(t, "Markdown", payload["parse_mode"])
				assert.NotContains(t, payload, "reply_markup")
				
				return &http.Response{
					StatusCode: 200,
					Body:       io.NopCloser(strings.NewReader(`{"ok": true}`)),
				}, nil
			},
		})

		err := handler.SendMessage("123456", "Hello from TrackGuard", nil)
		require.NoError(t, err)
		assert.True(t, called, "HTTP client should have been called")
	})

	t.Run("sends message with inline keyboard", func(t *testing.T) {
		mockDB := &MockTelegramDB{}
		mockRP := &MockRedpandaProducer{}
		handler := api.NewTelegramHandler(mockDB, mockRP)

		buttons := [][]api.InlineButton{
			{
				{Text: "Pay Now", CallbackData: "pay_now:ctx123"},
				{Text: "Mark OK", CallbackData: "mark_ok:ctx123"},
			},
		}

		called := false
		handler.SetHTTPClient(&MockHTTPClient{
			DoFunc: func(req *http.Request) (*http.Response, error) {
				called = true
				body, _ := io.ReadAll(req.Body)
				var payload map[string]interface{}
				err := json.Unmarshal(body, &payload)
				require.NoError(t, err)
				
				assert.Contains(t, payload, "reply_markup")
				replyMarkup := payload["reply_markup"].(map[string]interface{})
				assert.Contains(t, replyMarkup, "inline_keyboard")
				
				keyboard := replyMarkup["inline_keyboard"].([]interface{})
				assert.Len(t, keyboard, 1) // One row
				row := keyboard[0].([]interface{})
				assert.Len(t, row, 2) // Two buttons
				
				return &http.Response{
					StatusCode: 200,
					Body:       io.NopCloser(strings.NewReader(`{"ok": true}`)),
				}, nil
			},
		})

		err := handler.SendMessage("123456", "Action required", buttons)
		require.NoError(t, err)
		assert.True(t, called, "HTTP client should have been called")
	})

	t.Run("returns error on API failure", func(t *testing.T) {
		mockDB := &MockTelegramDB{}
		mockRP := &MockRedpandaProducer{}
		handler := api.NewTelegramHandler(mockDB, mockRP)

		handler.SetHTTPClient(&MockHTTPClient{
			DoFunc: func(req *http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: 400,
					Body:       io.NopCloser(strings.NewReader(`{"ok": false, "error_code": 400}`)),
				}, nil
			},
		})

		err := handler.SendMessage("123456", "Test", nil)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "telegram send failed")
	})
}

// TestTelegramInlineKeyboardRendered tests inline keyboard button formatting
func TestTelegramInlineKeyboardRendered(t *testing.T) {
	t.Run("single button row", func(t *testing.T) {
		buttons := [][]api.InlineButton{
			{
				{Text: "Approve", CallbackData: "approve:123"},
			},
		}

		payload := map[string]interface{}{
			"chat_id": "123456",
			"text":    "Test",
		}

		if len(buttons) > 0 {
			payload["reply_markup"] = map[string]interface{}{
				"inline_keyboard": buttons,
			}
		}

		data, err := json.Marshal(payload)
		require.NoError(t, err)

		var result map[string]interface{}
		err = json.Unmarshal(data, &result)
		require.NoError(t, err)

		replyMarkup := result["reply_markup"].(map[string]interface{})
		keyboard := replyMarkup["inline_keyboard"].([]interface{})
		assert.Len(t, keyboard, 1)
		
		row := keyboard[0].([]interface{})
		assert.Len(t, row, 1)
		
		button := row[0].(map[string]interface{})
		assert.Equal(t, "Approve", button["text"])
		assert.Equal(t, "approve:123", button["callback_data"])
	})

	t.Run("multiple button rows", func(t *testing.T) {
		buttons := [][]api.InlineButton{
			{
				{Text: "Pay Now", CallbackData: "pay_now:ctx1"},
				{Text: "Send Reminder", CallbackData: "send_reminder:ctx1"},
			},
			{
				{Text: "Mark OK", CallbackData: "mark_ok:ctx1"},
				{Text: "Investigate", CallbackData: "investigate:ctx1"},
			},
		}

		payload := map[string]interface{}{
			"chat_id": "123456",
			"text":    "Test",
		}

		if len(buttons) > 0 {
			payload["reply_markup"] = map[string]interface{}{
				"inline_keyboard": buttons,
			}
		}

		data, err := json.Marshal(payload)
		require.NoError(t, err)

		var result map[string]interface{}
		err = json.Unmarshal(data, &result)
		require.NoError(t, err)

		replyMarkup := result["reply_markup"].(map[string]interface{})
		keyboard := replyMarkup["inline_keyboard"].([]interface{})
		assert.Len(t, keyboard, 2) // Two rows
		
		// First row
		row1 := keyboard[0].([]interface{})
		assert.Len(t, row1, 2)
		assert.Equal(t, "Pay Now", row1[0].(map[string]interface{})["text"])
		
		// Second row
		row2 := keyboard[1].([]interface{})
		assert.Len(t, row2, 2)
		assert.Equal(t, "Mark OK", row2[0].(map[string]interface{})["text"])
	})
}

// TestTelegramCallbackParsed tests callback data parsing
func TestTelegramCallbackParsed(t *testing.T) {
	t.Run("parses pay_now action", func(t *testing.T) {
		action, contextID := api.ParseCallbackData("pay_now:context_123")
		assert.Equal(t, "pay_now", action)
		assert.Equal(t, "context_123", contextID)
	})

	t.Run("parses mark_ok action", func(t *testing.T) {
		action, contextID := api.ParseCallbackData("mark_ok:context_456")
		assert.Equal(t, "mark_ok", action)
		assert.Equal(t, "context_456", contextID)
	})

	t.Run("parses send_reminder action", func(t *testing.T) {
		action, contextID := api.ParseCallbackData("send_reminder:context_789")
		assert.Equal(t, "send_reminder", action)
		assert.Equal(t, "context_789", contextID)
	})

	t.Run("parses investigate action", func(t *testing.T) {
		action, contextID := api.ParseCallbackData("investigate:context_abc")
		assert.Equal(t, "investigate", action)
		assert.Equal(t, "context_abc", contextID)
	})

	t.Run("handles missing context", func(t *testing.T) {
		action, contextID := api.ParseCallbackData("pay_now")
		assert.Equal(t, "pay_now", action)
		assert.Equal(t, "", contextID)
	})

	t.Run("handles empty callback", func(t *testing.T) {
		action, contextID := api.ParseCallbackData("")
		assert.Equal(t, "", action)
		assert.Equal(t, "", contextID)
	})
}

// TestTelegramCallbackWritesToHITLTable tests callback writes to hitl_actions table
func TestTelegramCallbackWritesToHITLTable(t *testing.T) {
	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)

	app := fiber.New()
	app.Post("/webhooks/telegram/callback", handler.HandleCallback)

	callbackData := map[string]interface{}{
		"callback_query": map[string]interface{}{
			"id":   "cq_123",
			"data": "pay_now:context_123",
			"from": map[string]interface{}{
				"id": float64(987654321),
			},
			"message": map[string]interface{}{
				"chat": map[string]interface{}{
					"id": float64(987654321),
				},
			},
		},
	}

	body, _ := json.Marshal(callbackData)
	req := httptest.NewRequest(http.MethodPost, "/webhooks/telegram/callback", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Give goroutine time to write to DB
	time.Sleep(100 * time.Millisecond)

	// Verify HITL response was written
	require.Len(t, mockDB.WrittenResponses, 1)
	assert.Equal(t, int64(987654321), mockDB.WrittenResponses[0].UserID)
	assert.Equal(t, "pay_now", mockDB.WrittenResponses[0].Action)
	assert.Equal(t, "context_123", mockDB.WrittenResponses[0].ContextID)
}

// TestTelegramCallbackPayNowEmitsEvent tests pay_now action emits FOUNDER_APPROVED_PAYMENT event
func TestTelegramCallbackPayNowEmitsEvent(t *testing.T) {
	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)

	app := fiber.New()
	app.Post("/webhooks/telegram/callback", handler.HandleCallback)

	callbackData := map[string]interface{}{
		"callback_query": map[string]interface{}{
			"id":   "cq_456",
			"data": "pay_now:finance_context_789",
			"from": map[string]interface{}{
				"id": float64(123456789),
			},
			"message": map[string]interface{}{
				"chat": map[string]interface{}{
					"id": float64(123456789),
				},
			},
		},
	}

	body, _ := json.Marshal(callbackData)
	req := httptest.NewRequest(http.MethodPost, "/webhooks/telegram/callback", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Give goroutine time to publish event
	time.Sleep(100 * time.Millisecond)

	// Verify event was published
	require.Len(t, mockRP.PublishedEvents, 1)
	assert.Equal(t, "FOUNDER_APPROVED_PAYMENT", mockRP.PublishedEvents[0]["event_type"])
	assert.Equal(t, "finance_context_789", mockRP.PublishedEvents[0]["context_id"])
}

// TestTelegramCallbackMarkOKSilent tests mark_ok action is silent (just logged)
func TestTelegramCallbackMarkOKSilent(t *testing.T) {
	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)

	app := fiber.New()
	app.Post("/webhooks/telegram/callback", handler.HandleCallback)

	callbackData := map[string]interface{}{
		"callback_query": map[string]interface{}{
			"id":   "cq_789",
			"data": "mark_ok:context_silent",
			"from": map[string]interface{}{
				"id": float64(555666777),
			},
			"message": map[string]interface{}{
				"chat": map[string]interface{}{
					"id": float64(555666777),
				},
			},
		},
	}

	body, _ := json.Marshal(callbackData)
	req := httptest.NewRequest(http.MethodPost, "/webhooks/telegram/callback", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Give goroutine time to process
	time.Sleep(100 * time.Millisecond)

	// Verify HITL response was written (logged)
	require.Len(t, mockDB.WrittenResponses, 1)
	assert.Equal(t, "mark_ok", mockDB.WrittenResponses[0].Action)

	// Verify NO event was published (silent action)
	assert.Len(t, mockRP.PublishedEvents, 0, "mark_ok should not emit any events")
}

// TestTelegramCallbackSendReminderEmitsEvent tests send_reminder action emits event
func TestTelegramCallbackSendReminderEmitsEvent(t *testing.T) {
	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)

	app := fiber.New()
	app.Post("/webhooks/telegram/callback", handler.HandleCallback)

	callbackData := map[string]interface{}{
		"callback_query": map[string]interface{}{
			"id":   "cq_reminder",
			"data": "send_reminder:customer_123",
			"from": map[string]interface{}{
				"id": float64(111222333),
			},
			"message": map[string]interface{}{
				"chat": map[string]interface{}{
					"id": float64(111222333),
				},
			},
		},
	}

	body, _ := json.Marshal(callbackData)
	req := httptest.NewRequest(http.MethodPost, "/webhooks/telegram/callback", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")

	resp, err := app.Test(req, 10000)
	require.NoError(t, err)
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Give goroutine time to publish event
	time.Sleep(100 * time.Millisecond)

	// Verify event was published
	require.Len(t, mockRP.PublishedEvents, 1)
	assert.Equal(t, "FOUNDER_SEND_REMINDER", mockRP.PublishedEvents[0]["event_type"])
	assert.Equal(t, "customer_123", mockRP.PublishedEvents[0]["context_id"])
}

// TestTelegramCallbackInvalidRequest tests invalid callback requests
func TestTelegramCallbackInvalidRequest(t *testing.T) {
	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)

	app := fiber.New()
	app.Post("/webhooks/telegram/callback", handler.HandleCallback)

	t.Run("malformed JSON returns 400", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/webhooks/telegram/callback", strings.NewReader(`{invalid json`))
		req.Header.Set("Content-Type", "application/json")

		resp, err := app.Test(req, 10000)
		require.NoError(t, err)
		assert.Equal(t, http.StatusBadRequest, resp.StatusCode)
	})

	t.Run("empty callback query returns 200", func(t *testing.T) {
		callbackData := map[string]interface{}{}
		body, _ := json.Marshal(callbackData)
		req := httptest.NewRequest(http.MethodPost, "/webhooks/telegram/callback", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")

		resp, err := app.Test(req, 10000)
		require.NoError(t, err)
		assert.Equal(t, http.StatusOK, resp.StatusCode)
	})
}
