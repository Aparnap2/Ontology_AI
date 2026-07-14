package redpanda_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/require"

	"iterateswarm-core/internal/redpanda"
)

func uniqueTopic(t *testing.T) string {
	t.Helper()
	return fmt.Sprintf("test-%s", uuid.New().String()[:8])
}

func skipIfRedpandaDown(t *testing.T) {
	t.Helper()
	c, err := redpanda.NewClient([]string{"localhost:9094"}, "health-check")
	if err != nil {
		t.Skip("Redpanda not available:", err)
	}
	defer c.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := c.Health(ctx); err != nil {
		t.Skipf("Redpanda not available: %v", err)
	}
}

func TestRedpandaClient_HappyPath(t *testing.T) {
	skipIfRedpandaDown(t)
	topic := uniqueTopic(t)
	c, err := redpanda.NewClient([]string{"localhost:9094"}, topic)
	require.NoError(t, err)
	require.NotNil(t, c)
	defer c.Close()

	err = c.Publish([]byte(`{"test": "hello"}`))
	require.NoError(t, err)
}

func TestRedpandaPublishToTopic(t *testing.T) {
	skipIfRedpandaDown(t)
	topic := uniqueTopic(t)
	c, err := redpanda.NewClient([]string{"localhost:9094"}, "default-topic")
	require.NoError(t, err)
	defer c.Close()

	err = c.PublishToTopic(topic, []byte(`{"test": "message"}`))
	require.NoError(t, err)
}

func TestRedpandaProduceMessage(t *testing.T) {
	skipIfRedpandaDown(t)
	topic := uniqueTopic(t)
	c, err := redpanda.NewClient([]string{"localhost:9094"}, topic)
	require.NoError(t, err)
	defer c.Close()

	msg := map[string]interface{}{"event": "test", "data": "value"}
	err = c.ProduceMessage(topic, msg)
	require.NoError(t, err)
}
