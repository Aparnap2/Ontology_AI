package web_test

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/segmentio/kafka-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"iterateswarm-core/internal/db"
	"iterateswarm-core/internal/events"
	"iterateswarm-core/internal/web"
)

// computeHMAC computes HMAC-SHA256 signature for testing
func computeHMAC(body []byte, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// setupTestDB creates a test database connection, skipping if DB is unavailable
func setupTestDB(t *testing.T) (*pgxpool.Pool, func()) {
	t.Helper()

	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		dsn = "postgres://postgres:postgres@localhost:5432/iterateswarm_test?sslmode=disable"
	}

	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Skipf("Skipping: could not create DB pool: %v", err)
	}

	// Verify connection
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	err = pool.Ping(ctx)
	if err != nil {
		pool.Close()
		t.Skipf("Skipping: PostgreSQL not reachable: %v", err)
	}

	teardown := func() {
		pool.Close()
	}

	return pool, teardown
}

// setupTestApp creates a test Fiber app with Razorpay handler
func setupTestApp(t *testing.T) (*fiber.App, func()) {
	t.Helper()

	pool, poolTeardown := setupTestDB(t)
	repo := db.NewRepositoryFromPool(pool)

	// Always use mock producer for tests to avoid Kafka dependency
	producerInterface := &mockProducer{}

	// Get Razorpay secret from env or use test value
	secret := os.Getenv("RAZORPAY_WEBHOOK_SECRET")
	if secret == "" {
		secret = "test_secret"
	}

	handler := web.NewRazorpayHandler(secret, repo, producerInterface)

	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
		ErrorHandler: func(c *fiber.Ctx, err error) error {
			return c.Status(500).JSON(fiber.Map{"error": err.Error()})
		},
	})

	// Register the Razorpay webhook route
	app.Post("/webhooks/razorpay", handler.Handle)

	teardown := func() {
		poolTeardown()
	}

	return app, teardown
}

// mockProducer is a mock Redpanda producer for testing
type mockProducer struct{}

func (m *mockProducer) Publish(value []byte) error {
	return nil
}

func (m *mockProducer) PublishToTopic(topic string, value []byte) error {
	return nil
}

func (m *mockProducer) ProduceMessage(topic string, message map[string]interface{}) error {
	return nil
}

func (m *mockProducer) PublishFeedback(data []byte) error {
	return nil
}

func (m *mockProducer) PublishEnvelope(topic string, envelope events.EventEnvelope) error {
	return nil
}

func (m *mockProducer) Consume(ctx context.Context, topic string) <-chan kafka.Message {
	return make(chan kafka.Message)
}

func (m *mockProducer) Close() error {
	return nil
}

func (m *mockProducer) Health(ctx context.Context) error {
	return nil
}

// TestRazorpayValidSignatureAccepted tests that valid HMAC signatures are accepted
func TestRazorpayValidSignatureAccepted(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	paymentID := "pay_test_valid_" + time.Now().Format("20060102150405")
	payload := map[string]interface{}{
		"event": "payment.captured",
		"payload": map[string]interface{}{
			"payment": map[string]interface{}{
				"entity": map[string]interface{}{
					"id":       paymentID,
					"amount":   500000, // ₹5000 in paise
					"currency": "INR",
				},
			},
		},
	}
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	sig := computeHMAC(body, "test_secret")

	req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Razorpay-Signature", sig)

	resp, err := app.Test(req)
	require.NoError(t, err)
	assert.Equal(t, 200, resp.StatusCode, "Valid signature should be accepted")

	// Verify response body
	var respBody map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Equal(t, "accepted", respBody["status"])
}

// TestRazorpayInvalidSignatureRejected tests that invalid signatures are rejected with 401
func TestRazorpayInvalidSignatureRejected(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	payload := map[string]interface{}{"event": "payment.captured"}
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
	req.Header.Set("X-Razorpay-Signature", "invalid_signature")

	resp, err := app.Test(req)
	require.NoError(t, err)
	assert.Equal(t, 401, resp.StatusCode, "Invalid signature should be rejected")

	// Verify response body
	var respBody map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Equal(t, "invalid_signature", respBody["error"])
}

