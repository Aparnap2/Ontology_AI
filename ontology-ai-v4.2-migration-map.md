# OntologyAI V4.2 Migration Map — Agents, Workflows, Tools, and Features

## Goal

This migration map shows exactly what stays, what changes, what gets reframed, and what should be removed so the existing codebase honestly fits the new framing:

**OntologyAI = a lightweight, ontology-driven operational intelligence layer for small businesses and startups with fragmented tools and limited historical data.**

The purpose is not to rebuild the system. The purpose is to make the current architecture semantically correct for the new product truth.

---

## 1. Migration principle

Do **not** optimize for “more agents.”
Optimize for:
- shared business objects,
- shared relationships,
- governed actions,
- reusable inference rules,
- and one coherent interface for querying and acting on the business.

That means:
- keep most top-level agents,
- refactor subagents that use private meanings,
- turn watchlist logic into ontology population/inference rules,
- and force workflows to read/write through the ontology.

---

## 2. Canonical target shape

### Top-level roles remain five
1. Chief of Staff
2. FP&A
3. Growth Analytics
4. Reliability & Delivery
5. Communications

### Core ontology objects
1. Customer
2. Deal
3. RevenueMetric
4. Incident
5. Message
6. PlannedAction

### Core workflow verbs
Every workflow should do one or more of these:
- query objects,
- update objects,
- infer new state from rules,
- propose governed action,
- execute approved action,
- explain current state.

---

## 3. Agent-by-agent migration

## Chief of Staff

### Keep
- Keep as the default front door.
- Keep as orchestration and synthesis layer.
- Keep as the fallback route for unknown user requests.

### Change
- Change primary identity from “router” or “guardian lead” to **ontology query and delegation interface**.
- It should answer questions by traversing ontology objects and links first, then delegate to specialists only when deeper domain action is needed.
- It must stop depending on ad hoc summaries from specialists as its primary source of truth.

### New responsibility
- Cross-object reasoning.
- Example: “Why did customer health drop?” should combine `Customer`, `RevenueMetric`, `Incident`, and `Message` state rather than only forwarding to one specialist.

### Code impact
- Refactor prompt/system framing.
- Add ontology adapter usage.
- Add helper methods for object traversal and linked summaries.

### Delete / demote
- Demote any “watch failure patterns” branding in this agent’s prompt or output.

---

## FP&A

### Keep
- Keep as finance and business health specialist.
- Keep runway, burn, revenue, cash interpretation logic.

### Change
- Stop acting like a standalone finance analyzer over raw tables.
- It must become the owner of `RevenueMetric` object quality and finance-related `PlannedAction` proposals.

### New responsibility
- Maintain and explain financial ontology state.
- Example actions:
  - update runway_days,
  - attach spend anomalies to `RevenueMetric`,
  - propose cancellation or collection actions as governed writes.

### Code impact
- Standardize outputs against shared ontology terms.
- Replace finance-specific implicit entity names with canonical objects.
- Wrap spend/cash actions in governed-write decorator.

### Delete / demote
- Remove any wording implying autonomous legal/financial execution without approval.

---

## Growth Analytics

### Keep
- Keep funnel, conversion, retention, and growth interpretation.
- Keep experimental / trend-oriented reasoning.

### Change
- Stop being only a reporting specialist.
- It should become the owner of `Deal`, customer-growth linkages, and growth inference rules.

### New responsibility
- Maintain growth ontology truth.
- Example:
  - map funnel stages into `Deal.stage`,
  - compute relationship between messaging, customer activity, and conversion,
  - emit governed actions for campaign or CRM updates.

### Code impact
- Replace raw metric-only answers with ontology-linked explanations.
- Use explicit links: `Deal -> Customer`, `Message -> Deal`.
- Ensure every output can identify which object(s) changed.

### Delete / demote
- Any pure dashboard-only passive wording.

---

## Reliability & Delivery

### Keep
- Keep incidents, delivery risk, operational execution, and system-health surface.

### Change
- Stop behaving as generic ops alerting.
- It should become the owner of the `Incident` object and its links to customers, delivery commitments, and actions.

### New responsibility
- Incident ontology stewardship.
- Example:
  - classify incidents,
  - link incidents to affected customers,
  - propose remediation actions,
  - update resolution state.

### Code impact
- Move incident reasoning into typed object updates.
- Require explicit object linkage when reporting impact.
- Route any operational writeback through governed actions.

### Delete / demote
- Any incident language that is not tied to a concrete object or linked impact.

---

## Communications

### Keep
- Keep drafting, tailoring, summarizing, and stakeholder message support.

### Change
- Stop being treated as a generic text utility.
- It should become the owner of the `Message` object and communication-linked actions.

### New responsibility
- Communication ontology stewardship.
- Example:
  - store draft messages as objects,
  - link message threads to customers and deals,
  - propose outbound sends via governed actions,
  - summarize stakeholder sentiment into structured properties.

### Code impact
- `CommsGraph` should return object-aware output.
- Drafts must include object references where possible.
- Sending should always be a governed action unless explicitly low-risk.

### Delete / demote
- Any “just draft text” framing without structured message-state ownership.

---

## 4. Subagent migration rules

Subagents may remain, but only under these conditions:

### Rule 1: No private ontology
A subagent cannot define its own meaning for:
- customer,
- account,
- deal,
- incident,
- message,
- action,
- risk,
- owner.

It must import or reference canonical object definitions.

### Rule 2: No ad hoc joins
If a subagent needs to connect incident -> customer or message -> deal, it must use named link definitions, not custom SQL/query logic embedded in prompts or helper methods.

### Rule 3: Outputs must reference objects
Every subagent output should identify:
- objects read,
- objects updated,
- actions proposed,
- confidence limits or missing data.

