# OntologyAI Command Center — Production Test Checklist

## 1. Infrastructure Tests (Pre-requisites)

### Docker Containers
- [ ] PostgreSQL running: `docker ps | grep sarthi-postgres` (health check: `pg_isready -U sarthi -d sarthi`)
- [ ] Redis running: `docker ps | grep sarthi-redis` (health check: `redis-cli ping` → PONG)
- [ ] Qdrant running: `docker ps | grep sarthi-qdrant` (health check: `curl -f http://localhost:6333/healthz`)
- [ ] Mockoon ERPNext running on `:8099`: `docker ps | grep sg-mock-erpnext`
- [ ] Mockoon HubSpot running on `:8098`: `docker ps | grep sg-mock-hubspot`
- [ ] Mockoon QuickBooks running on `:8097`: `docker ps | grep sg-mock-quickbooks`
- [ ] Redpanda running (if using event bus): `docker ps | grep sarthi-redpanda`

### Database Schema
- [ ] `mission_state` table exists: `\dt mission_state` in PostgreSQL
- [ ] `planned_actions` table exists: `\dt planned_actions`
- [ ] `agent_traces` table exists: `\dt agent_traces`
- [ ] DB schema applied via migrations (005_week3_dashboard.sql, command_center.sql)
- [ ] `hitl_queue` table exists (for approval pipeline)
- [ ] `agent_outputs` table exists (for finance alerts + BI queries)

### Seed Data
- [ ] Seed data loaded: `psql "$DATABASE_URL" -f scripts/seed_data.sql`
- [ ] Demos tenant `demo-tenant-001` exists in `founders` table
- [ ] Vendor baselines exist (AWS, Vercel, Slack, Notion)
- [ ] Finance snapshots exist with MRR and burn rate
- [ ] Sample transactions loaded into `transactions` table

### Go Server
- [ ] Go server running on `:3000`: `curl -sf http://localhost:3000/health`
- [ ] Server binary builds clean: `go build -o bin/server ./cmd/server`
- [ ] All Go tests pass: `go test ./... -v`
- [ ] HTMX tests pass (6 command center tests): `go test ./internal/web/... -run TestCommand -v`

### Python AI Worker
- [ ] Python dependencies installed: `cd apps/ai && uv sync`
- [ ] Python unit tests pass (38 tests): `uv run pytest tests/ -v`
- [ ] Startup guardian tests pass: `uv run pytest tests/unit/orchestration/ -v`

---

## 2. Command Center Dashboard Tests (Go HTMX)

