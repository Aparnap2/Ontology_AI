# OntologyAI — Palantir-Style Ontology for Small Businesses

> OntologyAI builds a live Ontology of a small business from its existing tools, and lets AI specialists query and act on it — with every consequential action gated by human approval.

[![Tests](https://img.shields.io/badge/tests-994%2B%20passing-brightgreen)](#)
[![Architecture](https://img.shields.io/badge/architecture-SSE%20%2B%20Specialist-blue)](#)
[![Go](https://img.shields.io/badge/Go-1.24-blue?logo=go)](#)
[![Python](https://img.shields.io/badge/Python-3.13-green?logo=python)](#)

---

## V4.1 Architecture: Five Canonical Specialists

Browser connects via HTMX SSE. Go dispatches to Temporal in goroutines. Five Python specialist agents handle each domain.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              Browser (HTMX + SSE)                                     │
│  ┌───────────────────┐  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ command_chat.html  │  │ command_approvals│  │ command_operating│                    │
│  │ hx-ext="sse"       │  │ Approve / Hold   │  │ -layer.html      │                    │
│  │ sse-connect="/api/ │  │ → Temporal Signal│  │ Prepared Brief   │                    │
│  │  command/chat/     │  └────────┬─────────┘  │ Pending Decisions│                    │
│  │  events"           │           │              │ Active Roles     │                    │
│  └────────┬───────────┘           │              └────────┬─────────┘                   │
│           │ SSE event:chat        │ POST approve/hold     │ SSE event:mission          │
└───────────┼───────────────────────┼───────────────────────┼─────────────────────────────┘
            │                       │                       │
            ▼                       ▼                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                         Go Core (Fiber v2)                                            │
│  Handler struct: SSEHub (typed fan-out), temporal.Client, WaitGroup                  │
│  specialistRoutes map: @mention → workflow + displayName                             │
│  goroutine dispatch + tryBroadcast() for SSE push                                    │
│  API Routes: chat/events, chat/send, approvals/:id/approve,                         │
│              alert-lineage, operating-layer, mission-state, dashboard/*              │
└──────────────────────────────────────────────────────────────────────────────────────┘
              │ Temporal                         │ SQL / POST
              ▼                                  ▼
┌──────────────────────────────┐    ┌──────────────────────────────────────────────┐
│  Temporal Server              │    │  PostgreSQL                                    │
│  Task Queue:                  │    │  Tables: mission_states, planned_actions,     │
│  TRACKGUARD-MAIN-QUEUE        │    │  chat_messages, agent_traces                  │
│  Workflows: ChiefOfStaff,     │    │                                                │
│  FPA, GrowthAnalytics,        │    └──────────────────────────────────────────────┘
│  Reliability, Comms           │
│  Signals: "hitl-approval"     │
└───────┬──────────────────────┘
        │ Temporal activity dispatch
        ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    Python AI Worker (Temporal SDK + LangGraph)                         │
│  LangGraph Agent Graphs: FinanceGraph, DataGraph, OpsGraph, CommsGraph                │
│  LLM Provider: Azure AI Foundry / Groq / Ollama (auto-detected)                       │
│  Structured Output: Pydantic v2 SpecialistResponse schema with Literal constraints     │
│  5 canonical specialists enforced via Literal types                                    │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Chat Flow: @mention → Specialist Workflow → SSE Result

```
User types "@finance Q3 revenue?" → HTMX POST /api/command/chat/send
  → Go Handler extracts @mentions → matches in specialistRoutes map
  → Broadcasts user bubble via SSE (immediate)
  → go func() with sync.WaitGroup:
      → tryBroadcast() → "🤔 Thinking..." → SSE
      → Temporal ExecuteWorkflow("FPAWorkflow", input)
      → Python workflow → LangGraph agent → LLM result
      → run.Get(ctx, &result) → renderChatBubble() → tryBroadcast() → SSE
```

### Specialist Route Map

```go
var specialistRoutes = map[string]specialistRoute{
    "@sarthi":  {"ChiefOfStaffWorkflow", "Chief of Staff"},
    "@agent":   {"ChiefOfStaffWorkflow", "Chief of Staff"},
    "@qa":      {"ChiefOfStaffWorkflow", "Chief of Staff"},
    "@ask":     {"ChiefOfStaffWorkflow", "Chief of Staff"},
    "@finance": {"FPAWorkflow", "FP&A"},
    "@fpa":     {"FPAWorkflow", "FP&A"},
    "@data":    {"GrowthAnalyticsWorkflow", "Growth Analytics"},
    "@growth":  {"GrowthAnalyticsWorkflow", "Growth Analytics"},
    "@ops":     {"ReliabilityWorkflow", "Reliability & Delivery"},
    "@comms":   {"CommsWorkflow", "Communications"},
}
```
- O(1) map lookup, 10 aliases → 5 canonical workflows.
- Backward compat aliases maintained: `@sarthi`, `@agent`, `@qa`, `@ask` all route to ChiefOfStaff.
- V3 legacy aliases (`qa_workflow` → `ChiefOfStaffWorkflow`, `finance_workflow` → `FPAWorkflow`, etc.) preserved as re-exports with deprecation warnings.

### Key V4.1 Decisions

| Decision | Benefit |
|----------|---------|
| **Five canonical specialists** | Chief of Staff, FP&A, Growth Analytics, Reliability & Delivery, Communications — exactly 5, no Hiring |
| **SpecialistResponse Literal schema** | Pydantic enforces valid specialist names and workflow names at the type level |
| **Backward-compat workflow re-exports** | `QAWorkflow`, `FinanceWorkflow`, `DataWorkflow`, `OpsWorkflow` → new canonical names with deprecation |
| **OntologyAI branding** | All page titles, display names, and documentation use "OntologyAI" not "OntologyAI" |
| **API Mission State endpoints** | `GET /api/mission-state` and `POST /api/mission-state` for machine-readable JSON (Python AI ↔ Go Core) |

---

## V4.1 New: Operating Layer

### Agent Authority Manifest
5 specialist agents + 1 correlation agent defined in `apps/ai/src/agents/authority_manifest.py`:

| Agent | Domain | Escalation Tier | Allowed Tools |
|-------|--------|-----------------|---------------|
| **Chief of Staff** | cofounder | approve | draft_investor_update |
| **FP&A** | finance | review | pause_failed_payment_retry |
| **Growth Analytics** | bi | auto | draft_investor_update |
| **Reliability & Delivery** | ops | auto | flag_churn_risk_customer, schedule_customer_checkin |
| **Communications** | ops | auto | draft_investor_update |
| **Correlation Agent** | correlation | review | (none — alert-only) |

### SpecialistResponse Schema
All 5 canonical specialist responses validated via Pydantic `Literal`:

```python
class SpecialistResponse(BaseModel, strict=True):
    specialist: Literal[
        "Chief of Staff", "FP&A", "Growth Analytics",
        "Reliability & Delivery", "Communications"
    ]
    workflow_name: Literal[
        "ChiefOfStaffWorkflow", "FPAWorkflow",
        "GrowthAnalyticsWorkflow", "ReliabilityWorkflow", "CommsWorkflow"
    ]
    summary: str
    detailed_response: str
    requires_hitl: bool = False
    planned_action_id: Optional[str] = None
    mission_state_patch: Optional[dict] = None
    citations: list[str] = []
    followups: list[str] = []
```

### Alert Lineage
Every `GuardianMessage` carries an `AlertLineage` schema (`apps/ai/src/schemas/guardian.py`):
- `pattern_id`, `source_metrics`, `mission_context`, `raise_timeline_risk`, `suggested_tool_ids`, `owner_agent`

### MissionState Explainability
Fields via migration 005:
- `last_update_reason` — why this write happened
- `last_changed_fields` — which fields were modified (JSONB)
- `active_agent_roles` — derived from authority manifest (JSONB)

### Brief Generator
`apps/ai/src/session/brief_generator.py` — `generate_prepared_brief()`:
- 2-sentence LLM summary auto-triggered on MissionState write
- Persists to `prepared_brief` field

### StrategyDelta Audit Trail
`apps/ai/src/agents/cofounder/curator.py` — structured audit log for curator confidence updates.

---

## Command Center Dashboard

15+ HTMX-driven screens:

| Dashboard Panel | Route | Auto-refresh |
|----------------|-------|-------------|
| **Chat Panel** | `POST /api/command/chat/send` + SSE `GET /api/command/chat/events` | SSE push (instant) |
| **Approvals Queue** | `GET /api/command/approvals` + `POST approve/:id` | Poll + Signal |
| **Mission State** | `GET /api/command/mission-state` | On load |
| **Status Bar** | `GET /api/command/status` | 10s |
| **KPI Cards** | `GET /api/command/kpis` | 15s |
| **Watchlist** | `GET /api/command/watchlist` | 30s |
| **Timeline** | `GET /api/command/timeline` | 15s |
| **Agent Fleet** | `GET /api/command/agent-fleet` | 30s |
| **Chart Data** | `GET /api/command/chart-data` (JSON) | On demand |
| **Dashboard Heartbeat** | `GET /api/command/events` (SSE) | Push |
| **Alert Lineage** | `GET /api/command/alert-lineage` | On load |
| **Operating Layer** | `GET /api/command/operating-layer` | On load |
| **Mission SSE** | `GET /api/command/mission/events` (SSE) | Push |
| **HITL SSE** | `GET /api/command/hitl/events` (SSE) | Push |
| **Session SSE** | `GET /api/command/session/events` (SSE) | Push |

---

## Core Components

### Specialist Agent System
5 workflow types dispatched from the Go core via Temporal:
- **Chief of Staff (@sarthi/@agent/@qa/@ask)** — General Q&A, founder strategic thinking partner
- **FP&A (@finance/@fpa)** — MRR/burn analysis, anomaly detection via FinanceGraph
- **Growth Analytics (@data/@growth)** — Query, transform, aggregate via DataGraph
- **Reliability & Delivery (@ops)** — Deploy, monitor, alert via OpsGraph
- **Communications (@comms)** — Draft, summarize, tailor stakeholder communications via CommsGraph

### HITL with Temporal Signals
- AI proposes action → `planned_actions` row created with `status=pending`
- Temporal workflow reaches `AwaitWithTimeout("hitl-approval", 48h)`
- User clicks Approve → POST → `SignalWorkflow(ctx, id, "hitl-approval", true)`
- Workflow unblocks, execution continues

### Tool Calling Surface (ToolRegistry)
4 tool functions defined as `ToolDef` entries in a global `TOOL_REGISTRY`, wired to HITL manager:

| Tool | Tier | Trigger | Action |
|------|------|---------|--------|
| `pause_failed_payment_retry` | review | FG-05 (3+ failed payments) | Pause Stripe retry (real API + MOCK_MODE) |
| `draft_investor_update` | approve | Schedule | Load MissionState + LLM draft email |
| `schedule_customer_checkin` | auto | FG-03, BG-04 | Slack chat_postMessage via SlackClient |
| `flag_churn_risk_customer` | auto | BG-06, BG-04 | Update churn_risk_users in MissionState |

Tools auto-register via `register_tool(ToolDef(...))` on import. `get_tools_for_tier()` and `get_tools_for_patterns()` enable pattern-driven tool suggestion.

### ACE Reflector Loop (Slack Integration)
- `SlackClient` extended with `SocketModeClient` (WebSocket, no Bolt)
- Button interactions routed in `slack_buttons.py` (5 action types)
- ACE loop: button click → `score_from_button()` (Reflector) → `update_strategy_confidence()` (Curator)

### MissionState Write Path
- **Python AI** compiles operational state (MRR, burn, health, signals)
- **POST** to `/api/mission-state` → **PostgreSQL** (`mission_states` table)
- **GET** → Go templates → HTML (dashboard)
- Fields: `prepared_brief`, `pending_decisions`, `last_updated_by`
- Explainability: `last_update_reason`, `last_changed_fields`, `active_agent_roles`
- Auto-generated brief: `generate_prepared_brief()` on every MissionState write

### SSE Chat System
- HTMX `hx-ext="sse"` declaratively subscribes to SSE stream
- Server sends `event: chat` with HTML fragments as data payload
- **SSEHub** (`sse_hub.go`): Event-type filtered fan-out hub with per-subscriber channels (buffer 64)
  - `Subscribe(tenantID, eventTypes...)` — typed subscriptions (chat, mission, hitl, session)
  - `Broadcast(tenantID, SSEEvent)` — delivers only to matching subscribers

### Goroutine Safety Patterns
- `sync.WaitGroup` for graceful shutdown tracking of in-flight workflow dispatches
- Context cancellation via `c.Context().Done()` in SSE handlers
- 5-minute context timeout merged from request context for workflow dispatch
- `select { case ch <- msg: default: log }` prevents goroutine pile-up

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Go Core** | Go 1.24 + Fiber v2 + HTMX |
| **Python AI** | Python 3.13 + Temporal SDK + LangGraph + DSPy |
| **Workflow Engine** | Temporal (1.39 SDK) |
| **LLM** | Azure AI Foundry / Groq / Ollama (auto-detected via OpenAI SDK) |
| **Structured Output** | Pydantic v2 (strict mode) with Literal constraints |
| **Relational DB** | PostgreSQL (MissionState, chat, approvals, traces) |
| **Vector Store** | Qdrant (agent memory, semantic search) |
| **Cache** | Redis (session state, working memory) |
| **Observability** | Langfuse v4 (LLM tracing) |
| **Config** | Env-only via pydantic-settings — zero hardcoded secrets |

---

## Test Coverage (994+ Passing — Go Build Clean)

| Suite | Tests | Status |
|-------|-------|--------|
| Python Unit Tests | 994 | ✅ All passing |
| Go HTMX Web Handlers | 74+ | ✅ All passing |
| Go Build | Clean | ✅ Binary compiles successfully |
| E2E Smoke Test | 9/9 | ✅ Real Docker + real LLM (Groq) |
| DB Tests | 🟡 Skip | Requires PostgreSQL container |
| Webhook Tests | 🟡 Skip | Requires Redpanda container |

---

## Project Structure

```
apps/
  core/              # Go Modular Monolith
    cmd/
      server/        # HTTP server entrypoint
      worker/        # Temporal worker entrypoint
    internal/
      web/           # HTTP handlers (Fiber + HTMX + SSE)
        handler.go       # All endpoints, @mention routing (10 aliases, 5 workflows)
        sse.go           # SSE handler with DB polling
        command_center_test.go  # 74+ tests including V4.1 branding/routing/mission-state
        templates/
          command_center.html       # Main dashboard
          partials/                 # HTMX partials (13+ panels)
      agents/        # Go agent definitions
      config/        # LLM configuration
      db/            # sqlc generated code
      database/      # Connection utilities
      temporal/      # Temporal client (SignalWorkflow, ExecuteWorkflow)
      workflow/      # Temporal workflows & stubs
    sqlc.yaml        # sqlc configuration
  ai/                # Python AI Worker
    src/
      agents/
        comms/       # V4.1 — CommsGraph (real implementation)
        base/        # Abstract agent class, tool framework
        tools/       # ToolRegistry + 4 ToolDef implementations
      workflows/
        chief_of_staff_workflow.py   # @workflow.defn(name="ChiefOfStaffWorkflow")
        fpa_workflow.py              # @workflow.defn(name="FPAWorkflow")
        growth_analytics_workflow.py # @workflow.defn(name="GrowthAnalyticsWorkflow")
        reliability_workflow.py      # @workflow.defn(name="ReliabilityWorkflow")
        comms_workflow.py            # @workflow.defn(name="CommsWorkflow")
        qa_workflow.py               # Backward-compat → ChiefOfStaffWorkflow
        finance_workflow.py          # Backward-compat → FPAWorkflow
        data_workflow.py             # Backward-compat → GrowthAnalyticsWorkflow
        ops_workflow.py              # Backward-compat → ReliabilityWorkflow
      schemas/
        specialist_response.py       # V4.1 — 9-field schema with Literal constraints
      worker.py                     # Registers all 12 workflows, 13 activities
    tests/           # 994+ passing
```

---

## Quick Start

```bash
# Start infrastructure
docker start ontology_ai-postgres ontology_ai-qdrant ontology_ai-redis

# Run Python tests
cd apps/ai && uv run pytest tests/ -v

# Run Go web handler tests
cd apps/core && go test ./internal/web/... -v

# Start Python Temporal worker
cd apps/ai && uv run python -m src.worker

# Start Go server
cd apps/core && go run cmd/server/main.go

# Verify SSE chat works
# Open http://localhost:8080/command
# Type "@finance What's my current burn?" → see "🤔 Thinking..." → see answer
```

---

## Migration Notes (OntologyAI → OntologyAI V4.1)

- **Branding**: "OntologyAI" → "OntologyAI" across all page titles, display names, and documentation
- **Specialist roster**: 6 specialists → 5 canonical specialists (Hiring removed)
- **Workflow renames**: QAWorkflow → ChiefOfStaffWorkflow, FinanceWorkflow → FPAWorkflow, DataWorkflow → GrowthAnalyticsWorkflow, OpsWorkflow → ReliabilityWorkflow
- **Backward compat**: All legacy aliases re-exported with deprecation warnings
- **SpecialistResponse**: New Pydantic schema enforces valid specialist names and workflow names via Literal types
- **API endpoints**: `GET /api/mission-state` and `POST /api/mission-state` added for Python AI ↔ Go Core integration

---

## Development Principles

1. **Decision latency** — every feature must shorten the time between signal and action
2. **SSE-first** — push over pull; real-time streams over polling
3. **Exception quality** — high trust beats high volume; reduce false positives
4. **Founder cognition** — fewer, sharper, more actionable messages
5. **Trust gradually** — copilot → workflow assistant → semi-autonomous → autonomous
6. **No hardcoded secrets** — env-only configuration, centralized in `config/database.py`
7. **Composition over inheritance** — new packages import and nest existing schemas, never modify them
8. **Deterministic core** — finance, guardrails, and forecasting are pure Python with zero LLM calls
9. **Explainability** — every MissionState write carries reason, changed fields, and active agent roles
10. **Authority boundaries** — agents declare permissions in authority_manifest; tools check allowlists
