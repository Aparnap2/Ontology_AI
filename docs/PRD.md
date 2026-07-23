# OntologyAI Workspace

> **Source of Truth:** This file is the canonical PRD. Archived superseded versions live in `archive/`.

OntologyAI Workspace is an enterprise-focused AI operations workspace that turns messy business evidence into a shared business map, surfaces operational truth, and drafts governed workflow pilots for review and deployment planning. It is designed as a self-serve FDE companion and a multi-agent FDE operating system, not a small-business dashboard, generic chatbot, or no-code automation builder.

## Product position

OntologyAI Workspace is best understood as an enterprise **ops twin** and guided pilot-building environment. The platform converts raw evidence from conversations, uploads, exports, and connected tools into typed operational objects, diagnoses what is stuck or risky, and generates governed workflow drafts plus handoff artifacts.

### One-line pitch

OntologyAI Workspace turns messy enterprise operations into a shared business map, reveals what is broken, and drafts governed workflows teams can review, approve, and pilot.

### What it is

- A self-serve FDE companion for enterprise discovery and pilot design.
- A shared workspace for evidence intake, ontology review, operational truth, approvals, and exports.
- An ontology-first AI operating layer with deterministic validation and governance controls.
- A portfolio-grade demonstration of the Forward Deployed Engineer method as software.

### What it is not

- A founder alert bot.
- A finance-only assistant.
- A passive dashboard.
- A generic no-code builder.
- An unconstrained autonomous action engine.
- A small-business utility bundle built around a few lightweight API add-ons.

---

## Table of Contents

```
├── 1. Executive Summary
├── 2. V4.0 Evolution
├── 3. V3.0 Implementation Status - Chief of Staff (Legacy)
├── 4. Problem Statement
├── 5. Solution Overview
├── 6. The 6 Agents (V1-3) + 3 Specialist Agents (V4)
├── 7. Chief of Staff Features (V3.0 Legacy)
│   ├── 7.1 Decision Journal
│   ├── 7.2 Weekly Synthesis
│   ├── 7.3 Investor Relations
│   ├── 7.4 CommsTriage
│   └── 7.5 HiringAgent
├── 8. Guardian Watchlist (17 Patterns — V2.0 Legacy)
│   ├── 8.1 Finance Guardian (FG-01 to FG-06)
│   ├── 8.2 BI Guardian (BG-01 to BG-06)
│   └── 8.3 Ops Guardian (OG-01 to OG-05)
├── 9. Memory Spine (5 Layers — V2.0 Legacy)
├── 10. RAG Kernel (≤800 Token Context Assembly)
├── 11. HITL Manager (3-Tier Routing + Temporal Signals)
├── 12. LLMOps (Langfuse, Eval Loop, Self-Analysis)
├── 13. Temporal Workflows (12 Total)
├── 14. System Architecture (V4.0)
├── 15. Low-Level Design (V4.0)
├── 16. Workflows & SOP
├── 17. Test Strategy
├── 18. Deployment
├── 19. Build Checklist
├── 20. Metrics & KPIs
└── 21. Timeline + Demo Script (V4.0)
```

---

---

## 2. V4.0 Evolution — Chat/SSE/Specialist Architecture

### Summary of Changes

| Decision | Before (V3.x) | After (V4.0) | Benefit |
|----------|--------------|--------------|---------|
| **Chat UI** | Raw JS EventSource + client-side DOM building | HTMX `hx-ext="sse"` with server-rendered HTML fragments | ~40 fewer lines of JS, auto-reconnect, XSS-safe |
| **Workflow Dispatch** | Synchronous `run.Get()` blocking HTTP handler | Goroutine + `tryBroadcast()` SSE push | No 60s timeout, immediate "Thinking..." feedback |
| **Mention Routing** | `if-else` chain growing with each specialist | `map[string]specialistRoute` O(1) lookup | Adding specialist = 1 map entry + 1 Python class |
| **HITL Approval** | UI-only — buttons did not signal workflows | `SignalWorkflow("hitl-approval")` unblocks `AwaitWithTimeout` | End-to-end working HITL |
| **Mission State** | No write path — dashboard polled stale data | `POST /api/mission-state` from Python AI | Real-time state from LLM to dashboard |
| **Chat Bubbles** | Client-rendered via JS template strings | `renderChatBubble()` server-side with `html.EscapeString()` | Single source of HTML truth, XSS-safe |
| **Dead Stubs** | 50 lines of placeholder types in `stubs.go` | Cleaned to 10 lines, only real convenience types | No confusion between stub and real implementation |

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser (HTMX)                                  │
│  ┌──────────────────────────┐    ┌───────────────────────────────┐          │
│  │  command_chat.html        │    │  command_approvals.html       │          │
│  │  hx-ext="sse"             │    │  Approve / Hold buttons      │          │
│  │  sse-connect="/api/...    │    │  → Temporal Signal           │          │
│  └──────────┬────────────────┘    └───────────┬───────────────────┘          │
│             │ SSE event:chat                   │ POST approve/hold            │
└─────────────┼──────────────────────────────────┼─────────────────────────────┘
              │                                  │
              ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Go Core (Fiber v2)                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Handler ← chatBroadcast ← temporal ← wg                             │   │
│  │  SSE endpoint (SetBodyStreamWriter) → specialistRoutes map           │   │
│  │  → goroutine dispatch → tryBroadcast() for SSE push                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  API Routes: /api/command/chat/events (SSE) · /api/command/chat/send       │
│  /api/command/approvals/:id/approve · /api/mission-state · 10+ dashboard   │
└─────────────────────────────┬───────────────────────────────────────────────┘
              │ Temporal ExecuteWorkflow / SignalWorkflow
              ▼
┌─────────────────────────────┐    ┌──────────────────────────────────────────┐
│  Temporal Server             │    │  PostgreSQL                                │
│  QAWorkflow · FinanceWorkflow│    │  mission_state · planned_actions           │
│  DataWorkflow · OpsWorkflow  │    │  chat_messages · agent_traces             │
│  CommsWorkflow · HiringWorkflow│   │                                          │
│  Signal: "hitl-approval"     │    └──────────────────────────────────────────┘
└──────┬──────────────────────┘                    ▲
       │ Temporal Task Queue                       │ POST
       ▼                                           │
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Python AI Worker (Specialist Agents)                        │
│  FinanceWorkflow → FinanceGraph · DataWorkflow → DataGraph                    │
│  OpsWorkflow → OpsGraph · CommsWorkflow → CommsGraph                         │
│  → Writes: mission_state, planned_actions, agent_traces                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow: Chat → Specialist → SSE Result

```
User types "@finance Q3 revenue?" → HTMX POST /api/command/chat/send
  → Go Handler extracts @mentions → matches "@finance" in specialistRoutes
  → tryBroadcast() → "🤔 Thinking..." → SSE → Browser
  → go func() with WaitGroup:
      → Temporal ExecuteWorkflow("FinanceWorkflow", input)
      → Python FinanceWorkflow.run() → FinanceGraph.invoke() → LLM
      → run.Get() → renderChatBubble() → tryBroadcast() → SSE
```

### Data Flow: HITL Approval via Temporal Signal

```
Agent proposes action → INSERT planned_actions (status=pending)
  → Temporal workflow reaches AwaitWithTimeout("hitl-approval", 48h)
  → User clicks "Approve" → POST /api/command/approvals/{workflow_id}/approve
  → SignalWorkflow(workflowID, "hitl-approval", true)
  → Workflow unblocks, continues execution
```

