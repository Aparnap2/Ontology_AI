# IterateSwarm — Codebase Map (Simple Edition)

> **Goal**: After reading this, you'll know **which file does what** and **how they connect**. No deep dives, just a map.

---

## The Big Picture: Two Services

```
┌─────────────────────────────────────────────────────────────┐
│  GO BACKEND (apps/core)          PYTHON AI (apps/ai)        │
│  ─────────────────────           ────────────────           │
│  • Receives webhooks             • Runs AI agents           │
│  • Orchestrates workflows        • Stores memories          │
│  • Talks to Temporal             • Exposes gRPC             │
│  • Talks to Discord/GitHub       • Sends Slack messages     │
└─────────────────────────────────────────────────────────────┘
```

**Communication**: Go calls Python via **gRPC** (port 50051). Python runs as a separate process.

---

## Go Backend (`apps/core`) — File Map

### Entry Points (start here to understand flow)
| File | What It Does |
|------|-------------|
| `cmd/server/main.go` | Starts HTTP server on port 3000. All webhooks hit here first. |
| `cmd/worker/main.go` | Starts Temporal worker. Registers all workflows + activities. |

### HTTP Layer (`internal/api/`)
| File | What It Does |
|------|-------------|
| `handlers.go` | **Main router**. Has all the `/webhooks/*`, `/health`, `/demo/*` endpoints. |
| `middleware.go` | JWT auth, CORS, request logging. |
| `auth.go` | GitHub OAuth login → JWT token generation. |

### Workflows (`internal/workflow/`)
| File | What It Does |
|------|-------------|
| `workflow.go` | **FeedbackWorkflow** — the main feedback processing flow. |
| `sarthi_router.go` | **OntologyAIRouter** — routes business events to child workflows. |
| `activities.go` | **All activities** — the actual work units (AnalyzeFeedback, SendDiscordApproval, etc.). |
| `business_os_workflow.go` | Executes SOPs via Python gRPC. |
| `onboarding_workflow.go` | Telegram-based founder onboarding. |

### AI Agents (Go side) (`internal/agents/`)
| File | What It Does |
|------|-------------|
| `stubs.go` | **TriageAgent** + **SpecAgent** stubs. These are simplified — real ones call Azure OpenAI. |

### Events (`internal/events/`)
| File | What It Does |
|------|-------------|
| `envelope.go` | **EventEnvelope** struct — the canonical shape for ALL events flowing through the system. |
| `dictionary.go` | Event type constants (PAYMENT_SUCCESS, USER_SIGNED_UP, etc.). |

### External Integrations (`internal/`)
| File | What It Does |
|------|-------------|
| `temporal/client.go` | Wraps Temporal client (start workflow, signal, health check). |
| `redpanda/client.go` | Wraps Redpanda (Kafka) for publishing/subscribing events. |
| `grpc/client.go` | gRPC client to call Python AI service. |
| `webhooks/handlers.go` | Generic webhook processing logic. |
| `webhooks/payments.go` | Payment-specific webhook handlers (Razorpay, Stripe). |

### Database (`internal/db/`)
| File | What It Does |
|------|-------------|
| `repository.go` | Main repository — CRUD for feedback, issues, idempotency keys. |
| `dbsqlc/` | **Generated code** from sqlc. Don't edit manually. |
| `migrations/` | SQL migration files (001, 002, 003). |

### Web UI (`internal/web/`)
| File | What It Does |
|------|-------------|
| `handler.go` | Admin dashboard routes. |
| `founder_handler.go` | Founder dashboard with SSE live feed. |
| `sse.go` | Server-Sent Events implementation. |
| `templates/` | HTML templates for the web UI. |

### Debug Tools (`internal/debug/`)
| File | What It Does |
|------|-------------|
| `handlers.go` | LiteDebug Console routes. |
| `kafka_browser.go` | Redpanda topic browser. |
| `workflow_inspector.go` | Temporal workflow inspector. |

---

## Python AI Service (`apps/ai`) — File Map

### Entry Point
| File | What It Does |
|------|-------------|
| `src/main.py` | Starts both Temporal worker AND gRPC server. `--mode` flag controls what runs. |

### gRPC Server
| File | What It Does |
|------|-------------|
| `src/grpc_server.py` | Implements `AgentService` + `SOPExecutor`. This is what Go calls via gRPC. |

### AI Agents (`src/agents/`) — Each agent has 5 files
```
src/agents/anomaly/
├── state.py    ← TypedDict defining what data flows through the agent
├── graph.py    ← LangGraph definition (nodes + edges)
├── nodes.py    ← The actual functions (detect_anomaly, send_slack, etc.)
├── prompts.py  ← DSPy predictor definitions (how LLM is prompted)
└── thresholds.py ← Rule-based thresholds (no LLM needed for these)
```

| Agent | Purpose |
|-------|---------|
| `anomaly/` | Detects anomalies in revenue/ops data |
| `investor/` | Generates investor-ready updates |
| `pulse/` | Monitors business KPIs |
| `qa/` | RAG-based Q&A for founders |
| `base.py` | Shared base class with banned-jargon validation |

