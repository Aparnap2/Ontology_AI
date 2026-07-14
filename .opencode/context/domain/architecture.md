# IterateSwarm Architecture

> **Purpose**: Document the current system architecture — Go modular monolith for core, Python AI worker for agents, Temporal for orchestration, PostgreSQL for state.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (HTMX + SSE + Chart.js)                                │
│  GET /command → command_center.html                             │
└───────────────────┬─────────────────────────────────────────────┘
                    │ hx-get / hx-post / hx-ext="sse"
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Go Core (apps/core/) — Fiber v2 HTTP Server                    │
│                                                                  │
│  ┌─────────────────────┐  ┌────────────────────────────────┐   │
│  │  handler.go          │  │  SSE (sse.go + handler.go)      │   │
│  │  • Dashboard, Feed   │  │  • SetBodyStreamWriter pattern  │   │
│  │  • HITL Queue (crud) │  │  • APICommandChatEvents (chat)  │   │
│  │  • Agent Map, Tasks  │  │  • APICommandEvents (dash)      │   │
│  │  • Config, Telemetry │  │  • AgentEvent polling (sse.go)  │   │
│  │  • Command Center:   │  │                                  │   │
│  │    Status, KPIs,     │  │  Temporal Client (temporal/)    │   │
│  │    MissionState,     │  │  • ExecuteWorkflow               │   │
│  │    Watchlist,        │  │  • SignalWorkflow (HITL)        │   │
│  │    Timeline,         │  │                                  │   │
│  │    Approvals, Chat   │  │  DB (database/ + db/)           │   │
│  │  • @mention routing  │  │  • sqlc generated queries       │   │
│  └─────────────────────┘  │  • Raw SQL via lib/pq             │   │
│                            └────────────────────────────────┘   │
└───────────────────┬─────────────────────────────────────────────┘
                    │ Temporal ExecuteWorkflow / SignalWorkflow
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Temporal Server                                                │
│  Task Queue: TRACKGUARD-MAIN-QUEUE                              │
│  Orchestrates Go activities + Python workflows                  │
└───────────────────┬─────────────────────────────────────────────┘
                    │ Worker picks up workflow tasks
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Python AI Worker (apps/ai/)                                    │
│                                                                  │
│  ┌─────────────────────┐  ┌────────────────────────────────┐   │
│  │  Specialist Agents   │  │  LangGraph Agent Graphs        │   │
│  │                      │  │  • FinanceGraph (finance)      │   │
│  │  FinanceWorkflow     │  │  • DataGraph (data)            │   │
│  │  DataWorkflow        │  │  • OpsGraph (ops)              │   │
│  │  OpsWorkflow         │  │  • (Comms, Hiring, QA — TBD)   │   │
│  │  CommsWorkflow (TBD) │  │                                  │   │
│  │  HiringWorkflow(TBD) │  │  LLM Provider: Groq (Ollama)    │   │
│  │  QAWorkflow (TBD)    │  │  Structured Output: instructor  │   │
│  └─────────────────────┘  └────────────────────────────────┘   │
└───────────────────┬─────────────────────────────────────────────┘
                    │ Writes mission_state, planned_actions, agent_traces
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL                                                      │
│  Tables: mission_state, planned_actions, agent_traces,          │
│          chat_messages, hitl_queue, agent_outputs               │
└─────────────────────────────────────────────────────────────────┘
```

> **Architecture decisions documented in:** [ADR-001: Sarthi v4.0 Architecture Evolution](../adr/001-sarthi-v4-architecture-evolution.md)

## Key Design Decisions

### Go Modular Monolith (apps/core/)

- **Framework**: Fiber v2 (`github.com/gofiber/fiber/v2`)
- **HTMX**: Server-rendered HTML partials with `hx-trigger`, `hx-swap`, `hx-target`
- **SSE**: Fiber v2 `SetBodyStreamWriter` + `*bufio.Writer` for streaming (see [sse.go](/apps/core/internal/web/sse.go))
- **Templates**: Embedded via `//go:embed` in `internal/web/templates/`
- **Database**: Direct `database/sql` + `lib/pq` (not sqlc for command center — raw SQL queries)
- **Temporal SDK**: `go.temporal.io/sdk` v1.39.0 for workflow dispatch and signaling

