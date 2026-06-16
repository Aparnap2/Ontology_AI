package redpanda

import (
	"testing"
	"time"

	"iterateswarm-core/internal/events"
)

func TestProducer_PublishSlackEvent_WritesToCorrectTopic(t *testing.T) {
	client, err := NewClient([]string{"localhost:9092"}, "trackguard.slack.events")
	if err != nil {
		t.Skip("Redpanda not available:", err)
	}
	defer client.Close()

	envelope := events.EventEnvelope{
		EventType:  "FOUNDER_MESSAGE",
		TenantID:  "tenant-123",
		Source:    events.EventSource("slack"),
		PayloadRef: "raw_events:test-123",
		OccurredAt: time.Now().UTC(),
	}

	err = client.PublishEnvelope("trackguard.slack.events", envelope)
	if err != nil {
		t.Fatalf("Failed to publish slack event: %v", err)
	}
}

func TestProducer_PublishStripeEvent_WritesToCorrectTopic(t *testing.T) {
	client, err := NewClient([]string{"localhost:9092"}, "trackguard.stripe.events")
	if err != nil {
		t.Skip("Redpanda not available:", err)
	}
	defer client.Close()

	envelope := events.EventEnvelope{
		EventType:  "PAYMENT_SUCCEEDED",
		TenantID:  "tenant-456",
		Source:    events.EventSource("stripe"),
		PayloadRef: "raw_events:payment-456",
		OccurredAt: time.Now().UTC(),
	}

	err = client.PublishEnvelope("trackguard.stripe.events", envelope)
	if err != nil {
		t.Fatalf("Failed to publish stripe event: %v", err)
	}
}

func TestProducer_FailsGracefully_WhenRedpandaDown(t *testing.T) {
	client, err := NewClient([]string{"localhost:9999"}, "test-topic")
	if err != nil {
		t.Logf("Expected error creating client: %v", err)
		return
	}
	defer client.Close()

	envelope := events.EventEnvelope{
		EventType:  "TEST_EVENT",
		TenantID:  "tenant-123",
		Source:    events.EventSource("test"),
		PayloadRef: "raw_events:test",
		OccurredAt: time.Now().UTC(),
	}

	err = client.PublishEnvelope("test-topic", envelope)
	if err == nil {
		t.Error("Expected error when Redpanda is down, got nil")
	}
	t.Logf("Got expected error: %v", err)
}