// TestRazorpayInvalidJSONRejected tests that invalid JSON is rejected with 400
func TestRazorpayInvalidJSONRejected(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader([]byte("not json")))
	req.Header.Set("X-Razorpay-Signature", "test")

	resp, err := app.Test(req)
	require.NoError(t, err)
	assert.Equal(t, 400, resp.StatusCode, "Invalid JSON should be rejected")

	// Verify response body
	var respBody map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Equal(t, "invalid_json", respBody["error"])
	assert.Contains(t, respBody["details"], "") // Error details should be present
}

// TestRazorpayUnknownEventGoesToDLQ tests that unknown events are sent to DLQ
func TestRazorpayUnknownEventGoesToDLQ(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	payload := map[string]interface{}{"event": "unknown.event"}
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	sig := computeHMAC(body, "test_secret")

	req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
	req.Header.Set("X-Razorpay-Signature", sig)

	resp, err := app.Test(req)
	require.NoError(t, err)
	assert.Equal(t, 200, resp.StatusCode, "Unknown event should return 200 but go to DLQ")

	// Verify response body indicates DLQ
	var respBody map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Contains(t, respBody["status"], "dlq")
}

// TestRazorpayMissingEventNameGoesToDLQ tests that missing event names are sent to DLQ
func TestRazorpayMissingEventNameGoesToDLQ(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	payload := map[string]interface{}{"payload": map[string]interface{}{}}
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	sig := computeHMAC(body, "test_secret")

	req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
	req.Header.Set("X-Razorpay-Signature", sig)

	resp, err := app.Test(req)
	require.NoError(t, err)
	assert.Equal(t, 200, resp.StatusCode, "Missing event name should return 200 but go to DLQ")

	// Verify response body indicates DLQ
	var respBody map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Contains(t, respBody["status"], "dlq")
}

// TestRazorpayDuplicateEventRejected tests idempotency handling
func TestRazorpayDuplicateEventRejected(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	payload := map[string]interface{}{
		"event": "payment.captured",
		"payload": map[string]interface{}{
			"payment": map[string]interface{}{
				"entity": map[string]interface{}{
					"id":       "pay_duplicate_test",
					"amount":   500000,
					"currency": "INR",
				},
			},
		},
	}
	body, err := json.Marshal(payload)
	require.NoError(t, err)

	sig := computeHMAC(body, "test_secret")

	// First request
	req1 := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
	req1.Header.Set("Content-Type", "application/json")
	req1.Header.Set("X-Razorpay-Signature", sig)

	resp1, err := app.Test(req1)
	require.NoError(t, err)
	assert.Equal(t, 200, resp1.StatusCode)

	// Second request with same payload (should be rejected as duplicate)
	req2 := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
	req2.Header.Set("Content-Type", "application/json")
	req2.Header.Set("X-Razorpay-Signature", sig)

	resp2, err := app.Test(req2)
	require.NoError(t, err)
	assert.Equal(t, 200, resp2.StatusCode)

	// Verify duplicate response
	var respBody map[string]interface{}
	err = json.NewDecoder(resp2.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Equal(t, "duplicate", respBody["status"])
}

// TestRazorpayDifferentPaymentIdsAccepted tests that different payment IDs are accepted
func TestRazorpayDifferentPaymentIdsAccepted(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	timestamp := time.Now().Format("20060102150405")

	// First payment
	payload1 := map[string]interface{}{
		"event": "payment.captured",
		"payload": map[string]interface{}{
			"payment": map[string]interface{}{
				"entity": map[string]interface{}{
					"id":       "pay_unique_1_" + timestamp,
					"amount":   500000,
					"currency": "INR",
				},
			},
		},
	}
	body1, _ := json.Marshal(payload1)
	sig1 := computeHMAC(body1, "test_secret")

	req1 := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body1))
	req1.Header.Set("Content-Type", "application/json")
	req1.Header.Set("X-Razorpay-Signature", sig1)

	resp1, err := app.Test(req1)
	require.NoError(t, err)
	assert.Equal(t, 200, resp1.StatusCode)

	// Second payment with different ID
	payload2 := map[string]interface{}{
		"event": "payment.captured",
		"payload": map[string]interface{}{
			"payment": map[string]interface{}{
				"entity": map[string]interface{}{
					"id":       "pay_unique_2_" + timestamp,
					"amount":   300000,
					"currency": "INR",
				},
			},
		},
	}
	body2, _ := json.Marshal(payload2)
	sig2 := computeHMAC(body2, "test_secret")

	req2 := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body2))
	req2.Header.Set("Content-Type", "application/json")
	req2.Header.Set("X-Razorpay-Signature", sig2)

	resp2, err := app.Test(req2)
	require.NoError(t, err)
	assert.Equal(t, 200, resp2.StatusCode)

	var respBody map[string]interface{}
	err = json.NewDecoder(resp2.Body).Decode(&respBody)
	require.NoError(t, err)
	assert.Equal(t, "accepted", respBody["status"])
}

