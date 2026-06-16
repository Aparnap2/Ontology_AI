package redpanda

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/segmentio/kafka-go"
	"iterateswarm-core/internal/events"
)

// Producer interface for publishing events
type Producer interface {
	Publish(value []byte) error
	PublishToTopic(topic string, value []byte) error
	ProduceMessage(topic string, message map[string]interface{}) error
	PublishFeedback(data []byte) error
	PublishEnvelope(topic string, envelope events.EventEnvelope) error
	Consume(ctx context.Context, topic string) <-chan kafka.Message
	Close() error
	Health(ctx context.Context) error
}

// Client wraps the Kafka client.
type Client struct {
	writer *kafka.Writer
	reader *kafka.Reader
	topic  string
}

// NewClient creates a new Kafka client.
func NewClient(brokers []string, topic string) (*Client, error) {
	log.Printf("Connecting to Kafka at %v", brokers)

	// Don't set Topic on Writer - we'll set it on each message for flexibility
	writer := &kafka.Writer{
		Addr:         kafka.TCP(brokers...),
		Balancer:     &kafka.LeastBytes{},
		BatchTimeout: 10 * time.Millisecond,
	}

	// Ensure topics exist by creating them if needed
	for _, t := range []string{topic, "trackguard.slack.events", "trackguard.stripe.events", "trackguard.guardian.results", "trackguard.hitl.decisions"} {
		ensureTopic(brokers, t)
	}

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:  brokers,
		Topic:    topic,
		GroupID:  "iterateswarm-consumer",
		MinBytes: 10e3, // 10KB
		MaxBytes: 10e6, // 10MB
	})

	return &Client{
		writer: writer,
		reader: reader,
		topic:  topic,
	}, nil
}

// ensureTopic creates a topic if it doesn't exist.
func ensureTopic(brokers []string, topic string) {
	conn, err := kafka.Dial("tcp", brokers[0])
	if err != nil {
		log.Printf("Warning: Could not connect to Kafka: %v", err)
		return
	}
	defer conn.Close()

	controller, err := conn.Controller()
	if err != nil {
		log.Printf("Warning: Could not get controller: %v", err)
		return
	}

	controllerConn, err := kafka.Dial("tcp", fmt.Sprintf("%s:%d", controller.Host, controller.Port))
	if err != nil {
		log.Printf("Warning: Could not connect to controller: %v", err)
		return
	}
	defer controllerConn.Close()

	topicConfigs := []kafka.TopicConfig{
		{
			Topic:             topic,
			NumPartitions:     1,
			ReplicationFactor: 1,
		},
	}
	err = controllerConn.CreateTopics(topicConfigs...)
	if err != nil && !strings.Contains(err.Error(), "already exists") {
		log.Printf("Topic creation result: %v", err)
	}
}

// Publish sends a message to the configured topic.
func (c *Client) Publish(value []byte) error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	msg := kafka.Message{
		Topic: c.topic,
		Value: value,
		Key:   []byte(time.Now().Format(time.RFC3339)),
	}

	err := c.writer.WriteMessages(ctx, msg)
	if err != nil {
		log.Printf("Failed to publish message: %v", err)
		return err
	}

	log.Printf("Message published to %s", c.topic)
	return nil
}

// PublishToTopic sends a message to a specific topic (overrides configured topic).
func (c *Client) PublishToTopic(topic string, value []byte) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	msg := kafka.Message{
		Topic: topic,
		Value: value,
		Key:   []byte(time.Now().Format(time.RFC3339)),
	}

	err := c.writer.WriteMessages(ctx, msg)
	if err != nil {
		log.Printf("Failed to publish message: %v", err)
		return err
	}

	log.Printf("Message published to %s", topic)
	return nil
}

// ProduceMessage publishes a map as a JSON message to a topic.
func (c *Client) ProduceMessage(topic string, message map[string]interface{}) error {
	data, err := json.Marshal(message)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}
	return c.PublishToTopic(topic, data)
}

// PublishFeedback sends a feedback event.
func (c *Client) PublishFeedback(data []byte) error {
	return c.Publish(data)
}

// PublishEnvelope publishes an event envelope to the specified topic
func (c *Client) PublishEnvelope(topic string, envelope events.EventEnvelope) error {
	data, err := json.Marshal(envelope)
	if err != nil {
		return fmt.Errorf("failed to marshal envelope: %w", err)
	}
	return c.PublishToTopic(topic, data)
}

// Consume consumes messages from a topic.
func (c *Client) Consume(ctx context.Context, topic string) <-chan kafka.Message {
	records := make(chan kafka.Message, 100)

	go func() {
		defer close(records)

		for {
			select {
			case <-ctx.Done():
				return
			default:
				msg, err := c.reader.FetchMessage(ctx)
				if err != nil {
					if ctx.Err() != nil {
						return
					}
					log.Printf("Consumer error: %v", err)
					continue
				}
				records <- msg
			}
		}
	}()

	return records
}

// Close closes the client.
func (c *Client) Close() error {
	if c.reader != nil {
		c.reader.Close()
	}
	if c.writer != nil {
		return c.writer.Close()
	}
	return nil
}

// Health checks if the client is healthy.
func (c *Client) Health(ctx context.Context) error {
	conn, err := kafka.Dial("tcp", c.writer.Addr.String())
	if err != nil {
		return err
	}
	defer conn.Close()
	return nil
}
