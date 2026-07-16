# OntologyAI V5.1 — Implementation Plan

**Status:** APPROVED — decisions locked (see §8.1)
**Author:** Solution Architect (agent)
**Date:** 2026-07-16
**Branch target:** `feature/ontologyai-v5.1` (see Open Questions §8)
**Inputs:** `prd.md` (V5.1, 1638 lines) + codebase audit summary
**Repo:** `/home/aparna/Desktop/iterate_swarm` (Go core + Python AI, rebranded TrackGuard/Sarthi → OntologyAI)

---

## 0. How to read this plan

This plan is the contract for the V5.1 build. It is organized as:

1. Scope & principles
2. Phased roadmap (PRD §29 enriched with audit reality)
3. Module-by-module spec (every new/refactored file)
4. Data model & migrations (PRD §22)
5. Agent delegation map (who builds what, in what order)
6. Risks & mitigations
7. Acceptance criteria (PRD §31)
8. Open questions / decisions needed from the user

**Hard rule for all agents:** TDD-first. Write the failing test (PRD §28.1 list) *before* the implementation. Reuse over rewrite (PRD §24, §30.12). Thin-LLM / fat-deterministic-core (PRD §11). No code or file edits happen until this plan is approved.

---

## 1. Scope & Principles

### 1.1 In scope
- Exactly **6 workflows**: `ChiefOfStaffWorkflow`, `DiscoveryWorkflow`, `OntologyMappingWorkflow`, `TruthAnalysisWorkflow`, `WorkflowBuilderWorkflow`, `GovernanceWorkflow` (PRD §7).
- Exactly **6 ontology object types**: `Party`, `Engagement`, `MoneyEvent`, `Issue`, `Message`, `PlannedAction` (PRD §12).
- Canonical `EngagementState` shared state (PRD §14).
- `ExecutableWorkflowDraft` + deterministic runtime compilers (`n8n`, `custom_agent`) (PRD §12.7, §17, §23.1).
- 11 canonical link types (PRD §13).
- 7 persistence tables (PRD §22).
- 11 shared workspace UI screens (PRD §19.2).
- Artifact export service (truth map, ontology snapshot, workflow pack, SOP pack, action register, executable draft) (PRD §5.2, §10).
- `@sarthi` backward-compat alias preserved (PRD §25.3, audit constraint).

### 1.2 Principles (non-negotiable, from PRD §4, §11, §30)
- **P1 — Thin LLM / fat deterministic core.** LLMs only for ambiguity, extraction, synthesis, intent parsing, narrative. Routing, validation, thresholds, formatting, state merges, blast-radius (when rule-derivable), and export payloads are deterministic code (PRD §11.1–11.3).
- **P2 — Reuse over rewrite.** Reuse `worker.py`, `governance.py`, `mission_state.py` read path, Go `handler.go` `planned_actions` + HITL `SignalWorkflow("hitl-approval")`, `sse_hub.go`, `cofounder/router.py`, `authority_manifest.py`, HTMX templates, APScheduler, Redis/Qdrant/Postgres clients, Langfuse, Pydantic `extra="forbid", strict=True` conventions (audit "reuse-ready").
- **P3 — TDD-first.** Failing test committed before implementation for every module (PRD §26.1, §28).
- **P4 — Governance exclusivity.** Only `GovernanceWorkflow` may set `status="activated"` / `executing` / `completed` / `exported` on external side effects (PRD §10.6, §18.3, §31.6).
- **P5 — `@sarthi` backward-compat.** Go route map entry, 2 HTML templates, and Go tests referencing `@sarthi` must keep working (audit constraint).
- **P6 — No private models.** No agent owns a private model of the business; all read/write `EngagementState` via typed patches (PRD §4.2, §14.2).
- **P7 — Graceful degradation.** Every workflow degrades on missing data (PRD §4.10, §28.2).

### 1.3 Explicitly out of scope (V5.1)
- Full production connector coverage (PRD §30.9).
- New databases or orchestration engines (PRD §30.6).
- New agents beyond the 5 operational + ChiefOfStaff (PRD §30.1).
- New ontology types beyond the 6 (PRD §30.2).

---

## 2. Phased Roadmap (PRD §29 enriched with audit reality)

Each phase lists: **Goal**, **Files touched**, **Tests to write first (TDD)**, **Done-criteria**.

### Phase 0 — Surface cleanup
- **Goal:** Normalize naming to OntologyAI; keep compat aliases; update docs/route names. No behavior change.
- **Files touched:**
  - `apps/ai/src/worker.py` — rename task queue constant `TRACKGUARD-MAIN-QUEUE` → `ONTOLOGYAI-MAIN-QUEUE` (env-overridable; see OQ §8). Keep old name as fallback default for one version.
  - `apps/core/internal/web/handler.go` — add `@ontologyai`, `@chief` aliases → `ChiefOfStaffWorkflow`; keep `@sarthi`, `@agent`, `@qa`, `@ask` (P5).
  - `apps/ai/src/agents/authority_manifest.py` — relabel `domain` literals to FDE vocabulary (keep enum values, change display `voice`/`role` copy).
  - Docs: `AGENTS.md` V4.2 → V5.1 status table; `prd.md` already renamed.
