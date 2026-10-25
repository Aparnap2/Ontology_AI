# AGENTS.md - IterateSwarm Coding Guidelines

## Project Overview

**Go + Python ChatOps platform** with Temporal orchestration and HTMX UI.

**Tech Stack:**
- **Go Core** (`apps/core/`): Go 1.24, Fiber, sqlc, Temporal SDK, HTMX
- **Python** (`apps/ai/`): Python 3.13, LangGraph, DSPy, Pydantic
- **LLM Providers**: OpenAI-compatible SDK (Azure AI Foundry, Groq, Ollama)
- **Infrastructure**: Docker (Temporal, Qdrant, PostgreSQL)

---

## V4.2 Status (OntologyAI)

| Component | Status | Notes |
|-----------|--------|-------|
| Python Tests | ✅ 901 passing / 26 skipped / 0 failed | Ontology schema + governance + adapter TDD suites |
| Go Build | ✅ Clean | Binary compiles successfully |
| Go HTMX Handler Tests | ✅ 74+ passing | command center, business, founder, LLMops, onboarding, watchlist, telegram, razorpay, alert lineage, operating layer |
| HTMX Routes | ✅ 15+ routes | Command center dashboard panels + SSE endpoints + alert-lineage + operating-layer |
| SSE Streaming | ✅ | HTMX `hx-ext="sse"` + `SetBodyStreamWriter` pattern + SSEHub event-type filtering |
| SSEHub Event-Type Filtering | ✅ | `Subscribe(tenantID, eventTypes...)` with per-subscriber channels (buffered 64) |
| Specialist Agents | ✅ | 5 canonical: ChiefOfStaff, FP&A, GrowthAnalytics, Reliability, Comms |
| HITL Temporal Signals | ✅ | `SignalWorkflow("hitl-approval")` unblocks `AwaitWithTimeout` |
| MissionState Write Path | ✅ | `POST /api/mission-state` from Python AI → PostgreSQL |
| @mention Routing | ✅ | `map[string]specialistRoute` — O(1) map lookup, 10 aliases → 5 workflows |
| Ontology Schema | ✅ | Object Types + Link Types in `apps/ai/src/ontology/` |
| Ontology Adapter | ✅ | `mission_state_to_ontology()` in `apps/ai/src/ontology/adapter.py` |
| Governed Writes | ✅ | `@governed_write` decorator in `apps/ai/src/ontology/governance.py` |
| Authority Manifest | ✅ | 5 agents with role/permissions/tool allowlists |
| E2E Smoke Test | ✅ | Real Docker + real LLM |
| Knowledge Catalog | ✅ | 10-category schema + 11 link tables in `apps/core/migrations/011_knowledge_catalog.sql` |
| DB Tests | 🟡 Skip | Requires PostgreSQL container |

---

## Build/Lint/Test Commands

### Go (apps/core/)

```bash
# Download dependencies
go mod download

# Run all tests
go test ./...

# Run tests for specific package
go test ./internal/agents/...

# Run single test
go test ./internal/agents/... -run TestTriageAgent -v

# Format code
go fmt ./...

# Build worker
mkdir -p bin
go build -o bin/worker ./cmd/worker
go build -o bin/server ./cmd/server

# Run server
go run cmd/server/main.go

# Run worker
go run cmd/worker/main.go
```

### Makefile

```bash
# Start all services
make up

# Stop services
make down

# Build all
make build

# Generate protobuf code
make proto
```

### Python (apps/ai/)

```bash
# Install dependencies (requires uv)
cd apps/ai
uv sync

# Run all tests
uv run pytest tests/ -v

# Run specific test suite
uv run pytest tests/test_session.py -v
uv run pytest tests/test_cofounder.py -v
uv run pytest tests/test_guardian.py -v
uv run pytest tests/test_slackbot.py -v
uv run pytest tests/test_curator_graphiti.py -v  # 1 pre-existing timeout

# Run with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing
```

---

## Code Style Guidelines

### Go (Core Service)

**Imports:**
- Standard library first
- Third-party packages second
- Internal packages last with full module path
- Group imports with blank lines between groups

**Formatting:**
- `go fmt` standard formatting
- Use goimports for import organization

**Types:**
- Explicit types on struct fields
- Return concrete types, accept interfaces
- Use meaningful type names

**Naming:**
- `camelCase` for unexported identifiers
- `PascalCase` for exported identifiers
- `SCREAMING_SNAKE_CASE` for constants
- Acronyms: all caps (HTTP, URL, ID, SSE, HITL)

