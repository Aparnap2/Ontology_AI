# OntologyAI Workspace

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

## 2. Updated ICP

**Old ICP:** FDE / enterprise operator, 6–18 months to raise, needs enterprise ops intelligence.

**New ICP:** Any cross-functional enterprise team or business unit that:
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

V4.2 extends the Ontology with a schema/semantic layer — not a rewrite. All four components below are **implemented and TDD-verified** in this release: **42 ontology tests passing** (23 schema + 12 adapter + 7 governance), on top of the 1286-test Python suite (32 skipped, 0 failed) and a clean Go build.

1. **Ontology schema module** (`apps/ai/src/ontology/`) — a Python module that formalizes the Ontology as code:
   - `object_types.py` — strict Pydantic v2 models (`extra="forbid"`, `strict=True`) for exactly **six Object Types**: `Customer`, `Deal`, `RevenueMetric`, `Incident`, `Message`, `PlannedAction`, each declaring typed Properties per Section 3.1. An `OBJECT_TYPES` registry maps names → models for the governance/adapter layers.
   - `link_types.py` — a `LINK_TYPES` registry (dict of name → `(source_type, target_type, cardinality)`) for the **four Link Types** from Section 3.2, plus a `resolve_link(link_name, source_id, db=None)` helper that **raises `KeyError` for unknown link names** and resolves target object IDs through an injectable backend (no inline joins elsewhere).
   - These models are the typed contract that the existing `mission_states` JSON blob is extended toward.

2. **MissionState → Ontology adapter** (`apps/ai/src/ontology/adapter.py`) — a function `mission_state_to_ontology(state) -> dict[str, list[BaseModel]]` that maps the existing flat `MissionState` keys into the six typed Object Type lists. `MissionState` is **not** deleted; the adapter is an additive, **tolerant** mapping layer (unknown/legacy keys are ignored, never raised). It is wired into the Chief of Staff workflow's context-building step so the specialist queries via Object Types rather than raw `MissionState` dict access.

3. **Governed-write enforcement** (`apps/ai/src/ontology/governance.py`) — a `@governed_write(object_type, property_name, ...)` decorator that enforces the non-negotiable rule that writes above a defined blast radius require an associated `PlannedAction` and human approval. It is backed by an overridable `OBJECT_WRITE_POLICY` (object_type → property → `{requires_approval, blast_radius}`) and a two-gate trigger: an explicit `requires_approval` flag **or** a blast radius at/above the configured threshold (default `medium`). When a `PlannedAction` is required, the decorator **emits** the `PlannedAction` and blocks the underlying write (HITL pattern); writes below threshold commit directly. A `GovernanceError` is raised when no `PlannedAction` can be produced. Reference wrappers demonstrate one governed path per specialist: `governed_fpa_cancel`, `governed_growth_flag`, `governed_reliability_incident_update`, `governed_comms_send`.

> Note: The ontology schema module, adapter, and governance decorator ship complete and verified in V4.2. Incremental follow-on work remains (full retrofitting of every specialist write path through `@governed_write`, and complete migration of the flat `MissionState` blob to normalized Object Type rows) — but the Ontology layer itself is real, tested code, not a plan.

> **Canonical ontology types (V5.1):** The V5.1 product contract specifies exactly 6 canonical ontology object types: Party, Engagement, MoneyEvent, Issue, Message, PlannedAction. These are the entity types that the OntologyAI core populates, links, and reasons over. The V4.2 types (Customer, Deal, RevenueMetric, Incident, Message, PlannedAction) were the precursor naming — V5.1 renames and stabilises them to the canonical set above.
>
> **UI view-model categories (V5.1):** Artifact, Decision, and Metric are V5.1 view-model categories used in the StrategyWorkflow UI and artifact system. They are **NOT** V5.1 canonical ontology types and are never populated or linked by the V5.1 Discovery/OntologyMapping pipelines. They appear only in the StrategyWorkflow (V6) context.

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

---

## 7. V5.1 Implementation Status

> V5.1 established the canonical 6-workflow FDE roster (`Discovery`, `OntologyMapping`, `TruthAnalysis`, `WorkflowBuilder`, `Governance` + `ChiefOfStaff` control plane), the `EngagementState` shared-state model, the deterministic multi-runtime compiler architecture, and the Palantir-inspired ontology layer.

### 7.1 V5.1 Completed Milestones