- **Tests first:** `test_route_map.py` (new) asserting `@ontologyai`/`@chief`/`@sarthi`/`@discover`/`@map`/`@truth`/`@build`/`@govern` map correctly (PRD §28.1). Existing Go `command_center_test.go` `@sarthi` assertions must stay green.
- **Done-criteria:** All existing 901 Python + 74 Go tests pass; new aliases resolve; no logic changed.

### Phase 1 — Contracts first (schemas)
- **Goal:** Define all typed contracts; tests fail; then implement.
- **Files touched (new):** `apps/ai/src/ontology/object_types.py` (rewrite), `link_types.py` (new), `action_types.py` (new), `workflow_drafts.py` (new); `apps/ai/src/schemas/engagement_state.py`, `specialist_response.py` (extend), `workflow_spec.py`, `sop.py`, `executable_workflow_draft.py`.
- **Tests first (PRD §28.1):** `test_ontology_schema.py`, `test_link_and_action_registry.py`, `test_engagement_state.py`, `test_specialist_response.py`, `test_workflow_spec_schema.py`, `test_sop_schema.py`, `test_executable_workflow_draft.py`. Assertions: strict validation, unknown-field rejection (`extra="forbid"`), workflow-name exactness.
- **Done-criteria:** All 7 schema test files fail first, then pass; `OBJECT_TYPES` registry contains exactly the 6 canonical types; `PlannedAction`/`ExecutableWorkflowDraft` validate per PRD §12.6–12.7.

### Phase 2 — Workflow shells
- **Goal:** Register exactly 6 workflows without changing runtime model.
- **Files touched:** `apps/ai/src/workflows/__init__.py` (refactor), `discovery_workflow.py`, `ontology_mapping_workflow.py`, `truth_analysis_workflow.py`, `workflow_builder_workflow.py`, `governance_workflow.py` (new); `chief_of_staff_workflow.py` (refactor into control-plane orchestrator). `worker.py` registers the 6 (drop `PulseWorkflow`/`InvestorWorkflow`/etc. from active roster — see OQ §8 on legacy retention).
- **Tests first:** `test_workflow_names.py` (assert exactly 6 registered with exact names), `test_workspace_mode.py`.
- **Done-criteria:** `test_workflow_names.py` passes; `worker.py` imports only the 6; legacy workflows isolated behind a flag or removed per OQ.

### Phase 3 — Shared state wiring
- **Goal:** `EngagementState` canonical; deterministic patch merge; workspace mode + phase transitions.
- **Files touched:** `apps/ai/src/schemas/engagement_state.py` (canonical model), `apps/ai/src/session/mission_state.py` (keep as compat read adapter; add `engagement_state.py` adapter), `apps/ai/src/ontology/adapter.py` (keep `mission_state_to_ontology` working until Phase 4 — P: must NOT break), new `apps/ai/src/session/engagement_state_store.py` (Postgres `engagement_states` read/write).
- **Tests first:** `test_engagement_state.py` (merge-safe patching, unknown-key rejection, phase transitions), `test_workspace_mode.py`.
- **Done-criteria:** Workflows read/write only typed patches; `mission_state_to_ontology` still importable & callable; `engagement_states` table written via new store.

### Phase 4 — Specialist behavior
- **Goal:** Implement the 5 operational workflows' logic (ChiefOfStaff already shelled in P2).
- **Files touched:** the 5 workflow modules from P2; `apps/ai/src/ontology/governance.py` (rewrite `OBJECT_WRITE_POLICY` to new 6 types; keep `@governed_write` decorator); `apps/ai/src/agents/cofounder/router.py` → `apps/ai/src/agents/chief_of_staff/intent_classifier.py` (refactor, not duplicate).
- **Tests first:** `test_discovery_workflow.py`, `test_ontology_mapping_workflow.py`, `test_truth_analysis_workflow.py`, `test_workflow_builder_workflow.py`, `test_governance_workflow.py`, `test_hitl_governance.py`. Assertions: deterministic findings run before LLM synthesis; governance exclusivity; approval-required behavior; graceful missing-data.
- **Done-criteria:** All 5 workflow tests pass; truth analysis runs deterministic checks first (PRD §10.4); governance blocks medium/high blast radius (PRD §18.1).