### Python AI Worker (apps/ai/)

- **SDK**: `temporalio` >= 1.11.0 for workflow/activity definitions
- **LangGraph**: `langgraph>=1.0.0` for agent state graphs
- **Prompt Optimization**: `dspy-ai>=3.1.3`
- **Structured Outputs**: `pydantic>=2.0.0` (via instructor)
- **HTTP**: `httpx>=0.28.0` (never `requests`)
- **LLM Provider**: OpenAI-compatible SDK (Groq, Azure AI Foundry, Ollama)
- **Vector DB**: `qdrant-client>=1.16.0`
- **Session Store**: `redis>=5.0.3`

### Chat Flow Architecture

1. User types `@finance` in HTMX form (command_chat.html)
2. POST to `/api/command/chat/send` → `APICommandChatSend(h)`
3. `extractMentions()` + `specialistRoutes` map → workflow type + display name
4. "🤔 Thinking..." via `tryBroadcast()` → SSE channel
5. Temporal `ExecuteWorkflow` dispatched in background goroutine
6. Python workflow completes → agent.invoke activity → Groq LLM
7. Result rendered as HTML bubble via `renderChatBubble()`
8. SSE sends `event: chat` → HTMX `sse-swap="chat"` appends to DOM

```
@mention routing (handler.go:1242-1257):
  @sarthi / @agent / @qa / @ask → QAWorkflow  → "Sarthi"
  @finance                        → FinanceWorkflow → "Finance"
  @data                           → DataWorkflow → "Data"
  @ops                            → OpsWorkflow → "Ops"
  @comms                          → CommsWorkflow → "Comms" (TBD)
  @hiring                         → HiringWorkflow → "Hiring" (TBD)
```

### 3-Tier HITL (Human-in-the-Loop)

| Tier | Description | Behavior |
|------|-------------|----------|
| **Auto** | Low-risk, high-confidence | Executes immediately, logs to agent_traces |
| **Notify** | Medium risk | Flags in dashboard timeline, no block |
| **Block** | High risk / requires approval | Writes to `planned_actions`, shows in approval queue |

- Approval action → `APICommandApprovalAction` → `SignalWorkflow(workflowID, "hitl-approval", true)`
- HITL gates block Python workflow execution until human approves

### Mission State System

<<<<<<< Updated upstream
- **Python AI layer** writes compiled operational state to `mission_state` table
- **Go handlers** read `mission_state` for dashboard KPIs, signals, health score
- Fields: mrr, burn_rate, runway_days, burn_alert, burn_severity, trust_score, churn_rate, error_spike, active_alerts, founder_focus
=======
- **Python AI layer** writes compiled operational state to `mission_states` table (migration 004 reconciled schema drift `mission_state` → `mission_states`)
- **Go handlers** read `mission_states` for dashboard KPIs, signals, health score
- Core fields: mrr, burn_rate, runway_days, burn_alert, burn_severity, trust_score, churn_rate, error_spike, active_alerts, founder_focus
- **New cognitive offloading fields (2026-06-28):**
  - `prepared_brief` — LLM-generated brief prepopulated for founder context before a decision
  - `pending_decisions` — JSONB array of open decisions awaiting founder action
  - `last_updated_by` — Which agent/specialist last wrote to MissionState (traceability)
- **Explainability fields (migration 005):**
  - `last_update_reason` — why this write happened (string)
  - `last_changed_fields` — which fields were modified (JSONB array)
  - `active_agent_roles` — derived from authority manifest (JSONB array)
- **Auto-generated brief:** `generate_prepared_brief()` in `apps/ai/src/session/brief_generator.py` runs on every MissionState write — 2-sentence LLM summary using max_tokens=80, temperature=0.3
>>>>>>> Stashed changes
- Context budget: 800 tokens max for mission state compilation

