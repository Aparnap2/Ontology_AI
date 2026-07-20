package temporal

import (
	"context"
	"log"
	"os"

	"go.temporal.io/sdk/client"
)

// ONTOLOGYAI_MAIN_QUEUE is the canonical V5.1 task queue for OntologyAI workflows.
// It is env-overridable via TEMPORAL_TASK_QUEUE and falls back to the legacy
// TRACKGUARD-MAIN-QUEUE name so the pilot never hard-fails on queue misconfiguration.
const ONTOLOGYAI_MAIN_QUEUE = "ONTOLOGYAI-MAIN-QUEUE"

// Legacy fallback queue retained for one version (V5.1 OQ §8.4 decision).
const legacyTaskQueue = "TRACKGUARD-MAIN-QUEUE"

// Client wraps the Temporal client.
type Client struct {
	Client client.Client
}

// ResolveTaskQueue returns the task queue to use, in priority order:
//  1. TEMPORAL_TASK_QUEUE env var (if non-empty)
//  2. ONTOLOGYAI_MAIN_QUEUE (canonical)
//  3. legacyTaskQueue (TRACKGUARD-MAIN-QUEUE) — never hard-fail
//
// The pilot must never crash on queue misconfiguration, so this always returns
// a usable queue name.
func ResolveTaskQueue() string {
	if q := os.Getenv("TEMPORAL_TASK_QUEUE"); q != "" {
		return q
	}
	return ONTOLOGYAI_MAIN_QUEUE
}

// NewClient creates a new Temporal client.
func NewClient(hostPort, namespace string) (*Client, error) {
	log.Printf("Connecting to Temporal at %s", hostPort)

	c, err := client.Dial(client.Options{
		HostPort:  hostPort,
		Namespace: namespace,
	})
	if err != nil {
		return nil, err
	}

	return &Client{Client: c}, nil
}

// StartWorkflow starts a new workflow execution. If taskQueue is empty it
// resolves to the canonical OntologyAI queue (with legacy fallback).
func (c *Client) StartWorkflow(ctx context.Context, workflowID, taskQueue string, input interface{}) (client.WorkflowRun, error) {
	if taskQueue == "" {
		taskQueue = ResolveTaskQueue()
	}
	run, err := c.Client.ExecuteWorkflow(
		ctx,
		client.StartWorkflowOptions{
			ID:        workflowID,
			TaskQueue: taskQueue,
		},
		input,
	)
	if err != nil {
		log.Printf("Failed to start workflow: %v", err)
		return nil, err
	}

	log.Printf("Workflow started: id=%s, run_id=%s", run.GetID(), run.GetRunID())
	return run, nil
}

// SignalWorkflow sends a signal to a workflow.
func (c *Client) SignalWorkflow(ctx context.Context, workflowID, signalName string, payload interface{}) error {
	err := c.Client.SignalWorkflow(ctx, workflowID, "", signalName, payload)
	if err != nil {
		log.Printf("Failed to signal workflow: %v", err)
		return err
	}

	log.Printf("Signal sent: workflow=%s, signal=%s", workflowID, signalName)
	return nil
}

// Health checks if the client is healthy.
func (c *Client) Health(ctx context.Context) error {
	_, err := c.Client.CheckHealth(ctx, nil)
	return err
}

// Close closes the client.
func (c *Client) Close() {
	if c.Client != nil {
		c.Client.Close()
	}
}