**Error Handling:**
- Check errors immediately: `if err != nil`
- Return errors up the call stack
- Wrap errors with context: `fmt.Errorf("context: %w", err)
- Use fiber.Error for HTTP status codes

**Struct Tags:**
- JSON tags: `json:"field_name,omitempty"`
- Database tags from sqlc generated code
- Form tags: `form:"field_name"`

**Logging:**
- Use internal/logging package
- Structured logging with key-value pairs
- Log at appropriate levels (Info, Warn, Error)

**SSE Pattern:**
- Use Fiber v2 `SetBodyStreamWriter` with `*bufio.Writer`
- Named SSE events: `event: chat`, `event: heartbeat`, `event: connected`
- Non-blocking broadcast: `tryBroadcast()` with `select { case ch <- msg: default: log }`
- HTMX declarative: `hx-ext="sse"` + `sse-connect` + `sse-swap` + `hx-swap`
- HTML fragments as SSE data payload (server-rendered via `renderChatBubble()`)
- Always `html.EscapeString()` on user/LLM text for XSS protection

**Goroutine Safety:**
- `sync.WaitGroup` for tracking in-flight workflow dispatches
- Context cancellation via `c.Context().Done()` in SSE handlers
- 5-minute context timeout for workflow dispatch goroutines
- Non-blocking channel sends with `select/default` to prevent goroutine pile-up

**Specialist Route Map Pattern:**
```go
var specialistRoutes = map[string]specialistRoute{
    "@sarthi":  {"QAWorkflow", "OntologyAI"},
    "@finance": {"FinanceWorkflow", "Finance"},
    "@data":    {"DataWorkflow", "Data"},
    "@ops":     {"OpsWorkflow", "Ops"},
}
```
- O(1) map lookup replaces if-else chain
- Adding a specialist = 1 map entry + 1 Python workflow class

### SQL (sqlc)

**Schema:**
- Place in `internal/db/schema.sql`
- Use `IF NOT EXISTS` for idempotent migrations
- Include indexes for frequently queried columns

**Queries:**
- Place in `internal/db/queries/`
- Name queries with action prefix: `-- name: {Action}{Entity} :{one|many}`
- Use `@param` notation for parameters

### Protobuf

**Generation:**
- Source files in `proto/` directory
- Generated code goes to `gen/go/`
- Use `buf generate` for code generation

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
        handler.go   # All endpoints, @mention routing, SSE broadcast
        sse.go       # Legacy SSE handler with DB polling
        command_center_test.go  # 52+ tests
        templates/
          command_center.html       # Main dashboard
          partials/                 # HTMX partials (13+ panels)
            command_chat.html        # Chat with hx-ext="sse"
            command_approvals.html   # Approval queue (approve/hold)
            command_mission_state.html
      agents/        # Go agent definitions
      config/        # LLM configuration
      db/            # sqlc generated code
      database/      # Connection utilities
      temporal/      # Temporal client (SignalWorkflow, ExecuteWorkflow)
      workflow/      # Temporal workflows & stubs (cleaned)
    sqlc.yaml       # sqlc configuration
  ai/                # Python AI Worker
    src/
      agents/        # Agent definitions
        pulse/       # PulseAgent (daily business pulse)
        anomaly/     # AnomalyAgent (explains spikes)
        investor/    # InvestorAgent (weekly updates)
        qa/          # QAAgent (founder Q&A)
        comms/       # CommsTriageAgent
        hiring/      # HiringAgent
        base/        # Abstract agent class, tool framework
        finance/     # V4 NEW — Finance specialist (FinanceGraph)
        data/        # V4 NEW — Data specialist (DataGraph)
        ops/         # V4 NEW — Ops specialist (OpsGraph)
      workflows/     # V4 NEW — Temporal workflow definitions
        finance_workflow.py
        data_workflow.py
        ops_workflow.py
      business/      # V3.0 MBA integration
      predictive/    # V3.0 Forecasting engine
      activities/    # Temporal activities
      orchestration/ # Pipeline orchestrators
      services/      # Trust battery, alert gate
      session/       # MissionState, relevance gate
      guardian/      # Watchlist, detector, assemblers
      integrations/  # Stripe, Plaid, Slack, ERPNext, HubSpot, QuickBooks
      memory/        # Graphiti, Qdrant, spine
      schemas/       # Pydantic models
        knowledge_catalog.py  # V6 NEW — Knowledge Catalog schema (10 categories + 11 link types)
      events/        # Redis Streams event bus
    tests/           # Pytest test suite (319+ tests)
    pyproject.toml   # Python dependencies
```

---

## Key Conventions

1. **Feature Branches**: Use `git checkout -b feature/description`
2. **Commits**: Use Conventional Commits (`feat:`, `fix:`, `refactor:`)
3. **Never commit to main**
4. **Environment**: Use `.env` file for secrets (never commit)
5. **Database**: Use sqlc for type-safe SQL; regenerate after schema changes

---

## LLM Configuration

The system uses the **official OpenAI Go SDK v3** which is compatible with:

