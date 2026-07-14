# IterateSwarm Codebase — Complete Guide

> **Purpose**: A complete, noob-friendly explanation of the IterateSwarm codebase. Covers what every part does, why it exists, how the pieces fit together, and what tools/technologies are used. After reading this, you should be able to navigate, modify, and extend the codebase with confidence.

---

## Table of Contents

1. [What Is IterateSwarm?](#1-what-is-iterateswarm)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Go Backend (`apps/core`) — Complete Tour](#3-go-backend-appscore--complete-tour)
4. [Python AI Service (`apps/ai`) — Complete Tour](#4-python-ai-service-appsai--complete-tour)
5. [Communication Between Services](#5-communication-between-services)
6. [Key Workflows Explained](#6-key-workflows-explained)
7. [Key Agents Explained](#7-key-agents-explained)
8. [Database & Persistence](#8-database--persistence)
9. [Event Flow — Full Journey](#9-event-flow--full-journey)
10. [Tools, Technologies & Concepts](#10-tools-technologies--concepts)
11. [Development Workflow](#11-development-workflow)
12. [Running the Stack Locally](#12-running-the-stack-locally)
13. [Common Patterns & Conventions](#13-common-patterns--conventions)
14. [FAQ](#14-faq)

---

## 1. What Is IterateSwarm?

IterateSwarm is a **ChatOps platform** that automates how a startup founder processes feedback and runs internal operations. The core idea:

1. Feedback comes in from Discord, Slack, or webhooks.
2. An AI agent analyzes it, classifies it, and generates a GitHub issue spec.
3. A human (founder) approves or rejects via Discord buttons.
4. If approved, a GitHub issue is created automatically.
5. Internal business events (payments, hires, expenses) are routed to specialized "desks" (Finance, People, Legal, etc.) for automated processing.

The platform is built as a **modular monolith** with two primary services:

| Service | Language | Role |
|---------|----------|------|
| **Go Backend** | Go 1.24 | HTTP server, Temporal orchestration, external integrations |
| **Python AI Service** | Python 3.11 | LangGraph-based AI agents, exposed via gRPC |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ External Sources                                                    │
│ Discord Slack Webhooks Razorpay Telegram Cron Jobs                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ webhooks / events
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Go Backend (apps/core)                                              │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐     │
│ │ Fiber HTTP   │ │ Temporal     │ │ Redpanda Client          │     │
│ │ Server       │ │ Client       │ │ (Kafka-compatible)       │     │
│ │ :3000        │ │              │ │                          │     │
│ └──────┬───────┘ └──────┬───────┘ └──────────┬───────────────┘     │
│        │                │                    │                     │
│        │                │                    ▼                     │
│        │                │         ┌─────────────────────┐          │
│        │                │         │ Workflow Orchestrator│          │
│        │                │         │ (FeedbackWorkflow,   │          │
│        │                │         │ OntologyAIRouter, etc.)  │          │
│        │                │         └──────────┬──────────┘          │
│        │                │                    │                     │
│        │                │         ┌──────────┴──────────┐          │
│        │                │         │ Activities           │          │
│        │                │         │ AnalyzeFeedback      │◄──────► gRPC call
│        │                │         │ SendDiscordApproval  │ to Python AI
│        │                │         │ CreateGitHubIssue    │          │
│        │                │         └──────────┬──────────┘          │
│        │                │                    │                     │
│        │                │         ┌──────────┴──────────┐          │
│        │                │         │ Go AI Agents        │          │
│        │                │         │ (TriageAgent,       │          │
│        │                │         │ SpecAgent)          │          │
│        │                │         └─────────────────────────┘      │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          │ gRPC (:50051)
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Python AI Service (apps/ai)                                         │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐     │
│ │ gRPC Server  │ │ LangGraph    │ │ Qdrant Vector Store      │     │
│ │              │ │ Agents       │ │ (semantic memory)        │     │
│ │ AgentService │ │ Anomaly      │ │                          │     │
│ │ SOPExecutor  │ │ Investor     │ │                          │     │
│ │              │ │ Pulse        │ │                          │     │
│ │              │ │ QA           │ │                          │     │
│ │              │ │ Guardian     │ │                          │     │
│ │              │ └──────────────┘ └──────────────────────────┘     │
│ └──────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Infrastructure Services (Docker)

| Service | Purpose | Default Port |
|---------|---------|--------------|
| **Temporal** | Workflow orchestration engine | 7233 (server), 8233 (UI) |
| **Redpanda** | Kafka-compatible event streaming | 9094 |
| **PostgreSQL** | Primary relational database | 5432 |
| **Qdrant** | Vector database for semantic search | 6333 |

---

## 3. Go Backend (`apps/core`) — Complete Tour

### 3.1 Entry Points

| File | Purpose |
|------|---------|
| [`cmd/server/main.go`](apps/core/cmd/server/main.go) | Starts the Fiber HTTP server on port 3000. Registers all routes (webhooks, HITL, health, auth, web UI). |
| [`cmd/worker/main.go`](apps/core/cmd/worker/main.go) | Starts the Temporal worker on `feedback-queue`. Registers all workflows and activities. |
| [`cmd/consumer/main.go`](apps/core/cmd/consumer/main.go) | Redpanda consumer that reads from the `feedback-events` topic and starts Temporal workflows. Required for event-driven workflow triggering. |

### 3.2 Core Packages

#### `internal/api` — HTTP Handlers

- [`handlers.go`](apps/core/internal/api/handlers.go) — Main HTTP handler. Key endpoints:
  - `POST /webhooks/discord` — Receives Discord feedback, publishes to Redpanda.
  - `POST /webhooks/slack` — Receives Slack events, publishes to Redpanda.
  - `POST /webhooks/interaction` — Receives Discord button clicks (approve/reject), signals Temporal workflows.
  - `GET /health` — Simple health check.
  - `GET /health/details` — Detailed health with PostgreSQL, Temporal, Redpanda checks.
  - `GET /test/kafka` — Sends a test event to Redpanda (dev only).
  - `POST /internal/hitl/investigate` — HITL signal for "investigate".
  - `POST /internal/hitl/dismiss` — HITL signal for "dismiss".
  - `POST /internal/query` — BI query endpoint.
  - `POST /demo/feedback` — Demo feedback endpoint (bypasses Discord verification).
- [`middleware.go`](apps/core/internal/api/middleware.go) — JWT auth middleware (`RequireAuth()`), CORS, logging.
- [`auth.go`](apps/core/internal/api/auth.go) — GitHub OAuth login/callback, JWT token generation.
- [`telegram.go`](apps/core/internal/api/telegram.go) — Telegram onboarding handler.

#### `internal/workflow` — Temporal Workflows

- [`workflow.go`](apps/core/internal/workflow/workflow.go) — **FeedbackWorkflow**: The main feedback processing workflow.
  1. `AnalyzeFeedback` → AI analysis
  2. `SendDiscordApproval` → Discord embed with Approve/Reject buttons
  3. Wait for user signal (48-hour timeout)
  4. `CreateGitHubIssue` → GitHub API
- [`sarthi_router.go`](apps/core/internal/workflow/sarthi_router.go) — **OntologyAIRouter**: Parent workflow that routes events to child workflows (Revenue, CS, People, Finance, ChiefOfStaff). Implements Continue-As-New at 1000 events to prevent Temporal history bloat.
- [`business_os_workflow.go`](apps/core/internal/workflow/business_os_workflow.go) — **BusinessOSWorkflow**: Executes SOPs via Python gRPC.
- [`onboarding_workflow.go`](apps/core/internal/workflow/onboarding_workflow.go) — **OnboardingWorkflow**: Telegram-based founder onboarding.
- [`activities.go`](apps/core/internal/workflow/activities.go) — All activity implementations:
  - `AnalyzeFeedback` — Uses Go TriageAgent + SpecAgent (Azure OpenAI)
  - `SendDiscordApproval` — Sends Discord embed with buttons
  - `CreateGitHubIssue` — Creates GitHub/SwarmRepo issue
  - `StartSwarm` — Calls Python gRPC for multi-agent swarm
  - `RouteInternalEvent` — Routes events to Finance/People/Legal/Intelligence/IT/Admin desks
  - `ProcessFinanceOps`, `ProcessPeopleOps`, etc. — Desk-specific processing
  - `ExecuteSOPActivity` — Calls Python SOPExecutor via gRPC

#### `internal/agents` — Go AI Agents

- [`stubs.go`](apps/core/internal/agents/stubs.go) — **TriageAgent** and **SpecAgent** stubs. These are simplified implementations that return hardcoded/mock results. Real implementations would call Azure OpenAI.

#### `internal/events` — Event Definitions

- [`envelope.go`](apps/core/internal/events/envelope.go) — **EventEnvelope** struct. This is the **only shape** that flows through Redpanda and Temporal. Contains:
  - `TenantID` — Multi-tenant identifier
  - `EventType` — Normalized event type (e.g., `PAYMENT_SUCCESS`, `USER_SIGNED_UP`)
  - `Source` — Event source (razorpay, stripe, intercom, etc.)
  - `PayloadRef` — Reference to raw payload in PostgreSQL (NEVER raw JSON)
  - `PayloadHash` — SHA-256 hash for integrity
  - `OccurredAt` / `ReceivedAt` — Timestamps
  - `TraceID` — Distributed tracing ID
  - `IdempotencyKey` — Deduplication key
- [`dictionary.go`](apps/core/internal/events/dictionary.go) — Event type constants and normalization logic.

#### `internal/db` — Database Layer

- [`repository.go`](apps/core/internal/db/repository.go) — Main repository with methods like `SetIdempotencyKey`, `ListFeedback`, `ListIssues`.
- [`dbsqlc/`](apps/core/internal/db/dbsqlc/) — sqlc-generated type-safe SQL code. Contains models and query functions.
- [`migrations/`](apps/core/internal/db/migrations/) — SQL migration files (001, 002, 003).

#### `internal/temporal` — Temporal Client

- [`client.go`](apps/core/internal/temporal/client.go) — Wraps Temporal client with `StartWorkflow`, `SignalWorkflow`, `Health` methods.

#### `internal/redpanda` — Redpanda Client

- [`client.go`](apps/core/internal/redpanda/client.go) — Wraps Redpanda (Kafka) with `Publish`, `Subscribe`, `Health` methods.

#### `internal/web` — Web UI Handlers

- [`handler.go`](apps/core/internal/web/handler.go) — Admin dashboard routes.
- [`founder_handler.go`](apps/core/internal/web/founder_handler.go) — Founder dashboard with SSE streaming.
- [`sse.go`](apps/core/internal/web/sse.go) — Server-Sent Events for live feed.
- [`templates/`](apps/core/internal/web/templates/) — HTML templates for the admin UI.

#### `internal/grpc` — gRPC Client

- [`client.go`](apps/core/internal/grpc/client.go) — gRPC client for calling Python AI service.

#### `internal/logging` — Structured Logging

- [`logger.go`](apps/core/internal/logging/logger.go) — Structured JSON logging wrapper.

#### `internal/retry` — Retry Logic

- [`retry.go`](apps/core/internal/retry/retry.go) — Simple retry with exponential backoff.

#### `internal/webhooks` — Webhook Handlers

- [`handlers.go`](apps/core/internal/webhooks/handlers.go) — Generic webhook processing.
- [`payments.go`](apps/core/internal/webhooks/payments.go) — Payment-specific webhook handlers.

#### `internal/debug` — Debug Tools

- [`handlers.go`](apps/core/internal/debug/handlers.go) — LiteDebug Console routes.
- [`kafka_browser.go`](apps/core/internal/debug/kafka_browser.go) — Redpanda topic browser.
- [`workflow_inspector.go`](apps/core/internal/debug/workflow_inspector.go) — Temporal workflow inspector.

---

## 4. Python AI Service (`apps/ai`) — Complete Tour

### 4.1 Entry Point

- [`src/main.py`](apps/ai/src/main.py) — Starts both Temporal worker and gRPC server concurrently. Supports `--mode temporal|grpc|both`.

### 4.2 gRPC Server

- [`src/grpc_server.py`](apps/ai/src/grpc_server.py) — Implements `AgentService` (AnalyzeFeedback, StartSwarm) and `SOPExecutor` (ExecuteSOP) via gRPC. Wraps LangGraph agents and exposes them to Go backend.

### 4.3 Agents (`src/agents/`)

Each agent is a **LangGraph StateGraph** with:
- `state.py` — TypedDict defining the state schema
- `graph.py` — Graph definition (nodes + edges)
- `nodes.py` — Node function implementations
- `prompts.py` — DSPy predictor definitions
- `thresholds.py` — Rule-based threshold logic (for some agents)

#### Available Agents

| Agent | Purpose | Key Nodes |
|-------|---------|-----------|
| **AnomalyAgent** | Detects anomalies in revenue/ops data | `detect_anomaly` → `retrieve_anomaly_memory` → `generate_explanation` → `generate_action` → `build_slack_message` → `send_slack` |
| **InvestorAgent** | Generates investor-ready updates | `gather_metrics` → `generate_narrative` → `build_slack_message` → `send_slack` |
| **PulseAgent** | Monitors business pulse (KPIs, health) | `collect_metrics` → `check_thresholds` → `send_digest` |
| **QAAgent** | Answers founder questions using RAG | `retrieve_context` → `generate_answer` → `format_response` |
| **Guardian** | Watchlist detection and compliance | `check_watchlist` → `build_alert` → `deliver_alert` |

### 4.4 Activities (`src/activities/`)

Temporal activities that wrap agent execution:
- `run_anomaly_agent.py` — Wraps AnomalyAgent as a Temporal activity
- `run_investor_agent.py` — Wraps InvestorAgent
- `run_pulse_agent.py` — Wraps PulseAgent
- `run_qa_agent.py` — Wraps QAAgent
- `run_guardian_watchlist.py` — Wraps Guardian
- `send_slack_message.py` — Standalone Slack delivery activity
- `send_telegram.py` — Telegram delivery activity

### 4.5 Memory (`src/memory/`)

- [`qdrant_ops.py`](apps/ai/src/memory/qdrant_ops.py) — Qdrant client wrappers:
  - `upsert_memory` — Store memory with embedding
  - `search_memory` — Semantic search
  - `query_memory` — Filtered semantic query
  - `delete_memory` — Delete by point ID
  - `clear_tenant_memory` — Clear all tenant memories
- `spine.py` — MemorySpine for multi-layer memory (working, episodic, semantic, procedural).
- `rag_kernel.py` — RAG context loading.
- `compressor.py` — Memory compression for long-term storage.
- `compressed.py` — Compressed memory representation.

### 4.6 Integrations (`src/integrations/`)

- [`slack.py`](apps/ai/src/integrations/slack.py) — Slack/Telegram delivery:
  - `send_message` — Async Slack webhook with Telegram fallback
  - `send_message_sync` — Sync wrapper
  - `format_slack_blocks` — Block Kit helper
  - `deliver_guardian_alert` — Mockoon + capture sidecar for demo
- `stripe.py` — Stripe webhook integration.
- `plaid.py` — Plaid bank statement integration.
- `product_db.py` — Product database client.

### 4.7 Services (`src/services/`)

- `embeddings.py` — Ollama/OpenAI embedding generation.
- `qdrant.py` — Qdrant service wrapper.
- `relevance_scorer.py` — Relevance scoring for RAG.
- `tone_filter.py` — Tone validation (banned jargon check).
- `langfuse_client.py` — Langfuse tracing client.
- `slack_notifier.py` — Slack notification service.
- `crawler_service.py` — Web crawler for data gathering.
- `sandbox_client.py` — Sandbox execution client.
- `weekly_checkin.py` — Weekly check-in logic.

### 4.8 Workflows (`src/workflows/`)

Temporal workflows that orchestrate agents:
- `compression_workflow.py` — Memory compression workflow.
- `eval_loop_workflow.py` — Agent evaluation loop.
- `investor_workflow.py` — Investor update generation workflow.
- `pulse_workflow.py` — Pulse monitoring workflow.
- `qa_workflow.py` — Q&A workflow.
- `self_analysis_workflow.py` — Agent self-analysis.
- `weight_decay_workflow.py` — Memory weight decay.

### 4.9 Config (`src/config/`)

- [`config_module.py`](apps/ai/src/config/config_module.py) — Pydantic config models:
  - `TemporalConfig` — Temporal server settings
  - `OllamaConfig` — Ollama LLM settings
  - `QdrantConfig` — Qdrant vector DB settings
  - `TelegramConfig` — Telegram mock settings
  - `LoggingConfig` — Logging settings
- `llm.py` — LLM client configuration (Azure OpenAI / Ollama / Groq).
- `llm_guard.py` — LLM output guardrails.
- `event_dictionary.py` — Event type definitions and normalization.

### 4.10 SOPs (`src/sops/`)

- `base.py` — Base SOP class.
- `registry.py` — SOP registry.
- `bank_statement_ingest.py` — Bank statement ingestion SOP.
- `revenue_received.py` — Revenue received SOP.
- `weekly_briefing.py` — Weekly briefing SOP.

### 4.11 LLM Operations (`src/llmops/`)

- `eval_loop.py` — Agent evaluation loop.
- `self_analysis.py` — Agent self-analysis using DSPy.
- `tracer.py` — OpenTelemetry tracing.

### 4.12 HITL (`src/hitl/`)

- `manager.py` — Human-in-the-loop manager.
- `confidence.py` — Confidence scoring for HITL decisions.

### 4.13 Guardian (`src/guardian/`)

- `detector.py` — Watchlist pattern detection.
- `insight_builder.py` — Insight generation.
- `watchlist.py` — Watchlist management.

---

## 5. Communication Between Services

### 5.1 Go → Python (gRPC)

Go backend calls Python AI service via gRPC on port 50051:

```protobuf
service AgentService {
  rpc AnalyzeFeedback(AnalyzeFeedbackRequest) returns (AnalyzeFeedbackResponse);
  rpc StartSwarm(StartSwarmRequest) returns (StartSwarmResponse);
}

service SOPExecutor {
  rpc ExecuteSOP(ExecuteSOPRequest) returns (ExecuteSOPResponse);
}
```

Proto definitions: [`proto/ai/v1/agent.proto`](proto/ai/v1/agent.proto)

### 5.2 Go → Temporal

Activities are registered with the Temporal worker. Workflows schedule activities via `workflow.ExecuteActivity()`.

### 5.3 External → Go (HTTP)

Webhooks from Discord, Slack, Razorpay, etc. hit the Fiber HTTP server.

### 5.4 Go → Redpanda

Events are published to Redpanda topics via `redpandaClient.Publish()`.

---

## 6. Key Workflows Explained

### 6.1 FeedbackWorkflow

**File**: [`apps/core/internal/workflow/workflow.go`](apps/core/internal/workflow/workflow.go)

```
User Feedback
    ↓
AnalyzeFeedback
    ↓
[Is Duplicate?]
    → No → SendDiscordApproval
              ↓
           Wait for Signal (48h timeout)
              ↓
           [Approved] → CreateGitHubIssue → Done
           [Rejected/Timeout] → Cleanup → Done
    → Yes → Done (skip)
```

Key features:
- Retry policy: 5 attempts with exponential backoff
- 48-hour HITL timeout
- Dead Letter Queue (DLQ) for failed tasks
- Signal-based user approval via Discord buttons

### 6.2 OntologyAIRouter

**File**: [`apps/core/internal/workflow/sarthi_router.go`](apps/core/internal/workflow/sarthi_router.go)

Parent workflow that routes events to child workflows:

| Event Type | Child Workflow(s) |
|------------|-------------------|
| `PAYMENT_SUCCESS`, `SUBSCRIPTION_*`, `CRM_DEAL_*` | `RevenueWorkflow` |
| `USER_SIGNED_UP`, `SUPPORT_TICKET_*`, `TIME_TICK_D*` | `CSWorkflow` |
| `EMPLOYEE_*`, `CHECKLIST_*`, `ONBOARDING_*` | `PeopleWorkflow` |
| `EXPENSE_*`, `BANK_*`, `VENDOR_*`, `TIME_TICK_DAILY` | `FinanceWorkflow` |
| `TIME_TICK_MONTHLY`, `AGENT_OUTPUT`, `DECISION_LOGGED` | `ChiefOfStaffWorkflow` |
| `TIME_TICK_WEEKLY` | `RevenueWorkflow` + `ChiefOfStaffWorkflow` (multi-route) |

Key features:
- Continue-As-New at 1000 events (prevents Temporal history bloat)
- Idempotency via `SeenKeys` map
- Fire-and-forget child workflow spawning
- DLQ for unknown event types

### 6.3 AnomalyAgent Workflow (Python)

**File**: [`apps/ai/src/agents/anomaly/graph.py`](apps/ai/src/agents/anomaly/graph.py)

```
detect_anomaly
    ↓
[should_alert?]
    → No → END
    → Yes → retrieve_anomaly_memory
                ↓
            generate_explanation
                ↓
            generate_action
                ↓
            build_slack_message
                ↓
            send_slack
                ↓
            END
```

---

## 7. Key Agents Explained

### 7.1 TriageAgent (Go)

**File**: [`apps/core/internal/agents/stubs.go`](apps/core/internal/agents/stubs.go)

Stub implementation. Real version would:
1. Take feedback text, source, user ID
2. Classify into bug/feature/question
3. Assign severity (critical/high/medium/low)
4. Return confidence score

### 7.2 SpecAgent (Go)

**File**: [`apps/core/internal/agents/stubs.go`](apps/core/internal/agents/stubs.go)

Stub implementation. Real version would:
1. Take classification, severity, reasoning, confidence
2. Generate GitHub issue title
3. Generate description with reproduction steps
4. Generate acceptance criteria
5. Suggest labels

### 7.3 AnomalyAgent (Python)

**File**: [`apps/ai/src/agents/anomaly/`](apps/ai/src/agents/anomaly/)

LangGraph-based agent. Key features:
- Rule-based anomaly detection (no LLM for detection)
- DSPy-generated explanations and actions
- Qdrant memory retrieval for historical context
- Slack Block Kit message formatting
- Telegram fallback delivery

### 7.4 InvestorAgent (Python)

**File**: [`apps/ai/src/agents/investor/`](apps/ai/src/agents/investor/)

Generates investor-ready updates. Key features:
- Gathers metrics from various sources
- Generates narrative using DSPy
- Sends rich Slack message with full draft

### 7.5 QAAgent (Python)

**File**: [`apps/ai/src/agents/qa/`](apps/ai/src/agents/qa/)

RAG-based Q&A for founders. Key features:
- Retrieves relevant context from Qdrant
- Generates answer using DSPy
- Formats response with citations

---

## 8. Database & Persistence

### 8.1 PostgreSQL Schema

Key tables (defined in migrations):
- `feedback` — User feedback items
- `issues` — Generated GitHub issues
- `raw_events` — Raw event payloads (referenced by `PayloadRef`)
- `hitl_queue` — Human-in-the-loop approval queue
- `agent_outputs` — AI agent output records
- `founders` — Founder/user accounts
- `idempotency_keys` — Deduplication keys with TTL

### 8.2 Qdrant Vector Store

Collections:
- `sarthi_memory` — Main memory collection (768-dim vectors, cosine similarity)
- Memory types: `anomaly`, `revenue_event`, `briefing`, `general`

### 8.3 Redis

Used for:
- Session storage
- Caching
- (Potentially) LangGraph state checkpointing

---

## 9. Event Flow — Full Journey

### Scenario 1: Feedback Processing

```
1. User posts on Discord
       ↓
2. Discord webhook → POST /webhooks/discord
       ↓
3. Handler validates, generates feedback_id, publishes to Redpanda "feedback-events" topic
       ↓
4. Redpanda pushes to Temporal → FeedbackWorkflow
       ↓
5. Workflow schedules AnalyzeFeedback activity
       ↓
6. Activity calls TriageAgent (Go) → classification + severity
       ↓
7. Activity calls SpecAgent (Go) → title, description, labels
       ↓
8. Workflow schedules SendDiscordApproval activity
       ↓
9. Discord bot sends embed with Approve/Reject buttons
       ↓
10. User clicks "Approve" → POST /webhooks/interaction
       ↓
11. Handler parses custom_id (format: "approve:workflow_id"), signals Temporal
       ↓
12. Workflow receives signal, schedules CreateGitHubIssue
       ↓
13. GitHub API creates issue
       ↓
14. Done
```

### Scenario 2: Internal Event Routing

```
1. Razorpay webhook → Go backend
       ↓
2. Event normalized to EventEnvelope, published to Redpanda
       ↓
3. Redpanda pushes to Temporal → OntologyAIRouter
       ↓
4. OntologyAIRouter looks up event_type in routing table
       ↓
5. Spawns child workflow (e.g., RevenueWorkflow)
       ↓
6. Child workflow processes event (currently stubs)
       ↓
7. If event needs Python AI → calls SOPExecutor via gRPC
       ↓
8. Python agent processes, stores in Qdrant, sends Slack notification
       ↓
9. Done
```

---

## 10. Tools, Technologies & Concepts

### 10.1 Languages & Frameworks

| Component | Language | Framework/Library |
|-----------|----------|-------------------|
| HTTP Server | Go | Fiber v2 |
| AI Agents | Python | LangGraph, DSPy, instructor |
| Workflow Engine | Go + Python | Temporal SDK |
| gRPC | Go + Python | grpc-go, grpcio |
| Database | SQL | PostgreSQL, sqlc |
| Vector DB | — | Qdrant |
| Message Queue | — | Redpanda (Kafka-compatible) |

### 10.2 Key Concepts

| Concept | Explanation |
|---------|-------------|
| **Temporal Workflow** | A function that orchestrates activities (steps) with built-in retry, timeout, and signal handling. Guarantees exactly-once execution. |
| **Temporal Activity** | A single unit of work executed by a worker. Can be retried independently of the workflow. |
| **LangGraph StateGraph** | A directed graph where nodes are functions and edges define transitions. State flows through the graph. |
| **DSPy** | Prompt optimization framework. Compiles prompts against datasets to improve LLM output quality. |
| **Structured Output (instructor)** | Library that binds LLM JSON output to Pydantic models for type safety. |
| **EventEnvelope** | The canonical event shape that flows through Redpanda and Temporal. Never contains raw JSON — references PostgreSQL. |
| **HITL (Human-in-the-Loop)** | Workflow pauses for human approval via Discord buttons. Times out after 48 hours. |
| **Continue-As-New** | Temporal feature to restart a workflow with fresh history, preventing history size bloat. |
| **Idempotency Key** | Deduplication key (e.g., "razorpay:pay_abc:v1") to prevent double-processing. |
| **Fire-and-Forget** | Spawning a child workflow without waiting for its completion. |
| **Dead Letter Queue (DLQ)** | Storage for failed/unroutable events for manual inspection. |
| **Multi-Tenant** | Using `tenant_id` as the primary identifier for data isolation. |
| **Banned Jargon List** | A list of corporate buzzwords that agents must avoid in output. |
| **Slack Block Kit** | Rich message formatting for Slack (headers, sections, contexts). |
| **Qdrant Semantic Search** | Vector similarity search for finding related memories. |

### 10.3 Development Tools

| Tool | Purpose |
|------|---------|
| **Makefile** | Common commands (`make up`, `make down`, `make build`) |
| **Docker** | Containerization of all services |
| **sqlc** | Type-safe SQL code generation from SQL queries |
| **buf** | Protocol buffer management and code generation |
| **uv** | Fast Python package manager |
| **ruff** | Python linter (replaces flake8, black, isort) |
| **go fmt / revive** | Go formatting and linting |
| **GitHub Actions** | CI/CD (lint, test, build) |
| **Temporal CLI** | Workflow inspection and debugging |
| **Langfuse** | LLM observability and tracing |

---

## 11. Development Workflow

### 11.1 Git Flow

1. Create feature branch: `git checkout -b feat/short-description`
2. Make changes
3. Run tests: `go test ./...` (Go) / `pytest` (Python)
4. Format: `go fmt ./...` / `ruff check ./src`
5. Commit: Conventional Commits (`feat:`, `fix:`, `refactor:`)
6. Push: `git push -u origin feature/name`
7. GitHub Actions runs CI
8. Create Draft PR, get reviews
9. Merge to `main` only after CI passes

### 11.2 Testing

**Go**: `go test ./...` — Unit tests with standard `testing` package.

**Python**: `pytest` — Tests in `tests/` directory. Key fixtures:
- `conftest.py` — Shared fixtures for Qdrant, PostgreSQL
- `test_agent_logic.py` — Agent logic tests
- `test_llm_responses.py` — LLM response tests
- `test_qdrant.py` — Qdrant operations tests
- `e2e/` — End-to-end tests

### 11.3 Code Generation

```bash
# Generate Go SQL code
cd apps/core && sqlc generate

# Generate protobuf code
make proto

# Generate Python from proto
cd gen/python && python -m grpc_tools.protoc ...
```

---

## 12. Running the Stack Locally

### 12.1 Prerequisites

- Docker & Docker Compose
- Go 1.24+
- Python 3.11+ with `uv`
- Git

### 12.2 Setup

```bash
# 1. Clone and enter directory
git clone <repo-url>
cd iterate_swarm

# 2. Copy environment file
cp .env.example .env
# Edit .env with your secrets (Discord token, Azure OpenAI keys, etc.)

# 3. Start all infrastructure services
make up
# This starts: Temporal, Redpanda, PostgreSQL, Qdrant, Go consumer

# 4. Install Go dependencies
cd apps/core && go mod download

# 5. Install Python dependencies
cd apps/ai && uv sync
```

### 12.3 Running Services

```bash
# Terminal 1: Start Go HTTP server
cd apps/core && go run cmd/server/main.go

# Terminal 2: Start Go Temporal worker
cd apps/core && go run cmd/worker/main.go

# Terminal 3: Start Python AI service
cd apps/ai && uv run python -m src.main
```

### 12.4 Testing

```bash
# Trigger test feedback
curl -X POST http://localhost:3000/demo/feedback \
  -H "Content-Type: application/json" \
  -d '{"text": "The login button is broken", "source": "test", "user_id": "test-user"}'

# View Temporal UI
open http://localhost:8233

# View health
curl http://localhost:3000/health/details
```

### 12.5 Stopping

```bash
make down
```

---

## 13. Common Patterns & Conventions

### 13.1 Error Handling

**Go**: Return errors immediately, wrap with context using `fmt.Errorf("context: %w", err)`.

**Python**: Never raise from node functions. Write errors to `state["error"]` and `state["error_node"]`. Activities return `{"ok": False, "error": "..."}`.

### 13.2 Logging

**Go**: Use `structlog` or the internal `logging.Logger`. Include structured key-value pairs.

**Python**: Use `logging.getLogger(__name__)`. Use `logger.info`, `logger.warning`, `logger.error`.

### 13.3 Configuration

**Go**: Environment variables, loaded at startup.

**Python**: Pydantic models with `.env` file support via `pydantic-settings`.

### 13.4 Naming Conventions

| Language | Convention | Example |
|----------|------------|---------|
| Go | PascalCase (exported), camelCase (unexported) | `FeedbackWorkflow`, `analyzeFeedback` |
| Python | snake_case (functions/variables), PascalCase (classes) | `analyze_feedback`, `class AnomalyAgent` |
| SQL | snake_case | `created_at`, `tenant_id` |
| Proto | snake_case (fields), PascalCase (messages) | `feedback_id`, `AnalyzeFeedbackRequest` |

### 13.5 Protobuf Conventions

- Fields use `snake_case`
- Messages use `PascalCase`
- Services use `PascalCase`
- RPC methods use `PascalCase`
- Enums use `SCREAMING_SNAKE_CASE`

---

## 14. FAQ

### Q: Do I need Azure OpenAI keys?

**A**: Only for Go-based Triage/Spec agents. You can use Ollama defaults for local testing. Set `OLLAMA_BASE_URL` and `OLLAMA_API_KEY` in `.env`.

### Q: Can I run only the AI service?

**A**: Yes — `uv run python -m src.main` starts the gRPC server. It will fail to call Temporal/Redpanda without them, but you can mock those calls.

### Q: Where are Docker images defined?

**A**: `Dockerfile` in `apps/core` and `apps/ai`. `make build` builds them.

### Q: How are migrations handled?

**A**: SQL migration files in `apps/core/migrations/`. Run `make migrate-up` to apply.

### Q: What's the difference between Go agents and Python agents?

**A**: Go agents (TriageAgent, SpecAgent) are stubs that call Azure OpenAI directly. Python agents (AnomalyAgent, InvestorAgent, etc.) are full LangGraph implementations with DSPy optimization, Qdrant memory, and rich output formatting.

### Q: How does the multi-tenant isolation work?

**A**: Every operation includes a `tenant_id` parameter. Qdrant filters by `tenant_id`, PostgreSQL queries filter by `tenant_id`, and Temporal workflows receive `tenant_id` as input.

### Q: What is the "OntologyAI" naming about?

**A**: "OntologyAI" (सारथी) is a Sanskrit word meaning "charioteer" or "guide". It represents the AI agents guiding the founder through their business operations.

### Q: How do I add a new event type?

**A**:
1. Add the event type constant to `apps/core/internal/events/dictionary.go`
2. Add routing rule to `GetRoutingTable()` in `apps/core/internal/workflow/sarthi_router.go`
3. Implement the child workflow (or leave as stub)
4. If Python AI needed, add gRPC method to `proto/ai/v1/agent.proto` and implement in `apps/ai/src/grpc_server.py`

### Q: How do I add a new Python agent?

**A**:
1. Create directory `apps/ai/src/agents/new_agent/`
2. Create `state.py`, `graph.py`, `nodes.py`, `prompts.py`
3. Create activity in `apps/ai/src/activities/run_new_agent.py`
4. Register activity in `apps/ai/src/activities/__init__.py`
5. Register workflow in `apps/ai/src/worker.py` (if Temporal)
6. Add tests in `apps/ai/tests/`

### Q: What is the banned jargon list?

**A**: A list of ~90 corporate buzzwords (leverage, synergy, paradigm, etc.) that agents must avoid. Defined in `apps/ai/src/agents/base.py` as `BANNED_JARGON`. The `validate_tone()` method checks agent output for violations.

---

## File Index

Quick reference to key files by category:

### Go Backend Entry Points
- [`apps/core/cmd/server/main.go`](apps/core/cmd/server/main.go) - HTTP server
- [`apps/core/cmd/worker/main.go`](apps/core/cmd/worker/main.go) - Temporal worker
- [`apps/core/cmd/consumer/main.go`](apps/core/cmd/consumer/main.go) - Redpanda consumer

### Go Workflows
- [`apps/core/internal/workflow/workflow.go`](apps/core/internal/workflow/workflow.go)
- [`apps/core/internal/workflow/sarthi_router.go`](apps/core/internal/workflow/sarthi_router.go)
- [`apps/core/internal/workflow/business_os_workflow.go`](apps/core/internal/workflow/business_os_workflow.go)
- [`apps/core/internal/workflow/onboarding_workflow.go`](apps/core/internal/workflow/onboarding_workflow.go)
- [`apps/core/internal/workflow/activities.go`](apps/core/internal/workflow/activities.go)

### Go API
- [`apps/core/internal/api/handlers.go`](apps/core/internal/api/handlers.go)
- [`apps/core/internal/api/middleware.go`](apps/core/internal/api/middleware.go)
- [`apps/core/internal/api/auth.go`](apps/core/internal/api/auth.go)

### Go Events & Agents
- [`apps/core/internal/events/envelope.go`](apps/core/internal/events/envelope.go)
- [`apps/core/internal/agents/stubs.go`](apps/core/internal/agents/stubs.go)

### Python Entry Points
- [`apps/ai/src/main.py`](apps/ai/src/main.py)
- [`apps/ai/src/grpc_server.py`](apps/ai/src/grpc_server.py)

### Python Agents
- [`apps/ai/src/agents/base.py`](apps/ai/src/agents/base.py)
- [`apps/ai/src/agents/anomaly/graph.py`](apps/ai/src/agents/anomaly/graph.py)
- [`apps/ai/src/agents/anomaly/nodes.py`](apps/ai/src/agents/anomaly/nodes.py)
- [`apps/ai/src/agents/anomaly/state.py`](apps/ai/src/agents/anomaly/state.py)

### Python Memory & Integrations
- [`apps/ai/src/memory/qdrant_ops.py`](apps/ai/src/memory/qdrant_ops.py)
- [`apps/ai/src/integrations/slack.py`](apps/ai/src/integrations/slack.py)

### Python Config
- [`apps/ai/src/config/config_module.py`](apps/ai/src/config/config_module.py)

### Proto Definitions
- [`proto/ai/v1/agent.proto`](proto/ai/v1/agent.proto)

### Infrastructure
- [`docker-compose.yml`](docker-compose.yml)
- [`Makefile`](Makefile)
- [`apps/core/go.mod`](apps/core/go.mod)
- [`apps/ai/pyproject.toml`](apps/ai/pyproject.toml)

---

*This document is maintained as a living reference. Update as the codebase evolves.*