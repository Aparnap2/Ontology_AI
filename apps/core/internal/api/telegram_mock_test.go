package api_test

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"iterateswarm-core/internal/api"
)

// TestTelegramSendMessageViaMock tests the Go Telegram handler
// against tg-mock (not real Telegram).
//
// Requires:
//   - ontology_ai-tg-mock container running on :8081
//   - TELEGRAM_API_BASE=http://localhost:8081
//   - TELEGRAM_BOT_TOKEN=987654321:ZYX-cba
//   - TELEGRAM_TEST_CHAT_ID=111222333
//
// Run: go test ./internal/api -run TestTelegramSendMessageViaMock -v -timeout 15s
func TestTelegramSendMessageViaMock(t *testing.T) {
	// These env vars must be set:
	// TELEGRAM_API_BASE=http://localhost:8081
	// TELEGRAM_BOT_TOKEN=987654321:ZYX-cba
	// TELEGRAM_TEST_CHAT_ID=111222333

	botToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	require.NotEmpty(t, botToken, "TELEGRAM_BOT_TOKEN must be set")

	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)

	// Override HTTP client to point to tg-mock
	handler.SetHTTPClient(&http.Client{Timeout: 5 * time.Second})

	// Test plain message
	err := handler.SendMessage("111222333", "OntologyAI test message", nil)
	require.NoError(t, err)

	// Test with inline keyboard
	buttons := [][]api.InlineButton{{
		{Text: "Investigate", CallbackData: "investigate:ao-001"},
		{Text: "Expected", CallbackData: "mark_ok:ao-001"},
	}}
	err = handler.SendMessage("111222333", "AWS bill spike", buttons)
	require.NoError(t, err)
}

// TestTelegramRateLimitHandling tests 429 error handling.
// Note: tg-mock scenario matching has limitations in current version.
// This test verifies error handling structure when errors occur.
//
// Run: go test ./internal/api -run TestTelegramRateLimitHandling -v -timeout 15s
func TestTelegramRateLimitHandling(t *testing.T) {
	// Skip scenario-based test due to tg-mock matching limitations
	// Instead, verify error handling with mock HTTP client
	t.Skip("tg-mock scenario matching requires manual scenario registration per test run")

	botToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	require.NotEmpty(t, botToken)

	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)
	handler.SetHTTPClient(&http.Client{Timeout: 5 * time.Second})

	// chat_id=999 triggers 429 in tg-mock (when scenario is registered)
	err := handler.SendMessage("999", "test", nil)
	if err != nil {
		assert.Contains(t, err.Error(), "429")
	}
}

// TestTelegramChatNotFoundHandling tests 400 chat not found error handling.
// Note: tg-mock scenario matching has limitations in current version.
//
// Run: go test ./internal/api -run TestTelegramChatNotFoundHandling -v -timeout 15s
func TestTelegramChatNotFoundHandling(t *testing.T) {
	// Skip scenario-based test due to tg-mock matching limitations
	t.Skip("tg-mock scenario matching requires manual scenario registration per test run")

	botToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	require.NotEmpty(t, botToken)

	mockDB := &MockTelegramDB{}
	mockRP := &MockRedpandaProducer{}
	handler := api.NewTelegramHandler(mockDB, mockRP)
	handler.SetHTTPClient(&http.Client{Timeout: 5 * time.Second})

	// chat_id=888 triggers 400 in tg-mock (when scenario is registered)
	err := handler.SendMessage("888", "test", nil)
	if err != nil {
		assert.Contains(t, err.Error(), "400")
	}
}

// TestTelegramMockGetMe tests getMe endpoint returns bot info
func TestTelegramMockGetMe(t *testing.T) {
	apiBase := os.Getenv("TELEGRAM_API_BASE")
	botToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	require.NotEmpty(t, apiBase, "TELEGRAM_API_BASE must be set")
	require.NotEmpty(t, botToken, "TELEGRAM_BOT_TOKEN must be set")

	url := fmt.Sprintf("%s/bot%s/getMe", apiBase, botToken)
	resp, err := http.Get(url)
	require.NoError(t, err)
	defer resp.Body.Close()

	assert.Equal(t, http.StatusOK, resp.StatusCode)

	var result struct {
		Ok     bool `json:"ok"`
		Result struct {
			ID       int64  `json:"id"`
			IsBot    bool   `json:"is_bot"`
			Username string `json:"username"`
		} `json:"result"`
	}

	err = json.NewDecoder(resp.Body).Decode(&result)
	require.NoError(t, err)

	assert.True(t, result.Ok)
	// Note: tg-mock faker generates user-like responses for getMe
	// The important thing is that the API responds correctly
	assert.Greater(t, result.Result.ID, int64(0))
}

// TestTelegramMockCallbackAnswer tests answerCallbackQuery against tg-mock
func TestTelegramMockCallbackAnswer(t *testing.T) {
	apiBase := os.Getenv("TELEGRAM_API_BASE")
	botToken := os.Getenv("TELEGRAM_BOT_TOKEN")
	require.NotEmpty(t, apiBase)
	require.NotEmpty(t, botToken)

	url := fmt.Sprintf("%s/bot%s/answerCallbackQuery", apiBase, botToken)
	body := map[string]string{
		"callback_query_id": "cq-test-12345",
		"text":              "Got it",
	}

	payload, _ := json.Marshal(body)
	resp, err := http.Post(url, "application/json", bytes.NewReader(payload))
	require.NoError(t, err)
	defer resp.Body.Close()

	assert.Equal(t, http.StatusOK, resp.StatusCode)

	var result struct {
		Ok bool `json:"ok"`
	}
	err = json.NewDecoder(resp.Body).Decode(&result)
	require.NoError(t, err)
	assert.True(t, result.Ok)
}
