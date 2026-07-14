# IterateSwarm (OntologyAI) — Codebase Walkthrough

> This document is for **learning the codebase** so you can code yourself.
> Every section references actual files and line numbers. Go read the code.

---

## 1. THE BIG PICTURE

OntologyAI is a **ChatOps platform** that monitors startup health and alerts founders via Slack.
It has two services that talk to each other:

```
┌─────────────────────────────────────────────────────────────────┐
│                        FOUNDER'S SLACK                          │
│   /sarthi decide │ button clicks │ daily alerts │ weekly brief  │
└────────┬───────────────────┬────────────────────────┬───────────┘
         │                   │                        │
         ▼                   ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     GO CORE (apps/core/)                        │
│                                                                 │
│  Fiber HTTP Server (:3000)          Temporal Worker             │
│  ├── Webhooks (Slack/Discord)       ├── FeedbackWorkflow        │
│  ├── Auth (GitHub OAuth)            ├── OnboardingWorkflow      │
│  ├── HTMX Dashboard                 ├── BusinessOSWorkflow      │
│  ├── SSE Live Feed                  ├── InternalOpsWorkflow     │
│  └── Slack command proxy            └── OntologyAIRouter (event bus)│
│                                                                 │
│  Dependencies: Redpanda (events), PostgreSQL, Temporal          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ gRPC (:50051) + Redpanda events
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PYTHON AI (apps/ai/)                          │
│                                                                 │
│  Temporal Worker (SARTHI-MAIN-QUEUE)  APScheduler (optional)    │
│  ├── PulseWorkflow                     ├── finance_guardian (6h) │
│  ├── InvestorWorkflow                  ├── bi_pulse (daily 8am)  │
│  ├── QAWorkflow                        ├── ops_watch (4h)        │
│  ├── SelfAnalysisWorkflow              ├── investor_update (Mon) │
│  ├── CompressionWorkflow               └── weekly_synthesis(Mon)│
│  ├── WeightDecayWorkflow                                       │
│  └── MemoryMaintenanceWorkflow         Redis Streams Event Bus  │
│                                        (Python-side events)     │
│                                                                 │
│  Agents:                          Memory:                       │
│  ├── AnomalyAgent (LangGraph)     ├── Qdrant (vector search)    │
│  ├── InvestorAgent (LangGraph)    ├── Working/Episodic/Semantic │
│  ├── PulseAgent (LangGraph)       └── Compressed/Procedural     │
│  ├── QAAgent (ReAct + tools)                                    │
│  ├── CommsTriageAgent            Learning:                      │
│  ├── HiringAgent                  ├── FeedbackConsumer           │
│  └── CoFounderAgent (router)      ├── ACE Reflector             │
│      ├── correlation detector     └── Threshold adjustment      │
│      ├── curator (playbook)                                      │
│      └── reflector (ACE scoring)                                │
│                                                                 │
│  Dependencies: Redis, Qdrant, PostgreSQL, Temporal              │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight**: Go handles HTTP/webhooks/auth/HTMX. Python handles AI/agents/scheduling.
They communicate via **gRPC** (synchronous) and **Redpanda** (async events).

---

## 2. HOW TO TRACE A REQUEST

### Trace 1: Founder sends Slack message → Agent alert

```
1. Slack sends POST /webhooks/slack
   → apps/core/cmd/server/main.go:131  (route registration)
   → apps/core/internal/api/handlers.go:160  (HandleSlackWebhook)

2. Handler parses event, checks idempotency, publishes to Redpanda
   → handlers.go:262-287  (marshal + publish)

3. Go Temporal Worker picks up the event
   → apps/core/cmd/worker/main.go:52  (FeedbackWorkflow registered)

4. If it's an onboarding reply, Go handles it directly
   → handlers.go:232-257  (handleOnboardingReply)
```

### Trace 2: Scheduled finance check → Slack alert

```
1. APScheduler fires finance_guardian job
   → apps/ai/src/scheduler/sarthi_scheduler.py:49-55  (job registration)
   → sarthi_scheduler.py:142-146  (run_finance_guardian wrapper)

2. Wrapper calls orchestration function
   → apps/ai/src/orchestration/run_finance_guardian.py  (PulseAgent → Guardian → Slack)

3. PulseAgent runs (LangGraph)
   → apps/ai/src/agents/pulse/graph.py  (StateGraph pipeline)
   → apps/ai/src/agents/pulse/nodes.py  (individual nodes)

4. Guardian watchlist checks compliance
   → apps/ai/src/activities/run_guardian_watchlist.py

5. Slack message sent
   → apps/ai/src/activities/send_slack_message.py

6. Completion event emitted to Redis Streams
   → apps/ai/src/events/bus.py:45-66  (emit method)
```

### Trace 3: Founder clicks Slack feedback button

```
1. Slack sends interactive payload to Go
   → apps/core/internal/api/handlers.go:925  (HandleAgentFeedback)

2. Go parses button value (format: agent_type:pattern:tenant_id)
   → handlers.go:958-966  (split action value)

3. Go publishes feedback event to Redpanda
   → handlers.go:982-1004  (marshal + publish)

4. Python FeedbackConsumer reads from Redpanda
   → apps/ai/src/feedback_worker.py  (Redpanda consumer)
   → apps/ai/src/learning/feedback_consumer.py  (threshold adjustment)

5. Anomaly thresholds adjusted per tenant
   → apps/ai/src/agents/anomaly/thresholds.py  (get_tenant_thresholds)
```

### Trace 4: /sarthi decide slash command

```
1. Slack sends POST /slack/commands to Go
   → apps/core/cmd/server/main.go:134  (route)
   → main.go:230-273  (handleSlackCommandProxy)

