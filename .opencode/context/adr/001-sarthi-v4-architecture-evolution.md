# ADR-001: Sarthi v4.0 — Architecture Evolution

**Status**: Accepted

**Date**: 2026-06-28

**Context**: `command-chat`, `command-approvals`, `workflow-dispatch`, `sse-push`

**Bounded Contexts**: core (Go), ai (Python), temporal-orchestration

---

## Context

The IterateSwarm Sarthi agent platform underwent a major architecture evolution from v3.x to v4.0. The initial architecture had several pain points:

1. **Synchronous blocking dispatch** — Workflow `run.Get()` blocked the HTTP response handler for up to 60s, causing timeout errors and poor UX (no visual feedback during LLM processing).
2. **Raw JS EventSource** — Client-side JavaScript managed EventSource lifecycle (reconnect, error handling, JSON parsing). Every chat bubble required JS to build DOM elements client-side, duplicating template logic.
3. **If-else mention routing** — A growing chain of `if mention == "@finance"` / `else if mention == "@data"` conditionals in the handler. Adding a new specialist required touching the routing code.
4. **No HITL signal wiring** — Approval buttons existed in the UI but did not signal Temporal workflows to unblock `AwaitWithTimeout` gates. Approvals were UI-only with no workflow integration.
5. **Dead stubs** — `workflow/stubs.go` contained 50 lines of placeholder types (`QdrantClient`, `TriageAgent`, `SpecResult`, `Retrier`) that had real implementations elsewhere, creating confusion about where implementations lived.
6. **No MissionState write path** — The Python AI layer had no endpoint to persist mission state for the dashboard to consume.

## Decision

We made seven architectural decisions to address these issues. Each is documented below.

### Decision 1: HTMX SSE over WebSocket / Raw JS EventSource

**What**: Replaced raw JavaScript EventSource with HTMX's `hx-ext="sse"` extension for real-time chat push.

**How**:
- Template declares SSE connection declaratively: `sse-connect="/api/command/chat/events"` with `sse-swap="chat"` and `hx-swap="beforeend"`.
- HTMX manages the EventSource lifecycle — auto-reconnect, error recovery — eliminating ~40 lines of JS.
- Server sends named SSE events (`event: chat`) with HTML *fragments* as the data payload, not JSON.
- HTMX's SSE extension only processes events matching `sse-swap="chat"`; other event names (`connected`, `heartbeat`) pass through silently.

**Rationale**: Eliminates client-side DOM construction for chat bubbles. The server owns rendering via `renderChatBubble()` — single source of truth for HTML structure. HTMX handles connection lifecycle, freeing JS for only two concerns: status indicator (`htmx:sseOpen`/`htmx:sseError`) and auto-scroll (`MutationObserver`).

### Decision 2: Goroutine-based Workflow Dispatch

**What**: Workflow execution moved from synchronous `run.Get()` in the HTTP handler to asynchronous goroutine + SSE push.

**How**:
- HTTP handler starts a goroutine: `go func(...) { defer h.wg.Done(); ... }()` with `h.wg.Add(1)` tracking.
- Goroutine uses a 5-minute context timeout (merged from request context): `context.WithTimeout(reqCtx, 5*time.Minute)`.
- Immediate "🤔 Thinking..." indicator pushed via `tryBroadcast()` — non-blocking channel send using `select { case ch <- msg: default: log }`.
- On completion, `tryBroadcast()` pushes the result bubble via SSE. On failure, pushes an error bubble.
- `sync.WaitGroup` on the `Handler` struct enables graceful shutdown tracking.

**Rationale**: Eliminates 60s HTTP timeout failures. Users see immediate feedback ("Thinking...") while the LLM processes. Non-blocking `tryBroadcast` with `select/default` prevents goroutine pile-up if the SSE channel is full — messages are dropped with a log line instead of blocking the dispatcher.

### Decision 3: Map-based Specialist Routing

**What**: Replaced `if-else` mention chain with a declarative `map[string]specialistRoute` lookup.