> Full architecture decisions documented in [ADR-001: OntologyAI v4.0 Architecture Evolution](../.opencode/context/adr/001-sarthi-v4-architecture-evolution.md)

---

## 3. V3.0 Implementation Status - Chief of Staff (Legacy)

All Chief of Staff features are complete:

| Feature | Description | Files | Status |
|---------|-------------|-------|--------|
| **Decision Journal** | Slack modal to log decisions, Postgres + Qdrant storage, semantic search | `log_decision.py`, `slack_client.py`, `010_decisions.sql` | ✅ |
| **Weekly Synthesis** | Monday morning brief combining metrics, alerts, decisions, investor status | `synthesize_weekly_brief.py`, ChiefOfStaffWorkflow | ✅ |
| **Investor Relations** | Track investor relationships, warmup alerts, interaction history | `011_investor_relationships.sql`, `investor_relationships.py`, `check_relationship_health.py` | ✅ |
| **CommsTriage** | Daily Slack channel triage — classify messages by urgency/action items | `agents/comms/`, `run_comms_triage_agent.py` | ✅ |
| **HiringAgent** | Score candidates, track pipeline, cold candidate alerts | `agents/hiring/`, `run_hiring_agent.py`, `012_hiring.sql` | ✅ |

### V2.0 Status (Preserved)

| Step | Description | Status | Tests |
|------|-------------|--------|-------|
| **1** | Infrastructure swap (Redis added, Neo4j removed) | ✅ | — |
| **2** | Guardian watchlist (17 patterns: 6 Finance, 6 BI, 5 Ops) | ✅ | 28 new |
| **3** | Memory spine Protocol + write_all (5 layers) | ✅ | 30 new |
| **4** | LLMOps: tracer + eval_loop + self_analysis | ✅ | 10 new |
| **5** | HITL manager + confidence scoring | ✅ | 11 new |
| **6** | GuardianInsight DSPy signature (additive) | ✅ | — |
| **7** | Wire RAG kernel into all agents (fallback contract) | ✅ | — |
| **8** | DB migrations (5 new tables/columns, additive only) | ✅ | — |
| **9** | New Qdrant collections (compressed_memory, founder_blindspots) | ✅ | — |
| **10** | 4 new Temporal workflows (SelfAnalysis, EvalLoop, Compression, WeightDecay) | ✅ | — |
| **11** | Extend existing workflows with guardian watchlist | ✅ | — |
| **12** | Full test suite (241+ passing, zero regressions) | ✅ | 241 pass / 6 skip / 0 fail |

**Cumulative test growth:** 119 (V1.0) → 241+ (V2.0) → 250+ (V3.0) → 371+ (V4.0) → 1202+ (V4.2) → **1286+ (V5.1)** = **1167+ new tests since V1.0**, zero regressions.

---

## 4. Problem Statement

Every enterprise organization running operations across 4+ disconnected tools hits the same wall — **context evaporation**. Knowledge lives in tribal memory, spreadsheets, and Slack threads. When teams scale, reorg, or lose headcount, deals fall through, anomalies go unnoticed, and bad decisions compound silently.

**The specific acute pain:**
- "Our infrastructure costs doubled and nobody noticed for weeks."
- "We don't have a single source of truth for current operational state."
- "Why did that customer churn in March? No one documented the context."
- "We spend weeks of manual analysis before we can even draft a new process."

**What exists today and why it fails:**

| Tool | Problem |
|---|---|
| Tableau / Looker | Requires a data team, nobody maintains it |
| PagerDuty alerts | Fire without context or memory of the past |
| CRM / ERP | Manually updated, always stale |
| Spreadsheets | Static, disconnected from live data |

**The gap:** No system exists that ingests evidence from across disconnected tools, models it as a shared business map, diagnoses what is broken, and drafts governed workflow pilots — without requiring a dedicated data or operations engineering team.

---

## 5. Solution Overview

**Core flow (V5.1):**
```
User / Upload / Tool Connect
  → Ontology Workspace (HTMX + Go Fiber)
    → ChiefOfStaff (intent classification)
      → DiscoveryWorkflow (evidence gathering)
        → OntologyMappingWorkflow (typed object materialization)
          → TruthAnalysisWorkflow (diagnostics, blockers)
            → WorkflowBuilderWorkflow (governed draft generation)
              → GovernanceWorkflow (approval routing)
                → Export / Pilot / Handoff
```

**Three pillars (V5.1):**

| Pillar | Description |
|--------|-------------|
| **Understand** | Evidence intake, ontology setup, business map preview |
| **Diagnose** | Truth analysis, blockers, contradictions, missing ownership, risks |
| **Build** | Workflow drafts, governance, approvals, pilot export |

**Cross-pipeline trigger:** Evidence ingested via wizard/upload/conversation → ChiefOfStaff routes to Discovery → OntologyMapping materializes typed objects → TruthAnalysis diagnoses issues → WorkflowBuilder generates draft → Governance approves and routes to export.

**Value delivered:**

| Metric | Before | After |
|---|---|---|
| Cross-tool ops visibility | Spreadsheets + tribal knowledge | Shared business map with provenance |
| Process design cycle | Weeks of manual analysis | Guided wizard + governed draft in days |
| Operational truth | Stale, scattered dashboards | Real-time ontology with lineage |
| Workflow rollout | Ad hoc scripts, no governance | Approved pilot drafts with blast-radius controls |
| Cross-team handoff | Slack threads, lost context | Structured handoff artifacts |

---

## 6. Target Users & ICP

**Primary ICP:**

> Any cross-functional enterprise team or business unit that runs operations across 4+ disconnected tools, has no data engineering or analytics function, has less than ~12 months of clean historical data, and wants one place to see "what's actually true about the business right now" and act on it without hiring an ops/data hire.

| Qualifier | Why It Matters |
|---|---|
| Cross-functional team | Operations span multiple tools — no single source of truth |
| No data engineering | Cannot maintain dashboards or custom ML models |
| < 12 months clean data | Too little history for conventional ML; needs deterministic ontology-first approach |
| Wants actionable truth | Not just dashboards — needs diagnostics, recommendations, and governed action |
| Multi-tenant enterprise | Requires tenant isolation, role-based access, approval routing |

**Explicitly out of V5.1:**
- Small teams that can survive on point integrations alone
- Organizations with mature data engineering and analytics functions
- Teams with > 12 months of clean, well-modeled historical data
- Pure monitoring/observability use cases without operations workflow needs

---

## 7. The 6 Agents (V1-3) + 3 Specialist Agents (V4)

### 1. PulseAgent ✅ COMPLETE
**Status:** Implemented + 20 tests passing (V1.0) + wired with RAG kernel (V2.0)
**Files:** `apps/ai/src/agents/pulse/` (6 files, 1,203 lines)
**Trigger:** Daily 08:00 IST via Temporal
**Nodes:** 7 (fetch_data → retrieve_memory → compute_metrics → generate_narrative → build_slack_message → send_slack → persist_snapshot)
**V2.0 Additions:** RAG kernel context assembly, guardian watchlist integration, memory spine write_all

### 2. AnomalyAgent ✅ COMPLETE
**Status:** Implemented + 15 tests passing (V1.0) + wired with RAG kernel (V2.0)
**Files:** `apps/ai/src/agents/anomaly/` (6 files, 838 lines)
**Trigger:** Conditional (after PulseAgent if anomalies detected)
**Nodes:** 5 (retrieve_anomaly_memory → generate_explanation → generate_action → build_slack_message → send_slack)
**V2.0 Additions:** GuardianInsight DSPy signature, RAG kernel context, HITL routing, memory spine write_all