### Activities (`src/activities/`) — Temporal wrapper around agents
| File | What It Wraps |
|------|--------------|
| `run_anomaly_agent.py` | AnomalyAgent |
| `run_investor_agent.py` | InvestorAgent |
| `run_pulse_agent.py` | PulseAgent |
| `run_qa_agent.py` | QAAgent |
| `run_guardian_watchlist.py` | Guardian watchlist |
| `send_slack_message.py` | Standalone Slack delivery |
| `send_telegram.py` | Standalone Telegram delivery |

### Memory (`src/memory/`)
| File | What It Does |
|------|-------------|
| `qdrant_ops.py` | **Main Qdrant client** — upsert, search, query, delete memories |
| `spine.py` | MemorySpine — multi-layer memory orchestration |
| `rag_kernel.py` | RAG context loading |
| `compressor.py` | Memory compression for long-term storage |

### Integrations (`src/integrations/`)
| File | What It Does |
|------|-------------|
| `slack.py` | **Slack + Telegram delivery** — async Slack webhook, Telegram fallback |
| `stripe.py` | Stripe webhook integration |
| `plaid.py` | Plaid bank statement integration |
| `product_db.py` | Product database client |

### Services (`src/services/`)
| File | What It Does |
|------|-------------|
| `embeddings.py` | Generate embeddings (Ollama/OpenAI) |
| `qdrant.py` | Qdrant service wrapper |
| `relevance_scorer.py` | RAG relevance scoring |
| `tone_filter.py` | Banned jargon check |
| `langfuse_client.py` | LLM observability/tracing |
| `slack_notifier.py` | Slack notification service |
| `crawler_service.py` | Web crawler |
| `sandbox_client.py` | Sandbox execution |
| `weekly_checkin.py` | Weekly check-in logic |

### Config (`src/config/`)
| File | What It Does |
|------|-------------|
| `config_module.py` | Pydantic config models (Temporal, Ollama, Qdrant, etc.) |
| `llm.py` | LLM client config (Azure OpenAI / Ollama / Groq) |
| `llm_guard.py` | LLM output guardrails |
| `event_dictionary.py` | Event type definitions |

### SOPs (`src/sops/`) — Standard Operating Procedures
| File | What It Does |
|------|-------------|
| `base.py` | Base SOP class |
| `registry.py` | SOP registry |
| `bank_statement_ingest.py` | Bank statement ingestion SOP |
| `revenue_received.py` | Revenue received SOP |
| `weekly_briefing.py` | Weekly briefing SOP |

### Workflows (`src/workflows/`) — Temporal workflows (Python side)
| File | What It Does |
|------|-------------|
| `compression_workflow.py` | Memory compression |
| `eval_loop_workflow.py` | Agent evaluation |
| `investor_workflow.py` | Investor update generation |
| `pulse_workflow.py` | Pulse monitoring |
| `qa_workflow.py` | Q&A workflow |
| `self_analysis_workflow.py` | Agent self-analysis |
| `weight_decay_workflow.py` | Memory weight decay |

### LLM Operations (`src/llmops/`)
| File | What It Does |
|------|-------------|
| `eval_loop.py` | Agent evaluation loop |
| `self_analysis.py` | Agent self-analysis (DSPy) |
| `tracer.py` | OpenTelemetry tracing |

### HITL (`src/hitl/`)
| File | What It Does |
|------|-------------|
| `manager.py` | Human-in-the-loop manager |
| `confidence.py` | Confidence scoring |

### Guardian (`src/guardian/`)
| File | What It Does |
|------|-------------|
| `detector.py` | Watchlist pattern detection |
| `insight_builder.py` | Insight generation |
| `watchlist.py` | Watchlist management |

---

## How Data Flows (The Critical Paths)

### Path 1: Feedback Processing
```
Discord/Slack → /webhooks/discord (handlers.go)
             → repository.go (save to DB)
             → redpanda/client.go (publish to "feedback-events")
             → Temporal (FeedbackWorkflow)
             → workflow/activities.go (AnalyzeFeedback)
             → internal/agents/stubs.go (TriageAgent + SpecAgent)
             → workflow/activities.go (SendDiscordApproval)
             → Discord bot (embed with buttons)
             ← User clicks Approve
             → /webhooks/interaction (handlers.go)
             → Temporal (signal)
             → workflow/activities.go (CreateGitHubIssue)
             → GitHub API
```

### Path 2: Business Event Routing
```
Razorpay/Stripe → /webhooks/payments (webhooks/payments.go)
               → events/envelope.go (normalize to EventEnvelope)
               → redpanda/client.go (publish)
               → Temporal (OntologyAIRouter)
               → sarthi_router.go (route by event_type)
               → Child workflow (RevenueWorkflow, CSWorkflow, etc.)
               → If needs AI → grpc/client.go → Python gRPC
               → Python agents → qdrant_ops.py (store memory)
               → integrations/slack.py (send notification)
```

