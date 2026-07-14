# OntologyAI V4.2 — "Ontology-Lite" Repositioning: PRD Update + Coding Agent Prompt

> **Implementation Status: COMPLETE.** The ontology module, adapter, and governance decorator described in TASK 1–3 were implemented and are TDD-verified — **42 tests passing** (23 schema + 12 adapter + 7 governance) — on top of the 901-test Python suite (26 skipped, 0 failed) with a clean Go build. See `PRD_V4.2.md` §6 for the delivered design. The prompt below is preserved as the original build brief.

## 0. Why This Update Exists

Palantir's entire platform value rests on one concept: the **Ontology** — a semantic layer that turns raw, scattered data into business-meaningful Objects, Links, and Actions, so that dashboards, automations, and AI agents all reason over the same shared model instead of raw tables [cite:1][cite:2]. Foundry's own documentation calls the Ontology "the API of your organization ... a shared layer between engineers, business users, and AIP agents" [cite:1]. Every app, workflow, and AI action in Foundry reads and writes through that same layer, with permissioning, lineage, and audit trails enforced at the Action level [cite:2][cite:3].

Palantir's model assumes an enterprise with a data team, SAP/Salesforce-scale source systems, and years of historical data to build pipelines and, eventually, ML models on top of the Ontology [cite:3]. Small businesses and startups have the opposite condition: fragmented tools (Stripe, a spreadsheet, Slack, a CRM trial), no data engineering team, and rarely more than a few months of clean historical data — nowhere near enough to train custom ML models [cite:4].

**The repositioned thesis:** OntologyAI is a lightweight, ontology-driven operational layer for businesses that cannot afford Palantir and don't have the historical data to justify custom ML. Instead of training models on years of data, OntologyAI uses LLM specialists as the reasoning layer over a small, live Ontology (`MissionState`), with every consequential write gated by human approval — the same governed write-back principle Foundry enforces at the Action layer [cite:2][cite:5].

This document updates the PRD to reflect that positioning and gives the coding agent a concrete, non-ambiguous implementation prompt. It does not require rebuilding the architecture — it requires renaming, reframing, and lightly extending what already exists (MissionState, five specialists, HITL, Temporal workflows).

---

## 1. Repositioned Product Truth

| Layer | Old framing (V3.x / V4.1) | New framing (V4.2) | Palantir parallel |
|---|---|---|---|
| Core data model | "Guardian watchlist state" | **The Ontology** — a live, typed model of the business (customers, revenue, deals, incidents, messages) | Foundry Ontology: Object Types + Properties + Link Types [cite:1][cite:6] |
| Detection engine | "Guardian detection patterns" | **Ontology population + inference** — deterministic rules that populate and update Objects from raw source data | Foundry pipelines that materialize datasets into Objects [cite:6] |
| Five specialists | "Guardian pods" | **Applications** — pre-built vertical apps (FP&A, Growth, Reliability, Comms) that read/write the Ontology | Foundry Workshop apps built on top of the Ontology [cite:1][cite:7] |
| Chief of Staff | "Router" | **Object Explorer / AIP equivalent** — the conversational interface for querying and acting on the Ontology | Foundry's AIP natural-language interface over Ontology objects [cite:1] |
| HITL approval queue | "Safety net" | **Governed Actions** — every write to the Ontology or external system is a permissioned, audited Action | Foundry Action Framework with lineage and audit [cite:2][cite:5] |
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

This ICP is broader than the guardian framing, and it is *more* defensible because it explains the architecture (deterministic ontology population + thin LLM reasoning + mandatory human approval) as a direct consequence of the "no historical data" constraint, rather than an arbitrary safety choice.

---

## 3. Ontology Model — Concrete Mapping to Existing Code

This is not a new subsystem. It is a renaming and light schema extension of `MissionState` plus the five existing PostgreSQL tables.

### 3.1 Object Types (was: "mission state fields")

Each Object Type is a typed, named business entity with Properties and Link Types, matching Foundry's Object Type → Properties → Link Types pattern [cite:6][cite:8]:

| Object Type | Properties (subset) | Link Types |
|---|---|---|
| `Customer` | id, name, mrr, health_score, last_contact_at | → `Deal`, → `SupportThread` |
| `Deal` | id, stage, value, close_probability, owner | → `Customer` |
| `RevenueMetric` | period, mrr, burn, runway_days | → `Customer` (aggregate) |
| `Incident` | id, severity, opened_at, resolved_at, root_cause | → `Customer` (affected) |
| `Message` | id, channel, thread_id, sentiment, drafted_by | → `Customer`, → `Deal` |
| `PlannedAction` | id, type, blast_radius, status, requested_by | → any Object Type (polymorphic target) |

Implementation: extend the existing `mission_states` table's JSON schema with named, typed sub-objects instead of a flat blob. Each specialist's activities become the "pipeline" that populates one or more Object Types — directly analogous to Foundry's `@transform_df` pipelines that materialize raw source tables into Ontology Objects [cite:8].

### 3.2 Link Types (was: implicit joins in agent code)

Currently, relationships between entities (e.g., "this incident affected this customer") are implicit in ad hoc query logic. Under the Ontology model, Link Types must be **explicit, named, and reusable** — defined once, queried everywhere, exactly as Foundry's Link Types replace repeated manual joins [cite:8]:

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

Foundry's Action Framework requires every write to be permission-checked, validated, and lineage-tracked before committing [cite:2][cite:5]. The existing `planned_actions` table + HITL approval flow already satisfies this. The only requirement is that **every** specialist write to the Ontology (not just external API calls) goes through the same `PlannedAction` record — including internal Object Type updates above a defined blast radius.

### 3.4 What does NOT change

- Temporal workflow engine, durable execution, SSE streaming — unchanged.
- Five specialists (Chief of Staff, FP&A, Growth Analytics, Reliability & Delivery, Communications) — unchanged in count and workflow names from V4.1 rename plan.
- PostgreSQL as the store — unchanged; Ontology is a schema/semantic layer on top, not a new database.

---

## 4. Updated Non-Negotiable Rules

1. Every Object Type must have a documented schema (Properties + types) before any specialist can write to it.
2. Every Link Type must be defined once, centrally, and referenced by name — no ad hoc joins in specialist code.
3. Every write to an Object Type above its defined blast radius must create a `PlannedAction` and block on human approval — matching Foundry's governed write-back [cite:2][cite:5].
4. The Chief of Staff must be able to answer "what do we know about X" by querying Object Types and following Link Types — not by re-deriving from raw source data each time.
5. No specialist may claim a numeric fact that is not backed by a materialized Object Type property. If data is insufficient, the specialist must say so rather than infer from insufficient history — this is the direct product consequence of the "no historical data" constraint.

---

## 5. Coding Agent Prompt

Copy everything below the line into the coding agent as a single task brief.

---

**ROLE:** You are implementing OntologyAI V4.2, a repositioning of an existing multi-agent Temporal-based system from a "founder guardian" product to a "small-business Ontology + governed AI actions" product. The runtime architecture (Temporal, Postgres, SSE, HITL) is unchanged. Your job is schema/semantic-layer work, renaming, and light extension — NOT a rewrite.

**DO NOT:**
- Change the Temporal workflow engine, SSE mechanism, or number of specialists (remains 5: Chief of Staff, FP&A, Growth Analytics, Reliability & Delivery, Communications).
- Remove or weaken the HITL approval gate.
- Introduce any new database engine or vector store beyond what already exists.
- Rename anything not explicitly listed below.