### Agent Authority Manifest

New in 2026-06-28. Declarative capability/escalation registry for all 5 agents.

- **Location**: `apps/ai/src/agents/authority_manifest.py`
- **Schema**: `AgentAuthority` Pydantic model with fields: agent_name, role, voice, domain, can_emit_alerts, can_execute_tools, allowed_tool_ids, escalation_tier, triggers, writes_mission_fields
- **5 agents defined**: Sarthi (cofounder), Sarthi·Finance, Sarthi·Data, Sarthi·Ops, Correlation Agent
- **Helper functions**: `get_authority(agent_name)`, `can_execute_tool(agent_name, tool_id)`, `get_writes_mission_fields(agent_name)`
- **Used by**: HITL routing, tool execution guards, MissionState write-path validation

### Alert Lineage

New in 2026-06-28. Every `GuardianMessage` carries an `AlertLineage` schema attached.

- **Schema**: `AlertLineage` Pydantic model in `apps/ai/src/schemas/guardian.py`
- **Fields**: pattern_id, source_metrics, mission_context, raise_timeline_risk, suggested_tool_ids, owner_agent
- **Dashboard panel**: `GET /api/command/alert-lineage` → `command_alert_lineage.html`
- **Go handler**: `APICommandAlertLineage` in `handler.go`

### MissionState Explainability

New in 2026-06-28. Migration 005 adds explainability fields to `mission_states`.

- **Fields**: `last_update_reason` (TEXT), `last_changed_fields` (JSONB), `active_agent_roles` (JSONB)
- **Purpose**: Full audit trail for every MissionState write — why it happened, what changed, who was active
- **Dashboard panel**: `GET /api/command/operating-layer` → `command_operating_layer.html`
- **Go handler**: `APICommandOperatingLayer` in `handler.go`

### Brief Generator

New in 2026-06-28. Auto-generated 2-sentence business summary on every MissionState write.

- **Location**: `apps/ai/src/session/brief_generator.py`
- **Function**: `generate_prepared_brief(tenant_id)` — loads MissionState, generates brief via LLM, persists to `prepared_brief` field
- **LLM config**: `chat_completion()` with max_tokens=80, temperature=0.3
- **Template**: "Write 2 plain-English sentences summarising this business state. Runway: {runway_days}d | Burn alert: {burn_alert} | Churn rate: {churn_rate} | Active alerts: {active_alerts} | MRR trend: {mrr_trend} | Trust score: {trust_score}."
- **Non-blocking**: If LLM fails, MissionState write still succeeds (brief is optional)

### StrategyDelta (Audit Trail)

New in 2026-06-28. Structured audit trail for curator confidence updates.

- **Location**: `apps/ai/src/agents/cofounder/curator.py`
- **Schema**: `StrategyDelta` Pydantic model with fields: strategy_id, old_confidence, new_confidence, trigger_type, trigger_alert_id, delta, timestamp
- **Write path**: PostgreSQL first, falls back to `/tmp/strategy_audit.jsonl` if DB unavailable
- **Purpose**: Traceable, queryable, debuggable confidence changes for curator strategies

### Goroutine Safety

- `sync.WaitGroup` tracks dispatched workflows
- Context cancellation via `c.Context().Done()` in SSE handlers
- Non-blocking `tryBroadcast()` with `select/default` on buffered channel

### Key Files