2. Go proxies to Python Slack Bolt app via Redpanda or HTTP
   → main.go:244-254  (try Redpanda first)
   → main.go:257-272  (fallback to HTTP)

3. Python Slack Bolt app opens decision modal
   → apps/ai/src/slackbot.py  (/sarthi decide handler)

4. Modal submission → log_decision activity
   → apps/ai/src/activities/log_decision.py  (Postgres + Qdrant)
```

---

## 3. THE GO CORE — FILE BY FILE

### Entry Points

| File | Purpose |
|------|---------|
| [`cmd/server/main.go`](apps/core/cmd/server/main.go) | HTTP server. Initializes Fiber, Redpanda, Temporal, PostgreSQL, routes |
| [`cmd/worker/main.go`](apps/core/cmd/worker/main.go) | Temporal worker. Registers all workflows and activities |

### HTTP Layer

| File | Purpose |
|------|---------|
| [`internal/api/handlers.go`](apps/core/internal/api/handlers.go) | **All HTTP handlers**. Webhooks, health, feedback, HITL, BI query, agent feedback |
| [`internal/api/auth.go`](apps/core/internal/api/) | GitHub OAuth login/callback/logout with JWT |

**Key handler patterns in handlers.go:**

- **Idempotency**: Every webhook checks for duplicate deliveries using `h.repo.SetIdempotencyKey()` (lines 98-113, 216-229)
- **Redpanda publish**: All events go through `h.redpandaClient.Publish(data)` (lines 136, 281)
- **Graceful degradation**: If Redpanda/Temporal/Postgres is down, the server still starts with warnings (server/main.go:49-55, 59-66)

### Temporal Workflows

| File | Purpose |
|------|---------|
| [`internal/workflow/sarthi_router.go`](apps/core/internal/workflow/sarthi_router.go) | **Central event router**. Receives signals, routes to child workflows |
| [`internal/workflow/feedback.go`](apps/core/internal/workflow/) | FeedbackWorkflow — analyze feedback, create GitHub issues |
| [`internal/workflow/onboarding.go`](apps/core/internal/workflow/) | OnboardingWorkflow — question-answer flow for new founders |

**OntologyAIRouter is the most important Go workflow** (sarthi_router.go:110-227):

```
Signal Channel "ontology_ai.events" → Receive event → Check idempotency → 
Look up routing table → Spawn child workflow (fire-and-forget)
```

The routing table (lines 28-105) maps event types to workflows:
- `PAYMENT_SUCCESS` → RevenueWorkflow
- `USER_SIGNED_UP` → CSWorkflow
- `EXPENSE_RECORDED` → FinanceWorkflow
- `TIME_TICK_WEEKLY` → RevenueWorkflow + ChiefOfStaffWorkflow (multi-route!)

**Continue-As-New pattern** (line 125-132): After 1000 events, the workflow restarts itself to prevent Temporal history from growing unbounded.

### Infrastructure Clients

| File | Purpose |
|------|---------|
| [`internal/redpanda/client.go`](apps/core/internal/redpanda/) | Redpanda/Kafka producer with health check |
| [`internal/temporal/client.go`](apps/core/internal/temporal/) | Temporal client wrapper (StartWorkflow, SignalWorkflow, Health) |
| [`internal/db/`](apps/core/internal/db/) | sqlc-generated database queries + Repository pattern |
| [`internal/events/`](apps/core/internal/events/) | EventEnvelope struct shared across workflows |

---

## 4. THE PYTHON AI SERVICE — FILE BY FILE

### Entry Points

| File | Purpose |
|------|---------|
| [`src/main.py`](apps/ai/src/main.py) | **Main entry**. Runs Temporal worker, gRPC server, or both. Optional APScheduler mode |
| [`src/worker.py`](apps/ai/src/worker.py) | Dedicated Temporal worker. Registers 8 workflows + 9 activities |
| [`src/grpc_server.py`](apps/ai/src/grpc_server.py) | gRPC server for Go→Python calls. AnalyzeFeedback RPC with Qdrant duplicate check |
| [`src/slackbot.py`](apps/ai/src/slackbot.py) | Slack Bolt AsyncApp. `/sarthi decide` command + decision modal |

**main.py modes** (line 70):
```bash
python -m src.main --mode temporal   # Just Temporal worker
python -m src.main --mode grpc       # Just gRPC server
python -m src.main --mode both       # Both (default)
USE_APSCHEDULER=true python -m src.main  # Also start scheduled jobs
```

### Agent Architecture

Every agent follows the **LangGraph StateGraph pattern**:

```
State (dataclass) → Graph (StateGraph) → Nodes (functions) → Prompts (templates)
```

#### AnomalyAgent — [`src/agents/anomaly/`](apps/ai/src/agents/anomaly/)

| File | Purpose |
|------|---------|
| [`state.py`](apps/ai/src/agents/anomaly/state.py) | `AnomalyState` dataclass — metrics, thresholds, anomalies list |
| [`graph.py`](apps/ai/src/agents/anomaly/graph.py) | LangGraph pipeline: fetch_metrics → detect_anomaly → generate_alert |
| [`nodes.py`](apps/ai/src/agents/anomaly/nodes.py) | Node functions. Includes Slack feedback buttons |
| [`prompts.py`](apps/ai/src/agents/anomaly/prompts.py) | LLM prompt templates |
| [`thresholds.py`](apps/ai/src/agents/anomaly/thresholds.py) | **Dynamic thresholds** per tenant. Adjusted by feedback loop |

**Threshold system** (thresholds.py):
- Default thresholds defined as constants
- `get_tenant_thresholds()` checks for tenant-specific overrides
- `detect_anomaly_async()` compares metrics against thresholds
- Feedback loop adjusts thresholds: "acted_on" lowers threshold, "not_relevant" raises it

#### InvestorAgent — [`src/agents/investor/`](apps/ai/src/agents/investor/)

| File | Purpose |
|------|---------|
| [`state.py`](apps/ai/src/agents/investor/state.py) | `InvestorState` — investor data, narrative, critique |
| [`graph.py`](apps/ai/src/agents/investor/graph.py) | Pipeline: fetch_data → generate_narrative → critique_draft → finalize |
| [`nodes.py`](apps/ai/src/agents/investor/nodes.py) | Node functions with 8 specific critique criteria |
| [`prompts.py`](apps/ai/src/agents/investor/prompts.py) | LLM prompt templates |
| [`criteria.py`](apps/ai/src/agents/investor/criteria.py) | **8 measurable critique standards** (no jargon, specific numbers, etc.) |

#### PulseAgent — [`src/agents/pulse/`](apps/ai/src/agents/pulse/)

| File | Purpose |
|------|---------|
| [`state.py`](apps/ai/src/agents/pulse/state.py) | `PulseState` — current metrics snapshot |
| [`graph.py`](apps/ai/src/agents/pulse/graph.py) | Pipeline: fetch_metrics → analyze_trends → generate_briefing |
| [`nodes.py`](apps/ai/src/agents/pulse/nodes.py) | Node functions |
| [`prompts.py`](apps/ai/src/agents/pulse/prompts.py) | LLM prompt templates |

#### QAAgent — [`src/agents/qa/`](apps/ai/src/agents/qa/)

| File | Purpose |
|------|---------|
| [`state.py`](apps/ai/src/agents/qa/state.py) | `QAState` — question, tools, scratchpad |
| [`graph.py`](apps/ai/src/agents/qa/graph.py) | **ReAct loop**: think → act → observe → (loop or finish) |
| [`nodes.py`](apps/ai/src/agents/qa/nodes.py) | ReAct nodes with safety guards |

**QAAgent safety guards** (qa/graph.py):
- `MAX_TOOL_CALLS = 5` — prevents infinite loops
- Loop detection — stops if same tool called 3+ times
- Cost ceiling — $0.50 per query
- 30-second timeout per tool call

#### CoFounderAgent — [`src/agents/cofounder/`](apps/ai/src/agents/cofounder/)

| File | Purpose |
|------|---------|
| [`router.py`](apps/ai/src/agents/cofounder/router.py) | Routes messages to Employee Agents based on relevance gate |
| [`correlation.py`](apps/ai/src/agents/cofounder/correlation.py) | Cross-signal detection (burn+churn, errors+churn_risk, etc.) |
| [`curator.py`](apps/ai/src/agents/cofounder/curator.py) | ACE Curator — updates playbook confidence in memory |
| [`reflector.py`](apps/ai/src/agents/cofounder/reflector.py) | ACE Reflector — scores founder responses |

**ACE Framework** (reflector.py):
```
ACKNOWLEDGED  → +1.0  (founder saw the alert)
ACTED_ON      → +1.5  (founder took action)
IGNORED       → -0.5  (founder didn't respond)
DISPUTED      → -0.5  (founder disagreed)
DISMISSED     → -1.5  (founder explicitly dismissed)
```

#### CommsTriageAgent — [`src/agents/comms/`](apps/ai/src/agents/comms/)

| File | Purpose |
|------|---------|
| [`graph.py`](apps/ai/src/agents/comms/graph.py) | Pipeline: fetch_messages → classify → generate_digest → build_slack |

#### HiringAgent — [`src/agents/hiring/`](apps/ai/src/agents/hiring/)

| File | Purpose |
|------|---------|
| [`graph.py`](apps/ai/src/agents/hiring/graph.py) | Pipeline: load_candidate → fetch_role → score → update_pipeline → recommend |

### Base Agent — [`src/agents/base.py`](apps/ai/src/agents/base.py)

All agents inherit from `BaseAgent` which provides:
- `AgentResult` dataclass — standard output format (headline, do_this, urgency, etc.)
- `BANNED_JARGON` list — 100+ banned corporate buzzwords
- `_write_qdrant_memory()` — persist to vector store
- `_write_agent_output()` — persist to PostgreSQL
- `validate_tone()` — check for banned jargon in output

### Session Layer — [`src/session/`](apps/ai/src/session/)

| File | Purpose |
|------|---------|
| [`mission_state.py`](apps/ai/src/session/mission_state.py) | `MissionState` dataclass — finance/BI/ops/cross-functional metrics per tenant |
| [`context.py`](apps/ai/src/session/context.py) | `get_session_context()` — retrieve recent messages for a tenant |
| [`relevance_gate.py`](apps/ai/src/session/relevance_gate.py) | **Keyword-based routing** — determines which agents should respond |

**Relevance gate logic** (relevance_gate.py:243-274):
```
Agent responds if: keyword_hit OR (active_alert AND is_question)
```

Domain keywords:
- **finance**: burn, runway, revenue, mrr, arr, budget, raise, invest, ...
- **ops**: support, ticket, bug, error, deploy, downtime, latency, ...
- **bi**: metrics, dau, mau, retention, cohort, growth, analytics, kpi, ...

### Event Bus — [`src/events/bus.py`](apps/ai/src/events/bus.py)

Redis Streams event bus for Python-side events. Replaces Redpanda for Python→Python communication.

**Key methods:**
- `emit(topic, tenant_id, payload)` → Publish to `sarthi:{tenant_id}:{topic}` stream
- `consume(topic, tenant_id, group, consumer)` → Read from consumer group
- `read_recent(topic, tenant_id, count)` → Read last N messages (no group)
- `acknowledge(topic, tenant_id, group, message_ids)` → Mark processed

**Stream format**: `sarthi:{tenant_id}:{topic}` with MAX_STREAM_LENGTH=1000

### Scheduler — [`src/scheduler/sarthi_scheduler.py`](apps/ai/src/scheduler/sarthi_scheduler.py)

APScheduler replacing Temporal for simple cron/interval jobs.

| Job | Schedule | Orchestration Function |
|-----|----------|----------------------|
| finance_guardian | Every 6 hours | `run_finance_guardian()` |
| bi_pulse | Daily 8am UTC | `run_bi_pulse()` |
| ops_watch | Every 4 hours | `run_ops_watch()` |
| investor_update | Monday 7am UTC | `run_investor_update()` |
| weekly_synthesis | Monday 7:05am UTC | `run_weekly_synthesis()` |

**Important**: The scheduler wraps async orchestration functions with `asyncio.run()` (lines 142-174).

### Orchestration Layer — [`src/orchestration/`](apps/ai/src/orchestration/)

Each orchestration function chains multiple activities together:

| File | Pipeline |
|------|----------|
| [`run_finance_guardian.py`](apps/ai/src/orchestration/run_finance_guardian.py) | PulseAgent → Guardian watchlist → Slack alert → emit event |
| [`run_bi_pulse.py`](apps/ai/src/orchestration/run_bi_pulse.py) | PulseAgent → Slack notification → emit event |
| [`run_ops_watch.py`](apps/ai/src/orchestration/run_ops_watch.py) | PulseAgent → AnomalyAgent → Slack alert → emit event |
| [`run_investor_update.py`](apps/ai/src/orchestration/run_investor_update.py) | Relationship health check → InvestorAgent → Slack → emit event |
| [`run_weekly_synthesis.py`](apps/ai/src/orchestration/run_weekly_synthesis.py) | Metrics + Alerts + Decisions + Investor state → Synthesize brief → Slack |

**Pattern**: Each orchestration function follows the same structure:
```python
async def run_X(tenant_id: str) -> dict[str, Any]:
    run_id = str(uuid4())
    result = {"run_id": run_id, "tenant_id": tenant_id, "ok": True}
    
    # Step 1: Run agent
    try:
        agent_result = await run_some_agent(tenant_id)
        result["agent_result"] = agent_result
    except Exception as e:
        log.error(f"Agent failed: {e}")
        result["ok"] = False
        return result
    
    # Step 2: Send notification
    try:
        await send_slack_message(message)
    except Exception as e:
        log.warning(f"Slack failed: {e}")
    
    # Step 3: Emit completion event
    await emit("X.completed", tenant_id, {"run_id": run_id})
    
    return result
```

### Memory System — [`src/memory/`](apps/ai/src/memory/)

| File | Purpose |
|------|---------|
| [`qdrant_ops.py`](apps/ai/src/memory/qdrant_ops.py) | `QdrantMemoryManager` — upsert, search, decay, expire memories |
| [`working.py`](apps/ai/src/memory/working.py) | Short-term working memory |
| [`episodic.py`](apps/ai/src/memory/episodic.py) | Episode-based memory (events over time) |
| [`semantic.py`](apps/ai/src/memory/semantic.py) | Semantic/factual memory |
| [`compressed.py`](apps/ai/src/memory/compressed.py) | Compressed summaries of old memories |
| [`procedural.py`](apps/ai/src/memory/procedural.py) | Procedural/how-to memory |
| [`spine.py`](apps/ai/src/memory/spine.py) | Core identity memory |
| [`rag_kernel.py`](apps/ai/src/memory/rag_kernel.py) | RAG retrieval kernel |
| [`state_manager.py`](apps/ai/src/memory/state_manager.py) | State management across memory types |
| [`compressor.py`](apps/ai/src/memory/compressor.py) | Memory compression logic |

**Memory maintenance** (weekly):
- Decay: Reduce weight of old memories by 15% per week
- Expire: Remove memories older than threshold with low weight
- Optimize: Clean up Qdrant index performance

### Learning/Feedback — [`src/learning/`](apps/ai/src/learning/)

| File | Purpose |
|------|---------|
| [`feedback_consumer.py`](apps/ai/src/learning/feedback_consumer.py) | Reads feedback events from Redpanda, adjusts thresholds |

**Feedback loop**:
```
Slack button click → Go handler → Redpanda → Python FeedbackConsumer → 
Adjust anomaly thresholds → Next alert uses new thresholds
```

### Guardian — [`src/guardian/`](apps/ai/src/guardian/)

| File | Purpose |
|------|---------|
| [`watchlist.py`](apps/ai/src/guardian/watchlist.py) | Compliance watchlist checks |
| [`detector.py`](apps/ai/src/guardian/detector.py) | Anomaly/pattern detection |
| [`insight_builder.py`](apps/ai/src/guardian/insight_builder.py) | Build insights from detected patterns |

### Database Layer — [`src/db/`](apps/ai/src/db/)

| File | Purpose |
|------|---------|
| [`agent_outputs.py`](apps/ai/src/db/agent_outputs.py) | Persist agent results |
| [`compliance.py`](apps/ai/src/db/compliance.py) | Compliance records |
| [`contracts.py`](apps/ai/src/db/contracts.py) | Contract data |
| [`forecast.py`](apps/ai/src/db/forecast.py) | Financial forecasts |
| [`hitl_actions.py`](apps/ai/src/db/hitl_actions.py) | Human-in-the-loop action records |
| [`people.py`](apps/ai/src/db/people.py) | People/HR data |
| [`policy.py`](apps/ai/src/db/policy.py) | Policy records |
| [`raw_events.py`](apps/ai/src/db/raw_events.py) | Raw event storage |
| [`saas.py`](apps/ai/src/db/saas.py) | SaaS metrics |
| [`transactions.py`](apps/ai/src/db/transactions.py) | Financial transactions |
| [`hiring.py`](apps/ai/src/db/hiring.py) | Hiring pipeline data |
| [`investor_relationships.py`](apps/ai/src/db/investor_relationships.py) | Investor CRM data |

### Activities (Temporal) — [`src/activities/`](apps/ai/src/activities/)

Activities are the **unit of work** in Temporal workflows. Each is decorated with `@activity.defn`:

| File | Purpose |
|------|---------|
| [`run_pulse_agent.py`](apps/ai/src/activities/run_pulse_agent.py) | Run PulseAgent |
| [`run_anomaly_agent.py`](apps/ai/src/activities/run_anomaly_agent.py) | Run AnomalyAgent |
| [`run_investor_agent.py`](apps/ai/src/activities/run_investor_agent.py) | Run InvestorAgent |
| [`run_qa_agent.py`](apps/ai/src/activities/run_qa_agent.py) | Run QAAgent |
| [`run_guardian_watchlist.py`](apps/ai/src/activities/run_guardian_watchlist.py) | Run Guardian watchlist |
| [`send_slack_message.py`](apps/ai/src/activities/send_slack_message.py) | Send Slack notification |
| [`send_telegram.py`](apps/ai/src/activities/send_telegram.py) | Send Telegram message |
| [`log_decision.py`](apps/ai/src/activities/log_decision.py) | Log founder decision to Postgres + Qdrant |
| [`check_cold_candidates.py`](apps/ai/src/activities/check_cold_candidates.py) | Find candidates not contacted recently |
| [`check_relationship_health.py`](apps/ai/src/activities/check_relationship_health.py) | Check investor relationship warmth |
| [`synthesize_weekly_brief.py`](apps/ai/src/activities/synthesize_weekly_brief.py) | LLM synthesis of weekly data |
| [`memory_maintenance.py`](apps/ai/src/activities/memory_maintenance.py) | Decay, expire, optimize memories |

### Workflows (Temporal) — [`src/workflows/`](apps/ai/src/workflows/)

Workflows orchestrate activities with Temporal's durability guarantees:

| File | Purpose |
|------|---------|
| [`pulse_workflow.py`](apps/ai/src/workflows/pulse_workflow.py) | PulseAgent workflow |
| [`investor_workflow.py`](apps/ai/src/workflows/investor_workflow.py) | InvestorAgent workflow |
| [`qa_workflow.py`](apps/ai/src/workflows/qa_workflow.py) | QAAgent workflow |
| [`self_analysis_workflow.py`](apps/ai/src/workflows/self_analysis_workflow.py) | Self-analysis workflow |
| [`eval_loop_workflow.py`](apps/ai/src/workflows/eval_loop_workflow.py) | Evaluation loop workflow |
| [`compression_workflow.py`](apps/ai/src/workflows/compression_workflow.py) | Memory compression workflow |
| [`weight_decay_workflow.py`](apps/ai/src/workflows/weight_decay_workflow.py) | Memory weight decay workflow |
| [`memory_maintenance_workflow.py`](apps/ai/src/workflows/memory_maintenance_workflow.py) | Weekly memory maintenance |

---

## 5. DUAL EVENT SYSTEM — THE TRICKY PART

The codebase has **two event systems** running in parallel:

### Redpanda (Go-side)
- Used by Go core for: webhook events, feedback events, Slack command proxy
- Go publishes → Go consumes (Temporal signals)
- Go publishes → Python consumes (feedback_worker.py)
- Topic: `feedback-events`

### Redis Streams (Python-side)
- Used by Python for: agent completion events, orchestration events
- Python publishes → Python consumes
- Stream key: `sarthi:{tenant_id}:{topic}`
- Consumer groups for ordered processing

**Why two?** Redpanda is the "enterprise" event bus for cross-service communication.
Redis Streams is the lightweight alternative for Python-internal events.
They coexist without conflict because they serve different purposes.

---

## 6. DUAL SCHEDULING — ANOTHER TRICKY PART

### Temporal Workflows (durable, long-running)
- Used for: PulseWorkflow, InvestorWorkflow, QAWorkflow, memory maintenance
- Registered in: `src/worker.py`
- Task queue: `SARTHI-MAIN-QUEUE`
- Pros: Durable, replayable, visible in Temporal Web UI
- Cons: Heavier, requires Temporal server running

### APScheduler (lightweight, cron-like)
- Used for: finance_guardian, bi_pulse, ops_watch, investor_update, weekly_synthesis
- Registered in: `src/scheduler/sarthi_scheduler.py`
- Job store: PostgreSQL (SQLAlchemyJobStore)
- Pros: Simple, no Temporal dependency, good for periodic jobs
- Cons: Not durable across restarts (depends on job store), no replay

**When to use which?**
- Need durability + replay + signals? → Temporal
- Just need "run this every 6 hours"? → APScheduler

---

## 7. KEY PATTERNS TO UNDERSTAND

### Pattern 1: LangGraph Agent

Every agent follows this structure:

```python
# state.py — Define the state
@dataclass
class MyAgentState:
    tenant_id: str
    input_data: dict
    output: Optional[str] = None

# graph.py — Build the graph
def build_graph() -> StateGraph:
    graph = StateGraph(MyAgentState)
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_edge("step1", "step2")
    graph.set_entry_point("step1")
    graph.set_finish_point("step2")
    return graph.compile()

# nodes.py — Implement nodes
def step1_node(state: MyAgentState) -> dict:
    # Do work, return partial state update
    return {"output": "result"}

# prompts.py — LLM templates
STEP1_PROMPT = """You are a finance analyst..."""
```

### Pattern 2: Temporal Activity

```python
@activity.defn(name="my_activity")
async def my_activity(tenant_id: str, param: str) -> dict[str, Any]:
    if not tenant_id:
        return {"ok": False, "error": "tenant_id required"}
    try:
        result = do_work(tenant_id, param)
        return {"ok": True, "data": result}
    except Exception as e:
        log.error(f"Activity failed: {e}")
        return {"ok": False, "error": str(e)}
```

**Convention**: Always return `{"ok": bool, ...}`. Never raise from an activity unless it's truly unrecoverable.

### Pattern 3: Orchestration Function

```python
async def run_X(tenant_id: str) -> dict[str, Any]:
    run_id = str(uuid4())
    result = {"run_id": run_id, "tenant_id": tenant_id, "ok": True}
    
    try:
        agent_result = await run_agent(tenant_id)
        result["agent_result"] = agent_result
    except Exception as e:
        await send_slack_message(f"❌ Failed: {e}")
        result["ok"] = False
        return result
    
    await emit("X.completed", tenant_id, {"run_id": run_id})
    return result
```

### Pattern 4: Go HTTP Handler

```go
func (h *Handler) HandleX(c *fiber.Ctx) error {
    // 1. Parse request
    var req XRequest
    if err := c.BodyParser(&req); err != nil {
        return c.Status(fiber.StatusBadRequest).JSON(map[string]string{"error": "Invalid"})
    }
    
    // 2. Idempotency check
    if key := c.Get("X-Delivery-ID"); key != "" {
        isNew, _ := h.repo.SetIdempotencyKey(ctx, key, "source", 24*time.Hour)
        if !isNew { return c.JSON(map[string]string{"status": "already_processed"}) }
    }
    
    // 3. Publish to Redpanda
    data, _ := json.Marshal(event)
    h.redpandaClient.Publish(data)
    
    // 4. Return accepted
    return c.Status(fiber.StatusAccepted).JSON(XResponse{ID: id, Status: "accepted"})
}
```

### Pattern 5: Tenant Isolation

Every function that touches data takes `tenant_id` as its first parameter.
Every Qdrant query filters by `tenant_id`. Every SQL query has `WHERE tenant_id = %s`.

---

## 8. DATABASE TABLES

Key tables across the system:

| Table | Purpose | Used By |
|-------|---------|---------|
| `mission_states` | Per-tenant finance/BI/ops state | Session layer, CoFounder router |
| `session_messages` | Conversation history | Session context |
| `decisions` | Founder decisions log | `/sarthi decide`, weekly synthesis |
| `investor_relationships` | Investor CRM with warm_up_days | InvestorAgent, relationship health |
| `agent_outputs` | Persisted agent results | BaseAgent._write_agent_output() |
| `hitl_actions` | Human-in-the-loop records | BaseAgent (when fire_telegram=True) |
| `pattern_thresholds` | Per-tenant anomaly thresholds | FeedbackConsumer, thresholds.py |
| `agent_feedback` | Raw feedback events | Feedback loop |
| `finance_snapshots` | Financial KPI snapshots | Weekly synthesis |
| `agentalerts` | Alert history | Weekly synthesis |

---

## 9. CONFIGURATION

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql://sarthi:sarthi@localhost:5432/sarthi` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis for event bus |
| `TEMPORAL_HOST` | `localhost:7233` | Temporal server |
| `AZURE_OPENAI_ENDPOINT` | — | Azure AI Foundry LLM |
| `AZURE_OPENAI_API_KEY` | — | Azure API key |
| `GROQ_API_KEY` | — | Groq LLM provider |
| `OPENAI_API_KEY` | — | OpenAI provider |
| `OLLAMA_BASE_URL` | — | Local Ollama provider |
| `SLACK_BOT_TOKEN` | — | Slack Bot OAuth token |
| `SLACK_APP_TOKEN` | — | Slack Socket Mode token |
| `USE_APSCHEDULER` | `false` | Enable APScheduler mode |
| `ACTIVE_TENANTS` | `default` | Comma-separated tenant IDs for scheduler |

### LLM Auto-Detection — [`src/config/llm.py`](apps/ai/src/config/llm.py)

The system auto-detects which LLM provider to use based on which env vars are set.
Priority: Azure → Groq → OpenAI → Ollama

---

## 10. HOW TO ADD A NEW AGENT

Step-by-step guide to adding a new agent:

### 1. Create agent directory
```
apps/ai/src/agents/my_agent/
├── __init__.py
├── state.py      # MyAgentState dataclass
├── graph.py      # LangGraph StateGraph
├── nodes.py      # Node functions
└── prompts.py    # LLM templates
```

### 2. Define state (state.py)
```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class MyAgentState:
    tenant_id: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    output: Optional[str] = None
    error: Optional[str] = None
```

### 3. Build graph (graph.py)
```python
from langgraph.graph import StateGraph
from src.agents.my_agent.state import MyAgentState
from src.agents.my_agent.nodes import step1_node, step2_node

def build_graph():
    graph = StateGraph(MyAgentState)
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_edge("step1", "step2")
    graph.set_entry_point("step1")
    graph.set_finish_point("step2")
    return graph.compile()
```

### 4. Create activity (activities/run_my_agent.py)
```python
from temporalio import activity

@activity.defn(name="run_my_agent")
async def run_my_agent(tenant_id: str) -> dict[str, Any]:
    from src.agents.my_agent.graph import build_graph
    graph = build_graph()
    result = await graph.ainvoke({"tenant_id": tenant_id, ...})
    return {"ok": True, "output": result.get("output")}
```

### 5. Register in worker (worker.py)
```python
from src.activities.run_my_agent import run_my_agent
# Add to activities list
```

### 6. Create orchestration (orchestration/run_my_agent.py)
```python
async def run_my_agent_job(tenant_id: str) -> dict[str, Any]:
    result = await run_my_agent(tenant_id)
    await send_slack_message(result["output"])
    await emit("my_agent.completed", tenant_id, {...})
    return result
```

### 7. Add to scheduler (if periodic)
```python
# In sarthi_scheduler.py
scheduler.add_job(
    run_my_agent_job,
    trigger=IntervalTrigger(hours=X),
    args=[tenant_id],
    id=f"my_agent_{tenant_id}",
    replace_existing=True,
)
```

---

## 11. TESTING

### Python Tests — [`apps/ai/tests/`](apps/ai/tests/)

| File | What it tests |
|------|--------------|
| [`test_agent_logic.py`](apps/ai/tests/test_agent_logic.py) | Agent result validation, tone checks |
| [`test_embeddings.py`](apps/ai/tests/test_embeddings.py) | Embedding generation |
| [`test_event_dictionary.py`](apps/ai/tests/test_event_dictionary.py) | Event type mapping |
| [`test_event_envelope.py`](apps/ai/tests/test_event_envelope.py) | Event envelope serialization |
| [`test_grpc_server.py`](apps/ai/tests/test_grpc_server.py) | gRPC server functionality |
| [`test_llm_connectivity.py`](apps/ai/tests/test_llm_connectivity.py) | LLM provider connections |
| [`test_qdrant.py`](apps/ai/tests/test_qdrant.py) | Qdrant vector operations |
| [`test_sandbox_client.py`](apps/ai/tests/test_sandbox_client.py) | Sandbox execution |
| [`test_tone_filter.py`](apps/ai/tests/test_tone_filter.py) | Jargon detection |

### Go Tests

```bash
cd apps/core
go test ./...                    # All tests
go test ./internal/agents/...    # Agent tests
go test ./internal/htmx/...      # HTMX route tests
```

### Running Python Tests

```bash
cd apps/ai
uv run pytest tests/ -v          # All tests
uv run pytest tests/test_agent_logic.py -v  # Specific file
```

---

## 12. COMMON GOTCHAS

1. **Two event buses**: Redpanda (Go) and Redis Streams (Python). Don't mix them.
2. **Two schedulers**: Temporal (durable) and APScheduler (lightweight). Choose based on need.
3. **psycopg2 vs asyncpg**: Some files use sync `psycopg2` (weekly_synthesis), others use async. This is a known inconsistency.
4. **Tenant isolation**: Always pass `tenant_id` as first param. Always filter DB queries by it.
5. **Qdrant datetime**: Store as float timestamps, not ISO strings. The system had a bug with this before.
6. **ReAct loop**: QAAgent can loop forever without the MAX_TOOL_CALLS guard.
7. **Continue-As-New**: OntologyAIRouter must restart after 1000 events or Temporal will error.
8. **Graceful degradation**: Both Go and Python start even if dependencies are down. Check logs for "Warning:" messages.
9. **Slack command proxy**: Go proxies `/sarthi decide` to Python. If Redpanda is down, it falls back to HTTP.
10. **Feedback loop is async**: Button clicks → Redpanda → Python consumer. There's a delay before thresholds update.

---

## 13. QUICK REFERENCE: WHERE IS X?

| Question | Answer |
|----------|--------|
| Where are HTTP routes defined? | [`apps/core/cmd/server/main.go`](apps/core/cmd/server/main.go:124-194) |
| Where are Temporal workflows registered (Go)? | [`apps/core/cmd/worker/main.go`](apps/core/cmd/worker/main.go:52-94) |
| Where are Temporal workflows registered (Python)? | [`apps/ai/src/worker.py`](apps/ai/src/worker.py:51-59) |
| Where is the event routing table? | [`apps/core/internal/workflow/sarthi_router.go`](apps/core/internal/workflow/sarthi_router.go:28-105) |
| Where are anomaly thresholds? | [`apps/ai/src/agents/anomaly/thresholds.py`](apps/ai/src/agents/anomaly/thresholds.py) |
| Where is the feedback consumer? | [`apps/ai/src/learning/feedback_consumer.py`](apps/ai/src/learning/feedback_consumer.py) |
| Where is the Slack bot? | [`apps/ai/src/slackbot.py`](apps/ai/src/slackbot.py) |
| Where is the gRPC interface? | [`apps/ai/src/grpc_server.py`](apps/ai/src/grpc_server.py) |
| Where is the Redis event bus? | [`apps/ai/src/events/bus.py`](apps/ai/src/events/bus.py) |
| Where is the scheduler? | [`apps/ai/src/scheduler/sarthi_scheduler.py`](apps/ai/src/scheduler/sarthi_scheduler.py) |
| Where is the mission state? | [`apps/ai/src/session/mission_state.py`](apps/ai/src/session/mission_state.py) |
| Where is the relevance gate? | [`apps/ai/src/session/relevance_gate.py`](apps/ai/src/session/relevance_gate.py) |
| Where is the base agent? | [`apps/ai/src/agents/base.py`](apps/ai/src/agents/base.py) |
| Where is Qdrant memory manager? | [`apps/ai/src/memory/qdrant_ops.py`](apps/ai/src/memory/qdrant_ops.py) |
| Where are DB migrations? | [`infra/migrations/`](infra/migrations/) + [`apps/ai/src/session/001_session_layer.sql`](apps/ai/src/session/001_session_layer.sql) |
| Where is LLM config? | [`apps/ai/src/config/llm.py`](apps/ai/src/config/llm.py) |

---

## 14. COMPONENT GRAPH: RUNTIME DEPENDENCY FLOW

### Infrastructure Layer
```
Docker Compose (docker-compose.yml) → 
├── PostgreSQL:5433 (structured data)
├── Qdrant:6333 (vector memory)
├── Redis:6379 (working memory/sessions)
├── Redpanda:9094 (event bus)
├── Temporal:7233 (workflow orchestration)
├── Prometheus:9090 (metrics)
├── Grafana:3001 (dashboards)
└── Jaeger:16686 (tracing)
```

### Application Layer Data Flow
```
External Events (Slack/Discord/Webhooks) →
Go Gateway (apps/core:3000) →
├── Redpanda Events → Python AI Worker (apps/ai)
├── PostgreSQL (structured persistence)
├── Temporal Workflows (orchestration)
└── HTMX UI (founder dashboard)

Python AI Worker →
├── LangGraph Agents (pulse/anomaly/investor/qa)
├── Memory Spine (5-layer: Redis→Qdrant→Graphiti→PostgreSQL→Qdrant)
├── Guardian Watchlist (17 failure patterns)
├── Temporal Activities (durable execution)
└── Slack/Telegram Delivery
```

### Configuration Dependencies
```
.env → docker-compose.yml → service containers
apps/ai/pyproject.toml → Python dependencies
apps/core/go.mod → Go dependencies
config/otel/collector.yaml → OpenTelemetry tracing
infra/migrations/*.sql → PostgreSQL schema
scripts/demo_seed.py → synthetic data seeding
```

### Runtime Data Flow
```
1. Webhook → Go Fiber Handler → Event Envelope → Redpanda
2. Redpanda → Temporal Signal → Workflow Execution
3. Workflow → Python Activity → LangGraph Agent
4. Agent → Memory Spine → Qdrant/PostgreSQL/Redis
5. Agent Result → Slack Block Kit → Founder Notification
6. Feedback Button → Go Handler → Redpanda → Python Consumer → Threshold Adjustment
```

---

## 15. HIDDEN COUPLING: CROSS-FOLDER DEPENDENCIES

### Critical Hidden Couplings Identified:

1. **Event Schema Coupling**:
   - `apps/core/internal/events/envelope.go` defines EventEnvelope struct
   - `apps/ai/src/schemas/event_envelope.py` must match exactly
   - **Risk**: Changing Go struct breaks Python deserialization

2. **Database Schema Coupling**:
   - `infra/migrations/*.sql` defines PostgreSQL schema
   - `apps/ai/src/db/*.py` assumes specific table structures
   - `apps/core/internal/db/queries/*.sql` uses same tables
   - **Risk**: Migration changes can break both Go and Python queries

3. **Temporal Task Queue Coupling**:
   - `apps/core/cmd/worker/main.go` publishes to "SARTHI-MAIN-QUEUE"
   - `apps/ai/src/worker.py` consumes from same queue
   - **Risk**: Queue name changes break cross-service communication

4. **gRPC Protocol Coupling**:
   - `proto/ai/v1/*.proto` defines service interface
   - `gen/go/ai/` and `gen/python/ai/` generated code must stay in sync
   - **Risk**: Proto changes require regeneration in both languages

5. **Memory Collection Coupling**:
   - `apps/ai/src/setup/init_qdrant_collections.py` creates collections
   - `apps/ai/src/memory/*.py` assumes specific collection names/schemas
   - **Risk**: Collection schema changes break memory operations

6. **Configuration Coupling**:
   - `docker-compose.yml` service names hardcoded in connection strings
   - `apps/ai/src/config/config_module.py` assumes specific hostnames
   - **Risk**: Service renames break internal networking

### Dependency Matrix:
```
apps/core/internal/events/ ←→ apps/ai/src/schemas/
apps/core/internal/db/ ←→ infra/migrations/ ←→ apps/ai/src/db/
apps/core/cmd/worker/ ←→ apps/ai/src/worker.py
proto/ ←→ gen/go/ ←→ gen/python/
config/ ←→ apps/*/src/config/
scripts/demo_seed.py ←→ infra/migrations/ ←→ apps/ai/src/memory/
```

---

## 16. CONTEXT INTEGRITY CHECK

### Files Evaluated:
I successfully analyzed the following key files and directories:

**Root Level:**
- docker-compose.yml, Makefile, README.md, CODEBASE_WALKTHROUGH.md
- .env.example, pytest.ini, buf.yaml, render.yaml

**Apps Structure:**
- apps/ai/src/ (complete directory tree with 200+ files)
- apps/core/ (complete directory tree with 100+ files)
- apps/swarm-chat/, apps/swarm-repo/, apps/sandbox/

**Configuration:**
- config/otel/collector.yaml, config/prometheus/, config/grafana/
- infra/migrations/*.sql, k8s/helm/, docker/

**Scripts & Tools:**
- scripts/ (40+ shell/Python scripts)
- playwright/ (E2E tests), mockoon/ (API mocking)

**Generated Code:**
- gen/go/, gen/python/, proto/

**Documentation:**
- docs/decisions/ (6 ADRs), docs/*.md

### OMITTED FILES:
Due to the comprehensive nature of this codebase (1000+ files), the following were not individually examined but their structure was captured:

**Binary/Generated Content:**
- .mypy_cache/, __pycache__/, node_modules/ equivalent directories
- Compiled binaries in apps/core/bin/
- Docker build contexts and temporary files

**Large External Dependencies:**
- signoz-install/ (complete SigNoz installation - 500+ files)
- Frontend assets in signoz-install/frontend/
- Third-party configuration templates

**Test Artifacts:**
- playwright/test-results/, playwright/playwright-report/
- Individual test output files and screenshots

**Development Tools:**
- .qodo/, .zencoder/, .zenflow/ (AI coding assistant configs)
- IDE-specific configuration files

All critical runtime dependencies, configuration files, source code, and architectural components were successfully analyzed. The omitted files are primarily build artifacts, external tools, and generated content that don't affect the core system architecture or runtime dependencies.