### 3. InvestorAgent ✅ COMPLETE
**Status:** Implemented + 14/15 tests passing (93%) (V1.0) + wired with RAG kernel (V2.0)
**Files:** `apps/ai/src/agents/investor/` (5 files, 813 lines)
**Trigger:** Weekly Friday 08:00 IST via Temporal
**Nodes:** 5 (fetch_metrics → retrieve_memory → generate_draft → build_slack_message → send_slack)
**V2.0 Additions:** HITL Tier 3 (always requires approval), RAG kernel context, memory spine write_all

### 4. QAAgent ✅ COMPLETE
**Status:** Implemented + 15 tests passing (V1.0) + wired with RAG kernel (V2.0)
**Files:** `apps/ai/src/agents/qa/` (5 files, 955 lines)
**Trigger:** On-demand via Slack message
**Nodes:** 5 (match_question → fetch_data → retrieve_memory → generate_answer → send_slack)
**V2.0 Additions:** RAG kernel context for richer answers, memory spine write_all, decision search tool

### 5. CommsTriageAgent ✅ V3.0 NEW
**Status:** Implemented (V3.0)
**Files:** `apps/ai/src/agents/comms/` (4 files)
**Trigger:** Daily via Temporal workflow
**Nodes:** 4 (fetch_messages → classify_messages → generate_digest → build_slack_message)
**Features:** Slack channel message classification, urgency detection, action item extraction

### 6. HiringAgent ✅ V3.0 NEW
**Status:** Implemented (V3.0)
**Files:** `apps/ai/src/agents/hiring/` (4 files)
**Trigger:** On-demand (candidate application received)
**Nodes:** 5 (load_candidate → fetch_role_requirements → score_candidate → update_pipeline → generate_recommendation)
**Features:** Candidate scoring using DSPy, pipeline stage management, cold candidate alerts

### 7. FinanceAgent ✅ V4.0 NEW — Specialist
**Status:** Implemented (V4.0) — 319 Python tests passing
**Files:** `apps/ai/src/agents/finance/graph.py`, `apps/ai/src/workflows/finance_workflow.py`
**Trigger:** On-demand via @finance mention in chat
**Workflow:** FinanceWorkflow → FinanceGraph → LLM
**Features:** MRR/burn analysis, financial anomaly detection, structured Pydantic output

### 8. DataAgent ✅ V4.0 NEW — Specialist
**Status:** Implemented (V4.0)
**Files:** `apps/ai/src/agents/data/graph.py`, `apps/ai/src/workflows/data_workflow.py`
**Trigger:** On-demand via @data mention in chat
**Workflow:** DataWorkflow → DataGraph → LLM
**Features:** Query, transform, aggregate, export data

### 9. OpsAgent ✅ V4.0 NEW — Specialist
**Status:** Implemented (V4.0)
**Files:** `apps/ai/src/agents/ops/graph.py`, `apps/ai/src/workflows/ops_workflow.py`
**Trigger:** On-demand via @ops mention in chat
**Workflow:** OpsWorkflow → OpsGraph → LLM
**Features:** Deploy monitoring, operational alerting, incident analysis

---

## 8. Chief of Staff Features (V3.0 Legacy)

OntologyAI V3.0 adds **Chief of Staff capabilities** — proactive support for founder operations beyond passive monitoring.

### 7.1 Decision Journal

| Feature | Implementation |
|---------|---------------|
| Slack Modal | `/sarthi decide` command opens modal for decision entry |
| Postgres Storage | `decisions` table with tenant_id, decided, alternatives, reasoning, timestamps |
| Qdrant Index | Semantic search over past decisions |
| QA Integration | QAAgent can now search decision history |