**TASK 1 — Ontology Schema Module (Python, `apps/ai/src/ontology/`)**
1. Create `apps/ai/src/ontology/object_types.py` defining Pydantic models for exactly these Object Types: `Customer`, `Deal`, `RevenueMetric`, `Incident`, `Message`, `PlannedAction`. Each model must declare typed Properties matching Section 3.1 of the PRD above. Use strict Pydantic v2 mode.
2. Create `apps/ai/src/ontology/link_types.py` with a `LINK_TYPES` registry (dict of name → (source_type, target_type, cardinality)) matching Section 3.2. Add a helper function `resolve_link(link_name: str, source_id: str) -> list[str]` that queries Postgres for linked object IDs — no inline joins permitted elsewhere in the codebase after this task.
3. Write `tests/unit/test_ontology_schema.py` FIRST:
   - Test each Object Type model validates required fields and rejects extra/unknown fields (strict mode).
   - Test `LINK_TYPES` registry contains all four link types from Section 3.2 with correct cardinality strings.
   - Test `resolve_link` raises `KeyError` for unknown link names.
4. Only after tests are written and failing, implement the models and registry to pass them.

**TASK 2 — MissionState → Ontology Adapter**
1. Do not delete `MissionState`. Add `apps/ai/src/ontology/adapter.py` with a function `mission_state_to_ontology(state: dict) -> dict[str, list[BaseModel]]` that maps existing flat `MissionState` keys into the six typed Object Type lists above.
2. Write `tests/unit/test_ontology_adapter.py` FIRST covering: empty state → empty ontology dict; a populated state with customers/deals/incidents maps correctly; unknown/legacy keys are ignored without raising.
3. Wire this adapter into the Chief of Staff workflow's context-building step so it queries via Object Types, not raw `MissionState` dict access, going forward.

**TASK 3 — Governed Write Enforcement**
1. Add a `blast_radius: Literal["low", "medium", "high"]` property to `PlannedAction` (Section 3.1) if not already present in the `planned_actions` table — check first via migration.
2. Write `tests/unit/test_governed_writes.py` FIRST:
   - Test that any specialist attempting to write an Object Type property flagged `requires_approval=True` in its schema without an associated `PlannedAction` raises a `GovernanceError`.
   - Test that writes below blast radius threshold proceed without approval.
   - Test that writes at/above threshold create a `PlannedAction` row and block via existing HITL `wait_condition` pattern.
3. Implement a decorator `@governed_write(object_type, property_name)` in `apps/ai/src/ontology/governance.py` that wraps specialist activity functions and enforces this rule. Apply it to at least one write path per specialist (FP&A cancellation action, Growth Analytics flag, Reliability incident update, Comms send action) as a reference implementation — do not need to retrofit every single write path in this task, but the decorator itself must be fully tested and production-ready.

**TASK 4 — PRD and Documentation Update**
1. Create `PRD_V4.2.md` at repo root using Section 1–4 of this document verbatim as the new "Product Truth" and "ICP" sections, replacing the equivalent sections in the current PRD. Keep all existing technical sections (workflow names, route map, API contracts) from PRD_V4.1 unchanged except where this document explicitly modifies them.
2. Update `README.md` top-level description to: "OntologyAI builds a live Ontology of a small business from its existing tools, and lets AI specialists query and act on it — with every consequential action gated by human approval." Do not otherwise change README structure.
3. Do NOT touch branding/Docker/CI renaming tasks from the V4.1 plan — those are separate work and out of scope here.

**ACCEPTANCE CRITERIA:**
- `uv run pytest tests/unit/test_ontology_schema.py tests/unit/test_ontology_adapter.py tests/unit/test_governed_writes.py -v` — all pass.
- `grep -r "blast_radius" apps/ai/src/ontology/` returns non-empty.
- `PRD_V4.2.md` exists and contains the phrase "Ontology" at least 10 times and does not contain the phrase "16 failure patterns."
- No changes to `apps/ai/src/worker.py` workflow registration count (still 5 specialist workflows + Chief of Staff).
- Existing test suite (`uv run pytest tests/unit/ -q`) still passes with zero regressions.

**EXECUTION ORDER:** Task 1 → Task 2 → Task 3 → Task 4. Each task's tests must be written and observed failing before implementation begins (strict TDD). Report back after each task with test output before proceeding to the next.

---