- **Azure AI Foundry**: Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY`
- **Groq**: Set `GROQ_API_KEY`
- **OpenAI**: Set `OPENAI_API_KEY`
- **Ollama**: Set `OLLAMA_BASE_URL` and `OLLAMA_API_KEY` (local)

Configuration is auto-detected. See `internal/config/llm.go`.

---

## Section 13: Accumulated Learnings

| Date | Task | Learning |
| ---- | ---- | -------- |
| 2026-10-18 | #97 QA bound test | `QAGraph` (`apps/ai/src/agents/qa/graph.py`) is a `@dataclass` requiring `tenant_id`; `invoke()` is single-shot. No `max_iterations` exists in the QA module (only in `src/mission/`). Assert call counts, not invented attributes. |
| 2026-10-18 | #94 finance-guardian tests | Product alert contract is `guardian_result["match_count"] > 0`. `shouldalert` is test-fiction — grep before inventing mock fields. Also: `run_pulse_agent` mock must include `"ok": True` or the product takes its failure path. |
| 2026-10-18 | #93 scheduler bootstrap tests | `bootstrap_scheduler()` reads `ACTIVE_TENANTS` (default `"default"`). Always set env explicitly per test; scheduler funcs in `src/scheduler/ontology_ai_scheduler.py` are **sync** `def` → `MagicMock`, not `AsyncMock`. |
| 2026-10-18 | #92 unit/integrations mode | Polluters must restore global state: `tests/test_v6_worker_import_gate.py` evicted `src.integrations.*` from `sys.modules` without restore, so a later `@patch("src.integrations.erpnext.MOCK_MODE")` re-imported a **fresh** module and patched it while the test ran a stale bound function. Snapshot + restore in `try/finally`. |
| 2026-10-18 | #92 hubspot mock mode | `MOCK_MODE` in `src/integrations/{erpnext,hubspot}.py` is computed at **import time** from `ERPNEXT_URL`/`HUBSPOT_ACCESS_TOKEN`. A leaked `set_env_vars` (session-scoped autouse in `tests/integration/test_mockoon_pipeline.py`) made `importlib.reload` recompute `MOCK_MODE=False` → real API 401. Scope env-mutating autouse fixtures to the module that needs them. |
| 2026-10-18 | verification hygiene | Mutation evidence is only valid if the mutation actually applied. Assert the anchor was found and confirm `git diff --stat` restored to 0 afterwards — a silently unapplied mutation yields a false "pass". |
| 2026-10-18 | #91 slackbot wiring | `src/session/relevance_gate.py` exposes `evaluate_relevance`/`get_triggered_agents` — **no `relevance_gate` symbol**. `handle_slack_message` (`src/integrations/slack.py:339`) imports `get_triggered_agents` directly, so `patch("...relevance_gate")` raises `AttributeError`. Retarget patches at the imported name (`get_triggered_agents`), and grep the module for the real symbol before trusting a patch target. |
| 2026-10-18 | #90 canonical schema | `ON CONFLICT (tenant_id) DO UPDATE` needs a matching UNIQUE; plural `mission_states` had **no `CREATE TABLE` in either runner dir** — only `ALTER TABLE` (`004`), so the runner can't bootstrap a fresh DB (`004`'s ALTER fails on empty DB). Canonical CREATE lived only in `apps/ai/src/session/001_session_layer.sql` (hand-applied). Fix = one canonical migration `apps/core/internal/db/migrations/013_mission_states_canonical.sql` (04b6af2) as source of truth, consumed by the AI fixture — a deliberate **cross-app shared-schema contract** documented in the migration. `004`/test type drift: `active_alerts`/`churn_risk_users` are **TEXT** (001), not 004's JSONB/INT; `churn_rate` FLOAT. Before adding a UNIQUE, confirm the append-only path is dead: singular `mission_state` is a **VIEW** over plural, and the only id-keyed writer (`src/mission/runtime.py` `persist_mission_state`/`update_mission_kpis`) has zero prod/test callers → one-row-per-tenant holds → `UNIQUE(tenant_id)` safe. Integration fixtures must require `TEST_DATABASE_URL` with **no implicit default** and `pytest.fail` (not skip) on unset/connect failure (7d03b5f). |
| 2026-10-18 | #88 core mock :3000 | Mockoon `chooseResponse` (`response-rules-interpreter.js`) selects from responses with `rules.length>0`, and if none fulfil it falls back to `this.routeResponses.find(r=>r.default) ?? this.routeResponses[0]` — so a **rule-less success response placed second is unreachable**, and every request hits response[0]. Fix = put the SUCCESS response FIRST with a presence rule `{target:"body",modifier:"<field>",operator:"null",invert:true}` and mark the ERROR response `"default":true`. `null` operator returns true also for `''`, so empty values correctly fall through to the 400. `{{randomInt}}` renders EMPTY in this Mockoon build — use literals; `{{body 'x'}}` echo + `{{now 'x'}}` work. `pkill -f` self-matches a command line containing the same literal → use a bracket class (`ontology-ai[-]demo`) and never mix a kill pattern with a literal launch line in one shell invocation. Detached `setsid nohup ... &` mock dies if the launching shell's process group is killed by a tool timeout — launch, poll, and test in **separate** invocations. |
| 2026-10-18 | #95 vendor-incident e2e | `SeenSet._seen` is now a read-only **snapshot** property (`apps/ai/src/control_plane/idempotency.py:253-262`), so `ingress_mod._seen._seen.clear()` is a **silent no-op**. An autouse `_clean` fixture that used it leaked COMMITTED idempotency claims across tests → the second test in any process hit `deny:duplicate` on its first submit → no `permit:executed` → the helper dereferenced a `None` permit (crash at `tests/test_vendor_incident_e2e.py:302`). The signature is pairing-agnostic (ANY two tests in one process → the 2nd fails; each passes alone), which points at fixture state, not the test body. Use `_seen.clear()`/`reset_seen()`. Grep `._seen._seen.clear()` for **writes** (also `scripts/demo_blocker_investigation.py:93`); read-only `._seen._seen` reads are harmless. |
| 2026-10-18 | #96 jira demo binding | `CapabilityOpRegistry.assert_allowed` is fail-closed on `role_caps=None`/`[]` (P0 contract), so an op-layer integration test that omits the allowlist is DENIED (`no allowlist supplied for this principal`), not default-allowed — supply the explicit intended list (`["jira.create","jira.update","jira.read"]`). Prove the new negative coverage has teeth by mutating the `None` branch to `return` and expecting `DID NOT RAISE`; the unauthorized-omission case stays red-free because that branch is separate. |
| 2026-10-18 | #98 investor-warmup triage | Warmup suite dies before product code. The `deepeval` pytest11 plugin autoloads dotenv (`deepeval/config/settings.py:192`), reading `apps/ai/.env:28` (`...:5432/iterateswarm`) **before** `tests/conftest.py:13`'s `setdefault(...:5433)`, so the 5433 intent is dead and the test hits the foreign `ontologiai` DB on 5432 (`iterateswarm` role absent → `psycopg2.OperationalError`). Proof: `-p no:deepeval` → 5433, default → 5432. Even with a valid DSN it cannot pass: no `investor_relationships` migration exists (only `archive/PRD_V4.2.md:388`), 5432 `to_regclass` = ABSENT, 5433 = 0 rows, seed names only in the test. Classification TEST_INFRA (root) + ENVIRONMENT (trigger), not CODE_DEFECT; repair → #103. |
| 2026-10-21 | new-issue triage (19 rows) | Mockoon fixtures with hardcoded past dates are **time bombs**: once "now" passes them, overdue/30-day-window assertions flip (QuickBooks `finance_overdue_invoices` 2→3, DSO→None; HubSpot `closedate`). Mockoon has **no date arithmetic** — `{{now 'yyyy-MM-dd' -90 days}}`, `{{now 'yyyy-MM-dd' -90}}`, and `{{date ...}}` all ignore the offset/return empty (probe-verified on `mockoon/cli:latest`); only `{{now 'format'}}` works, rendered **at request time in container UTC** (matches `datetime.utcnow()`). Time-invariant recipe: overdue → `DueDate={{now 'yyyy-MM-dd'}}` (midnight < now on any real request), not-overdue → far-future literal (`2099-12-31`), paid-in-30d → `TxnDate={{now 'yyyy-MM-dd'}}`. Env-gated tests need **both** proofs: rerun without the env var (clean skip) AND with a real DSN/key (pass) — a skip alone never proves the test body works. `uv run ruff check --fix` removed 4 pre-existing F401s in touched test files; the 2 remaining E402s in `test_tone_filter.py` are intentional (env must be set before `src` import). |

| 2026-10-25 | FG-1 post-triage | Canonical gate re-run on commit 0f27c2e (HEAD): **46 failed, 3397 passed, 81 skipped, 199 deselected, 8 errors** in 724.41s (was 79/3378/61/4). 8 errors = DB-gated suites without TEST_DATABASE_URL (mission_state x5, investor_warmup x3). Remaining 46 = env/owner-decision blocked: 4 evals (#102 paused), 4 mockoon-pipeline (pass in isolation, env in full run), ~17 mockoon-endpoints, ~10 connectors, 3 vendor (TEST_INFRA), 2 authority-manifest (arch owner), 1 governance (policy owner), 2 temporal-smoke, 1 incident-e2e, 1 replay. No new code defects introduced. |