### Phase 5 — Runtime compilers
- **Goal:** Deterministic export payload generation for n8n + custom_agent.
- **Files touched (new):** `apps/ai/src/runtime/__init__.py`, `n8n_compiler.py`, `custom_agent_compiler.py`; artifact export service `apps/ai/src/runtime/artifact_export.py` (or `apps/ai/src/services/artifact_export.py`).
- **Tests first:** `test_n8n_compiler.py`, `test_custom_agent_compiler.py`, `test_artifact_exports.py`. Assertions: deterministic compiler output (same input → same payload), `export_payload` only populated by compiler (never LLM), artifact shape correct.
- **Done-criteria:** Compilers produce valid n8n JSON / custom_agent config from `ExecutableWorkflowDraft`; artifacts exportable (PRD §10.6, §31.10).

### Phase 6 — UI and artifacts
- **Goal:** 11 shared workspace screens; artifact exports; executable draft panel; approvals/governance UX.
- **Files touched:** `apps/core/internal/web/handler.go` (route map → engagement routes; add workspace endpoints), `sse_hub.go` (reuse), HTMX templates in `apps/core/internal/web/templates/` (re-skin dashboard → workspace views; guardian cards → truth cards; decision journal → action register). Go `planned_actions` HITL path reused.
- **Tests first:** Go HTMX handler tests for new workspace routes; `test_artifact_exports.py` (integration). UI test checklist (PRD §28.4): workspace creation, mode selection, upload flow, follow-up rendering, ontology graph, draft review, approval buttons, export buttons.
- **Done-criteria:** 11 screens present; approvals obvious & safe (PRD §19.5); `@sarthi` templates still render.

### Phase 7 — Final verification
- **Goal:** Full regression + acceptance gate.
- **Files touched:** none (verification only).
- **Tests:** Run full Python suite (target ≥901 + new V5.1), Go build + `go test ./...`, integration tests (PRD §28.3).
- **Done-criteria:** All acceptance criteria §7 met; workflow count = 6; object type count = 6; only Governance finalizes execution; artifacts export; zero regression on reusable infra.

---

## 3. Module-by-Module Spec

> Convention: every new/refactored Python module uses `BaseModel` with `model_config = ConfigDict(extra="forbid", strict=True)` (PRD §11, audit Pydantic convention).

### 3.1 Ontology layer — `apps/ai/src/ontology/`

#### `object_types.py` (REWRITE)
- **Responsibility:** Canonical 6 object types.
- **Key types:** `Party` (subtypes customer/supplier/employee/contractor/partner/approver), `Engagement` (deal/order/job/project/service_case), `MoneyEvent` (receivable/payable/payment/refund/writeoff/expense), `Issue` (delay/dispute/defect/incident/risk/blocker), `Message` (email/whatsapp/call_note/sms/note/meeting_summary), `PlannedAction` (PRD §12.1–12.6).
- **Reuses:** Pydantic `extra="forbid", strict=True` pattern from current file.
- **Must NOT break:** `governance.py` imports `PlannedAction` from here — keep `PlannedAction` importable with at least `id, type, blast_radius, status, requested_by`. `adapter.py` imports `OBJECT_TYPES` — keep the registry dict but replace values.

#### `link_types.py` (NEW)
- **Responsibility:** 11 canonical link types (PRD §13): `party_engagement`, `engagement_money_event`, `engagement_issue`, `message_party`, `message_engagement`, `issue_planned_action`, `money_event_planned_action`, `party_planned_action`, `engagement_planned_action`, `workflow_action`, `workflow_object_dependency`.
- **Key type:** `LinkType(BaseModel)` with `name, source_type, target_type, cardinality, semantic_meaning, source_refs`.
- **Reuses:** none (greenfield); follows `object_types.py` style.
- **Must NOT break:** nothing yet (new import).

#### `action_types.py` (NEW)
- **Responsibility:** Full `PlannedAction` model + action registry/helpers (PRD §12.6).
- **Key types:** `PlannedAction` (full field set: `target_object_type` Literal of 6, `requires_approval`, `execution_payload`, `source_refs`), `ActionRegistry`.
- **Reuses:** field semantics from current `object_types.PlannedAction`; `governance.py` will import from here instead of `object_types`.
- **Must NOT break:** `governance.py` `default_create_planned_action` returns a `PlannedAction` — keep compatible constructor signature during transition.

#### `workflow_drafts.py` (NEW)
- **Responsibility:** `ExecutableWorkflowDraft` model (PRD §12.7).
- **Key types:** `ExecutableWorkflowDraft` with `runtime` Literal["n8n","custom_agent"], `status` Literal[7 values], `trigger/inputs/steps/decision_points/approvals/side_effects/fallback_paths/success_criteria` as `list[dict]`, `export_payload: dict | None`.
- **Rules enforced:** `export_payload` only set by compiler; `status="activated"` only by Governance.
- **Reuses:** Pydantic convention.
- **Must NOT break:** none (new).