**How**:
```go
var specialistRoutes = map[string]specialistRoute{
    "@sarthi":  {"QAWorkflow", "Sarthi"},
    "@agent":   {"QAWorkflow", "Sarthi"},
    "@qa":      {"QAWorkflow", "Sarthi"},
    "@ask":     {"QAWorkflow", "Sarthi"},
    "@finance": {"FinanceWorkflow", "Finance"},
    "@data":    {"DataWorkflow", "Data"},
    "@ops":     {"OpsWorkflow", "Ops"},
    "@comms":   {"CommsWorkflow", "Comms"},
    "@hiring":  {"HiringWorkflow", "Hiring"},
}
```
- Mention aliases (@sarthi/@agent/@qa/@ask) map to the same workflow type (QAWorkflow).
- Adding a new specialist = one map entry + one Python workflow class — no routing code changes.
- Lookup is O(1) map access instead of O(n) if-else chain.

**Rationale**: A new specialist (e.g., `@legal`) requires only a new Python workflow in `apps/ai/src/workflows/legal_workflow.py` and one line in the map — no handler changes. The `specialistRoute` struct carries both `workflowType` (for Temporal dispatch) and `displayName` (for UI rendering), keeping routing and presentation coupled in one place.

### Decision 4: Temporal Signal for HITL Approval

**What**: The Approve button now signals the Temporal workflow to unblock the Human-In-The-Loop gate.

**How**:
- Approve button POST → `APICommandApprovalAction` → `temporal.SignalWorkflow(ctx, workflowID, "hitl-approval", true)`.
- Hold button does not signal → workflow continues waiting on `AwaitWithTimeout` (48h timeout).
- DB status update (`planned_actions.status = "approved" | "held"`) is a secondary side effect for UI polling.
- Signal has a 5-second context timeout to avoid hanging the HTTP handler.

**Rationale**: Without this signal, Temporal workflows with `AwaitWithTimeout` for HITL approval would never unblock. The UI buttons were effectively decorative. Now the approval action causes the workflow to proceed — the DB update is secondary (for the polling-based approval list view). The primary control flow is Temporal signal → workflow resume.

### Decision 5: Server-rendered Chat Bubbles

**What**: Chat bubble HTML is rendered server-side by `renderChatBubble()` and pushed as HTML fragments over SSE, not JSON.

**How**:
- `renderChatBubble(sender, displayName, text, timeStr string) string` builds the full HTML string using `bytes.Buffer` with proper HTML escaping.
- Agent-specific CSS classes: `agent-sarthi`, `agent-finance`, `agent-data`, `agent-ops`.
- Agent initials map: Y/S/F/D/O for You/Sarthi/Finance/Data/Ops.
- All text is `html.EscapeString()` — no XSS vector from LLM output.
- SSE endpoint writes this HTML directly as the SSE data payload under `event: chat`.
- HTMX `sse-swap="chat"` + `hx-swap="beforeend"` appends it to `#chat-messages`.

**Rationale**: Server-side rendering means one template source of truth — the `renderChatBubble()` output matches the initial server-rendered messages in the Go template. No client-side Handlebars/Mustache/JS template strings. Event escaping on all user and LLM-generated text prevents XSS.

### Decision 6: MissionState Write Path (POST Endpoint)

**What**: Python AI layer writes to `mission_state` table via a POST endpoint that the Go core exposes. Mission state data flows: Python AI → POST → PostgreSQL → GET → Dashboard.

**How**:
- Go core exposes `POST /api/mission-state` for Python AI workers.
- Dashboard reads via `GET /api/mission-state` — server-side rendered, no client state.
- Data flow: Python LangGraph agents → POST endpoint → `mission_state` table → GET endpoint → Go templates → HTML.

**Rationale**: Pure server-side rendered state. No client-side state management. The dashboard is a "dumb" consumer — it just renders what the server gives it. The Python AI layer is the only writer of mission state data, ensuring write locality.

### Decision 7: Remove Dead Stubs

**What**: `workflow/stubs.go` reduced from ~50 lines to 10 lines, removing all placeholder types that had real implementations.

**Removed**: `QdrantClient`, `TriageAgent`, `SpecResult`, `Retrier`, `MemoryClient`, `Embedder` stub types and their placeholder methods.

**Retained**: `DiscordApprovalInput` struct — a convenience type used within the workflow package for Discord approval payloads.

