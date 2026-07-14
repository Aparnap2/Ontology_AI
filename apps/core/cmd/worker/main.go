package main

import (
	"context"
	"database/sql"
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/lib/pq"
	"go.temporal.io/sdk/worker"
	"google.golang.org/grpc"

	coregrpc "iterateswarm-core/internal/grpc"
	"iterateswarm-core/internal/temporal"
	"iterateswarm-core/internal/workflow"
)

func main() {
	// Command line flags
	temporalAddr := flag.String("temporal", "localhost:7233", "Temporal address")
	namespace := flag.String("namespace", "default", "Temporal namespace")
	aiGRPCAddr := flag.String("ai-grpc", "localhost:50051", "Python AI service gRPC address")
	taskQueue := flag.String("queue", "feedback-queue", "Task queue name")

	flag.Parse()

	log.Println("Starting IterateSwarm Worker...")

	// Initialize Temporal client
	temporalClient, err := temporal.NewClient(*temporalAddr, *namespace)
	if err != nil {
		log.Fatalf("Failed to connect to Temporal: %v", err)
	}
	defer temporalClient.Close()
	log.Println("Connected to Temporal")

	// Initialize gRPC client for AI service
	aiClient, err := coregrpc.NewClientWithoutBlock(*aiGRPCAddr)
	if err != nil {
		log.Printf("Warning: Failed to connect to AI gRPC server: %v", err)
		log.Println("Worker will start, but AI calls will fail until AI service is available")
	} else {
		defer aiClient.Close()
		log.Println("Connected to AI gRPC service")
	}

	// Initialize database connection for DLQ (optional — graceful fallback if unavailable)
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL != "" {
		db, dbErr := sql.Open("postgres", databaseURL)
		if dbErr != nil {
			log.Printf("Warning: Failed to connect to database: %v", dbErr)
			log.Println("Worker will start, but DLQ writes will fall back to logging")
		} else {
			defer db.Close()
			workflow.InitDLQDatabase(db)
			log.Println("Connected to database for DLQ")
		}
	} else {
		log.Println("DATABASE_URL not set — DLQ writes will fall back to logging")
	}

	// Create Temporal worker
	w := worker.New(temporalClient.Client, *taskQueue, worker.Options{})

	// Register feedback workflow and activities
	w.RegisterWorkflow(workflow.FeedbackWorkflow)

	// Wire the Python AI gRPC client into activities so it's available when
	// desk ops (Finance, People, Legal, etc.) and other Python-integration
	// activities are implemented. Currently:
	//   - AnalyzeFeedback uses Azure OpenAI directly (Go-based agents)
	//   - StartSwarm still creates its own per-call connection (TODO: refactor)
	//   - Desk ops (ProcessFinanceOps, etc.) are stubs awaiting proto updates
	// The aiClient connection is lazily established (non-blocking dial) and may
	// be nil if the Python AI service was unavailable at startup.
	var aiClientConn *grpc.ClientConn
	if aiClient != nil {
		aiClientConn = aiClient.Conn()
	}
	activities := workflow.NewActivities(aiClientConn)

	// Also set the client on the global singleton used by standalone activities
	if aiClientConn != nil {
		workflow.InitAIClient(aiClientConn)
	}

	w.RegisterActivity(activities.AnalyzeFeedback)
	w.RegisterActivity(activities.SendDiscordApproval)
	w.RegisterActivity(activities.CreateGitHubIssue)

	// Register onboarding workflow and activities
	w.RegisterWorkflow(workflow.OnboardingWorkflow)
	w.RegisterActivity(workflow.GetNextQuestionActivity)
	w.RegisterActivity(workflow.SendTelegramOnboardingMessageActivity)
	w.RegisterActivity(workflow.ProcessOnboardingAnswerActivity)
	w.RegisterActivity(workflow.StoreOnboardingAnswerActivity)
	w.RegisterActivity(workflow.DetectArchetypeActivity)
	w.RegisterActivity(workflow.CompleteOnboardingActivity)

	// Register BusinessOS workflow and child workflows
	w.RegisterWorkflow(workflow.BusinessOSWorkflow)
	w.RegisterWorkflow(workflow.SOPExecutorWorkflow)
	w.RegisterActivity(workflow.ExecuteSOPActivity)

	// Register InternalOps workflow and activities
	w.RegisterWorkflow(workflow.InternalOpsWorkflow)
	w.RegisterActivity(workflow.RouteInternalEvent)
	w.RegisterActivity(workflow.ProcessFinanceOps)
	w.RegisterActivity(workflow.ProcessPeopleOps)
	w.RegisterActivity(workflow.ProcessLegalOps)
	w.RegisterActivity(workflow.ProcessIntelligenceOps)
	w.RegisterActivity(workflow.ProcessITOps)
	w.RegisterActivity(workflow.ProcessAdminOps)
	w.RegisterActivity(workflow.PersistInternalOpsResult)
	w.RegisterActivity(workflow.CreateHITLRecord)

	// Register WorkflowRouter and child workflows (Phase 5)
	w.RegisterWorkflow(workflow.WorkflowRouter)
	// Legacy compat aliases for in-flight workflows
	w.RegisterWorkflow(workflow.RevenueWorkflow)
	w.RegisterWorkflow(workflow.CSWorkflow)
	w.RegisterWorkflow(workflow.PeopleWorkflow)
	w.RegisterWorkflow(workflow.FinanceWorkflow)
	w.RegisterWorkflow(workflow.ChiefOfStaffWorkflow)
	w.RegisterActivity(workflow.SendToDLQActivity)

	log.Printf("Worker listening on task queue: %s", *taskQueue)

	// Start worker in goroutine
	errCh := make(chan error, 1)
	go func() {
		err := w.Run(worker.InterruptCh())
		if err != nil {
			errCh <- err
		}
	}()

	// Wait for shutdown signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-quit:
		log.Println("Shutting down worker...")
	case err := <-errCh:
		log.Printf("Worker error: %v", err)
	}

	// Give activities time to complete
	_, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	log.Println("Worker stopped")
}