#### `governance.py` (REWRITE policy, KEEP decorator)
- **Responsibility:** Governed-write enforcement + blast-radius + approval gating.
- **Keep:** `@governed_write` decorator, `GovernanceError`, `_BLAST_RANK`, `default_create_planned_action` signature.
- **Rewrite:** `OBJECT_WRITE_POLICY` keys from `{Customer,Deal,RevenueMetric,Incident,Message}` → `{Party,Engagement,MoneyEvent,Issue,Message,PlannedAction,Workflow}` with new property entries (PRD §18.1 triggers).
- **Reuses:** decorator machinery; `PlannedAction` import (now from `action_types.py`).
- **Must NOT break:** existing `governed_*` reference wrappers compile (update object_type args); `test_*` governance tests still pass after policy update.

#### `adapter.py` (KEEP until Phase 4, then UPDATE)
- **Responsibility:** `mission_state_to_ontology` mapping.
- **Keep working through Phase 3:** do NOT delete `RevenueMetric` derivation yet (audit: "keep `mission_state_to_ontology` working until adapter.py updated").
- **Phase 4 change:** replace `RevenueMetric` derivation with `MoneyEvent` mapping; remove `_REVENUE_SCALAR_KEYS` / `_derive_revenue_metric` (audit: RevenueMetric→MoneyEvent is breaking).
- **Must NOT break:** any caller importing `mission_state_to_ontology` during Phases 0–3.

### 3.2 Schemas — `apps/ai/src/schemas/`

#### `engagement_state.py` (NEW)
- **Responsibility:** Canonical `EngagementState` (PRD §14.1).
- **Key type:** `EngagementState(BaseModel)` with `engagement_id, tenant_id, workspace_mode, phase, operator_goal, discovery_notes, ontology_objects, ontology_links, truth_findings, workflow_specs, executable_workflow_drafts, planned_actions, unresolved_questions, data_sources, freshness, updated_at`.
- **Reuses:** Pydantic convention; `extra="forbid"` for patch validation.
- **Must NOT break:** `mission_state.py` read path remains for compat (Phase 3 bridge).

#### `specialist_response.py` (EXTEND)
- **Responsibility:** `SpecialistResponse` (PRD §15.1).
- **Extend:** `specialist` Literal to include the 6 FDE specialists; add `engagement_state_patch: dict | None`, `unresolved_questions: list[str]`; keep `requires_hitl`/`planned_action_id` coupling.
- **Reuses:** current schema file (edit in place).
- **Must NOT break:** existing imports of `SpecialistResponse`.

#### `workflow_spec.py` (NEW)
- **Responsibility:** `WorkflowSpec` (PRD §15.2): `workflow_spec_id, workflow_name, business_goal, trigger, preconditions, required_inputs, responsible_role, decision_points, approval_points, exception_paths, expected_output, success_metric, linked_objects, sop_id, draft_runtime_targets`.

#### `sop.py` (NEW)
- **Responsibility:** `SOP` + `SOPStep` (PRD §15.3): step fields `step_number, actor, instruction, input, output, approval_required, fallback_if_failed`.

#### `executable_workflow_draft.py` (NEW)
- **Responsibility:** Re-export / canonical `ExecutableWorkflowDraft` (may alias `ontology/workflow_drafts.py` or define here and import there). Decide single source of truth (recommend `ontology/workflow_drafts.py` is canonical; this re-exports).

### 3.3 Workflows — `apps/ai/src/workflows/`

#### `chief_of_staff_workflow.py` (REFACTOR → control plane)
- **Responsibility:** PRD §8.1, §16.1 — intent classify, route, merge patches, summarize.
- **Reuses:** Temporal `@workflow.defn(name="ChiefOfStaffWorkflow")`; `mission_state_to_ontology` (Phase 3); new `engagement_state_store`.
- **Must NOT break:** Go dispatch still starts `ChiefOfStaffWorkflow` by name; `@sarthi` alias resolves to it.

#### `discovery_workflow.py`, `ontology_mapping_workflow.py`, `truth_analysis_workflow.py`, `workflow_builder_workflow.py`, `governance_workflow.py` (NEW)
- **Responsibility:** PRD §8.2–8.6, §16.2–16.6.
- **Reuses:** `worker.py` bootstrap pattern; `governance.py` for Governance; `engagement_state_store` for read/write; `specialist_response.py` return type.
- **Must NOT break:** each returns valid `SpecialistResponse`; only Governance sets activation status.

### 3.4 Runtime/export — `apps/ai/src/runtime/` (GREENFIELD — highest risk)

#### `n8n_compiler.py`, `custom_agent_compiler.py` (NEW)
- **Responsibility:** Deterministic compilation of `ExecutableWorkflowDraft` → runtime payload (PRD §17.3).
- **Key funcs:** `compile(draft: ExecutableWorkflowDraft) -> dict` returning `export_payload`. Pure functions, no LLM, no I/O.
- **Reuses:** `workflow_drafts.py` model; runtime-selection logic from PRD §17.
- **Must NOT break:** none (new); must be importable by `governance_workflow` and artifact service.

