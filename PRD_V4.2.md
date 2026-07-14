# OntologyAI V4.2 — Product Requirements Document

> OntologyAI builds a live Ontology of a small business from its existing tools, and lets AI specialists query and act on it — with every consequential action gated by human approval.

---

## 1. Repositioned Product Truth

| Layer | Old framing (V3.x / V4.1) | New framing (V4.2) | Palantir parallel |
|---|---|---|---|
| Core data model | "Guardian watchlist state" | **The Ontology** — a live, typed model of the business (customers, revenue, deals, incidents, messages) | Foundry Ontology: Object Types + Properties + Link Types |
| Detection engine | "failure patterns" | **Ontology population + inference** — deterministic rules that populate and update Objects from raw source data | Foundry pipelines that materialize datasets into Objects |
| Five specialists | "Guardian pods" | **Applications** — pre-built vertical apps (FP&A, Growth, Reliability, Comms) that read/write the Ontology | Foundry Workshop apps built on top of the Ontology |
| Chief of Staff | "Router" | **Object Explorer / AIP equivalent** — the conversational interface for querying and acting on the Ontology | Foundry's AIP natural-language interface over Ontology objects |
| HITL approval queue | "Safety net" | **Governed Actions** — every write to the Ontology or external system is a permissioned, audited Action | Foundry Action Framework with lineage and audit |
| Positioning | "Founder's guardian, catches blindspots" | **"Palantir-style Ontology, without the data team or the data"** — small-business operational intelligence layer | — |

**One-sentence pitch:** OntologyAI builds a live Ontology of a small business from its existing scattered tools, and lets AI specialists query and act on it — with every consequential action gated by human approval, because there isn't enough historical data to trust a model to decide alone.

---

## 2. Updated ICP

**Old ICP:** Solo SaaS founder, 6–18 months to raise, needs guardian against blindspots.

**New ICP:** Any small business or early-stage startup (1–20 people) that:
- runs operations across 4+ disconnected tools (Stripe/Razorpay, a spreadsheet, a CRM, Slack/email, a support inbox),
- has no data engineering or analytics function,
- has less than ~12 months of clean historical data — too little to train or justify a custom ML model,
- wants one place to see "what's actually true about the business right now" and act on it without hiring an ops/data hire.

This ICP is broader than the guardian framing, and it is *more* defensible because it explains the architecture (deterministic Ontology population + thin LLM reasoning + mandatory human approval) as a direct consequence of the "no historical data" constraint, rather than an arbitrary safety choice.

---

## 3. Ontology Model — Concrete Mapping to Existing Code

This is not a new subsystem. It is a renaming and light schema extension of `MissionState` plus the five existing PostgreSQL tables.

### 3.1 Object Types (was: "mission state fields")

Each Object Type is a typed, named business entity with Properties and Link Types, matching Foundry's Object Type → Properties → Link Types pattern:

| Object Type | Properties (subset) | Link Types |
|---|---|---|
| `Customer` | id, name, mrr, health_score, last_contact_at | → `Deal`, → `SupportThread` |
| `Deal` | id, stage, value, close_probability, owner | → `Customer` |
| `RevenueMetric` | period, mrr, burn, runway_days | → `Customer` (aggregate) |
| `Incident` | id, severity, opened_at, resolved_at, root_cause | → `Customer` (affected) |
| `Message` | id, channel, thread_id, sentiment, drafted_by | → `Customer`, → `Deal` |
| `PlannedAction` | id, type, blast_radius, status, requested_by | → any Object Type (polymorphic target) |

Implementation: extend the existing `mission_states` table's JSON schema with named, typed sub-objects instead of a flat blob. Each specialist's activities become the "pipeline" that populates one or more Object Types — directly analogous to Foundry's `@transform_df` pipelines that materialize raw source tables into Ontology Objects.

### 3.2 Link Types (was: implicit joins in agent code)

Currently, relationships between entities (e.g., "this incident affected this customer") are implicit in ad hoc query logic. Under the Ontology model, Link Types must be **explicit, named, and reusable** — defined once, queried everywhere, exactly as Foundry's Link Types replace repeated manual joins:

```python
# apps/ai/src/ontology/link_types.py
LINK_TYPES = {
    "incident_affects_customer": ("Incident", "Customer", "many_to_many"),
    "deal_belongs_to_customer": ("Deal", "Customer", "many_to_one"),
    "message_relates_to_deal": ("Message", "Deal", "many_to_one"),
    "action_targets_object": ("PlannedAction", "*", "polymorphic"),
}
```

### 3.3 Actions (was: "planned_actions" HITL rows) — no structural change, only formalization

Foundry's Action Framework requires every write to be permission-checked, validated, and lineage-tracked before committing. The existing `planned_actions` table + HITL approval flow already satisfies this. The only requirement is that **every** specialist write to the Ontology (not just external API calls) goes through the same `PlannedAction` record — including internal Object Type updates above a defined blast radius.

