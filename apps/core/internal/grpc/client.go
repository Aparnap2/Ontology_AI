package grpc

import (
	"context"
	"log"

	pb "github.com/Aparnap2/iterate_swarm/gen/go/ai/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// Client wraps the gRPC connection to the Python AI service.
type Client struct {
	conn   *grpc.ClientConn
	client pb.AgentServiceClient
}

// NewClient creates a new gRPC client connected to the Python AI service.
func NewClient(addr string) (*Client, error) {
	log.Printf("Connecting to gRPC server at %s", addr)

	conn, err := grpc.NewClient(
		addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, err
	}

	return &Client{
		conn:   conn,
		client: pb.NewAgentServiceClient(conn),
	}, nil
}

// NewClientWithoutBlock creates a new gRPC client without blocking.
func NewClientWithoutBlock(addr string) (*Client, error) {
	log.Printf("Connecting to gRPC server at %s (non-blocking)", addr)

	conn, err := grpc.NewClient(
		addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, err
	}

	return &Client{
		conn:   conn,
		client: pb.NewAgentServiceClient(conn),
	}, nil
}

// AnalyzeFeedback sends feedback to the Python AI service for analysis.
func (c *Client) AnalyzeFeedback(ctx context.Context, text, source, userID string) (*pb.AnalyzeFeedbackResponse, error) {
	req := &pb.AnalyzeFeedbackRequest{
		Text:   text,
		Source: source,
		UserId: userID,
	}

	log.Printf("Sending feedback to AI service: text=%s, source=%s, user=%s", text, source, userID)

	resp, err := c.client.AnalyzeFeedback(ctx, req)
	if err != nil {
		log.Printf("AI service error: %v", err)
		return nil, err
	}

	if resp != nil && resp.Spec != nil {
		log.Printf(
			"AI analysis complete: is_duplicate=%v, type=%v, severity=%v",
			resp.IsDuplicate,
			resp.Spec.Type,
			resp.Spec.Severity,
		)
	}

	return resp, nil
}

// Conn returns the underlying gRPC ClientConn so it can be used by the workflow
// Activities struct for future Python AI service integration.
func (c *Client) Conn() *grpc.ClientConn {
	return c.conn
}

// Close closes the gRPC connection.
func (c *Client) Close() error {
	log.Println("Closing gRPC connection")
	return c.conn.Close()
}

// IsDuplicate checks if the response indicates a duplicate.
func IsDuplicate(resp *pb.AnalyzeFeedbackResponse) bool {
	return resp.IsDuplicate
}

// GetSeverity returns the severity as a string.
func GetSeverity(resp *pb.AnalyzeFeedbackResponse) string {
	if resp == nil || resp.Spec == nil {
		return "unspecified"
	}
	switch resp.Spec.Severity {
	case pb.Severity_SEVERITY_LOW:
		return "low"
	case pb.Severity_SEVERITY_MEDIUM:
		return "medium"
	case pb.Severity_SEVERITY_HIGH:
		return "high"
	case pb.Severity_SEVERITY_CRITICAL:
		return "critical"
	default:
		return "unspecified"
	}
}

// GetIssueType returns the issue type as a string.
func GetIssueType(resp *pb.AnalyzeFeedbackResponse) string {
	if resp == nil || resp.Spec == nil {
		return "unspecified"
	}
	switch resp.Spec.Type {
	case pb.IssueType_ISSUE_TYPE_BUG:
		return "bug"
	case pb.IssueType_ISSUE_TYPE_FEATURE:
		return "feature"
	case pb.IssueType_ISSUE_TYPE_QUESTION:
		return "question"
	default:
		return "unspecified"
	}
}