#### `artifact_export.py` (NEW)
- **Responsibility:** Build exportable artifacts (truth map, ontology snapshot, workflow pack, SOP pack, action register, executable draft) as JSONB into `artifact_exports` (PRD §5.2, §22.6).
- **Reuses:** `engagement_state_store` read; compilers for draft payload.

### 3.5 Session/state — `apps/ai/src/session/`

#### `mission_state.py` (KEEP as compat read)
- **Responsibility:** unchanged read path; deprecated write path.
- **Must NOT break:** `get_mission_state` still callable; `adapter.py` uses it through Phase 3.

#### `engagement_state_store.py` (NEW)
- **Responsibility:** Postgres `engagement_states` CRUD + deterministic patch merge (PRD §14.2).
- **Reuses:** `src.config.database` client; `engagement_state.py` model.

### 3.6 Go gateway — `apps/core/internal/web/`

#### `handler.go` (EDIT route map + workspace endpoints)
- **Edit:** `specialistRoutes` map → engagement routes (PRD §25): add `@ontologyai`,`@chief`,`@discover`,`@map`,`@truth`,`@build`,`@govern`; keep `@sarthi`,`@agent`,`@qa`,`@ask` (P5); remap `@finance`/`@fpa`→`TruthAnalysisWorkflow` (money), `@ops`→`WorkflowBuilderWorkflow`/`TruthAnalysisWorkflow`, `@comms`→`DiscoveryWorkflow`/`WorkflowBuilderWorkflow` (PRD §25.3).
- **Reuse:** `planned_actions` HITL `SignalWorkflow("hitl-approval")` path (lines 1863–1900) unchanged.
- **Must NOT break:** `@sarthi` route + Go tests (command_center_test.go lines 791–807).

#### `sse_hub.go` (REUSE)
- **Responsibility:** SSE broadcast; reused as-is for workspace streaming.

#### HTMX templates `templates/` (RE-SKIN)
- **Edit:** dashboard → 11 workspace screens (PRD §19.2); guardian cards → truth cards; decision journal → action register; keep 2 `@sarthi`-referencing templates.
- **Reuses:** existing HTMX partials structure.

### 3.7 Scheduler — `apps/ai/src/scheduler/ontology_ai_scheduler.py` (KEEP semantics)
- **Responsibility:** APScheduler jobs; change job *semantics* to engagement-phase cadence, keep infra (PRD §24.3).
- **Must NOT break:** scheduler bootstrap; CI job definitions (devops-agent scope).

### 3.8 Authority manifest — `apps/ai/src/agents/authority_manifest.py` (REFACTOR)
- **Edit:** relabel 5 agents → `Discovery, OntologyMapper, TruthAnalyst, WorkflowBuilder, Governance` + `ChiefOfStaff`; update `domain` enum + `writes_mission_fields` → `writes_engagement_fields`; keep `get_authority`/`can_execute_tool` API.
- **Must NOT break:** any importer of `get_authority`/`can_execute_tool`.

### 3.9 Router — `apps/ai/src/agents/cofounder/router.py` (REFACTOR → intent classifier)
- **Edit:** `Router.route` → `ChiefOfStaffIntentClassifier.classify(message) -> IntentCategory` (PRD §16.1 step 3 categories). Keep `route_message` convenience fn.
- **Reuses:** `relevance_gate`, `trust_battery` if still relevant; drop investor-escalation keywords (deprecate, PRD §24.4).
- **Must NOT break:** `worker.py` / handler import path (update import in ChiefOfStaffWorkflow).

---

## 4. Data Model & Migrations (PRD §22)

### 4.1 Tables

| Table | Status | Notes |
|---|---|---|
| `engagement_states` | **NEW** | PRD §22.2: `id UUID PK, tenant_id UUID, engagement_id TEXT UNIQUE, workspace_mode TEXT, phase TEXT, state JSONB NOT NULL, updated_at TIMESTAMPTZ` |
| `planned_actions` | **ALTER** | Existing (command_center.sql) has `actor, action_type, target_ref, risk_level, requires_approval, status, ...`. Add columns to match PRD §12.6: `target_object_type TEXT, execution_payload JSONB, source_refs JSONB[], temporal_workflow_id TEXT` (already referenced in handler.go line 1873). Keep `status` vocabulary extended to PRD §12.6 literals. |
| `executable_workflow_drafts` | **NEW** | PRD §22.4 |
| `workflow_specs` | **NEW** | PRD §22.3 |
| `approvals` | **NEW** | PRD §22.5 |
| `session_messages` | **NEW** | PRD §22.1 (chat/connector messages; distinct from legacy `chat_messages`) |
| `artifact_exports` | **NEW** | PRD §22.6 |
| `data_sources` | **NEW** | PRD §22.7 |
| `mission_states` | **BRIDGE (keep 1 version)** | Keep for compat read; `engagement_states` is canonical write target. See OQ §8 on full migration vs bridge. |