### 3.4 What does NOT change

- Temporal workflow engine, durable execution, SSE streaming — unchanged.
- Five specialists (Chief of Staff, FP&A, Growth Analytics, Reliability & Delivery, Communications) — unchanged in count and workflow names from V4.1 rename plan.
- PostgreSQL as the store — unchanged; the Ontology is a schema/semantic layer on top, not a new database.

---

## 4. Updated Non-Negotiable Rules

1. Every Object Type must have a documented schema (Properties + types) before any specialist can write to it.
2. Every Link Type must be defined once, centrally, and referenced by name — no ad hoc joins in specialist code.
3. Every write to an Object Type above its defined blast radius must create a `PlannedAction` and block on human approval — matching Foundry's governed write-back.
4. The Chief of Staff must be able to answer "what do we know about X" by querying Object Types and following Link Types — not by re-deriving from raw source data each time.
5. No specialist may claim a numeric fact that is not backed by a materialized Object Type property. If data is insufficient, the specialist must say so rather than infer from insufficient history — this is the direct product consequence of the "no historical data" constraint.

---

## 5. Current State — What Exists Now

The V4.2 repositioning is built on top of a working V4.1 runtime. The following capabilities are already implemented and in production:

- **Five canonical specialists** — Chief of Staff, FP&A, Growth Analytics, Reliability & Delivery, and Communications. Each is a Temporal workflow (`ChiefOfStaffWorkflow`, `FPAWorkflow`, `GrowthAnalyticsWorkflow`, `ReliabilityWorkflow`, `CommsWorkflow`) backed by a LangGraph agent (FinanceGraph, DataGraph, OpsGraph, CommsGraph).
- **Temporal orchestration** — durable execution, task queue `TRACKGUARD-MAIN-QUEUE`, and a `hitl-approval` signal that unblocks `AwaitWithTimeout` after human review.
- **HITL approval queue** — AI proposes an action → a `planned_actions` row is created with `status=pending` → the workflow blocks on `AwaitWithTimeout("hitl-approval", 48h)` → a user approves via `SignalWorkflow(ctx, id, "hitl-approval", true)` → execution continues.
- **SSE streaming** — HTMX `hx-ext="sse"` declaratively subscribes to a server stream. The Go `SSEHub` (`sse_hub.go`) provides event-type-filtered fan-out with per-subscriber channels (buffer 64) via `Subscribe(tenantID, eventTypes...)` and `Broadcast(tenantID, SSEEvent)`.
- **MissionState write path** — the Python AI worker compiles operational state (MRR, burn, health, signals) and `POST`s it to `/api/mission-state` → PostgreSQL (`mission_states` table). `GET` returns it for Go template rendering. Fields include `prepared_brief`, `pending_decisions`, `last_updated_by`, plus explainability fields `last_update_reason`, `last_changed_fields`, and `active_agent_roles`.
- **@mention routing** — a Go `specialistRoutes` map provides O(1) lookup from 10 aliases to 5 canonical workflows, with backward-compat aliases (`@sarthi`, `@agent`, `@qa`, `@ask` → Chief of Staff).
- **Tool calling surface** — a `ToolRegistry` of 4 `ToolDef` tools (`pause_failed_payment_retry`, `draft_investor_update`, `schedule_customer_checkin`, `flag_churn_risk_customer`) wired to the HITL manager and gated by an agent authority manifest.
- **Agent authority manifest** — 5 specialist agents + 1 correlation agent with declared roles, escalation tiers, and allowed-tool allowlists.

---

## 6. What V4.2 Delivers (Implemented & Verified)

V4.2 extends the Ontology with a schema/semantic layer — not a rewrite. All four components below are **implemented and TDD-verified** in this release: **42 ontology tests passing** (23 schema + 12 adapter + 7 governance), on top of the 901-test Python suite (26 skipped, 0 failed) and a clean Go build.

1. **Ontology schema module** (`apps/ai/src/ontology/`) — a Python module that formalizes the Ontology as code:
   - `object_types.py` — strict Pydantic v2 models (`extra="forbid"`, `strict=True`) for exactly **six Object Types**: `Customer`, `Deal`, `RevenueMetric`, `Incident`, `Message`, `PlannedAction`, each declaring typed Properties per Section 3.1. An `OBJECT_TYPES` registry maps names → models for the governance/adapter layers.
   - `link_types.py` — a `LINK_TYPES` registry (dict of name → `(source_type, target_type, cardinality)`) for the **four Link Types** from Section 3.2, plus a `resolve_link(link_name, source_id, db=None)` helper that **raises `KeyError` for unknown link names** and resolves target object IDs through an injectable backend (no inline joins elsewhere).
   - These models are the typed contract that the existing `mission_states` JSON blob is extended toward.