**Rationale**: The removed types have real implementations in `apps/ai/src/` (Python) or `apps/core/internal/agents/` (Go). Keeping stubs created confusion — developers had to check whether a type was a stub or the real implementation. Removing them means "if it's in stubs.go, it's a real convenience type used here." This reduces cognitive load and prevents stale stubs from diverging from real implementations.

---

## Consequences

### Positive

| Decision | Benefit |
|----------|---------|
| HTMX SSE | ~40 fewer lines of JS. Auto-reconnect built-in. Server owns HTML rendering. |
| Goroutine dispatch | No more 60s HTTP timeout. Users see "Thinking..." immediately. Graceful shutdown via WaitGroup. |
| Map routing | O(1) lookup. Adding a specialist = 1 map entry + 1 Python class. No handler changes. |
| Temporal Signal | Approval buttons actually unblock workflows. HITL gates work end-to-end. |
| Server-rendered bubbles | Single source of truth for HTML. XSS-safe via html.EscapeString. No client templates. |
| MissionState POST | Clear write path. Dashboard is a dumb renderer. No client state hydration. |
| Remove stubs | 40 fewer lines of stale dead code. Clear signal: "if it's here, it's real." |
<<<<<<< Updated upstream
=======
| SSEHub event filtering | Event-type routing eliminates channel explosion. Per-subscriber channels reduce head-of-line blocking. |
| ToolRegistry + HITL mapping | Self-documenting tools with explicit tier. Central registry enables pattern-driven tool suggestion. |
| Slack SocketMode | No Bolt dependency. No public Slack Events URL needed. ACE loop closes feedback via reflector. |
| Authority Manifest | Declarative agent permissions — who can do what, write where. Centralizes tool allowlists. |
| Alert Lineage | Every alert carries full context: pattern, metrics, mission state, risk, suggested tools, owner agent. |
| MissionState Explainability | Every write carries reason, changed fields, active roles — full audit trail without querying git. |
| Brief Generator | Auto-generated 2-sentence summary on every MissionState write — founder reads this first. |
| StrategyDelta Audit Trail | Structured audit log for curator confidence updates — traceable, queryable, debuggable. |
>>>>>>> Stashed changes

### Tradeoffs

| Decision | Tradeoff |
|----------|----------|
| HTMX SSE | HTML fragments over SSE inflates bandwidth per message vs JSON. More challenging to integrate with non-HTMX clients. |
| Goroutine dispatch | Error handling is in goroutine closures, not in the HTTP return path. Log-based monitoring required. |
| Map routing | Workflow type strings are not type-checked. A typo in `"FinanaceWorkflow"` fails at runtime, not compile time. |
| Temporal Signal | Approval logic is split between Go handler (signal) and Temporal workflow (AwaitWithTimeout). Must keep both in sync. |
| Server-rendered bubbles | Harder to add interactive elements (copy buttons, actions) — would need JS event delegation. |
| MissionState POST | Tight coupling between Python worker and Go schema. Schema changes require coordinated deploys. |
| Remove stubs | `DiscordApprovalInput` still exists as a convenience type — could become stale if Discord integration changes. |
<<<<<<< Updated upstream
=======
| SSEHub event filtering | Per-subscriber channels (64 buffer) per client increase memory under high concurrent connections. |
| ToolRegistry | Tools are auto-registered on import — import order dependencies could cause registration race at startup. |
| Slack SocketMode | Requires `SLACK_APP_TOKEN` (Socket Mode token) in addition to `SLACK_BOT_TOKEN`. WebSocket dependency for event ingestion. |
| Authority Manifest | Adding a new agent requires updating the manifest AND the specialistRoutes map — two files to touch. |
| Alert Lineage | Extra Pydantic model on every GuardianMessage — small overhead per alert for full traceability. |
| MissionState Explainability | Extra DB columns (migration 005) — small storage overhead for full audit trail. |
| Brief Generator | LLM call on every MissionState write — bounded by max_tokens=80, temperature=0.3, but still an external call. |
| StrategyDelta | Falls back to file audit log if PostgreSQL unavailable — eventual consistency for audit trail. |
>>>>>>> Stashed changes

### Risks