### 4.2 Migration pattern (follow existing `apps/core/internal/db/migrations/NNN_*.sql`)
- New file: `010_ontologyai_v51.sql` (or split per concern). Use `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` (idempotent, per AGENTS.md).
- `planned_actions` ALTER: `ALTER TABLE planned_actions ADD COLUMN IF NOT EXISTS target_object_type TEXT; ...` — non-destructive.
- `engagement_states`: JSONB `state` holds the full `EngagementState` dict (PRD §22.2).
- sqlc: regenerate `apps/core/internal/db/` after schema change (`make proto` / sqlc per AGENTS.md). Add queries to `internal/db/queries/` with `-- name: {Action}{Entity} :{one|many}` convention.
- Python side: `engagement_state_store.py` uses `asyncpg` directly (matches `mission_state.py` style) — no sqlc for Python.

### 4.3 Indexes
- `engagement_states(tenant_id)`, `engagement_states(engagement_id)`.
- `planned_actions(status)`, `planned_actions(tenant_id)`.
- `executable_workflow_drafts(engagement_id, status)`.
- `approvals(engagement_id, status)`.

---

## 5. Agent Delegation Map

Sequencing with dependencies (→ = depends on):

```
database-optimizer  ┐
ai-engineer(schemas)┼─→ ai-engineer(workflows) ─→ ai-engineer(runtime compilers)
                    │
backend-developer ←─┘ (after schemas + engagement_states migration land)
devops-agent (parallel: CI/scheduler job semantics, after schemas)
testing-agent (continuous + final regression; depends on all)
docker-agent (env/compose only — keep infra, minimal touch)
```

### 5.1 ai-engineer (schemas + workflows + runtime compilers)
- **Scope:** All Python modules in §3.1–3.4 (ontology, schemas, workflows, runtime).
- **Inputs:** PRD §12, §13, §14, §15, §16, §17; audit gap list.
- **Sequence internally:** schemas (Phase 1) → workflow shells (Phase 2) → specialist logic (Phase 4) → compilers (Phase 5).
- **Acceptance:** `test_ontology_schema.py`, `test_link_and_action_registry.py`, `test_engagement_state.py`, `test_specialist_response.py`, `test_workflow_spec_schema.py`, `test_sop_schema.py`, `test_executable_workflow_draft.py`, `test_workflow_names.py`, `test_discovery_workflow.py`, `test_ontology_mapping_workflow.py`, `test_truth_analysis_workflow.py`, `test_workflow_builder_workflow.py`, `test_governance_workflow.py`, `test_n8n_compiler.py`, `test_custom_agent_compiler.py`, `test_hitl_governance.py` all pass. Exactly 6 workflows, 6 object types. Governance exclusivity enforced in code.

### 5.2 database-optimizer (migrations + repo)
- **Scope:** `010_ontologyai_v51.sql` (7 tables + `planned_actions` alter), sqlc regen, `engagement_state_store.py` (or hand off store to ai-engineer — recommend db-optimizer owns SQL/migration, ai-engineer owns the Python store that calls it).
- **Inputs:** PRD §22; existing `command_center.sql` `planned_actions` shape; AGENTS.md sqlc conventions.
- **Acceptance:** migrations apply idempotently on fresh + existing DB; `engagement_states` writable; `planned_actions` has new columns; sqlc compiles; Go build clean.

### 5.3 backend-developer (Go routes + SSE + HTMX workspace UI)
- **Scope:** `handler.go` route map → engagement routes; new workspace endpoints; HTMX templates re-skin to 11 screens; truth cards; action register; keep `sse_hub.go` + HITL path.
- **Inputs:** PRD §19, §25; audit reuse list (handler.go, sse_hub.go, templates); `@sarthi` constraint.
- **Depends on:** schemas + `engagement_states` migration (to wire endpoints).
- **Acceptance:** Go `go test ./...` green (incl. `@sarthi` tests); 11 screens render; approval buttons call existing HITL signal; `@sarthi` templates intact.

### 5.4 devops-agent (CI / scheduler job semantics)
- **Scope:** Update CI to run V5.1 suite; adjust `ontology_ai_scheduler.py` job semantics to engagement-phase cadence (keep APScheduler infra); ensure `TRACKGUARD-MAIN-QUEUE` rename (or env override) propagates to CI/deploy.
- **Inputs:** PRD §24.3; existing scheduler; OQ §8 on queue naming.
- **Acceptance:** CI runs Python + Go suites; scheduler jobs registered; no infra rewrite.