### Rule 4: Low-data honesty
If history is insufficient, the subagent must say so explicitly instead of producing high-confidence trend claims.

---

## 5. Workflow-by-workflow migration

## ChiefOfStaffWorkflow

### Keep
- keep as default route and front-door workflow.

### Refactor to
- ontology query workflow,
- cross-specialist synthesis workflow,
- approval-state explainer.

### Must do
- fetch ontology snapshot,
- traverse links,
- delegate only when deeper analysis or action generation is required,
- return object-aware answer.

---

## FPAWorkflow

### Keep
- keep workflow shell and Temporal contract.

### Refactor to
- finance ontology maintenance and governed-finance-action workflow.

### Must do
- read `RevenueMetric`, `Customer`, optional `Deal` context,
- propose `PlannedAction` for spend correction / collections,
- block on HITL when blast radius threshold is reached.

---

## GrowthAnalyticsWorkflow

### Keep
- keep workflow shell and registration.

### Refactor to
- growth ontology update and analysis workflow.

### Must do
- update `Deal` and linked customer context,
- surface object-linked reasons for funnel changes,
- optionally create action proposals for CRM or campaign changes.

---

## ReliabilityWorkflow

### Keep
- keep workflow shell and registration.

### Refactor to
- incident and delivery ontology workflow.

### Must do
- update `Incident`,
- link impact to customers or delivery commitments,
- generate governed remediation actions when needed.

---

## CommsWorkflow

### Keep
- create / keep as real workflow, not stub.

### Refactor to
- message-state and communication-action workflow.

### Must do
- create/update `Message` objects,
- relate them to customers/deals,
- create governed send actions when outbound execution is requested.

---

## 6. Feature migration map

| Existing feature | Keep / Change / Remove | What it becomes |
|---|---|---|
| MissionState | Change | Ontology backbone / semantic state layer |
| Guardian detection patterns | Change | Inference + ontology population rules |
| HITL queue | Keep | Governed action layer |
| SSE updates | Keep | Live ontology/action event stream |
| Dashboard panels | Change | Object + action views, not just alerts |
| Specialist chat | Keep | Ontology query/workbench UI |
| Hiring logic | Remove | Out of scope for 5-agent model |
| Freeform specialist outputs | Change | Object-aware structured outputs |

---

## 7. Tooling migration map

## Keep as-is
- Temporal
- PostgreSQL
- SSE transport
- existing approval/unblock mechanism
- workflow registration model

## Add / refactor
- ontology object schemas,
- ontology link registry,
- ontology adapter from MissionState,
- governed-write decorator,
- object-aware specialist response contract.

## Do not add unless clearly necessary
- graph database,
- additional orchestration engine,
- new specialist categories,
- ML training pipeline.

---

## 8. What should be deleted

Delete or remove from active product truth:
- “Guardian detection patterns” as hero positioning,
- “guardian” as the main product identity,
- any Hiring specialist or route,
- any workflow wording that implies specialists own private realities,
- any passive “report only” framing where the new system should query/update ontology and propose actions.

---

## 9. What should be added

Add these explicit capabilities:

1. Canonical object schema module.
2. Link type registry.
3. MissionState -> ontology adapter.
4. Governed write wrapper/decorator.
5. Object-aware specialist response format.
6. Low-data disclosure rule in specialist outputs.
7. Dashboard sections showing:
   - current objects,
   - linked objects,
   - pending actions,
   - approved / executed actions,
   - data sufficiency or freshness.

---

## 10. Hard truth: what fits now vs after migration

### Already fits well
- Temporal durability
- HITL approvals
- SSE
- five-agent top-level structure
- command-center UX direction

### Partially fits
- MissionState
- specialist boundaries
- dashboard panels
- route map

### Now implemented (V4.2 ontology layer shipped)
- **Ontology schema** — `object_types.py` with 6 strict Pydantic v2 Object Types (TDD-verified, 23 tests).
- **Shared object semantics** — `link_types.py` `LINK_TYPES` registry + `resolve_link()` (raises `KeyError` for unknown links).
- **Reusable links** — 4 canonical Link Types defined once, queried everywhere.
- **Governed internal writes** — `governance.py` `@governed_write` decorator + `OBJECT_WRITE_POLICY` blast-radius gate (7 tests); reference wrappers per specialist.
- **MissionState → Ontology adapter** — `adapter.py` tolerant mapping (12 tests).

### Still incremental (follow-on work)
- full retrofitting of every specialist write path through `@governed_write`,
- complete migration of the flat `MissionState` blob to normalized Object Type rows,
- object-aware cross-agent reasoning in every workflow,
- low-data explicitness surfaced in every specialist output.

That means the Ontology core is **now real and tested**, while broader workflow retrofitting remains incremental — a targeted migration that is well underway.

---

## 11. Recommended migration order

### Phase 1 — semantics
- define object schemas,
- define links,
- define response contract.

### Phase 2 — state alignment
- adapt MissionState,
- reclassify failure patterns as inference rules,
- add low-data behavior.

### Phase 3 — workflow behavior
- upgrade Chief of Staff,
- make each specialist read/write via ontology,
- enforce governed writes.

### Phase 4 — UI and PRD
- update dashboard copy,
- update README and PRD,
- remove legacy guardian language.

---

## 12. Final answer

You do **not** need to replace your full agent architecture.

You **do** need to:
- keep the five top-level specialists,
- refactor subagents so they share one business vocabulary,
- turn workflows into ontology pipelines and governed actions,
- demote watchlist logic into inference rules,
- and make MissionState a real ontology layer instead of a loose shared blob.

That is the smallest honest migration path from the current codebase to the new framing.