1. **SSE channel saturation** — `tryBroadcast` drops messages when the channel is full (buffered to 100). Under high concurrency, users may miss status updates. Mitigation: monitor `chatBroadcast` channel fill rate; increase buffer or add per-client channels if needed.
2. **Goroutine lifetime** — Long-lived goroutines (5-min timeout) hold references to request context. If the client disconnects, the goroutine continues until timeout or completion. Mitigation: check `ctx.Done()` in the goroutine loop pattern for future streaming responses.
3. **Specialist routing fragility** — Workflow type strings bypass compile-time checking. Mitigation: add a test that iterates all routes and verifies workflow names match registered Temporal workflow types.
4. **Signal ID mismatch** — The workflow ID used in the approval action must match the workflow ID that created the `planned_actions` row. If they diverge, signals are lost. Mitigation: store `workflow_id` in the `planned_actions` table and use it for signaling.
<<<<<<< Updated upstream
=======
5. **Tool tier mismatch** — A tool's `hitl_tier` could diverge from the HITL manager's routing decision for a given pattern. Mitigation: `get_tools_for_tier()` provides a single source of truth — tools should be registered with tiers that match the HITL manager output.
6. **Slack SocketMode reconnection** — If the Socket Mode WebSocket drops, Slack button interactions are lost until reconnection. Mitigation: SocketModeClient auto-reconnects; monitor reconnection events via the `on_socket_connected` callback.
7. **Authority manifest drift** — If a tool is added but not registered in the manifest, or vice versa, tool execution guards may block valid actions. Mitigation: add a startup check that validates manifest tool IDs against TOOL_REGISTRY keys.
8. **Brief generator failure** — If LLM call fails, MissionState write still succeeds (brief is optional). Mitigation: log.warning on empty brief, return None — non-blocking degradation.
9. **StrategyDelta file fallback** — If PostgreSQL is down, audit logs go to `/tmp/strategy_audit.jsonl` — not queryable, not durable. Mitigation: monitor file growth, alert if fallback path is active.
>>>>>>> Stashed changes

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser (HTMX)                                  │
│                                                                              │
│  ┌──────────────────────────┐    ┌───────────────────────────────┐          │
│  │  command_chat.html        │    │  command_approvals.html       │          │
│  │  hx-ext="sse"             │    │  hx-post="/api/command/       │          │
│  │  sse-connect="/api/...    │    │    approvals/{id}/approve"    │          │
│  │  events"                  │    │  hx-swap="outerHTML"          │          │
│  │  sse-swap="chat"          │    └───────────┬───────────────────┘          │
│  │  hx-swap="beforeend"      │                │                             │
│  └──────────┬────────────────┘                │                             │
│             │ SSE stream                      │ POST                         │
└─────────────┼──────────────────────────────────┼─────────────────────────────┘
              │                                  │
              ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Go Core (Fiber v2)                                   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Handler struct                                                        │   │
│  │  ┌─────────────┐  ┌───────────────┐  ┌──────────────┐                 │   │
│  │  │ chatBroadcast│  │ temporal      │  │ wg sync.     │                 │   │
│  │  │ chan fiber.Map│ │ *temporal.Client│ │ WaitGroup     │                 │   │
│  │  │ (buffered 100)│  │               │  │              │                 │   │
│  │  └──────┬──────┘  └───────┬───────┘  └──────────────┘                 │   │
│  │         │                 │                                            │   │
│  │  ┌──────▼──────┐  ┌──────▼───────┐                                    │   │
│  │  │ SSE endpoint │  │ specialis-   │                                    │   │
│  │  │ SetBodyStream│  │ tRoutes map  │                                    │   │
│  │  │ Writer       │  │ mention→Wkfl │                                    │   │
│  │  │ renderChat-  │  │ + displayName│                                    │   │
│  │  │ Bubble()     │  └──────┬───────┘                                    │   │
│  │  └──────────────┘         │                                            │   │
│  │                           │ goroutine dispatch                          │   │
│  │                           │ tryBroadcast() for SSE push                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  API Routes (Fiber)                                                   │   │
│  │  GET  /api/command/chat/events  → SSE stream (chat bubbles)          │   │
│  │  POST /api/command/chat/send    → goroutine + Temporal dispatch      │   │
│  │  POST /api/command/approvals/:id/approve → SignalWorkflow("hitl...") │   │
│  │  POST /api/command/approvals/:id/hold   → DB update only             │   │
│  │  GET  /api/mission-state        → read from PostgreSQL               │   │
│  │  POST /api/mission-state        → write from Python AI               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
              │                                  │
              │ Temporal                         │ SQL
              ▼                                  ▼