| Milestone | Status | Notes |
|-----------|--------|-------|
| 6 canonical workflows + O(1) route map | ✅ | `@mention` map routes 17 aliases to 6 V5.1 (+ 1 gated V6) workflows |
| Ontology layer (6 object types, 11 link types) | ✅ | Pydantic v2 strict models + `LINK_TYPES` registry |
| Deterministic compilers (Windmill/n8n/ADK-Go/PydanticAI/smolagents) | ✅ | `RuntimeCompiler` ABC + `get_compiler()` factory |
| Governance exclusivity + `@governed_write` | ✅ | Only `GovernanceWorkflow` may finalize external execution |
| `EngagementState` + `merge_patch` | ✅ | Single canonical source of truth |
| Worker registration (all 18 workflows) | ✅ | `worker.py` registers 6 V5.1 canonical + 4 V6 (gated) + 8 legacy V4.1 (gated) |
| Windmill compile activity | ✅ | `compile_windmill_workflow` registered in worker.py |
| StrategyWorkflow specialist name fix | ✅ | `specialist="ChiefOfStaff"` → `"Strategy"` |
| `workspace_ontology.go` canonical link types | ✅ | 9 object types + 11 link types (no broken refs) |
| `EngagementStateStore` Python CRUD service | ✅ | asyncpg-backed save/load/list |
| **Ontology Setup Wizard (5-step HTMX)** | ✅ | Problem Framing → Evidence Intake → Candidate Review → Relationship Review → Approval. Orchestration-only over ChiefOfStaff + Discovery. 6 HTMX partials. 97 tests. |
| ChiefOfStaff wizard routing | ✅ | `classify_intent` extended with wizard intents without breaking existing routing |

### 7.2 V5.1 Test Coverage

| Test Suite | Count | Status |
|-----------|-------|--------|
| Ontology setup state models | 28 | ✅ |
| Go handler (wizard endpoints) | 17 | ✅ |
| ChiefOfStaff workflow | 52 | ✅ |
| Worker registration | 5 | ✅ |
| Windmill compile activity | 7 | ✅ |
| EngagementStateStore | 8 | ✅ |
| Engagement state | 47 | ✅ |
| Governance gate | 40 | ✅ |
| **Total V5.1 new tests** | **156** | **✅ 0 failures** |
| **Grand total (all versions)** | **1286 passing / 32 skipped** | **✅** |

### 7.3 Key Constraints

- **Workflow roster**: exactly 6 V5.1 canonical workflows (`ChiefOfStaffWorkflow`, `DiscoveryWorkflow`, `OntologyMappingWorkflow`, `TruthAnalysisWorkflow`, `WorkflowBuilderWorkflow`, `GovernanceWorkflow`) + `StrategyWorkflow` (V6, gated behind `ENABLE_V6_WORKFLOWS=on`). StrategyWorkflow is outside the locked V5.1 contract.
- **Wizard = UX only**: the 5-step ontology setup wizard is a guided HTMX orchestration layer over existing `ChiefOfStaffWorkflow` + `DiscoveryWorkflow`. No new Temporal workflow type.
- **Governance exclusivity preserved**: only `GovernanceWorkflow` may finalize external execution or set `status=activated/exported`.
- **Windmill primary** (ADR-009). n8n is legacy backward compat.
- **V5.1 spec note:** The locked V5.1 PRD specifies n8n + custom_agent as the canonical deterministic runtime compilers. Windmill (ADR-009) was introduced post-V5.1 as a better execution-runtime fit (native Python/TypeScript scripts, built-in approvals, AGPL license) but is documented here as transitional architecture. It is not part of the locked V5.1 product contract and should be considered a V5.2 or V6 capability. For strict V5.1 deployments, n8n remains the canonical target.
- **Legacy V4.1 workflows** (Pulse, Investor, FPA, GrowthAnalytics, etc.) — gated behind `LEGACY_FDE_MODULES=on`. Default: off.

### 7.4 V5.1 Active Roster vs Legacy/V6 Compatibility

The default active V5.1 Temporal worker registers exactly **6 canonical workflows**:

| # | Workflow | Role | Category |
|---|----------|------|----------|
| 1 | `ChiefOfStaffWorkflow` | Control-plane orchestrator | V5.1 canonical |
| 2 | `DiscoveryWorkflow` | Evidence intake & fact extraction | V5.1 canonical |
| 3 | `OntologyMappingWorkflow` | Object/link type population | V5.1 canonical |
| 4 | `TruthAnalysisWorkflow` | Cross-source truth diagnosis | V5.1 canonical |
| 5 | `WorkflowBuilderWorkflow` | Executable workflow draft generation | V5.1 canonical |
| 6 | `GovernanceWorkflow` | Approval gate & external execution finalization | V5.1 canonical |

**V6 `StrategyWorkflow`** — gated behind `ENABLE_V6_WORKFLOWS=on`. Default: off.
**Legacy V4.1 workflows** (Pulse, Investor, FPA, GrowthAnalytics, etc.) — gated behind `LEGACY_FDE_MODULES=on`. Default: off.

When `ENABLE_V6_WORKFLOWS=on` is set:
- `StrategyWorkflow` is added to the active Temporal worker
- `@strategy` alias is added to the route map (7 total aliases)

When `LEGACY_FDE_MODULES=on` is set:
- All 11 legacy V4.1 workflows are added alongside the active roster

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