| File | Role |
|------|------|
| `/apps/core/internal/web/handler.go` | All HTTP handlers, @mention routing, SSE broadcasting, alert-lineage, operating-layer |
| `/apps/core/internal/web/sse.go` | Legacy SSE handler with DB polling |
| `/apps/core/internal/web/sse_hub.go` | SSEHub fan-out hub with event-type filtering (Subscribe/Broadcast) |
| `/apps/core/internal/temporal/client.go` | Temporal client wrapper (SignalWorkflow, ExecuteWorkflow) |
| `/apps/core/internal/workflow/stubs.go` | DiscordApprovalInput type (cleaned) |
| `/apps/core/internal/db/schema/command_center.sql` | Schema: mission_states, planned_actions, agent_traces, chat_messages |
| `/apps/core/internal/db/migrations/005_mission_state_explainability.sql` | Migration: last_update_reason, last_changed_fields, active_agent_roles |
| `/apps/core/internal/web/templates/command_center.html` | Main dashboard template (HTMX + SSE + Chart.js) |
| `/apps/core/internal/web/templates/partials/command_chat.html` | Chat panel with SSE extension |
| `/apps/core/internal/web/templates/partials/command_approvals.html` | Approval queue UI (approve/hold) |
<<<<<<< Updated upstream
| `/apps/core/internal/web/command_center_test.go` | Test suite (52 tests covering chat, approvals, mission state, SSE) |
| `/apps/ai/src/workflows/finance_workflow.py` | Finance specialist Temporal workflow |
| `/apps/ai/src/workflows/data_workflow.py` | Data specialist Temporal workflow |
| `/apps/ai/src/workflows/ops_workflow.py` | Ops specialist Temporal workflow |
=======
| `/apps/core/internal/web/templates/partials/command_alert_lineage.html` | Alert lineage panel (pattern, metrics, risk, suggested tools) |
| `/apps/core/internal/web/templates/partials/command_operating_layer.html` | Operating layer panel (brief, last writer, pending decisions, active roles) |
| `/apps/core/internal/web/command_center_test.go` | Test suite (19+ command center tests, part of 74+ web tests) |
| `/apps/ai/src/agents/authority_manifest.py` | Agent authority/permissions registry (5 agents) |
| `/apps/ai/src/agents/tools/__init__.py` | ToolRegistry with ToolDef dataclass, auto-registration, tier queries |
| `/apps/ai/src/agents/tools/pause_payment_retry.py` | Tool: Pause Stripe retry (tier: review) |
| `/apps/ai/src/agents/tools/draft_investor_update.py` | Tool: Draft investor email (tier: approve) |
| `/apps/ai/src/agents/tools/schedule_customer_checkin.py` | Tool: Schedule at-risk checkin (tier: auto) |
| `/apps/ai/src/agents/tools/flag_churn_risk.py` | Tool: Flag churn risk segment (tier: auto) |
| `/apps/ai/src/agents/cofounder/curator.py` | Curator with StrategyDelta audit trail |
| `/apps/ai/src/session/brief_generator.py` | Auto-generated 2-sentence business brief on MissionState write |
| `/apps/ai/src/session/mission_state.py` | MissionState dataclass with explainability fields |
| `/apps/ai/src/schemas/guardian.py` | GuardianMessage with AlertLineage schema |
| `/apps/ai/src/workflows/finance_workflow.py` | Finance specialist Temporal workflow |
| `/apps/ai/src/workflows/data_workflow.py` | Data specialist Temporal workflow |
| `/apps/ai/src/workflows/ops_workflow.py` | Ops specialist Temporal workflow |
| `/apps/ai/src/integrations/slack_client.py` | Slack WebClient + SocketModeClient for interactive messages |
| `/apps/ai/src/integrations/slack_buttons.py` | ACE button routing (acknowledge, dispute, breakdown, log_decision) |
| `/apps/ai/src/hitl/manager.py` | HITLManager with route_extended for guardrail-aware tier routing |
| `/apps/ai/src/hitl/confidence.py` | Confidence scoring (pattern_seen_before, data_quality, volatility) |
| `/apps/ai/src/hitl/approval_queue.py` | Approval request/response with Slack notification |
>>>>>>> Stashed changes

## Architecture Evolution (2026-06-28)

**Sarthi shifted from "AI agents replace work" to "AI coordination layer":**
- Specialist agents are focused (one domain each)
- Humans own critical approvals (HITL block tier)
- Deterministic Go core handles routing, not AI decisions
- Python LLM layer for analysis & structured output only