2. **MissionState → Ontology adapter** (`apps/ai/src/ontology/adapter.py`) — a function `mission_state_to_ontology(state) -> dict[str, list[BaseModel]]` that maps the existing flat `MissionState` keys into the six typed Object Type lists. `MissionState` is **not** deleted; the adapter is an additive, **tolerant** mapping layer (unknown/legacy keys are ignored, never raised). It is wired into the Chief of Staff workflow's context-building step so the specialist queries via Object Types rather than raw `MissionState` dict access.

3. **Governed-write enforcement** (`apps/ai/src/ontology/governance.py`) — a `@governed_write(object_type, property_name, ...)` decorator that enforces the non-negotiable rule that writes above a defined blast radius require an associated `PlannedAction` and human approval. It is backed by an overridable `OBJECT_WRITE_POLICY` (object_type → property → `{requires_approval, blast_radius}`) and a two-gate trigger: an explicit `requires_approval` flag **or** a blast radius at/above the configured threshold (default `medium`). When a `PlannedAction` is required, the decorator **emits** the `PlannedAction` and blocks the underlying write (HITL pattern); writes below threshold commit directly. A `GovernanceError` is raised when no `PlannedAction` can be produced. Reference wrappers demonstrate one governed path per specialist: `governed_fpa_cancel`, `governed_growth_flag`, `governed_reliability_incident_update`, `governed_comms_send`.

> Note: The ontology schema module, adapter, and governance decorator ship complete and verified in V4.2. Incremental follow-on work remains (full retrofitting of every specialist write path through `@governed_write`, and complete migration of the flat `MissionState` blob to normalized Object Type rows) — but the Ontology layer itself is real, tested code, not a plan.

---

## 7. What Remains Planned

The following are explicitly out of scope for the V4.2 schema/semantic-layer work and remain planned or deferred:

- **Full retrofitting of every specialist write path** with `@governed_write`. V4.2 establishes the decorator and applies it as a reference implementation to at least one write path per specialist (FP&A cancellation, Growth Analytics flag, Reliability incident update, Comms send); covering every write path is follow-on work.
- **Complete migration** of the `mission_states` flat JSON blob to fully typed, normalized Object Type rows. V4.2 introduces the typed models and adapter; the migration of historical data and all read/write call sites is incremental.
- **Custom ML models.** Deliberately not pursued — the ICP's "no historical data" constraint means there is insufficient clean history to train or justify a custom model. Reasoning stays with thin LLM specialists over the deterministic Ontology.
- **Additional source-tool connectors** beyond the currently integrated set (Stripe/Razorpay, Slack, spreadsheet/CRM via existing integrations). New connectors populate Object Types but are not part of the V4.2 core schema work.
- **Branding / Docker / CI renaming** tasks from the broader V4.1 plan are separate work and out of scope for this document update.

---

## 8. Technical Architecture (carried from V4.1, unchanged except where V4.2 modifies it)

> The sections below preserve the existing V4.1 technical documentation. They are unchanged except where V4.2 explicitly modifies them (the six Object Types, four Link Types, and governed Actions described in Sections 3 and 6 above).

### V4.1 Architecture: Five Canonical Specialists

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
| **OntologyAI branding** | All page titles, display names, and documentation use "OntologyAI" |
| **API Mission State endpoints** | `GET /api/mission-state` and `POST /api/mission-state` for machine-readable JSON (Python AI ↔ Go Core) |

### HITL with Temporal Signals
- AI proposes action → `planned_actions` row created with `status=pending`
- Temporal workflow reaches `AwaitWithTimeout("hitl-approval", 48h)`
- User clicks Approve → POST → `SignalWorkflow(ctx, id, "hitl-approval", true)`
- Workflow unblocks, execution continues

### SSE Chat System
- HTMX `hx-ext="sse"` declaratively subscribes to SSE stream
- Server sends `event: chat` with HTML fragments as data payload
- **SSEHub** (`sse_hub.go`): Event-type filtered fan-out hub with per-subscriber channels (buffer 64)
  - `Subscribe(tenantID, eventTypes...)` — typed subscriptions (chat, mission, hitl, session)
  - `Broadcast(tenantID, SSEEvent)` — delivers only to matching subscribers

### MissionState Write Path
- **Python AI** compiles operational state (MRR, burn, health, signals)
- **POST** to `/api/mission-state` → **PostgreSQL** (`mission_states` table)
- **GET** → Go templates → HTML (dashboard)
- Fields: `prepared_brief`, `pending_decisions`, `last_updated_by`
- Explainability: `last_update_reason`, `last_changed_fields`, `active_agent_roles`
- Auto-generated brief: `generate_prepared_brief()` on every MissionState write

### Tech Stack

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