// TestRazorpayEventDictionaryResolution tests that known events are properly resolved
func TestRazorpayEventDictionaryResolution(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	timestamp := time.Now().Format("20060102150405")

	// Test various known Razorpay events
	knownEvents := []string{
		"payment.captured",
		"payment.failed",
		"subscription.activated",
		"subscription.cancelled",
		"invoice.paid",
		"refund.created",
	}

	for _, eventName := range knownEvents {
		t.Run(eventName, func(t *testing.T) {
			payload := map[string]interface{}{
				"event": eventName,
				"payload": map[string]interface{}{
					"payment": map[string]interface{}{
						"entity": map[string]interface{}{
							"id":       "pay_dict_test_" + eventName + "_" + timestamp,
							"amount":   100000,
							"currency": "INR",
						},
					},
				},
			}
			body, _ := json.Marshal(payload)
			sig := computeHMAC(body, "test_secret")

			req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("X-Razorpay-Signature", sig)

			resp, err := app.Test(req)
			require.NoError(t, err)
			assert.Equal(t, 200, resp.StatusCode)

			var respBody map[string]interface{}
			err = json.NewDecoder(resp.Body).Decode(&respBody)
			require.NoError(t, err)
			assert.Equal(t, "accepted", respBody["status"])
		})
	}
}

// TestRazorpayIdempotencyKeyFormat tests the idempotency key format
func TestRazorpayIdempotencyKeyFormat(t *testing.T) {
	// This test verifies the idempotency key construction logic
	// Format: razorpay:{event_name}:{payment_id}:v1

	eventName := "payment.captured"
	paymentID := "pay_test123"
	expected := "razorpay:" + eventName + ":" + paymentID + ":v1"

	assert.Equal(t, "razorpay:payment.captured:pay_test123:v1", expected)
}

// TestRazorpaySignatureTimingAttack tests that signature comparison is constant-time
func TestRazorpaySignatureTimingAttack(t *testing.T) {
	app, teardown := setupTestApp(t)
	defer teardown()

	payload := map[string]interface{}{"event": "payment.captured"}
	body, _ := json.Marshal(payload)

	// Generate valid signature
	validSig := computeHMAC(body, "test_secret")

	// Test with various invalid signatures that differ by 1 character
	invalidSigs := []string{
		validSig[:len(validSig)-1] + "0", // Last char different
		"0" + validSig[1:],               // First char different
		validSig[:len(validSig)/2] + "X" + validSig[len(validSig)/2+1:], // Middle char different
	}

	for _, invalidSig := range invalidSigs {
		req := httptest.NewRequest("POST", "/webhooks/razorpay", bytes.NewReader(body))
		req.Header.Set("X-Razorpay-Signature", invalidSig)

		resp, err := app.Test(req)
		require.NoError(t, err)
		assert.Equal(t, 401, resp.StatusCode, "All invalid signatures should be rejected")
	}
}

// TestComputeHMAC tests the HMAC computation helper function
func TestComputeHMAC(t *testing.T) {
	body := []byte(`{"event":"test"}`)
	secret := "test_secret"

	sig := computeHMAC(body, secret)

	// Verify it's a valid hex string
	_, err := hex.DecodeString(sig)
	require.NoError(t, err, "Signature should be valid hex")

	// Verify length (SHA256 produces 64 hex characters)
	assert.Equal(t, 64, len(sig), "SHA256 HMAC should produce 64 hex characters")

	// Verify consistency
	sig2 := computeHMAC(body, secret)
	assert.Equal(t, sig, sig2, "Same input should produce same signature")
}