### 5.5 testing-agent (V5.1 suite + regression)
- **Scope:** Author all PRD §28.1 test files not owned by feature agents; run full regression (target ≥901 Python + 74 Go + new); integration tests (PRD §28.3); UI checklist (§28.4).
- **Inputs:** PRD §28; audit "901 passing" baseline.
- **Acceptance:** zero regression on reusable infra; all V5.1 assertions pass; integration chain chat→discovery→ontology→truth→workflow→draft→governance→export green.

### 5.6 docker-agent (env / compose only — keep infra)
- **Scope:** Minimal — confirm `docker-compose` (Temporal, Qdrant, Postgres) still serves; add env var `TEMPORAL_TASK_QUEUE` override if renaming queue; no new services.
- **Inputs:** audit "keep infra"; PRD §21.3.
- **Acceptance:** `make up` brings all services; no new containers; existing services untouched.

---

## 6. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **`apps/ai/src/runtime/` greenfield (highest risk)** — deterministic compiler mandated, no existing reference. | TDD-first: write `test_n8n_compiler.py`/`test_custom_agent_compiler.py` with exact expected payloads before impl. Keep compilers pure (no LLM/I/O). ai-engineer owns; testing-agent validates determinism (same input → byte-stable output). |
| R2 | **`RevenueMetric`→`MoneyEvent` breaking change** — `adapter.py` derives RevenueMetric; deleting breaks callers. | Keep `mission_state_to_ontology` + RevenueMetric derivation through Phase 3. Only in Phase 4 replace derivation with MoneyEvent mapping. Grep all importers first; update in one commit. |
| R3 | **Naming collisions** — old `Customer/Deal/Incident` vs new `Party/Engagement/Issue`; `OBJECT_WRITE_POLICY` keys. | Phase 1 rewrites `object_types.py` + `governance.py` policy together. `OBJECT_TYPES` registry replaced atomically. Grep for old names across repo before delete. |
| R4 | **`@sarthi` backward-compat** — Go route map + 2 HTML templates + Go tests reference it. | P5: never remove `@sarthi` entry; keep 2 templates; Go tests stay. Add to regression gate. |
| R5 | **Governance exclusivity enforcement** — non-governance workflows could set `activated`. | Enforce in `workflow_drafts.py` model validator + `governance.py`; `test_governance_workflow.py` + `test_hitl_governance.py` assert only Governance transitions to `activated`/`executing`/`completed`/`exported`. |
| R6 | **Test regression on 901 existing tests** — broad refactor. | Phase 0 proves 901+74 still green post surface cleanup. Each later phase runs full suite. testing-agent owns regression gate. Legacy workflows isolated behind flag (OQ §8) to avoid import churn. |
| R7 | **`EngagementState` absent** — build fresh, keep `MissionState` as compat read. | Phase 3 builds `engagement_state_store.py` + bridge; `mission_state.py` read path untouched until OQ §8 decision on full migration. |
| R8 | **5 operational agents are NET-NEW, not 1:1 renames** — audit warns not simple rename. | Treat as new modules (§3.3), not renames. authority_manifest refactored to 5+1; old graphs (finance/bi/ops/comms) kept behind flag or removed per OQ §8. |
| R9 | **`planned_actions` schema drift** — handler.go reads `temporal_workflow_id` (line 1873) not in current `command_center.sql`. | database-optimizer ALTER adds missing columns; verify against handler.go reads/writes before Go changes. |

---

## 7. Acceptance Criteria (maps to PRD §31)

| # | PRD §31 criterion | Verification |
|---|---|---|
| 1 | Exactly 6 workflows | `test_workflow_names.py` |
| 2 | Exactly 6 ontology object types | `test_ontology_schema.py` + `OBJECT_TYPES` registry assert |
| 3 | `EngagementState` canonical | `test_engagement_state.py`; store writes `engagement_states` |
| 4 | `ExecutableWorkflowDraft` exists & validated | `test_executable_workflow_draft.py` |
| 5 | Every workflow returns valid `SpecialistResponse` | each workflow test asserts return type |
| 6 | Only `GovernanceWorkflow` finalizes external execution | `test_governance_workflow.py`, `test_hitl_governance.py` |
| 7 | Medium/high blast-radius requires approval | `governance.py` policy + tests |
| 8 | Workflow activation governance-gated | compiler + governance tests |
| 9 | Shared workspace views (chat, uploads, ontology, truth, workflows, drafts, approvals, artifacts) | backend-developer UI tests (§28.4) |
| 10 | Export: truth map, ontology snapshot, workflow pack, SOP pack, action register, executable draft | `test_artifact_exports.py` |
| 11 | All schema/workflow/route/compiler/governance/export tests pass | full suite green |
| 12 | Reusable infra preserved | regression gate (901 Py + 74 Go) |
| 13 | Reads as FDE companion, not founder alert bot | deprecation checklist (§24.4) applied; no investor/fundraiser/hiring copy |