┌─────────────────────────────┐    ┌──────────────────────────────────────┐
│  Temporal Server             │    │  PostgreSQL                           │
│                              │    │                                       │
│  Task Queue:                 │    │  Tables:                              │
│  TRACKGUARD-MAIN-QUEUE       │    │  - chat_messages (sender, mention,    │
│                              │    │      message, created_at)             │
│  Workflows:                  │    │  - planned_actions (HITL approval     │
│  QAWorkflow                  │    │      queue)                           │
│  FinanceWorkflow             │    │  - mission_state (AI writes via POST) │
│  DataWorkflow                │    │  - agent_events (SSE polling source)  │
│  OpsWorkflow                 │    │                                       │
│  CommsWorkflow               │    └──────────────────────────────────────┘
│  HiringWorkflow              │                    ▲
│                              │                    │ POST /api/mission-state
│  Signals:                    │                    │
│  "hitl-approval" (bool)      │                    │
└──────┬──────────────────────┘                    │
       │ Temporal Task Queue                       │
       ▼                                           │
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Python AI Worker (Temporal Worker)                         │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ QAWorkflow    │  │ FinanceWork- │  │ DataWorkflow │  │ OpsWorkflow      │ │
│  │ (sarthi/agent │  │ flow         │  │              │  │                  │ │
│  │  /qa/ask)     │  │              │  │              │  │                  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│         │                 │                 │                   │           │
│         ▼                 ▼                 ▼                   ▼           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  LangGraph Agent Graphs                                              │   │
│  │  - FinanceGraph (tools: query, analyze, report)                      │   │
│  │  - DataGraph (tools: transform, aggregate, export)                   │   │
│  │  - OpsGraph (tools: deploy, monitor, alert)                          │   │
│  │  - CommsGraph (tools: draft, notify, summarize)                      │   │
│  │  - HiringGraph (tools: search, screen, evaluate)                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                          LLM Provider (Azure/Groq/Ollama)                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow: User Sends Chat Message

```
User types "@finance Q3 revenue?" → HTMX POST /api/command/chat/send
  → Go Handler parses @mentions → matches "@finance" in specialistRoutes
  → INSERT chat_messages (sender=founder)
  → tryBroadcast("founder", "You", message) → SSE → Browser (immediate echo)
  → go func() with WaitGroup:
      → tryBroadcast("@finance", "Finance", "🤔 Thinking...") → SSE → Browser
      → Temporal ExecuteWorkflow("FinanceWorkflow", input)
      → Python FinanceWorkflow.run() → FinanceGraph.invoke()
      → LLM processes query → returns result
      → Temporal returns to Go goroutine (run.Get)
      → INSERT chat_messages (sender=agent)
      → tryBroadcast("agent", "Finance", answer) → SSE → Browser
```

### Data Flow: HITL Approval

```
Agent proposes action → INSERT planned_actions (status=pending)
  → Temporal workflow reaches AwaitWithTimeout("hitl-approval", 48h)
  → Dashboard shows approval button
  → User clicks "Approve"
  → HTMX POST /api/command/approvals/{workflow_id}/approve
  → Go handler calls SignalWorkflow(ctx, id, "hitl-approval", true)
  → Temporal workflow unblocks, continues execution
  → DB status updated to "approved" (secondary)
```

---

## Implementation Notes

- **Adding a new specialist**: Add entry to `specialistRoutes` map in `handler.go`, create Python workflow class in `apps/ai/src/workflows/`, register workflow with Temporal worker.
- **SSE channel sizing**: `chatBroadcast` is buffered to 100. If fill rate approaches capacity, consider per-client SSE channels or a larger buffer.
- **Shutdown**: `h.wg.Wait()` should be called during server shutdown to ensure all in-flight goroutines complete.
- **Testing pattern**: Handlers can be unit tested with `NewHandler(nil, nil)` — DB and Temporal are optional. SSE endpoints require `app.Test()` with proper `HX-Request` headers.
- **Error visibility**: Workflow errors are logged and pushed as SSE error bubbles. Monitor logs for `Failed to start X workflow` patterns.
