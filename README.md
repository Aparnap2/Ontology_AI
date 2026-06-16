# TrackGuard — Decision Intelligence for Seed-Stage Founders

> An operational decision intelligence system architected with deterministic agents, real-time health monitoring, and multi-domain alerting.
> Not a chatbot — a trusted multi-agent council that observes, analyzes, decides, and learns.

[![Tests](https://img.shields.io/badge/tests-375%20passing-brightgreen)](#)
[![Architecture](https://img.shields.io/badge/architecture-Guardian%20council-blue)](#)
[![Trust](https://img.shields.io/badge/trust-Profiled%20%2B%20Gated-orange)](#)
[![MBA](https://img.shields.io/badge/MBA-Finance%20%2B%20Guardrails%20%2B%20Forecasts-red)](#)

---

## The Architecture: A Digital Guardian Council

Each agent is a specialized decision-maker with bounded authority, durable memory, and explicit trust governance.

```text
                     ┌─────────────────────────┐
                     │  FOUNDER (Feedback Loop) │
                     │  Final authority for     │
                     │  irreversible decisions  │
                     └──────┬─────────────────┘
                            │
               ┌────────────┼────────────┐
               │            │            │
      ┌────────▼──┐  ┌─────▼──────┐  ┌──▼──────────┐
      │ ALERT GATE│  │  COUNCIL   │  │ CONFLICT    │
      │ 7-stage   │  │  AlertCouncil│  │ RESOLVER   │
      │ quality   │  │  synthesis │  │ Agent       │
      │ + business│  │  + priority│  │ Arbiter     │
      │ guardrails│  │  + recommend│  │             │
      └───────────┘  └─────┬──────┘  └─────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐
   │  FINANCE   │  │  BI ANALYST│  │  OPS WATCH  │
   │  Guardian  │  │  (leading  │  │  (operational│
   │  + Finance │  │  indicators)│  │  heartbeat) │
   │  Rules Engine│  │            │  │            │
   └──────┬─────┘  └──────┬──────┘  └──────┬──────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
               ┌───────────▼───────────┐
               │   BUSINESS PIPELINE   │
               │  Finance Rules →      │
               │  Guardrails → HITL →  │
               │  MissionState → Slack │
               └───────────┬───────────┘
                           │
               ┌───────────▼───────────┐
               │   PREDICTIVE GUARDIAN │
               │  Trend extrapolation  │
               │  Runway projection    │
               │  Churn acceleration   │
               │  Threshold alerts     │
               └───────────┬───────────┘
                           │
               ┌───────────▼───────────┐
               │   ANOMALY DETECTOR    │
               │  Cross-domain anomaly │
               │  inconsistency check  │
               │  — wandering scout    │
               └──────────────────────┘
                           │
               ┌───────────▼───────────┐
               │   MISSION STATE +     │
               │   ALERT DISPATCH      │
               │  Treasury (Kosha) +   │
               │  Enforcement (Danda)  │
               └──────────────────────┘
                           │
               ┌───────────▼───────────┐
               │   KNOWLEDGE GRAPH     │
               │  Graphiti temporal    │
               │  institutional memory │
               │  — connection (Mitra) │
               └──────────────────────┘
```

**New in V4: MBA Integration Layer.** Three new deterministic layers sit between the guardians and the founder:
- **Finance Rules** — 17 detection functions + 7 MBA primitives (WACC, NPV, IRR, burn multiple, etc.)
- **Guardrails Engine** — 7-stage policy evaluation (investor-facing, authority, reversibility, risk, privacy, approval tier, blocking)
- **Predictive Guardian** — trend forecasting, runway depletion projection, churn acceleration detection

---

## MBA Integration Layer

### Finance Rules (`business/finance_rules.py`)
17 detection functions extracted from guardian watchlist lambdas + 7 MBA finance primitives. Pure Python, zero LLM calls.

**Detections:** silent churn death, burn multiple creep, customer concentration risk, runway compression, failed payment clusters, payroll/revenue breach, leaky bucket activation, power user MRR masking, feature adoption drop, cohort retention degradation, NRR < 100%, trial activation wall, error segment correlation, support outpacing growth, cross-channel bug convergence, deploy frequency collapse, infra unit economics divergence.

**MBA Primitives:** `compute_burn_multiple`, `compute_runway_days`, `compute_effective_runway_days`, `compute_npv`, `compute_irr`, `compute_wacc`, `compute_working_capital_pressure`.

### Business Decision Envelope (`business/envelope.py`)
Canonical typed contract composing 5 existing schemas (`EventEnvelope`, `AlertDecision`, `GuardianMessage`, `DecisionResult`, `AlertEvidenceChain`) with `FinancialSnapshot` + `GuardrailResult`. Composition, not inheritance — zero source file modifications.

### Guardrails Engine (`business/guardrails.py`)
7-stage deterministic policy evaluation — no LLM calls:
1. **Investor-facing** — flag decisions visible to investors
2. **Authority** — map severity to approval tier (auto/review/blocking)
3. **Reversibility** — detect irreversible decisions (payouts, contracts, public comms)
4. **Risk classification** — financial / legal / reputational / operational
5. **Privacy** — PII detection via regex
6. **Approval tier final** — deterministic tier assignment
7. **Blocking override** — block when multiple critical conditions met

### Alert Quality Gate — Extended (`services/alert_gate.py`)
Expanded from 4 to 7 stages: schema → trust → dedup → tone → **authority** → **risk** → **privacy**.

### Trust Battery — Extended (`services/trust_battery.py`)
4 new guardrail fields added to `AgentTrustProfile`: `authority_limit`, `max_auto_approve_severity`, `investor_update_requires_approval`, `irreversible_decision_threshold`.

### Business Pipeline (`orchestration/run_business_pipeline.py`)
Chains 7 stages: finance rules → envelope → guardrails → HITL routing → MissionState update → events → Slack alert. Wrapped as Temporal activities.

### Predictive Guardian (`predictive/engine.py`)
10 pure forecasting functions using standard library only (math, statistics):
- **Linear trend** — OLS regression for any metric
- **Predict next** — single/multi-step forecast via trend extrapolation
- **Days to threshold** — when will a metric breach a critical value
- **Moving average** — sliding window smoother
- **Confidence intervals** — normal approximation bounds
- **Volatility** — coefficient of variation
- **Runway depletion** — trend-adjusted cash runway projection
- **Churn acceleration** — detects if churn rate is accelerating
- **Forecast summary** — complete metric forecast with trend, CI, volatility

### Startup Guardian (SG) — Deterministic Founder Council
Synchronous snapshot engine that queries ERPNext, HubSpot, and QuickBooks → assembles MissionStateV2 (Support, Execution, Team, Finance, Revenue) → runs 8 watchlists + 5 cross-domain correlations → computes overall health.

**Connectors:**
- **ERPNext** — `src/integrations/erpnext_client.py` (pure-stdlib Frappe REST client) + `erpnext.py` (mock/real mode, 4 snapshot sections)
- **HubSpot** — `src/integrations/hubspot.py` (mock mode + SDK fallback)
- **QuickBooks** — `src/integrations/quickbooks.py` (mock mode + httpx real, float-to-cents, DSO calculation)

**Assembly:** 5 domain assemblers in `src/guardian/assemblers/` transform flat snapshot dicts → Pydantic domain states + computed health enums.

**Detection:** 8 watchlist rules + 5 cross-domain correlations → `run_startup_detector()`. All deterministic, zero LLM calls.

**Orchestration:** `src/orchestration/run_startup_guardian.py` runs 3 connectors via `asyncio.to_thread`, assembles 5 domain states, computes `overall_health = worst(health)`.

**Testing:** 54 unit tests + 2 E2E tests against Mockoon containers (docker-compose.startup-guardian.yml). Mockoon fixtures with query-param routing for ERPNext doctypes. All monetary values in integer cents.

### HTMX Dashboards (Go side)
3 new admin panels in `apps/core/internal/web/`:
- **Decision Queue** — pending business decisions with approve/reject buttons (auto-refresh 10s)
- **Guardrail Status** — 2x2 grid of current guardrail states (auto-refresh 15s)
- **Finance Risk** — burn multiple, runway, working capital, WACC with color-coded risk (auto-refresh 15s)

---

## Core Components

### Trust Battery
Every agent has a dynamic trust profile with score (0.0–1.0), route priority, degraded mode, and full event audit history. Degraded agents (trust < 0.4) are hard-blocked at the relevance gate. Extended in V4 with guardrail authority limits and auto-approve thresholds.

### Session Layer
The `MissionState` is the single source of ground truth — shared context that every guardian reads and writes. Extended with 12 finance + guardrail fields in V4.

### Joint Alert Council
When 2+ guardians fire in the same session, the council synthesizes them into one alert with unified root cause, cross-domain severity, and a single recommended action. Prevents alert fatigue.

### Alert Quality Gate
Every alert passes through 7 stages before reaching the founder:
1. **Schema validation** — required fields, valid types
2. **Trust check** — agent not degraded
3. **Dedup check** — same alert not sent in last 60 minutes
4. **Tone filter** — basic text quality
5. **Authority check** — agent authorized for this severity level
6. **Risk assessment** — financial risk classification
7. **Privacy check** — PII detection

### Anomaly Detector
Roams across all MissionState fields looking for inconsistencies: burn alerts without operational symptoms, revenue growth with cash burn, short runways with misplaced founder focus.

### Conflict Resolver
Resolves contradictions between guardians — severity mismatches (critical vs. info) and signal contradictions. Highest severity wins; majority override available.

---

## What TrackGuard Answers

Every alert or recommendation answers four questions:

| Question | How |
|----------|------|
| **What happened?** | Guardian detects metric deviation |
| **Why did it happen?** | Narrative layer explains root cause |
| **What if nothing changes?** | Predictive Guardian — runway projection, churn probability, threshold crossing |
| **What should be done?** | Concrete recommended action with deadline |

---

## One-Week Incident Lifecycle

```text
T+0   → Raw data arrives (webhook / sync)
T+3m  → Guardian cycle fires (detect → reason → decide)
T+5m  → Finance Rules compute 17 detections + 7 MBA primitives
T+6m  → Guardrails Engine evaluates 7-stage policy
T+7m  → Predictive Guardian forecasts trend, runway, churn
T+8m  → BusinessDecisionEnvelope assembled
T+9m  → HITL routes (auto / review / approve / blocked)
T+10m → MissionState updated with finance + guardrail fields
T+11m → HTMX dashboard refreshes (Decision Queue, Guardrail Status, Finance Risk)
T+12m → Founder receives alert on Slack with recommendation
T+15m → Founder acknowledges / disputes via Slack button
T+20m → Trust score updated, event logged to Graphiti
T+48h → Follow-up check: was action taken? Outcome measured?
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | OpenRouter (nemotron-3-super-120b via API), Gemini fallback |
| **Embeddings** | OpenRouter (llama-nemotron-embed-vl-1b, 2048-dim) |
| **Semantic Memory** | Graphiti + Neo4j 5.26 |
| **Vector Store** | Qdrant (episodic + compressed) |
| **Relational DB** | PostgreSQL (MissionState, trust events, sessions) |
| **Cache** | Redis (working memory, session TTL) |
| **Tracing** | Langfuse v4 (@observe) |
| **Workflow** | Temporal (activity orchestration) |
| **Business Logic** | Pure Python — standard library only (no numpy, no LLM) |
| **Dashboard** | Go 1.24 + Fiber + HTMX |
| **Language** | Python 3.13, Go 1.24 |
| **Config** | Env-only via pydantic-settings — zero hardcoded secrets |

---

## Test Coverage (319+ Passing)

| Suite | Tests | Status |
|-------|-------|--------|
| Trust Battery | 28 | ✅ |
| Session Layer | 35 | ✅ |
| Co-founder Agent | 20 | ✅ |
| Correlation + Avoidance | 14 | ✅ |
| Guardian Watchlist | 69 | ✅ |
| Finance Guardian | 25 | ✅ |
| Memory Spine (Graphiti) | 26 | ✅ |
| HITL | 11 | ✅ |
| Finance Rules | 10 | ✅ |
| Guardrails Engine | 22 | ✅ |
| Business Pipeline | 14 | ✅ |
| Predictive Guardian (engine) | 33 | ✅ |
| Predictive Guardian (activity) | 10 | ✅ |
| Go HTMX Handlers | 13 | ✅ |
| Startup Guardian Connectors | 22 | ✅ |
| Startup Guardian Assemblers | 13 | ✅ |
| Startup Guardian Watchlists | 4 | ✅ |
| Startup Guardian Correlations | 6 | ✅ |
| Startup Guardian Detector | 3 | ✅ |
| Startup Guardian Orchestrator | 5 | ✅ |
| Startup Guardian E2E | 2 | ✅ |
| All Others | 100+ | ✅ |

---

## Project Structure

```
apps/
  core/                    # Go Modular Monolith
    cmd/                   # Entrypoints (server, worker, consumer)
    internal/
      web/                 # HTTP handlers + HTMX templates
        templates/         # 14 HTML templates (dashboard, panels)
        business_handler.go # Decision Queue, Guardrail Status, Finance Risk
      agents/              # Go agent definitions
      workflow/            # Temporal workflows & activities
      api/                 # Auth, webhook handlers
    migrations/            # SQL migrations
  ai/                      # Python AI Worker
    src/
      agents/              # Guardian agents (finance, bi, ops, qa, investor)
      business/            # MBA integration (NEW V4)
        finance_rules.py   # 17 detections + 7 MBA primitives
        guardrails.py      # 7-stage policy engine
        envelope.py        # BusinessDecisionEnvelope
      predictive/          # Forecasting engine (NEW V4)
        engine.py          # 10 pure forecasting functions
        schemas.py         # 6 Pydantic models
      activities/          # Temporal activities
        run_finance_rules.py
        run_guardrails.py
        run_predictive_guardian.py
      orchestration/       # Pipeline orchestrators
        run_business_pipeline.py
        run_startup_guardian.py       # Startup Guardian orchestrator
        run_startup_guardian_cli.py   # CLI entrypoint
      services/            # Trust battery, alert gate, decision engine
      session/             # MissionState, relevance gate
      guardian/            # Watchlist, detector
        assemblers/         # Startup Guardian domain state assemblers
        startup_watchlists.py
        startup_correlations.py
        startup_detector.py
      integrations/        # Stripe, Plaid, Slack, ERPNext, HubSpot, QuickBooks
      states/              # MissionStateV2 domain state schemas
      schemas/             # Pydantic models
      memory/              # Graphiti, Qdrant, spine
      events/              # Redis Streams event bus
    tests/unit/            # 319+ tests
    infrastructure/        # SQL migrations
```

---

## Quick Start

```bash
# Start infrastructure
docker start trackguard-postgres trackguard-neo4j trackguard-qdrant trackguard-redis

# Run Python tests
cd apps/ai && uv run pytest tests/unit/ -q

# Run Go tests
cd apps/core && go test ./internal/web/... -v

# Run worker
cd apps/ai && uv run python -m src.worker

# Run Startup Guardian with Mockoon containers
docker compose -f docker-compose.startup-guardian.yml up -d mock-erpnext mock-hubspot mock-quickbooks

# Run Startup Guardian E2E tests
ERPNEXT_URL=http://localhost:8099 ERPNEXT_USER=Administrator ERPNEXT_PASSWORD=admin \
  cd apps/ai && uv run pytest tests/integration/test_startup_guardian_e2e.py -v

# Run Startup Guardian CLI (mock mode, no containers needed)
cd apps/ai && uv run python -m src.orchestration.run_startup_guardian_cli my-tenant

# Run server
cd apps/core && go run cmd/server/main.go
```

---

## Development Principles

1. **Decision latency** — every feature must shorten the time between signal and action
2. **Exception quality** — high trust beats high volume; reduce false positives
3. **Founder cognition** — fewer, sharper, more actionable messages
4. **Trust gradually** — copilot → workflow assistant → semi-autonomous → autonomous
5. **No hardcoded secrets** — env-only configuration, centralized in `config/database.py`
6. **Composition over inheritance** — new packages import and nest existing schemas, never modify them
7. **Deterministic core** — finance, guardrails, and forecasting are pure Python with zero LLM calls