**Database:**
```sql
CREATE TABLE decisions (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    decided TEXT NOT NULL,
    alternatives TEXT,
    reasoning TEXT,
    decided_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 7.2 Weekly Synthesis

| Feature | Implementation |
|---------|---------------|
| ChiefOfStaffWorkflow | Temporal workflow triggered on TIME_TICK_WEEKLY |
| Data Sources | Metrics + Alerts (7 days) + Decisions (7 days) + Investor Status |
| LLM Synthesis | WEEKLY_SYNTHESIS_PROMPT generates 300-word brief |
| Delivery | Slack message with "Ask OntologyAI anything" button |

**Brief Format:**
- 🎯 ONE THING — single most important thing this week
- Numbers first, then narrative
- Max 300 words
- Reference relevant past decisions

### 7.3 Investor Relations

| Feature | Implementation |
|---------|---------------|
| Relationship Tracking | `investor_relationships` table with warmup_days, raise_priority |
| Interaction History | `investor_interactions` table tracking emails, calls, meetings |
| Warmup Alerts | Check relationship health, alert on cold investors |
| InvestorWorkflow Integration | Runs relationship health check before generating update |

**Database:**
```sql
CREATE TABLE investor_relationships (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    investor_name TEXT NOT NULL,
    firm TEXT NOT NULL,
    last_contact_at TIMESTAMP WITH TIME ZONE,
    warm_up_days INTEGER DEFAULT 30,
    raise_priority INTEGER DEFAULT 5,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE investor_interactions (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    investor_id INTEGER REFERENCES investor_relationships(id),
    interaction_type TEXT NOT NULL,
    summary TEXT,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 7.4 CommsTriage

| Feature | Implementation |
|---------|---------------|
| Channel Monitoring | Fetch recent messages from specified Slack channels |
| Classification | DSPy classifier categorizes: urgent, action_required, informational, fyi, meeting_request, external_comm |
| Priority | High/medium/low priority assignment |
| Digest Generation | Daily digest with categorized sections |

**Workflow:**
1. Fetch messages from configured Slack channels
2. Classify each message using DSPy
3. Extract urgent messages and action items
4. Generate digest summary
5. Deliver via Slack

### 7.5 HiringAgent

| Feature | Implementation |
|---------|---------------|
| Candidate Scoring | DSPy CandidateScorer evaluates resume vs role requirements |
| Pipeline Stages | new → screening → interview → offer → hired → rejected |
| Cold Candidate Alerts | Detect candidates not contacted in N days |
| Database | `roles` and `candidates` tables |

**Database:**
```sql
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    requirements TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE candidates (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    role_id INTEGER REFERENCES roles(id),
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    resume_url TEXT,
    source TEXT,
    status TEXT DEFAULT 'new',
    score_overall FLOAT,
    score_technical FLOAT,
    culture_signals TEXT[],
    red_flags TEXT[],
    recommended_action TEXT,
    last_contact_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 9. Guardian Watchlist (17 Patterns — V2.0 Legacy)

OntologyAI watches continuously for 17 seed-stage failure patterns across three domains. No founder needs to know to ask — OntologyAI detects before they know to look.

### 8.1 Finance Guardian (FG-01 to FG-06)

| ID | Pattern | Trigger |
|----|---------|---------|
| FG-01 | `silent_churn_death` | Monthly churn > 3% (→ 36% annual) |
| FG-02 | `burn_multiple_creep` | Net burn / new ARR > 2.0x |
| FG-03 | `customer_concentration_risk` | Top customer > 30% of MRR |
| FG-04 | `runway_compression_acceleration` | Burn growing faster than runway shrinks |
| FG-05 | `failed_payment_cluster` | 3+ failed payments in 7 days |
| FG-06 | `payroll_revenue_ratio_breach` | Payroll > 60% of revenue |

### 8.2 BI Guardian (BG-01 to BG-06)

| ID | Pattern | Trigger |
|----|---------|---------|
| BG-01 | `leaky_bucket_activation` | Signups growing, activation flat or falling |
| BG-02 | `power_user_mrr_masking` | Top 10% users hiding declining avg MRR/customer |
| BG-03 | `feature_adoption_post_deploy_drop` | Feature usage drops after deploy |
| BG-04 | `cohort_retention_degradation` | New cohorts retaining 10%+ worse than prior |
| BG-05 | `nrr_below_100_seed` | NRR < 100% (losing more than expanding) |
| BG-06 | `trial_activation_wall` | Users abandoning at same step repeatedly (>50%) |

### 8.3 Ops Guardian (OG-01 to OG-05)

| ID | Pattern | Trigger |
|----|---------|---------|
| OG-01 | `error_rate_user_segment_correlation` | Errors concentrated in one user segment (>10%) |
| OG-02 | `support_volume_outpacing_growth` | Support tickets growing 1.5x faster than users |
| OG-03 | `cross_channel_bug_convergence` | Same bug in 3+ channels simultaneously |
| OG-04 | `deploy_frequency_collapse` | Deploy frequency drops >50% MoM |
| OG-05 | `infrastructure_unit_economics_divergence` | AWS cost growth > 2x user growth |

---

## 10. Memory Spine (5 Layers — V2.0 Legacy)

OntologyAI's memory compounds with every event. Five layers, each with distinct purpose and TTL:

| Layer | Backend | TTL | Purpose |
|-------|---------|-----|---------|
| **L1** Working | Redis 7 | 1 hour | Current workflow context, session state |
| **L2** Episodic | Qdrant (existing collections) | 90 days → compressed | Raw event history |
| **L3** Semantic | Kuzu (embedded, replaces Neo4j) | Permanent | Relationships between patterns |
| **L4** Procedural | PostgreSQL (existing DB) | Permanent | Learned agent behavior, resolved blindspots, founder feedback |
| **L5** Compressed | Qdrant (new `compressed_memory` collection) | Permanent | Compressed episodic summaries (triggered every 50 writes) |

**Key properties:**
- Each layer implements the `MemoryLayer` Protocol: `read()`, `write()`, `available()`
- `available()` returns `False` gracefully when backing service is unreachable
- `write_all()` iterates all layers; failures are logged, never crash the agent
- Compression: Every 50 episodic writes → `CompressionWorkflow` compresses oldest 30 into L5
- Weight decay: Weekly `WeightDecayWorkflow` applies decay to L2 events older than 60 days (weight < 0.3 → eligible for compression)

---

## 11. RAG Kernel (≤800 Token Context Assembly)

Before every LLM call, the RAG kernel assembles context from all available memory layers:

```
Priority order: compressed (L5) > episodic (L2) > working (L1)
Max tokens: 800 (tiktoken gpt-4o-mini encoding)
Sort: by weight (desc) then recency_score (desc)
Fallback: if any layer fails → skip it; if all fail → return ""
```

**Fallback contract (non-negotiable):**
```python
context = ""
try:
    context = memory_spine.load_context(tenant_id, task, signal, max_tokens=800)
except Exception:
    context = ""  # Agent still runs with empty context
```

This ensures all 241 existing tests pass without a running memory spine.

---

## 12. HITL Manager (3-Tier Routing + Temporal Signals)

Every guardian alert is routed through a 3-tier human-in-the-loop system:

| Tier | Trigger | Action |
|------|---------|--------|
| **1 — AUTO** | Severity: info, Confidence: > 0.85, Pattern: seen before | Send immediately to Slack |
| **2 — SLACK REVIEW** | Severity: warning, Confidence: 0.60–0.85, OR: new pattern | Draft to `#sarthi-review` with [Send Now] [Edit] [Dismiss] buttons |
| **3 — HUMAN OVERRIDE** | Severity: critical, Confidence: < 0.60, OR: investor updates, OR: eval flag | Block send — require explicit human approval |

**Fallback:** If HITL manager is unreachable → default to AUTO (agent never blocks on HITL failure).

---

## 13. LLMOps (Langfuse, Eval Loop, Self-Analysis)

### Langfuse Tracer
- `@traced(agent, signature)` decorator on agent functions
- Zero test impact: pure pass-through when `LANGFUSE_SECRET_KEY` not set
- Records: input, output, tokens, latency, score for every LLM call
- Used to catch LLM drift from guardian tone or number hallucination

### Weekly Eval Loop
- `EvalLoopWorkflow` runs weekly
- Scores each agent on: guardian_score, accuracy_score, tone_score, action_score
- Results stored in `eval_scores` table
- Can flag agents for HITL Tier 3 routing if quality drops

### Agent Self-Analysis
- `SelfAnalysisWorkflow` runs weekly
- Agents review their own alert history and identify patterns
- Outputs: self-correction recommendations, blindspot resolution trends
- Results stored in `resolved_blindspots` table

---

## 14. Temporal Workflows (12 Total)

### Existing (V1.0 — 3 workflows)

| Workflow | Schedule | Description |
|----------|----------|-------------|
| PulseWorkflow | Daily 08:00 IST | Runs PulseAgent → AnomalyAgent (if anomalies found) |
| InvestorWorkflow | Weekly Friday 08:00 IST | Generates investor update draft |
| QAWorkflow | On-demand | Answers founder questions via Slack |

### V2.0 (4 workflows)

| Workflow | Schedule | Description |
|----------|----------|-------------|
| SelfAnalysisWorkflow | Weekly | Agent self-review, trend analysis |
| EvalLoopWorkflow | Weekly | Eval scoring across all agents |
| CompressionWorkflow | Trigger-based (every 50 episodic writes) | Compresses oldest 30 L2 events into L5 summary |
| WeightDecayWorkflow | Weekly | Applies decay to L2 events older than 60 days |

### V3.0 (2 workflows)

| Workflow | Schedule | Description |
|----------|----------|-------------|
| ChiefOfStaffWorkflow | Weekly (TIME_TICK_WEEKLY) | Synthesizes weekly brief from metrics, alerts, decisions |
| CommsTriageWorkflow | Daily | Triage Slack channels and deliver digest |

### V4.0 (3 new specialist workflows)

| Workflow | Schedule | Description |
|----------|----------|-------------|
| FinanceWorkflow | On-demand via @finance | Finance specialist (MRR/burn analysis) via FinanceGraph |
| DataWorkflow | On-demand via @data | Data specialist (query/transform/aggregate) via DataGraph |
| OpsWorkflow | On-demand via @ops | Ops specialist (deploy/monitor/alert) via OpsGraph |

### Activities (12 Total)

| Activity | Version | Description |
|----------|---------|-------------|
| `run_pulse_agent` | V1.0 | Runs PulseAgent |
| `run_anomaly_agent` | V1.0 | Runs AnomalyAgent |
| `run_investor_agent` | V1.0 | Runs InvestorAgent |
| `run_qa_agent` | V1.0 | Runs QAAgent |
| `send_slack_message` | V1.0 | Sends Slack messages |
| `run_guardian_watchlist` | V2.0 | NEW - Runs guardian pattern detection |
| `write_memory_spine` | V2.0 | NEW - Writes to all memory layers |
| `send_slack_review` | V2.0 | NEW - HITL Tier 2 review |
| `log_eval_scores` | V2.0 | NEW - Logs eval scores |
| `log_decision` | V3.0 | NEW - Logs decision to Postgres + Qdrant |
| `synthesize_weekly_brief` | V3.0 | NEW - Generates weekly brief |
| `check_relationship_health` | V3.0 | NEW - Checks investor relationship health |
| `run_comms_triage_agent` | V3.0 | NEW - Runs comms triage |
| `run_hiring_agent` | V3.0 | NEW - Scores candidate |
| `check_cold_candidates` | V3.0 | NEW - Finds cold candidates |
| `run_finance_agent` | V4.0 | NEW - Runs FinanceGraph for financial analysis |
| `run_data_agent` | V4.0 | NEW - Runs DataGraph for data query/transform |
| `run_ops_agent` | V4.0 | NEW - Runs OpsGraph for operational monitoring |

---

## 15. System Architecture (V4.0)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser (HTMX + SSE)                            │
│  ┌──────────────────────────┐    ┌───────────────────────────────┐          │
│  │  command_chat.html        │    │  command_approvals.html       │          │
│  │  hx-ext="sse"             │    │  Approve / Hold buttons      │          │
│  │  sse-connect="/api/...    │    │  → Temporal Signal           │          │
│  └──────────┬────────────────┘    └───────────┬───────────────────┘          │
│             │ SSE event:chat                   │ POST approve/hold            │
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
│  │  └──────┬──────┘  └───────┬───────┘  └──────────────┘                 │   │
│  │         │                 │                                            │   │
│  │  ┌──────▼──────┐  ┌──────▼───────┐                                    │   │
│  │  │ SSE endpoint │  │ specialist-  │                                    │   │
│  │  │ SetBodyStream│  │ Routes map   │                                    │   │
│  │  │ Writer       │  │ @mention→Wkfl│                                    │   │
│  │  │ renderChat-  │  │ + displayName│                                    │   │
│  │  │ Bubble()     │  └──────┬───────┘                                    │   │
│  │  └──────────────┘         │                                            │   │
│  │                           │ goroutine dispatch + tryBroadcast()        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  API Routes                                                           │   │
│  │  GET  /api/command/chat/events  → SSE stream (chat bubbles)          │   │
│  │  POST /api/command/chat/send    → goroutine + Temporal dispatch      │   │
│  │  POST /api/command/approvals/:id/approve → SignalWorkflow("hitl...") │   │
│  │  POST /api/command/approvals/:id/hold   → DB update                  │   │
│  │  GET  /api/mission-state        → read from PostgreSQL               │   │
│  │  POST /api/mission-state        → write from Python AI               │   │
│  │  GET  /api/command/*            → dashboard partials (13+ panels)     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
              │ Temporal                         │ SQL / POST
              ▼                                  ▼
┌─────────────────────────────┐    ┌──────────────────────────────────────────┐
│  Temporal Server             │    │  PostgreSQL                                │
│  Task Queue:                 │    │  Tables:                                   │
│  TRACKGUARD-MAIN-QUEUE       │    │  - mission_state (Python AI writes)       │
│                              │    │  - planned_actions (HITL approval queue)  │
│  Workflows (12):             │    │  - chat_messages (conversation history)   │
│  QAWorkflow                  │    │  - agent_traces (duration, tokens, cost)  │
│  PulseWorkflow               │    │  - agent_events (SSE polling source)      │
│  InvestorWorkflow            │    │                                           │
│  FinanceWorkflow · DataWorkflow     │                                          │
│  OpsWorkflow · CommsWorkflow        │                                          │
│  HiringWorkflow · ChiefOfStaffWorkflow   │                                   │
│  SelfAnalysisWorkflow · EvalLoopWorkflow   │                                 │
│  CompressionWorkflow · WeightDecayWorkflow  │                                │
│                              │                                           │
│  Signals: "hitl-approval"    │                                           │
└──────┬──────────────────────┘                                           │
       │ Temporal activity dispatch                                       │
       ▼                                                                  │
┌──────────────────────────────────────────────────────────────────────────┐
│                    Python AI Worker (Temporal SDK + LangGraph)           │
│                                                                          │
│  Specialist Workflows → LangGraph Agent Graphs                          │
│  FinanceWorkflow  → FinanceGraph (tools: query, analyze, report)        │
│  DataWorkflow     → DataGraph (tools: transform, aggregate, export)     │
│  OpsWorkflow      → OpsGraph (tools: deploy, monitor, alert)            │
│  CommsWorkflow    → CommsGraph (tools: draft, notify, summarize)        │
│  HiringWorkflow   → HiringGraph (tools: search, screen, evaluate)       │
│                                                                          │
│  Legacy: PulseAgent, AnomalyAgent, InvestorAgent, QAAgent               │
│  → Writes: mission_state, planned_actions, agent_traces                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**Tech Stack (V4.0):**

| Layer | Technology | Why |
|------|-----------|------|
| Go Core | Go 1.24 + Fiber v2 | High concurrency, HTMX SSR, SSE streaming |
| Web UI | HTMX + Go templates | Server-rendered, no JS framework |
| SSE | Fiber v2 SetBodyStreamWriter | Real-time push without WebSocket complexity |
| Workflow Engine | Temporal 1.39 | Durable execution, HITL signals |
| Agent Framework | LangGraph (Python) | Stateful agent graphs per specialist |
| LLM | Azure/Groq/Ollama (auto-detect) | Provider-agnostic via OpenAI SDK |
| Structured Output | instructor + Pydantic v2 | Type-safe agent output, no JSON parsing |
| Prompt Compiler | DSPy | Systematic, not hand-tuned |
| Relational DB | PostgreSQL | MissionState, chat, approvals, traces |
| Vector Store | Qdrant | Agent memory, semantic search |
| Cache | Redis | Session state, working memory |
| Observability | Langfuse | LLM trace + eval scoring |

**Polyglot split (V4.0):**

| Language | Owns |
|----------|------|
| Go | HTTP server, HTMX rendering, SSE streaming, Temporal dispatch + signaling, @mention routing, DB queries |
| Python | Temporal workflow definitions, LangGraph agent graphs per specialist, LLM integration, instructor-structured output, legacy guardian/watchlist/guardrails pipelines |

---

## 16. Low-Level Design (V4.0)

### 14.1 Repo Structure

```
apps/
├── core/                          # Go Modular Monolith
│   ├── cmd/
│   │   ├── server/                # HTTP server entrypoint
│   │   └── worker/                # Temporal Go worker
│   ├── internal/
│   │   ├── web/                   # HTTP handlers (Fiber + HTMX + SSE)
│   │   │   ├── handler.go         # All endpoints, @mention routing, SSE broadcast
│   │   │   ├── sse.go             # Legacy SSE handler with DB polling
│   │   │   ├── command_center_test.go  # 52+ tests
│   │   │   └── templates/
│   │   │       ├── command_center.html        # Main dashboard
│   │   │       └── partials/                  # 13+ HTMX partials
│   │   │           ├── command_chat.html        # Chat with hx-ext="sse"
│   │   │           ├── command_approvals.html   # Approval queue
│   │   │           └── command_mission_state.html
│   │   ├── agents/                # Go agent definitions
│   │   ├── config/                # Config management
│   │   ├── temporal/              # Temporal SDK wrapper (SignalWorkflow, ExecuteWorkflow)
│   │   ├── workflow/              # Temporal workflow stubs (cleaned)
│   │   ├── db/                    # sqlc generated queries
│   │   └── database/              # Connection utilities
│   │
│   └── ai/                        # Python AI Worker
│       ├── src/
│       │   ├── worker.py          # Temporal activity worker
│       │   ├── agents/
│       │   │   ├── pulse/         # PulseAgent (daily business pulse)
│       │   │   ├── anomaly/       # AnomalyAgent (explains spikes)
│       │   │   ├── investor/      # InvestorAgent (weekly updates)
│       │   │   ├── qa/            # QAAgent (founder Q&A)
│       │   │   ├── comms/         # CommsTriageAgent
│       │   │   ├── hiring/        # HiringAgent
│       │   │   ├── base/          # Abstract agent class, tool framework
│       │   │   ├── finance/       # V4.0 NEW — FinanceGraph (specialist)
│       │   │   ├── data/          # V4.0 NEW — DataGraph (specialist)
│       │   │   └── ops/           # V4.0 NEW — OpsGraph (specialist)
│       │   ├── business/          # V3.0 MBA integration (Finance Rules, Guardrails)
│       │   ├── predictive/        # V3.0 Forecasting engine
│       │   ├── workflows/         # V4.0 NEW — Temporal workflow definitions
│       │   │   ├── finance_workflow.py
│       │   │   ├── data_workflow.py
│       │   │   └── ops_workflow.py
│       │   ├── guardian/          # Watchlist, detector, insight_builder
│       │   ├── memory/            # Graphiti, Qdrant, spine, RAG kernel
│       │   ├── hitl/              # 3-tier routing logic
│       │   ├── llmops/            # Langfuse tracer, eval loop, self-analysis
│       │   ├── activities/        # Temporal activities
│       │   ├── integrations/      # Stripe, Plaid, Slack, ERPNext, HubSpot
│       │   └── services/          # Trust battery, alert gate, decision engine
│       ├── tests/
│       │   └── unit/              # 319+ tests
│       └── pyproject.toml
```

### 14.2 Database Schema — V2.0 Additions

**New columns (additive, no existing tables modified):**
```sql
ALTER TABLE agent_alerts
  ADD COLUMN IF NOT EXISTS insight_acknowledged  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS insight_already_knew  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS insight_not_relevant  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS blindspot_id          TEXT,
  ADD COLUMN IF NOT EXISTS guardian_pattern_name TEXT;
```

**New tables:**
```sql
-- Resolved blindspots (procedural memory L4)
CREATE TABLE IF NOT EXISTS resolved_blindspots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID REFERENCES tenants(id),
  blindspot_id    TEXT NOT NULL,
  detected_at     TIMESTAMPTZ NOT NULL,
  resolved_at     TIMESTAMPTZ,
  metric_at_detection NUMERIC,
  metric_at_resolution NUMERIC,
  founder_action  TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- LLMOps eval scores
CREATE TABLE IF NOT EXISTS eval_scores (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID REFERENCES tenants(id),
  agent_type      TEXT NOT NULL,
  week_of         DATE NOT NULL,
  guardian_score  NUMERIC,
  accuracy_score  NUMERIC,
  tone_score      NUMERIC,
  action_score    NUMERIC,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Onboarding success tracking
CREATE TABLE IF NOT EXISTS onboarding_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID REFERENCES tenants(id),
  event_type      TEXT NOT NULL,
  occurred_at     TIMESTAMPTZ DEFAULT NOW()
);
```

### 14.3 Qdrant Collections

**V1.0 collections (unchanged):**
- `pulse_memory` — Daily business pulse snapshots
- `anomaly_memory` — Historical anomaly episodes
- `investor_memory` — Past investor updates
- `qa_memory` — Past Q&A answers

**V2.0 new collections (additive):**
- `compressed_memory` — Compressed episodic summaries (L5)
- `founder_blindspots` — Detected and resolved blindspots

### 16.4 API Endpoints (V4.0)

```
COMMAND CENTER (Go — Fiber + HTMX + SSE):
  GET   /command                      Main dashboard page
  POST  /api/command/chat/send        Chat submission + Temporal dispatch
  GET   /api/command/chat/events      SSE stream for chat bubbles
  GET   /api/command/events           SSE stream for dashboard heartbeats
  GET   /api/command/status           Health score bar
  GET   /api/command/kpis             KPI cards (MRR, Runway, etc.)
  GET   /api/command/mission-state    Signals & health score
  GET   /api/command/watchlist        Watch items (FG, BG, OG)
  GET   /api/command/timeline         Recent activity feed
  GET   /api/command/approvals        Pending approval items
  POST  /api/command/approvals/:id/approve  SignalWorkflow + DB approve
  POST  /api/command/approvals/:id/hold     DB hold (no signal)
  GET   /api/command/chart-data       6-week trend data (JSON)
  GET   /api/command/agent-fleet      Agent fleet cards

MISSION STATE (Go — Python AI → PostgreSQL):
  GET   /api/mission-state            Read mission_state (dashboard render)
  POST  /api/mission-state            Write from Python AI workers

WEBHOOKS (Go — legacy, V3.0):
  POST  /webhooks/stripe              Stripe payment events
  POST  /webhooks/bank                Bank transaction feed

HEALTH:
  GET   /health                       Infra health check
```

---

## 17. Workflows & SOP

### Workflow 1 — Guardian Alert (end-to-end)

```
Stripe fires webhook
  → Go validates HMAC → FAIL: 401 stop | PASS: continue
  → Publish to Redpanda: stripe.events
  → Temporal PulseWorkflow starts
    → RunPulseAgent(event)
      → RAG Kernel loads context from memory spine
      → Guardian Watchlist checks 17 patterns
      → LangGraph generates narrative
    → IF watchitem triggered:
      → Build GuardianInsight (DSPy signature)
      → HITL routes (auto / review / approve)
      → SendSlackMessage(output_message)
    → WriteMemorySpine(all 5 layers)
    → Langfuse trace recorded
  → Founder receives alert < 5 minutes

  IF [Investigate] tapped:
    → /internal/hitl/investigate → Temporal signal
    → QAWorkflow: contextual answer with memory
    → Answer → Slack < 10 seconds

  IF [Dismiss] tapped:
    → Qdrant updated: "dismissed — not anomalous"
    → Future threshold raised for pattern
```

### Workflow 2 — Weekly Investor Update

```
Temporal cron fires: Friday 08:00 IST
  → InvestorWorkflow starts
    → Fetch pulse metrics (MRR, burn, runway)
    → RAG Kernel loads memory context
    → Generate draft (Markdown, <300 words)
    → HITL Tier 3: ALWAYS require human approval
    → Send draft to #sarthi-review with [Send Now] [Edit] buttons
  → Founder reviews, approves or edits
  → Final update sent to investors
```

### Workflow 3 — Weekly Self-Analysis + Eval

```
Temporal cron fires: Monday 07:05 AM IST
  → SelfAnalysisWorkflow starts
    → Review past week's alerts
    → Identify patterns, trends, self-corrections
    → Output: self-analysis report

  → EvalLoopWorkflow starts
    → Score each agent: guardian, accuracy, tone, action
    → If quality drops → flag for HITL Tier 3
    → Store eval_scores in PostgreSQL

  → WeightDecayWorkflow starts
    → Apply decay to L2 events older than 60 days
    → Weight < 0.3 → eligible for CompressionWorkflow

  → CompressionWorkflow (if 50+ episodic writes)
    → Compress oldest 30 L2 events into L5 summary
```

---

## 18. Test Strategy

### Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| **Python** | **901** | **✅ 901/927 (26 skipped, 1 pre-existing timeout in curator_graphiti)** |
| Go Web Handlers | 178 | ✅ 178/178 passing |
| Go Build | Clean | ✅ 0 errors |
| DB Tests | 🟡 Skip | Requires PostgreSQL container |
| Redpanda Tests | 🟡 Skip | Requires Redpanda container |


**Known Issues:**
- `test_generate_draft_returns_slack_preview` — flaky due to DSPy token truncation (max_tokens=512). Fix: increase to 1024 or make test tolerant of empty preview.

### Unit Tests

**Guardian Watchlist (28 new tests):**
```
test each detection_logic predicate independently
test no false positives on healthy signal sets
test all 17 watchlist items have required fields
test tenant isolation in detection
test watchlist returns empty on missing signals
```

**Memory Spine (30 new tests):**
```
every layer independently testable with mocked backing service
available() returns False gracefully when service is down
spine.load_context() returns "" (not crash) when all layers unavailable
RAG kernel never exceeds 800 tokens
tenant isolation (tenant B never sees tenant A data)
write_all logs failures but never crashes
compression triggers at 50-write threshold
weight decay applies after 60 days
```

**HITL Manager (11 new tests):**
```
auto route for info severity + >0.85 confidence
slack review route for warning severity
human override for critical severity
investor updates always require approval (Tier 3)
fallback to auto when HITL manager unreachable
confidence scoring edge cases
```

**LLMOps (10 new tests):**
```
@traced decorator is pure pass-through when LANGFUSE_SECRET_KEY not set
tracer records input/output/tokens/latency when configured
eval_loop calculates scores correctly
self_analysis identifies patterns in alert history
```

---

## 19. Deployment

### Local Development
```bash
# Start infrastructure
make up

# Start Python Temporal worker
cd apps/ai && uv run python -m src.worker

# Start Go server
cd apps/core && go run cmd/server/main.go

# Open command center
open http://localhost:8080/command
```

### Monitoring
- **Temporal Web UI:** http://localhost:8088 (workflow executions, retries)
- **Langfuse UI:** http://localhost:3001 (LLM traces, latency, costs)
- **Qdrant Dashboard:** http://localhost:6333/dashboard
- **Redis CLI:** `redis-cli -p 6379 ping`

---

## 20. Build Checklist

### Week 1 — V1.0: Foundation
- [x] `docker-compose.yml` with Temporal, Redpanda, PostgreSQL, Qdrant
- [x] Go Fiber: webhook handlers with HMAC validation
- [x] Redpanda topic: `stripe.events`
- [x] Temporal `PulseWorkflow` skeleton
- [x] Python worker: `run_pulse_agent` activity
- [x] LangGraph `PulseAgent`: all nodes
- [x] PostgreSQL migrations
- [x] Qdrant collections created
- [x] Slack delivery layer
- [x] 119 tests passing

### Week 2 — V1.0: Additional Agents
- [x] AnomalyAgent implementation + tests
- [x] InvestorAgent implementation + tests
- [x] QAAgent implementation + tests
- [x] 3 Temporal workflows deployed
- [x] 5 activities wired

### Week 3 — V2.0: Guardian Systems
- [x] Infrastructure swap (Redis added, Neo4j removed)
- [x] Guardian watchlist (17 patterns, 28 tests)
- [x] Memory spine (5 layers, 30 tests)
- [x] RAG kernel (≤800 token assembly)

### Week 4 — V2.0: Intelligence Layer
- [x] LLMOps: tracer + eval_loop + self_analysis (10 tests)
- [x] HITL manager + confidence (11 tests)
- [x] GuardianInsight DSPy signature
- [x] Wire RAG kernel into all 4 agents (fallback contract)

### Week 5 — V2.0: Production Hardening
- [x] DB migrations (5 new tables/columns)
- [x] New Qdrant collections (compressed_memory, founder_blindspots)
- [x] 4 new Temporal workflows
- [x] Extend existing workflows with guardian watchlist
- [x] Full test suite: 241+ passing, zero regressions

### V4.0: Chat/SSE/Specialist Evolution (June 2026)
- [x] HTMX SSE over WebSocket/Raw JS (`hx-ext="sse"` + `SetBodyStreamWriter`)
- [x] Server-rendered chat bubbles (`renderChatBubble()` with `html.EscapeString()`)
- [x] Goroutine-based workflow dispatch (no more 60s HTTP timeout)
- [x] Map-based specialist routing (`map[string]specialistRoute`, 9 aliases → 6 workflows)
- [x] Temporal Signal for HITL approval (`SignalWorkflow("hitl-approval")`)
- [x] MissionState write path (`POST /api/mission-state`)
- [x] Python specialist agents: Finance, Data, Ops (LangGraph graphs + Temporal workflows)
- [x] Remove dead stubs from `workflow/stubs.go` (cleaned to 10 lines)
- [x] ADR-001 documenting all 7 architecture decisions
- [x] 901 Python tests passing, 178 Go web handler tests passing
- [x] Go build clean (0 errors)

---

## 21. Metrics & KPIs

**Portfolio metrics:**

| Metric | Target | Actual |
|---|---|---|
| Unit tests passing | 1200+ | 1286 |
| E2E smoke test | 1 | ✅ |
| Technologies demonstrated | 15+ | 20+ |
| Observability | Langfuse dashboard | ✅ |

**Technical metrics:**

| Metric | Target |
|---|---|
| Ontology setup wizard completion | < 5 minutes guided UX |
| Evidence-to-business-map latency | < 30 seconds after submission |
| Ontology validation accuracy | 100% (deterministic, not LLM-dependent) |
| Governance gate enforcement | 100% — no external action bypasses approval |
| Pilot draft completeness | All required sections present before export |
| Workspace tenant isolation | Strict — tenant A never sees tenant B data |

---

## 22. Timeline

| Week | Dates | Deliverable | Status |
|---|---|---|---|
| 1 | Mar 21–27 | V1.0 Foundation + PulseAgent | ✅ Complete |
| 2 | Mar 28–Apr 3 | V1.0 Additional Agents | ✅ Complete |
| 3 | Apr 4–10 | V1.0 Cross-agent Integration | ✅ Complete |
| 4 | Apr 11–17 | V1.0 Production Polish | ✅ Complete |
| 5 | Apr 18–24 | V1.0: 4 Agents + 3 Workflows (119 tests) | ✅ Complete |
| 6 | Apr 25–30 | V2.0 Steps 1–4: Infrastructure, Watchlist, Memory, LLMOps | ✅ Complete |
| 7 | May 1–7 | V2.0 Steps 5–8: HITL, DSPy, RAG, DB Migrations | ✅ Complete |
| 8 | May 8–12 | V2.0 Steps 9–12: Qdrant, Workflows, Full Suite (241+ tests) | ✅ Complete |

**V2.0 Final Summary:**
- ✅ 4 agents wired with RAG kernel + fallback contract
- ✅ 17 guardian watchlist patterns (6 Finance, 6 BI, 5 Ops)
- ✅ 5-layer memory spine (Redis → Qdrant → Kuzu → PG → Qdrant)
- ✅ 3-tier HITL (auto → Slack review → human override)
- ✅ LLMOps (Langfuse tracer, eval loop, self-analysis)
- ✅ 7 Temporal workflows (3 existing + 4 new)
- ✅ 9 activities (5 existing + 4 new)
- ✅ 241 tests passed, 6 skipped, 0 failures
- ✅ Zero regressions from V1.0 (was 119, now 241+)

### V4.0 Evolution Timeline

| Week | Dates | Deliverable | Status |
|------|-------|-------------|--------|
| 1 | Jun 21–28 | V4.0 Architecture: SSE, goroutine dispatch, map routing | ✅ Complete |
| 2 | Jun 28 | HITL Signals, MissionState POST, Specialist agents | ✅ Complete |
| **V4.0 Final** | **Jun 28** | **901 Python + 178 Go tests, build clean** | **✅ Complete** |

**V4.0 Final Summary:**
- ✅ HTMX SSE chat with server-rendered bubbles (XSS-safe)
- ✅ Goroutine-based Temporal dispatch + "🤔 Thinking..." feedback
- ✅ Map-based @mention routing (O(1), 9 aliases → 6 workflows)
- ✅ Temporal Signal HITL approval (buttons work end-to-end)
- ✅ MissionState write path (Python AI → POST → PG → GET → Dashboard)
- ✅ 6 specialist agents: Finance, Data, Ops, Comms, Hiring, QA
- ✅ 12 Temporal workflows (9 legacy + 3 specialist)
- ✅ 901 Python tests + 178 Go web handler tests
- ✅ Go build clean, 0 errors
- ✅ ADR-001 documenting all 7 architecture decisions

---

## Appendix: 3-Minute Demo Script (V4.0)

```
[0:00] "OntologyAI V4.0 is an AI coordination layer for solo founders.
        Server-rendered command center with SSE push,
        goroutine-based Temporal dispatch, and domain-specific
        Python specialist agents."

[0:20] "The command center dashboard: 13+ HTMX panels.
        Chat with @mentions, approval queue with Temporal signals,
        Mission State, KPIs, watchlist, timeline, agent fleet."

[0:40] "Chat flow: Type '@finance Q3 revenue?' →
        HTMX POST → Go extracts @mention →
        specialistRoutes map → goroutine dispatch →
        Immediate '🤔 Thinking...' via SSE push."

[1:00] "Temporal dispatches FinanceWorkflow →
        Python FinanceGraph runs LangGraph agent →
        LLM processes query → result returned →
        renderChatBubble() → SSE event:chat → Browser."

[1:15] "HITL approval: Agent proposes action →
        planned_actions row created →
        Temporal workflow reaches AwaitWithTimeout →
        User clicks 'Approve' →
        SignalWorkflow('hitl-approval') unblocks gate."

[1:35] "6 specialist agents: Finance, Data, Ops, Comms,
        Hiring, QA. Map-based routing: O(1) lookup.
        Adding a specialist = 1 map entry + 1 Python class."

[2:00] "319 Python tests + 52 Go web handler tests.
        Go build clean, zero errors.
        12 Temporal workflows. 6 specialist agents.
        HTMX SSE with server-rendered bubbles."

[2:20] "All text is html.EscapeString() — XSS-safe.
        goroutine dispatch with sync.WaitGroup —
        no 60s timeouts. Temporal Signal HITL —
        buttons actually work."

[2:40] "This is OntologyAI V4.0. Not a dashboard maker.
        Not a chatbot. An AI coordination layer
        that routes to the right specialist
        without the founder needing to know who does what."

[3:00] END
```

---

## 22. V5.1 Evolution — Ontology Setup Wizard & Infrastructure

### Summary of Changes

| Decision | Before (V4.x) | After (V5.1) | Benefit |
|----------|--------------|--------------|---------|
| **Worker registration** | Only legacy V4.1 + ChiefOfStaff registered | 6 V5.1 by default (V6/legacy gated behind env flags) | Clean default roster, no dead registrations |
| **Windmill compile** | Only n8n compile activity existed | `compile_windmill_workflow` activity created + registered | Windmill support per ADR-009 |
| **Strategy specialist name** | Returned `"ChiefOfStaff"` | Returns `"Strategy"` | Correct specialist identity |
| **Ontology API** | 6 object types, 5 link types (2 broken) | 6 object types, 9 canonical link types (locked V5.1 contract) | Clean semantic model matching PRD §14 |
| **EngagementState persistence** | No Python-side CRUD service | `EngagementStateStore` with asyncpg | Python agents can read/write canonical state |
| **Ontology onboarding** | Manual/disjointed process | 5-step HTMX wizard with Pydantic state models | Guided UX over existing pipelines |
| **ChiefOfStaff routing** | No wizard intent support | `classify_intent` handles `setup_ontology`, `problem_framing`, etc. | Wizards routed through existing control plane |

### V5.1 API Surface (new endpoints)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/ontology-setup/:engagement_id` | Start or resume wizard |
| `GET` | `/ontology-setup/:engagement_id/step/:step` | Render wizard step partial (by number 1-5 or name) |
| `POST` | `/ontology-setup/:engagement_id/step/:step` | Submit step data and advance |
| `GET` | `/ontology-setup/:engagement_id/summary` | Review all steps before approval |
| `POST` | `/ontology-setup/:engagement_id/launch` | Approve and dispatch DiscoveryWorkflow |

### V5.1 Wizard Partial Templates

| Template | Step |
|----------|------|
| `ontology_setup_start.html` | Initial screen |
| `ontology_setup_problem_framing.html` | Step 1: business goal, scope, stakeholders |
| `ontology_setup_evidence_intake.html` | Step 2: source documents, data sources |
| `ontology_setup_candidate_review.html` | Step 3: proposed object/link types |
| `ontology_setup_relationship_review.html` | Step 4: relationships and cardinality |
| `ontology_setup_approval.html` | Step 5: approve and launch |

### Test Coverage (V5.1)

| Test Suite | Tests | Status |
|-----------|-------|--------|
| Worker registration | 5 | ✅ |
| Windmill compile activity | 7 | ✅ |
| EngagementStateStore | 8 | ✅ |
| Ontology setup state models | 28 | ✅ |
| Go wizard handler | 17 | ✅ |
| ChiefOfStaff wizard routing | 52 | ✅ |
| Engagement state | 47 | ✅ |
| Governance gate | 40 | ✅ |
| **V5.1 total** | **156** | **✅** |

---

## Product Positioning Remaster (V5.1)

### Why enterprise focus

OntologyAI shines when operations are too cross-functional, messy, and risky for simple automation glue. Small teams can often survive with a few point integrations, but larger organizations need a governed system that can unify evidence, preserve provenance, model relationships, identify contradictions, and route action through approvals instead of brittle one-off scripts.

This enterprise framing also better matches the product's ontology-first architecture, shared state design, governance model, handoff artifacts, and workflow-draft generation.

### UI language remaster

| Internal term | User-facing label |
|---|---|
| ChiefOfStaff | Workspace Guide |
| Ontology | Business Map |
| Truth Analysis | Operational Truth |
| Workflow Builder | Pilot Builder |
| Governance | Approvals & Safety |
| ExecutableWorkflowDraft | Pilot Draft |

### Navigation

Recommended primary workspace navigation:
- Workspace
- Business Map
- Findings
- Workflow Drafts
- Approvals
- Exports

### Product pillars

| Pillar | Internal Workflows | Visible Features |
|---|---|---|
| **Understand** | ChiefOfStaff + Discovery + OntologyMapping | Conversation, evidence intake, ontology setup, business map preview |
| **Diagnose** | TruthAnalysis | Blockers, contradictions, missing ownership, risks |
| **Build** | WorkflowBuilder + Governance | Workflow drafts, SOPs, approvals, pilot export |

### Build principle

Keep the backend contract strict and the frontend experience simple: typed state, deterministic validation, governed actions, and enterprise-grade review loops underneath; guided, comprehensible, outcome-first UX on top.

---

**Document Version:** 5.1
**Last Updated:** July 21, 2026
**Status:** ✅ V5.1 Complete — Ontology Setup Wizard, Full Worker Registration, Windmill Integration. **1286+ tests passing / 32 skipped**