---

## 8. Open Questions / Decisions Needed From User

Please answer before implementation starts:

1. **`mission_states` table:** Fully migrate to `engagement_states` (delete `mission_states`), or keep `mission_states` as a read-only bridge for one version (recommended: bridge, per audit)? This affects `mission_state.py` and migration `010`.
2. **Investor / hiring / founder-guardian modules:** Delete entirely, or gate behind a feature flag (e.g. `LEGACY_MODULES=on`)? Audit says "deprecate from active surface." Recommend: gate behind flag for one version, then delete.
3. **Legacy workflows** (`PulseWorkflow`, `InvestorWorkflow`, `SelfAnalysisWorkflow`, `EvalLoopWorkflow`, `CompressionWorkflow`, `WeightDecayWorkflow`, `MemoryMaintenanceWorkflow`, plus `FPA`/`GrowthAnalytics`/`Reliability`/`Comms`): Remove from `worker.py` active roster now, or keep registered behind a flag? Affects `worker.py` and `workflows/__init__.py`.
4. **Task queue name `TRACKGUARD-MAIN-QUEUE`:** Rename to `ONTOLOGYAI-MAIN-QUEUE` (env-overridable, old name as fallback), or keep the old name to avoid deploy churn? Recommend rename with env override + fallback default.
5. **Git branch / PR naming:** Use `feature/ontologyai-v5.1` and PR title "OntologyAI V5.1 — FDE companion + multi-agent OS"? Confirm branch name and whether to open PR against `main` (AGENTS.md says never commit to main).
6. **`executable_workflow_draft.py` schema location:** Single source of truth in `ontology/workflow_drafts.py` (re-exported by `schemas/`), or define in `schemas/` and import into `ontology/`? Recommend `ontology/workflow_drafts.py` canonical.
7. **Scope of UI in V5.1:** Full 11 screens with real interactivity, or 11 screens with read-only/partial interactivity (chat + ontology + truth + approvals + exports functional, others stubbed)? Affects backend-developer effort and Phase 6 done-criteria.
8. **`data_sources` vs existing `chat_messages`:** New `session_messages` table is distinct from legacy `chat_messages` — confirm we add `session_messages` (per PRD §22.1) and leave `chat_messages` as legacy, or consolidate? Recommend add `session_messages` new, leave `chat_messages` legacy.

---

## 8.1 User decisions — LOCKED

1. `mission_states` remains a **read-only bridge for one version**; `engagement_states` is the canonical write target.
2. Investor / hiring / founder-guardian modules remain **behind a feature flag** (`LEGACY_FDE_MODULES=on`) for one version, then become deletion candidates.
3. Legacy workflows are **removed from the active roster now**; optional legacy registration may exist behind a feature flag during transition.
4. Task queue name becomes **`ONTOLOGYAI-MAIN-QUEUE`**, with env override and fallback to `TRACKGUARD-MAIN-QUEUE`.
5. Branch is **`feature/ontologyai-v5.1`**; all work lands through PR into `main`.
6. **`apps/ai/src/ontology/workflow_drafts.py`** is the single source of truth for `ExecutableWorkflowDraft`.
7. V5.1 UI is **functional-core first**: chat, uploads, ontology, truth findings, workflow drafts, approvals, and exports MUST be functional; remaining screens must exist but may be lighter.
8. Add new **`session_messages`**; keep legacy `chat_messages` unchanged for compatibility.

## 8.2 Plan tighten-ups (from review)

- **Explicit migration checklist (do not miscount):** new = `engagement_states`, `executable_workflow_drafts`, `workflow_specs`, `approvals`, `session_messages`, `artifact_exports`, `data_sources` (7 new). Altered = `planned_actions` (extend fields). Bridge = `mission_states` kept read-only. Total distinct tables in scope = 8 (7 new + 1 altered), plus 1 legacy `chat_messages` left untouched.
- **UI must-function vs must-exist split (Phase 6):** MUST-FUNCTION = Workspace Overview, Conversational Intake, Uploads/Connected Sources, Ontology Explorer, Truth Findings, Workflow Drafts, Planned Actions/Approvals, Artifacts/Exports, Session Log. MUST-EXIST (lighter) = Discovery Evidence Queue, Go live/Handoff summary panel.
- **EngagementState deterministic merge conflict test (acceptance):** add a named assertion that concurrent/overlapping typed patches merge deterministically, conflicts log + preserve provenance, and unknown keys are rejected. Covered by `test_engagement_state.py`.
- **Compiler purity test (acceptance):** add a named assertion that `export_payload` is ONLY populated by deterministic compiler code; the LLM call path can propose structure but must never write `export_payload`. Covered by `test_n8n_compiler.py` + `test_custom_agent_compiler.py`.

---

*End of plan. APPROVED — implementation may proceed per the agent delegation map (§5).*