### Page Load
- [ ] Dashboard loads at `http://localhost:3000/admin/command`
- [ ] Page title contains "OntologyAI Command Center"
- [ ] HTMX script loads from `htmx.org@1.9.10`
- [ ] Tailwind CSS loads from CDN
- [ ] Dark theme applied (bg-surface: #0f1117)
- [ ] Header displays mission control subtitle
- [ ] Live timestamp updates every second

### Row 1: Status Bar
- [ ] `/api/command/status` returns HTMX partial on `HX-Request: true`
- [ ] Status bar shows 5 fields: Mission health, Risk level, Blindspots, Approvals, Last sync
- [ ] Mission health displays trust score from `mission_state.trust_score`
- [ ] Risk level computed from `mission_state.burn_alert` / `burn_severity`
- [ ] Blindspots count = rows where `burn_alert = true` in mission_state
- [ ] Approvals count = rows where `status = 'planned'` in planned_actions
- [ ] Status bar auto-refreshes every 30s via `hx-trigger="every 30s"`
- [ ] Without `HX-Request` header, returns plain text "Command Status"

### Row 2: KPI Cards
- [ ] `/api/command/kpis` returns 4 KPI cards
- [ ] **MRR**: displays `₹.XXL` from `mission_state.mrr` (default: "4.82L")
- [ ] **Runway**: displays `X.X mo` from `mission_state.runway_days` (default: "7.8 mo")
- [ ] **Activation / Trust Score**: displays `XX%` from `mission_state.trust_score` (default: "41%")
- [ ] **Support Load / Burn Rate**: displays value from `mission_state.burn_rate` (default: "128")
- [ ] Each card has label, value, delta description, and trend color
- [ ] Trend color: green for "up", yellow for "warn", red for "down"
- [ ] KPIs auto-refresh every 30s
- [ ] Without `HX-Request` header, returns plain text "Command KPIs"

### Row 3: Mission State Panel
- [ ] `/api/command/mission-state` returns HTMX partial
- [ ] Panel header: "MissionState board" with "AUTO-COMPILED" badge
- [ ] Panel shows 3 signal cards: Finance, BI, Ops
- [ ] **Finance signal**: Shows burn alert / MRR / burn multiple from `mission_state`
- [ ] **BI signal**: Shows churn rate from `mission_state.churn_rate` (default fallback: "Cohort -12%")
- [ ] **Ops signal**: Shows error spike from `mission_state.error_spike` (default fallback: "Error cluster 14%")
- [ ] Color-coded delta: warn (yellow) for warning, down (red) for critical
- [ ] Auto-refreshes every 30s

### Row 3: Watchlist Panel
- [ ] `/api/command/watchlist` returns items with severity badges
- [ ] **FG-04 Runway Compression** (severity: high)
- [ ] **BG-04 Cohort Degradation** (severity: med)
- [ ] **OG-02 Support Outpacing Growth** (severity: med)
- [ ] **OG-01 Error Segment Correlation** (severity: low)
- [ ] Each item has colored left border (red=high, yellow=med, green=low)
- [ ] Severity labels shown as colored pill badges
- [ ] Auto-refreshes every 30s

### Row 4: Agent Fleet Panel
- [ ] `/api/command/agent-fleet` returns agent cards
- [ ] **OntologyAI** agent card (Manager, synthesis): routing, conflict resolution, approval queuing
- [ ] **Finance** agent card: MRR, burn, runway, flagging, financing alerts
- [ ] **Data** agent card: Cohorts, funnel, metric queries, trend summaries
- [ ] **Ops** agent card: Errors, support, bug detection, incident correlation
- [ ] Each card has initial letter avatar with colored background
- [ ] Loads once on page load (no auto-refresh trigger)

### Row 4: Timeline Panel
- [ ] `/api/command/timeline` returns events from `agent_traces` table
- [ ] Timeline shows 5 default events (when DB empty):
  - "Stripe webhook accepted" at 08:03
  - "Finance watchlist fired" at 08:07
  - "Correlation raised severity" at 08:11
  - "Approval queued" at 08:18
  - "MissionState refreshed" at 08:29
- [ ] When DB has data, shows live events from `agent_traces` LIMIT 20
- [ ] Each event has timestamp (mono font), title, and description
- [ ] Events separated by bottom border
- [ ] Auto-refreshes every 30s

### Row 5: Pending Approvals Panel
- [ ] `/api/command/approvals` returns pending items from `planned_actions` WHERE `status = 'planned'`
- [ ] Default items (when DB empty):
  - "Investor update draft" with **Approve** / **Hold** buttons
  - "Create Jira issue" with **Approve** / **Hold** buttons
- [ ] Live items from DB show actor, action_type, target_ref, risk_level, reason
- [ ] Title format: `{actor} proposes {action_type} on {target_ref}`
- [ ] Clicking **Approve** posts to `/api/command/approvals/{id}/approve`
- [ ] Clicking **Hold** posts to `/api/command/approvals/{id}/hold`
- [ ] On approve/hold: returns empty string → HTMX swaps out the row
- [ ] Approve updates `planned_actions.status = 'approved'`
- [ ] Hold updates `planned_actions.status = 'held'`
- [ ] Auto-refreshes every **10s** (faster than other panels)
- [ ] "Waiting" badge displayed in panel header

### Row 5: Metrics Panel
- [ ] `/api/command/metrics` returns 4 metric cards:
  - **Average agent response**: 1.8s (GOOD, green)
  - **Approval turnaround**: 6m 12s (OK, blue)
  - **False alert rate**: 4.2% (LOW, yellow)
  - **Context budget**: 612 / 800 tokens (SAFE, gray)
- [ ] Each metric has value, label, and status pill
- [ ] Status pill color: green=GOOD, blue=OK, yellow=LOW, gray=SAFE
- [ ] Auto-refreshes every 30s

### Row 6: Trend Chart Panel
- [ ] `/api/command/chart-data` returns JSON with Content-Type `application/json`
- [ ] Chart JSON contains `labels` array: ["W1", "W2", "W3", "W4", "W5", "W6"]
- [ ] Chart JSON contains 3 datasets:
  - **Mission Health**: [84, 82, 80, 79, 75, 72] (blue)
  - **Risk Index**: [26, 29, 35, 38, 45, 52] (yellow)
  - **Execution Drag**: [18, 22, 24, 29, 34, 39] (purple)
- [ ] Canvas element `#command-chart` renders on page load
- [ ] Fallback text rendered when Chart.js not loaded
- [ ] HTMX after-swap event triggers chart re-render
- [ ] Auto-refreshes every 30s (JSON endpoint)
- [ ] Chart fallback renders labels as comma-separated text

### Row 6: Chat Panel
- [ ] `/api/command/chat` loads the chat HTML partial
- [ ] Chat panel title: "Agent Chat" with "Multi-agent conversation" subtitle
- [ ] SSE endpoint at `/api/command/events` streams real-time events
- [ ] On connect: shows "Connected to command center" message
- [ ] Heartbeat every 30s (no UI update)
- [ ] System events every 60s: mission refresh, health check, watchlist cycle
- [ ] Chat form has: @mention dropdown (all, sarthi, finance, data, ops)
- [ ] Message input field with Send button (indigo)
- [ ] Form posts to `/api/command/chat/send` via HTMX
- [ ] Chat messages display sender avatar (colored initial), name, timestamp, text
- [ ] System messages appear centered in italics
- [ ] Auto-scroll to bottom on new messages
- [ ] Connection lost shows warning message with reconnect
- [ ] Without DB: `/api/command/chat/send` returns empty body
- [ ] With DB: returns JSON with parsed @mentions

### SSE Endpoint (`/api/command/events`)
- [ ] SSE headers: `Content-Type: text/event-stream`, no-cache, keep-alive
- [ ] Event types: `connected`, `heartbeat`, `system`
- [ ] Connected event payload: `{"status":"connected","text":"Connected to command center"}`
- [ ] Heartbeat every 30s
- [ ] System events every 60s (MissionState refreshed, health check, watchlist cycle)
- [ ] Connection properly terminates on context cancellation

### Auto-Refresh Verification
- [ ] Status bar: every 30s (`hx-trigger="every 30s"`)
- [ ] KPIs: every 30s
- [ ] Mission state: every 30s
- [ ] Watchlist: every 30s
- [ ] Timeline: every 30s
- [ ] Metrics: every 30s
- [ ] Chart data: every 30s
- [ ] Approvals: every **10s** (critical path)
- [ ] Agent fleet: load once only
- [ ] Chat panel: load once only (SSE handles live updates)

### HTMX Route Registration (`/admin/command`)
- [ ] Page route: `GET /admin/command` → `CommandCenter` handler
- [ ] Status: `GET /api/command/status` (HTMX + non-HTMX)
- [ ] KPIs: `GET /api/command/kpis`
- [ ] Mission state: `GET /api/command/mission-state`
- [ ] Watchlist: `GET /api/command/watchlist`
- [ ] Agent fleet: `GET /api/command/agent-fleet`
- [ ] Timeline: `GET /api/command/timeline`
- [ ] Approvals: `GET /api/command/approvals`
- [ ] Approval action: `POST /api/command/approvals/:id/:action`
- [ ] Metrics: `GET /api/command/metrics`
- [ ] Chart data: `GET /api/command/chart-data`
- [ ] Chat send: `POST /api/command/chat/send`
- [ ] SSE events: `GET /api/command/events`
- [ ] SSE events (alias): `GET /api/command/stream`
- [ ] Chat partial: `GET /api/command/chat`

### Error / Edge Cases
- [ ] Dashboard loads when database is unreachable (handler has `h.db == nil` fallback)
- [ ] All panels show default/hardcoded values when DB is nil
- [ ] Mission state shows fallback signals when `mission_state` table is empty
- [ ] Timeline shows default events when `agent_traces` table is empty
- [ ] Approvals show default items when `planned_actions` table is empty
- [ ] KPI viewer shows defaults when `mission_state` query fails
- [ ] Approve/hold on already-processed items (returns empty, row gone)
- [ ] Approval action with invalid ID (gracefully handles)

### Business Decision Pipeline (Separate Routes)
- [ ] `/api/business/decision-queue` loads decision queue table
- [ ] `/api/business/guardrail-status` shows approval tier, reversibility, investor flag
- [ ] `/api/business/finance-risk` shows burn multiple, runway, working capital, WACC
- [ ] Decision approve/reject posts work with HTMX out-of-band swap
- [ ] Auto-refresh: decision queue every 10s, guardrail + finance risk every 15s

---

## 3. Python AI Tests

### Startup Guardian
- [ ] `make run-startup` executes without errors
- [ ] Startup Guardian assembles `MissionStateV2` from 3 connectors (ERPNext, HubSpot, QuickBooks)
- [ ] Connector failures logged to Dead Letter Queue via `send_to_dlq`
- [ ] `assemble_support_state()` processes ERPNext helpdesk data correctly
- [ ] `assemble_execution_state()` processes ERPNext project data correctly
- [ ] `assemble_team_state()` processes ERPNext HR data correctly
- [ ] `assemble_finance_state()` processes QuickBooks invoice data correctly
- [ ] `assemble_revenue_state()` processes HubSpot CRM data correctly
- [ ] Cross-domain health computed correctly (worst health wins)
- [ ] `state.overall_health` is properly calculated from 5 domain healths
- [ ] `state.connectors_ok` tracks success/failure per connector
- [ ] Startup Guardian emits `startup_guardian.completed` event on bus

### Slack Alert Forwarder
- [ ] `SlackAlertForwarder` only alerts on CRITICAL or ATTENTION health
- [ ] Deduplication via Redis: same health level not alerted twice within TTL (3600s)
- [ ] Alert format contains header, tenant info, domain healths, connector status
- [ ] Dedup key format: `alert:sent:{tenant_id}:{health_value}`
- [ ] Returns `{ok: true, skipped: true}` when health is GOOD
- [ ] Returns `{ok: true, skipped: true}` when duplicate detected
- [ ] Sends via `src.integrations.slack.send_message_sync` with text + blocks

### Approval Gate / Risk Classification
- [ ] `planned_actions` table stores risk_level: low, medium, high, critical
- [ ] Planned actions require approval (`requires_approval = TRUE` by default)
- [ ] Approval queue in dashboard reads `status = 'planned'` actions
- [ ] Status transitions: planned → approved | held
- [ ] Error state handled in `planned_actions.error` field

### Context Compiler
- [ ] `compile_context()` builds `CompiledContext` from mission state + Redis store
- [ ] Mission summary includes: burn_alert, burn_severity, runway_days, mrr_trend, churn_rate, error_spike, active_alerts, founder_focus
- [ ] Fetches recent events from Redis at `ctx:{tenant_id}:events:{agent_name}`
- [ ] Fetches active findings from Redis at `ctx:{tenant_id}:findings:{agent_name}`
- [ ] `compile_context_to_messages()` serializes context into system + user messages
- [ ] Error context included when `include_errors=True`

### Failure Buckets
- [ ] `_classify_error()` correctly classifies errors into 8 buckets:
  - `data_quality`: connection refused, timeout, socket, DNS errors
  - `reasoning_failure`: assertion, division by zero, arithmetic errors
  - `rules_interpretation`: threshold, policy, validation, constraint violations
  - `context_assembly_error`: KeyError, AttributeError, not found, missing
  - `wrong_tool_selection`: routing, dispatch, no tool, not implemented
  - `approval_policy_error`: authorization, forbidden, access denied
  - `narrative_quality`: template, render, format, hallucination
  - `unknown`: fallback for unclassified errors
- [ ] `record_failure()` stores failure with UUID, tenant_id, source, operation, error_message
- [ ] `get_failures()` filters by tenant_id and/or bucket
- [ ] `get_failure_summary()` returns bucket → count mapping
- [ ] `resolve_failure()` sets resolved=true with resolution text
- [ ] `clear_failures()` resets in-memory store

### Trace Store
- [ ] `record_trace()` stores AgentTrace with duration_ms, llm_calls, llm_tokens, llm_cost_usd
- [ ] `get_traces()` filters by tenant_id, agent_name, status
- [ ] `get_trace_summary()` returns total_traces, success_rate, avg_duration_ms, total_cost_usd, failure_buckets
- [ ] Traces sorted by created_at DESC, limited to 100

---

## 4. Integration Tests

### Mockoon Endpoints
- [ ] ERPNext mock responds: `curl -f http://localhost:8099/api/resource/Issue`
- [ ] HubSpot mock responds: `curl -f http://localhost:8098/crm/v3/objects/deals`
- [ ] QuickBooks mock responds: `curl -f http://localhost:8097/v3/company/*/invoice`

### Redis StateStore
- [ ] Redis `StateStore.set(key, value, ttl)` works correctly
- [ ] Redis `StateStore.get(key)` returns stored values
- [ ] Redis `StateStore.exists(key)` returns correct boolean
- [ ] Redis connectivity from Python AI worker: `redis_client.ping()` returns True

### PostgreSQL Connectivity
- [ ] Go server connects: `DATABASE_URL=postgres://sarthi:sarthi@localhost:5432/sarthi?sslmode=disable`
- [ ] Python AI worker connects with same DATABASE_URL
- [ ] `mission_state` INSERT/UPDATE/SELECT from Python ai-worker succeeds
- [ ] `planned_actions` INSERT/SELECT/UPDATE from Go server succeeds
- [ ] `agent_traces` INSERT from Python + SELECT from Go works (full round-trip)

### Go + Python Round-Trip
- [ ] Python AI writes `agent_traces` row → Go dashboard timeline reads it
- [ ] Python AI writes `mission_state` row → Go dashboard KPIs + status bar update
- [ ] Python AI writes `planned_actions` row → Go dashboard approvals panel updates
- [ ] Go dashboard approve/hold → `planned_actions` status changes
- [ ] All panels show DB values when data exists (override defaults)

### Make Targets
- [ ] `make test` runs Go tests (all pass)
- [ ] `make test-unit` runs Python unit tests (all pass)
- [ ] `make test-docker` runs Docker integration tests (mock containers required)
- [ ] `make test-startup` runs startup guardian tests
- [ ] `make test-all` runs everything
- [ ] `make verify` runs E2E verification script
- [ ] `make demo-health` checks all infrastructure endpoints
- [ ] `make mock-up` starts all 3 mock containers
- [ ] `make mock-down` stops all 3 mock containers
- [ ] `make mock-status` shows mock container state
- [ ] `make v3-up` starts V3 minimal stack

---

## 5. Questions to Ask the Dashboard

### Mission State
- "What does burn_alert show on the dashboard? Is it true or false?"
- "What's the current MRR value and trend direction?"
- "What is the churn rate percentage?"
- "Is there an error spike detected in the Ops signal?"
- "What's the trust score and risk level?"
- "How many blindspots are being tracked?"
- "What signals are shown under Finance, BI, and Ops?"
- "Does the burn multiple appear in the Finance signal?"

### KPI / Financial
- "What is the current MRR in lakhs?"
- "How many months of runway remain?"
- "What is the activation/trust score percentage?"
- "What is the burn rate or support load count?"
- "Are the trend colors correct (up green, warn yellow, down red)?"

### Agent Fleet
- "Which agents are displayed in the fleet?"
- "What are OntologyAI agent's responsibilities?"
- "What are Finance agent's responsibilities?"
- "What are Data agent's responsibilities?"
- "What are Ops agent's responsibilities?"

### Timeline / Agent Traces
- "Which agents ran most recently?"
- "Are there any failed agent traces in the timeline?"
- "What was the last action recorded on the timeline?"
- "How many timeline events are visible?"
- "What is the success rate of agents running?"

### Watchlist
- "What watchlist items are currently active?"
- "Which items have high severity?"
- "What is the FG-04 Runway Compression threshold?"
- "What is the OG-01 Error Segment Correlation severity?"

### Approval Queue
- "Are there pending approvals in the queue?"
- "What action types need approval?"
- "How many actions are waiting for approval?"
- "Can I approve a specific action? Does the row disappear on approve?"
- "Can I hold a specific action? Does the row disappear on hold?"
- "Does the approvals panel refresh faster (10s) than other panels?"

### System Health
- "What is the overall system health percentage?"
- "Are any connectors failing (ERPNext, HubSpot, QuickBooks)?"
- "Is the trust score healthy (>70%)?"
- "What is the average agent response time?"
- "What is the false alert rate?"
- "Is the context budget within limits?"

### Chart Data
- "What is the current Mission Health trend (6-week)?"
- "What is the Risk Index trajectory?"
- "What is the Execution Drag value?"
- "Are the chart values loading as JSON?"

### Chat / SSE
- "Is the SSE connection established?"
- "Are heartbeats arriving every 30s?"
- "Do system events appear every 60s?"
- "Can I send a chat message with @mention?"
- "Does the chat auto-scroll on new messages?"

### Infrastructure
- "Is PostgreSQL connected and reachable?"
- "Is Redis connected?"
- "Are Mockoon containers running?"
- "Does the `make demo-health` command show all green?"

---

## 6. Data Verification Steps

### Expected KPI Values (Default, No DB)

| KPI Label | Value | Delta | Trend Color |
|-----------|-------|-------|-------------|
| MRR | 4.82L | +8.4% vs last month | green (up) |
| Runway | 7.8 mo | -0.6 months compression | yellow (warn) |
| Activation | 41% | Funnel wall at onboarding step 3 | yellow (warn) |
| Support Load | 128 | +22% week over week | red (down) |

### Expected KPI Values (With DB seed data)

| KPI Label | Condition | Value |
|-----------|-----------|-------|
| MRR | From `mission_state.mrr` | `₹X.XXL` (mrr/100000) |
| Runway | From `mission_state.runway_days` | `X.X mo` (runway/30) |
| Trust Score | From `mission_state.trust_score` | `XX%` |
| Burn Rate | From `mission_state.burn_rate` | `₹X.XK` (burn/1000) |

### Default Timeline Events (No agent_traces)

| Time | Title | Description |
|------|-------|-------------|
| 08:03 | Stripe webhook accepted | Invoice payment failure cluster appended to event bus. |
| 08:07 | Finance watchlist fired | FG-05 and FG-04 evaluated for alert-worthiness. |
| 08:11 | Correlation raised severity | Support spike correlated with onboarding failure step. |
| 08:18 | Approval queued | Draft investor-update mention requires founder approval. |
| 08:29 | MissionState refreshed | Compiled context rebuilt under 800-token limit. |

### Live Timeline (From agent_traces)

| Column | Source | Format |
|--------|--------|--------|
| Time | `agent_traces.created_at` | `HH:MM` format |
| Title | `agent_name + ": " + action` | Truncated at 60 chars |
| Description | `status + " · " + error` | Truncated at 80 chars |

### Default Watchlist Items

| ID | Title | Severity | Border Color |
|----|-------|----------|--------------|
| FG-04 | Runway Compression | high | red |
| BG-04 | Cohort Degradation | med | yellow |
| OG-02 | Support Outpacing Growth | med | yellow |
| OG-01 | Error Segment Correlation | low | green |

### Default Approval Items (No planned_actions)

| ID | Title | Description |
|----|-------|-------------|
| 1 | Investor update draft | OntologyAI wants to mention runway compression in the next investor note. |
| 2 | Create Jira issue | Ops proposes an onboarding desync incident ticket with customer-impact label. |

### Live Approvals (From planned_actions)

| Column | Source | Format |
|--------|--------|--------|
| ID | `planned_actions.id` | UUID |
| Title | `actor + " proposes " + action_type + " on " + target_ref` | Truncated at 60 chars |
| Description | `planned_actions.approval_reason` | Truncated at 100 chars |

### Expected Metrics (Hardcoded)

| Metric | Value | Status | Pill Color |
|--------|-------|--------|------------|
| Average agent response | 1.8s | GOOD | green |
| Approval turnaround | 6m 12s | OK | blue |
| False alert rate | 4.2% | LOW | yellow |
| Context budget | 612 / 800 tokens | SAFE | gray |

### Expected Chart Data

| Dataset | W1 | W2 | W3 | W4 | W5 | W6 | Color |
|---------|----|----|----|----|----|----|-------|
| Mission Health | 84 | 82 | 80 | 79 | 75 | 72 | blue (#7dd3fc) |
| Risk Index | 26 | 29 | 35 | 38 | 45 | 52 | yellow (#f59e0b) |
| Execution Drag | 18 | 22 | 24 | 29 | 34 | 39 | purple (#a78bfa) |

### Expected Status Bar (From mission_state)

| Field | Source | Fallback |
|-------|--------|----------|
| Mission health | `mission_state.trust_score` | 72% |
| Risk level | `burn_alert=true → HIGH`, `burn_severity → UPPER()`, else MEDIUM | MEDIUM |
| Blindspots | `COUNT(*) WHERE burn_alert=true` | 5 |
| Approvals | `COUNT(*) WHERE status='planned'` | 3 |
| Last sync | `time.Now().Format("15:04:05")` | current time |

---

## 7. Quick Smoke Test (Run These Commands)

```bash
# 1. Check all container health
make demo-health

# 2. Verify Mockoon endpoints
curl -f http://localhost:8099/api/resource/Issue
curl -f http://localhost:8098/crm/v3/objects/deals
curl -f http://localhost:8097/v3/company/*/invoice

# 3. Verify Go server and dashboard
curl -sf http://localhost:3000/admin/command | grep "OntologyAI Command Center"

# 4. Verify all HTMX endpoints return partials
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/status
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/kpis
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/mission-state
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/watchlist
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/timeline
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/approvals
curl -sf -H "HX-Request: true" http://localhost:3000/api/command/metrics
curl -sf http://localhost:3000/api/command/chart-data

# 5. Verify SSE stream
curl -sfN http://localhost:3000/api/command/events

# 6. Run test suites
make test
cd apps/ai && uv run pytest tests/ -v

# 7. Verify seed data
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM mission_state"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM planned_actions"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM agent_traces"
```

## 8. LLM / Groq Provider Check

- [ ] Groq API key set: `echo $GROQ_API_KEY`
- [ ] Model: `qwen/qwen3-32b` configured in config
- [ ] Fallback provider configured if Groq is down
- [ ] Rate limit handling: max 3 real LLM calls per test run
- [ ] Mocked LLM calls used in unit tests (no real API during tests)
