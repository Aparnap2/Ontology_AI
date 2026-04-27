package main

import (
	"bytes"
	"context"
	"database/sql"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/jackc/pgx/v5/pgxpool"

	"iterateswarm-core/internal/api"
	"iterateswarm-core/internal/db"
	"iterateswarm-core/internal/debug"
	"iterateswarm-core/internal/redpanda"
	"iterateswarm-core/internal/temporal"
	"iterateswarm-core/internal/web"

	_ "github.com/lib/pq"
)

func main() {
	// Command line flags
	redpandaBrokers := flag.String("redpanda", "localhost:9094", "Redpanda brokers")
	temporalAddr := flag.String("temporal", "localhost:7233", "Temporal address")
	namespace := flag.String("namespace", "default", "Temporal namespace")
	port := flag.String("port", "3000", "HTTP server port")
	topic := flag.String("topic", "feedback-events", "Kafka topic")

	flag.Parse()

	log.Println("Starting IterateSwarm Core Server...")

	// Initialize Redpanda client
	redpandaClient, err := redpanda.NewClient([]string{*redpandaBrokers}, *topic)
	if err != nil {
		log.Fatalf("Failed to connect to Redpanda: %v", err)
	}
	defer redpandaClient.Close()
	log.Println("Connected to Redpanda")

	// Initialize Temporal client
	temporalClient, err := temporal.NewClient(*temporalAddr, *namespace)
	if err != nil {
		log.Fatalf("Failed to connect to Temporal: %v", err)
	}
	defer temporalClient.Close()
	log.Println("Connected to Temporal")

	// Initialize PostgreSQL database connection
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://iterateswarm:iterateswarm@localhost:5432/iterateswarm?sslmode=disable"
	}

	pgDB, err := sql.Open("postgres", dbURL)
	if err != nil {
		log.Printf("Warning: Failed to open PostgreSQL: %v", err)
	} else {
		if err := pgDB.Ping(); err != nil {
			log.Printf("Warning: PostgreSQL ping failed: %v", err)
		} else {
			log.Println("Connected to PostgreSQL")
		}
	}
	defer pgDB.Close()

	// Initialize pgxpool for advanced features (SSE, async operations)
	var pool *pgxpool.Pool
	ctx := context.Background()
	pool, err = pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Printf("Warning: Failed to create pgxpool: %v", err)
	} else {
		if err := pool.Ping(ctx); err != nil {
			log.Printf("Warning: pgxpool ping failed: %v", err)
		} else {
			log.Println("pgxpool initialized")
		}
	}
	defer pool.Close()

	// Create repository
	var repo *db.Repository
	if pgDB != nil {
		repo = db.NewRepository(pgDB)
		log.Println("Repository initialized with PostgreSQL")
	}

	// Create handler with PostgreSQL
	handler := api.NewHandler(redpandaClient, temporalClient, repo, pgDB)

	// Create Fiber app
	app := fiber.New(fiber.Config{
		AppName:      "IterateSwarm Core",
		ErrorHandler: errorHandler,
	})

	// Middleware
	app.Use(recover.New())
	app.Use(logger.New(logger.Config{
		Format: "[${time}] ${status} - ${method} ${path} (${latency})\n",
	}))
	app.Use(cors.New())

	// Health check routes (no auth required)
	app.Get("/health", handler.HandleHealth)
	app.Get("/health/details", handler.HandleDetailedHealth)

	// Webhook routes (no auth required - platform-specific verification)
	app.Post("/webhooks/discord", handler.HandleDiscordWebhook)
	app.Post("/webhooks/slack", handler.HandleSlackWebhook)
	app.Post("/webhooks/interaction", handler.HandleInteraction)

	// Slack slash command proxy - forwards to Python Slack Bolt handler
	app.Post("/slack/commands", handleSlackCommandProxy)

	// HITL routes (internal - simple token auth)
	app.Post("/internal/hitl/investigate", handler.HandleHITLInvestigate)
	app.Post("/internal/hitl/dismiss", handler.HandleHITLDismiss)

	// BI query endpoint (internal)
	app.Post("/internal/query", handler.HandleBIQuery)

	// Test route (no auth)
	app.Get("/test/kafka", handler.HandleKafkaTest)

	// Auth routes (public - no auth required)
	if pgDB != nil {
		authHandler := api.NewAuthHandler(pgDB)
		auth := app.Group("/auth")
		auth.Get("/github/login", authHandler.Login)
		auth.Get("/github/callback", authHandler.Callback)
		auth.Get("/logout", authHandler.Logout)
		log.Println("JWT auth initialized (DEV_MODE=" + os.Getenv("DEV_MODE") + ", TEST_MODE=" + os.Getenv("TEST_MODE") + ")")
	} else {
		log.Println("Auth not initialized - database unavailable")
	}

	// Protected API endpoints - require JWT auth
	protected := app.Group("/api")
	protected.Use(api.RequireAuth())

	protected.Get("/me", func(ctx *fiber.Ctx) error {
		return ctx.JSON(map[string]interface{}{
			"user_id":       api.GetUserID(ctx),
			"username":      api.GetUsername(ctx),
			"authenticated": true,
		})
	})

	// Debug routes (LiteDebug Console)
	debugHandler := debug.NewHandler(redpandaClient, temporalClient, "http://localhost:16686")
	debugHandler.RegisterRoutes(app)

	// Web routes (HTMX Admin Dashboard) - require auth
	webHandler := web.NewHandler(pgDB)
	webHandler.RegisterRoutes(app)
	webHandler.RegisterAdminRoutes(app)

	// Founder Dashboard routes
	if pool != nil {
		founderDashboardHandler := web.NewFounderDashboardHandler(pool)
		founderReflectionHandler := web.NewReflectionHandler(pool, redpandaClient)

		// Founder routes (public for demo)
		app.Get("/founder/dashboard", founderDashboardHandler.FounderDashboard)
		app.Get("/founder/dashboard/summary", founderDashboardHandler.FounderDashboardPartial)
		app.Get("/founder/dashboard/stream", founderDashboardHandler.FounderDashboardStream)
		app.Post("/founder/reflection", founderReflectionHandler.SubmitReflection)
		log.Println("Founder dashboard routes initialized")
	}

	// SSE routes (Server-Sent Events for Live Feed) - require auth
	sseHandler := web.NewSSEHandler(pgDB)
	app.Get("/api/stream/events", api.RequireAuth(), sseHandler.HandleSSE)

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-quit
		log.Println("Shutting down server...")
		if err := app.Shutdown(); err != nil {
			log.Printf("Error during shutdown: %v", err)
		}
	}()

	// Start server
	addr := ":" + *port
	log.Printf("Server listening on %s", addr)
	if err := app.Listen(addr); err != nil {
		log.Printf("Server error: %v", err)
	}
}

func errorHandler(c *fiber.Ctx, err error) error {
	log.Printf("Error: %v", err)
	code := fiber.StatusInternalServerError
	if e, ok := err.(*fiber.Error); ok {
		code = e.Code
	}
	return c.Status(code).JSON(map[string]string{
		"error": err.Error(),
	})
}

// handleSlackCommandProxy forwards Slack slash commands to Python Slack Bolt handler.
// This enables /sarthi decide and other slash commands.
func handleSlackCommandProxy(c *fiber.Ctx) error {
	slackBotURL := os.Getenv("SLACK_BOT_URL")
	if slackBotURL == "" {
		slackBotURL = "http://localhost:3001"
	}

	// Forward the request to Python Slack Bolt
	client := &http.Client{}
	resp, err := client.Post(slackBotURL+"/slack/events", "application/x-www-form-urlencoded", bytes.NewReader(c.Body()))
	if err != nil {
		log.Printf("Failed to proxy to Slack Bot: %v", err)
		return c.Status(fiber.StatusBadGateway).JSON(map[string]string{
			"error": "Slack command service unavailable",
		})
	}
	defer resp.Body.Close()

	// Copy response back to Slack
	return c.Status(resp.StatusCode).SendStream(resp.Body)
}