### Path 3: Python AI via gRPC
```
Go: grpc/client.go (calls)
  → Python: grpc_server.py (receives)
  → agents/anomaly/graph.py (runs LangGraph)
  → memory/qdrant_ops.py (read/write memories)
  → integrations/slack.py (send result)
  → Go: grpc/client.go (returns response)
```

---

## The Most Important Files to Know

### For Understanding Flow:
1. `apps/core/cmd/server/main.go` — entry point, see all routes
2. `apps/core/internal/api/handlers.go` — all HTTP endpoints
3. `apps/core/internal/workflow/workflow.go` — main feedback workflow
4. `apps/core/internal/workflow/sarthi_router.go` — event routing
5. `apps/ai/src/grpc_server.py` — gRPC entry point for Python

### For Modifying AI Behavior:
1. `apps/ai/src/agents/base.py` — shared agent logic (banned jargon, memory writing)
2. `apps/ai/src/agents/anomaly/graph.py` — anomaly agent graph
3. `apps/ai/src/agents/anomaly/nodes.py` — node implementations
4. `apps/ai/src/memory/qdrant_ops.py` — memory operations

### For Adding New Features:
1. `apps/core/internal/events/dictionary.go` — add new event type
2. `apps/core/internal/workflow/sarthi_router.go` — add routing rule
3. `proto/ai/v1/agent.proto` — add gRPC method
4. `apps/ai/src/grpc_server.py` — implement gRPC method

---

## Quick Reference: What Calls What

```
handlers.go
  ├── repository.go (DB)
  ├── temporal/client.go (start workflow)
  ├── redpanda/client.go (publish event)
  └── grpc/client.go (call Python)

workflow.go (FeedbackWorkflow)
  └── activities.go
      ├── agents/stubs.go (TriageAgent, SpecAgent)
      ├── discord (send approval)
      └── github (create issue)

sarthi_router.go
  └── Child workflows (RevenueWorkflow, CSWorkflow, etc.)
      └── activities.go
          └── grpc/client.go (call Python)

grpc_server.py
  ├── agents/anomaly/graph.py
  ├── agents/investor/graph.py
  ├── agents/pulse/graph.py
  ├── agents/qa/graph.py
  └── integrations/slack.py
      └── memory/qdrant_ops.py
```

---

## Directory Structure Summary

```
apps/core/
├── cmd/
│   ├── server/main.go      ← HTTP server entry
│   └── worker/main.go      ← Temporal worker entry
└── internal/
    ├── api/                ← HTTP handlers
    ├── workflow/           ← Temporal workflows + activities
    ├── agents/             ← Go AI agents (stubs)
    ├── events/             ← EventEnvelope definition
    ├── db/                 ← Database layer
    ├── temporal/           ← Temporal client wrapper
    ├── redpanda/           ← Redpanda client wrapper
    ├── grpc/               ← gRPC client to Python
    ├── web/                ← Web UI handlers
    ├── webhooks/           ← Webhook processors
    └── debug/              ← Debug tools

apps/ai/
├── src/
│   ├── main.py             ← Entry point (Temporal + gRPC)
│   ├── grpc_server.py      ← gRPC server (what Go calls)
│   ├── activities/         ← Temporal activity wrappers
│   ├── agents/             ← LangGraph AI agents
│   │   ├── base.py         ← Shared agent logic
│   │   ├── anomaly/        ← Anomaly detection agent
│   │   ├── investor/       ← Investor update agent
│   │   ├── pulse/          ← KPI monitoring agent
│   │   └── qa/             ← Q&A agent
│   ├── memory/             ← Qdrant memory operations
│   ├── integrations/       ← Slack, Stripe, Plaid
│   ├── services/           ← Embeddings, Langfuse, etc.
│   ├── config/             ← Pydantic config models
│   ├── sops/               ← Standard Operating Procedures
│   ├── workflows/          ← Python Temporal workflows
│   ├── llmops/             ← DSPy, evaluation
│   ├── hitl/               ← Human-in-the-loop
│   └── guardian/           ← Watchlist detection
└── tests/                  ← Test suite
```

---

## Common Tasks & Which Files to Touch

| Task | Files to Modify |
|------|----------------|
| Add new HTTP endpoint | `internal/api/handlers.go` |
| Add new event type | `events/dictionary.go` + `workflow/sarthi_router.go` |
| Modify feedback flow | `internal/workflow/workflow.go` + `activities.go` |
| Modify Go AI agent | `internal/agents/stubs.go` |
| Modify Python AI agent | `apps/ai/src/agents/{agent}/graph.py` + `nodes.py` |
| Add new Python agent | Create `apps/ai/src/agents/new_agent/` with state.py, graph.py, nodes.py, prompts.py |
| Add gRPC method | `proto/ai/v1/agent.proto` + `apps/ai/src/grpc_server.py` |
| Modify memory storage | `apps/ai/src/memory/qdrant_ops.py` |
| Add Slack message format | `apps/ai/src/integrations/slack.py` |
| Add SOP | `apps/ai/src/sops/` + register in `registry.py` |
