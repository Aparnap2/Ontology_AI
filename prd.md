# OntologyAI V5.1 — PRD + Workflow + SOP + Business Logic + Technical Specification

Version: 5.1  
Status: Final implementation spec  
Purpose: Portfolio-grade self-serve FDE companion + multi-agent FDE operating system  
Audience: Coding agent, engineering reviewer, portfolio reviewer

---

# 1. Product truth

OntologyAI V5.1 is a **self-serve FDE companion** and **multi-agent Forward Deployed Engineer system**.

It operates in two modes:
1. **FDE-assisted workspace** — a real FDE/operator uses the system to compress discovery, ontology mapping, truth analysis, workflow design, governance, and pilot deployment.
2. **Client self-serve workspace** — a client receives a workspace link, converses with the system, uploads files, connects tools, answers targeted follow-up questions, and the agents perform the same discovery-to-workflow loop.

OntologyAI is not just a reporting system.
Its job is to convert messy business inputs into shared operational truth, generate governed workflow designs, and where viable, produce executable automation drafts for n8n or custom agent runtimes.

The software demonstrates the FDE method as a reusable product layer:
- conversational discovery from ambiguous business inputs,
- ontology construction from uploads, transcripts, exports, and connected systems,
- multi-agent reasoning over shared state,
- governed workflow generation,
- executable workflow draft generation,
- governed deployment planning,
- and exportable handoff artifacts.

---

# 2. Portfolio positioning

## 2.1 One-line pitch

OntologyAI is a self-serve FDE companion that turns messy business operations into a shared ontology, diagnoses truth across people, money, work, messages, and decisions, and generates governed workflow specs plus executable automation drafts.

## 2.2 What this is not

It is not:
- a founder alert bot,
- a finance-only assistant,
- a general chatbot,
- a passive dashboard,
- a generic no-code builder,
- or an autonomous action engine with unlimited write access.

## 2.3 What this is

It is:
- a portfolio-grade simulation of how an FDE actually works,
- a shared agentic workspace for discovery and pilot building,
- an ontology-first AI operating layer,
- a governed multi-agent architecture,
- and a reusable discovery-to-deployment implementation framework.

---

# 3. Users and operating modes

## 3.1 Primary users

Primary users:
- FDE / operator / implementation engineer
- client-side owner / operations lead using a workspace directly

Secondary users:
- approvers
- reviewers
- domain contributors
- internal stakeholders consuming truth maps, workflows, SOPs, and approvals

## 3.2 Operating modes

OntologyAI runs in **engagement workspace mode** with two entry modes:

1. `fde_assisted`
2. `client_self_serve`

Both modes use the same ontology, workflow engine, governance layer, and artifact generation system.
The only difference is who drives the interaction.

## 3.3 Engagement phases

1. Discovery
2. Ontology Mapping
3. Truth Analysis
4. Workflow Design
5. Governance Review
6. Deployment Planning
7. Handoff

These phases are first-class workflow states in the product.

---

# 4. Non-negotiable principles

1. Shared ontology is the source of truth.
2. No agent owns a private model of the business.
3. LLMs are used only for ambiguity, extraction, synthesis, intent parsing, and language generation.
4. Deterministic code handles routing, validation, computations, thresholds, formatting, and state transitions.
5. Every consequential action must be represented as a `PlannedAction`.
6. Every deployable workflow must be represented as an `ExecutableWorkflowDraft`.
7. Medium/high-risk actions require explicit approval.
8. No external side-effect execution is finalized outside the governance path.
9. Outputs must be typed and validated.
10. Every workflow must degrade gracefully on missing data.
11. The system must generate deployable outputs, not just chat responses.
12. Reuse existing code aggressively before writing new infrastructure.

---

# 5. Final system shape

## 5.1 Product mental model

The final loop is:

1. User opens a workspace.
2. User chats, uploads files, or connects systems.
3. Discovery Agent extracts business facts and missing questions.
4. Ontology Mapper converts evidence into canonical objects and links.
5. Truth Analyst identifies what is stuck, missing, risky, contradictory, or action-worthy.
6. Workflow Builder produces workflow specs, SOPs, and executable workflow drafts.
7. Governance validates planned actions and executable drafts.
8. Approved drafts are exported or activated.
9. The system generates truth maps, workflow packs, SOP packs, and action registers.

## 5.2 Final product outputs

The system must produce one or more of:
- Truth Map
- Ontology Snapshot
- Workflow Pack
- SOP Pack
- Action Register
- Executable Workflow Draft
- Governed pilot-ready deployment package

---

# 6. Agent model

## 6.1 Control plane

### ChiefOfStaff Agent

Role:
- front-door interface,
- workspace orchestrator,
- state synthesizer,
- router,
- progress summarizer,
- handoff summarizer.

The ChiefOfStaff is not a domain specialist.
It coordinates the engagement and translates user intent into specialist work.

## 6.2 Operational agents

### 1. Discovery Agent
Purpose:
- conduct conversational discovery through chat,
- ingest uploads, transcripts, exports, screenshots, and connector-fed data,
- ask targeted follow-up questions only when evidence is missing,
- extract operational reality into typed discovery findings.

### 2. Ontology Mapper Agent
Purpose:
- transform discovered raw business facts into canonical objects, properties, links, provenance, and confidence metadata.

### 3. Truth Analyst Agent
Purpose:
- reason over the ontology to identify what is true, stuck, missing, risky, contradictory, or action-worthy.

### 4. Workflow Builder Agent
Purpose:
- translate ontology truth into workflow specs, responsibilities, approvals, SOPs, and implementation proposals,
- generate executable workflow drafts for supported runtimes,
- emit governed `PlannedAction` records for any deployable change.

### 5. Governance Agent
Purpose:
- enforce action validity,
- validate executable workflow drafts,
- enforce blast radius policy,
- create approval tasks,
- gate external side effects,
- maintain action lifecycle,
- log audit-ready execution metadata.

---

# 7. Workflow roster

The final active workflow set is exactly:

1. `ChiefOfStaffWorkflow`
2. `DiscoveryWorkflow`
3. `OntologyMappingWorkflow`
4. `TruthAnalysisWorkflow`
5. `WorkflowBuilderWorkflow`
6. `GovernanceWorkflow`

Exactly 6 workflows total.

---

# 8. Workflow responsibilities

## 8.1 ChiefOfStaffWorkflow

Responsibilities:
- accept workspace request,
- determine current phase,
- classify intent,
- route to one or more specialist workflows,
- merge outputs into shared state,
- produce next-step summary,
- surface unresolved questions,
- generate handoff summary when requested.

## 8.2 DiscoveryWorkflow

Responsibilities:
- ingest workspace messages, uploaded files, transcript summaries, spreadsheet summaries, screenshots, connector records, and manual notes,
- extract candidate entities, events, SOP fragments, process hints, and unresolved questions,
- ask targeted follow-up questions only when required facts are missing,
- produce typed discovery findings,
- never finalize ontology objects directly.

## 8.3 OntologyMappingWorkflow

Responsibilities:
- convert discovery findings into canonical objects,
- create links,
- attach provenance and confidence,
- flag ambiguities,
- produce ontology patch for shared state.

## 8.4 TruthAnalysisWorkflow

Responsibilities:
- analyze ontology snapshot,
- compute stuck/risk/contradiction/missing-state findings,
- generate truth report,
- propose candidate actions,
- never execute external actions.

## 8.5 WorkflowBuilderWorkflow

Responsibilities:
- take truth findings and generate workflow recommendations,
- define owner, trigger, inputs, outputs, approvals, fallback paths, and success metrics,
- generate SOPs,
- generate handoff-ready workflow packs,
- generate `ExecutableWorkflowDraft` objects for supported runtimes,
- produce planned actions if implementation, export, activation, or execution is proposed.

## 8.6 GovernanceWorkflow

Responsibilities:
- validate planned actions,
- validate executable workflow drafts,
- enforce blast radius policy,
- create approval tasks,
- gate external side effects,
- determine whether a workflow draft remains draft, is exportable, or is activatable,
- maintain action lifecycle,
- log audit-ready execution metadata.

---

# 9. End-to-end workflow

## 9.1 FDE-assisted mode

1. FDE creates workspace.
2. Client joins via link.
3. FDE or client provides context through chat/uploads/connectors.
4. Discovery builds evidence queue.
5. Ontology Mapper builds shared process map.
6. Truth Analyst surfaces bottlenecks and contradictions.
7. Workflow Builder proposes fix and draft automation.
8. Governance requests approvals where required.
9. Approved workflow is exported or activated.
10. Handoff artifacts are generated.

## 9.2 Client self-serve mode

1. Client opens workspace link.
2. System asks goal-oriented onboarding questions.
3. Client uploads files and connects systems.
4. Discovery extracts facts and asks only missing questions.
5. Ontology and process map appear progressively.
6. Truth Analyst identifies operational problems.
7. Workflow Builder proposes pilot workflow and SOP.
8. Governance blocks risky actions until approved.
9. User exports draft or activates allowed automation.

---

# 10. Business logic

## 10.1 Core business rule

Truth must be established before automation.
No workflow draft should be activated from raw notes alone.

## 10.2 Discovery rules

- At least one evidence source must exist before discovery completes.
- Evidence may come from chat, file upload, transcript summary, export, screenshot, or connector data.
- Missing required fields must trigger follow-up questions rather than hallucinated structure.

## 10.3 Ontology rules

- Every canonical object must have provenance.
- Every link must be evidence-backed.
- Ambiguous facts must remain unresolved instead of guessed.

## 10.4 Truth analysis rules

Deterministic checks run first:
- missing owners,
- overdue money events,
- blocked engagements,
- unresolved critical issues,
- unacted messages,
- orphaned records,
- duplicate/conflicting records.

LLM synthesis may only summarize or connect findings after deterministic checks complete.

## 10.5 Workflow generation rules

Every workflow spec must include:
- business goal,
- trigger,
- inputs,
- responsible role,
- decision points,
- approval requirements,
- exception path,
- output,
- success metric,
- SOP steps.

## 10.6 Deployment rules

- Executable drafts may exist in `draft`, `validated`, or `pending_approval` states without activation.
- Only GovernanceWorkflow may permit export or activation for risky workflows.
- Export payloads are generated by deterministic compiler code, not by freehand LLM JSON output.

## 10.7 Risk rules

Approval is required when:
- blast radius is `medium` or `high`,
- action changes external system state,
- action changes money state,
- action changes ownership,
- action sends outbound communication,
- action closes an issue without evidence,
- action activates a workflow with side effects.

---

# 11. Thin LLM, fat deterministic core

OntologyAI must inherit the proven architectural pattern from the existing Sarthi system: deterministic code for fetching, routing, validation, and state transitions; LLMs only for ambiguity, synthesis, narrative generation, and intent parsing. [file:556]

## 11.1 Allowed LLM jobs

LLM may do:
- intent parsing from natural language,
- extraction from messy text,
- synthesis across findings,
- follow-up question drafting,
- workflow naming and natural-language summaries,
- SOP narrative phrasing.

## 11.2 Forbidden LLM jobs when code can do it

LLM must not:
- compute thresholds,
- validate schemas,
- perform state merges,
- choose blast radius if it is rule-derivable,
- generate export payloads directly,
- finalize approvals,
- perform deterministic routing.

## 11.3 Boundary test

Before every LLM call:
1. Could an `if/elif` answer this? Use code.
2. Could a SQL query answer this? Use SQL.
3. Could a typed parser/validator answer this? Use code.

Only if all three are no should the LLM be used.

---

# 12. Canonical ontology model

The ontology has exactly 6 primary object types.

## 12.1 Party

Represents people or organizations relevant to the business.

Subtypes:
- customer
- supplier
- employee
- contractor
- partner
- approver

Required fields:
- `id: str`
- `kind: Literal["customer","supplier","employee","contractor","partner","approver"]`
- `name: str`
- `status: Literal["active","inactive","at_risk","blocked"]`
- `owner: str | None`
- `contact_points: list[str]`
- `notes: str | None`
- `source_refs: list[str]`

## 12.2 Engagement

Represents units of work, commercial motion, or deliverables.

Subtypes:
- deal
- order
- job
- project
- service_case

Required fields:
- `id: str`
- `kind: Literal["deal","order","job","project","service_case"]`
- `title: str`
- `status: Literal["new","quoted","active","blocked","done","billed","closed"]`
- `owner: str | None`
- `value: float | None`
- `due_date: str | None`
- `notes: str | None`
- `source_refs: list[str]`

## 12.3 MoneyEvent

Represents financial events and obligations.

Subtypes:
- receivable
- payable
- payment
- refund
- writeoff
- expense

Required fields:
- `id: str`
- `kind: Literal["receivable","payable","payment","refund","writeoff","expense"]`
- `amount: float`
- `currency: str`
- `status: Literal["open","due","paid","partial","overdue","cancelled"]`
- `due_date: str | None`
- `occurred_at: str | None`
- `counterparty_id: str | None`
- `notes: str | None`
- `source_refs: list[str]`

## 12.4 Issue

Represents blockers, disputes, delays, defects, or incidents.

Subtypes:
- delay
- dispute
- defect
- incident
- risk
- blocker

Required fields:
- `id: str`
- `kind: Literal["delay","dispute","defect","incident","risk","blocker"]`
- `severity: Literal["low","medium","high","critical"]`
- `status: Literal["open","investigating","waiting","resolved","closed"]`
- `opened_at: str | None`
- `resolved_at: str | None`
- `owner: str | None`
- `summary: str`
- `notes: str | None`
- `source_refs: list[str]`

## 12.5 Message

Represents communication artifacts.

Subtypes:
- email
- whatsapp
- call_note
- sms
- note
- meeting_summary

Required fields:
- `id: str`
- `channel: Literal["email","whatsapp","call_note","sms","note","meeting_summary"]`
- `thread_id: str | None`
- `timestamp: str | None`
- `direction: Literal["inbound","outbound","internal"]`
- `summary: str`
- `sentiment: Literal["positive","neutral","negative","mixed","unknown"]`
- `needs_action: bool`
- `source_refs: list[str]`

## 12.6 PlannedAction

Represents proposed or governed changes.

Required fields:
- `id: str`
- `type: str`
- `title: str`
- `blast_radius: Literal["low","medium","high"]`
- `status: Literal["draft","pending_approval","approved","rejected","executing","completed","failed"]`
- `requested_by: str`
- `target_object_type: Literal["Party","Engagement","MoneyEvent","Issue","Message","Workflow"]`
- `target_id: str`
- `rationale: str`
- `requires_approval: bool`
- `execution_payload: dict | None`
- `source_refs: list[str]`

## 12.7 ExecutableWorkflowDraft

Represents a machine-readable workflow draft ready for compilation or export.

Required fields:
- `id: str`
- `runtime: Literal["n8n","custom_agent"]`
- `name: str`
- `source_workflow_spec_id: str`
- `status: Literal["draft","validated","pending_approval","approved","exported","activated","failed"]`
- `trigger: dict`
- `inputs: list[dict]`
- `steps: list[dict]`
- `decision_points: list[dict]`
- `approvals: list[dict]`
- `side_effects: list[dict]`
- `fallback_paths: list[dict]`
- `success_criteria: list[str]`
- `export_payload: dict | None`
- `source_refs: list[str]`

Rules:
- `export_payload` may only be populated by deterministic compiler logic.
- `status="activated"` may only be set by `GovernanceWorkflow`.
- Any outbound communication or money-state change requires approval.

---

# 13. Canonical link types

Minimum required link types:
- `party_engagement`
- `engagement_money_event`
- `engagement_issue`
- `message_party`
- `message_engagement`
- `issue_planned_action`
- `money_event_planned_action`
- `party_planned_action`
- `engagement_planned_action`
- `workflow_action`
- `workflow_object_dependency`

Every link must declare:
- `name`
- `source_type`
- `target_type`
- `cardinality`
- `semantic_meaning`
- `source_refs`

---

# 14. Shared state model

## 14.1 Canonical EngagementState

```python
class EngagementState(BaseModel):
    engagement_id: str
    tenant_id: str
    workspace_mode: Literal["fde_assisted", "client_self_serve"]
    phase: Literal[
        "discovery",
        "ontology_mapping",
        "truth_analysis",
        "workflow_design",
        "governance_review",
        "deployment_planning",
        "handoff",
    ]
    operator_goal: str | None
    discovery_notes: list[dict]
    ontology_objects: dict[str, list[dict]]
    ontology_links: list[dict]
    truth_findings: list[dict]
    workflow_specs: list[dict]
    executable_workflow_drafts: list[dict]
    planned_actions: list[dict]
    unresolved_questions: list[str]
    data_sources: list[dict]
    freshness: dict[str, str]
    updated_at: str
```

## 14.2 State rules

- All specialist workflows read `EngagementState` first.
- All specialist workflows write back a typed patch, not arbitrary freeform state.
- State merge must be deterministic.
- Unknown keys are rejected.
- State merge conflicts must log and preserve provenance.
- `workspace_mode` is immutable after creation unless explicitly migrated.

---

# 15. Structured contracts

## 15.1 SpecialistResponse

Every workflow must return a typed `SpecialistResponse`.

Required fields:
- `specialist: Literal["Discovery","OntologyMapper","TruthAnalyst","WorkflowBuilder","Governance","ChiefOfStaff"]`
- `workflow_name: str`
- `summary: str`
- `detailed_response: str`
- `objects_read: list[str]`
- `objects_written: list[str]`
- `actions_proposed: list[str]`
- `requires_hitl: bool`
- `planned_action_id: str | None`
- `citations: list[str]`
- `followups: list[str]`
- `engagement_state_patch: dict | None`
- `confidence: float | None`
- `unresolved_questions: list[str]`

Rules:
- `requires_hitl=True` requires `planned_action_id`.
- `engagement_state_patch` must validate against the allowed schema.
- `workflow_name` must equal the actual workflow definition name.

## 15.2 WorkflowSpec

Each generated workflow spec must contain:
- `workflow_spec_id`
- `workflow_name`
- `business_goal`
- `trigger`
- `preconditions`
- `required_inputs`
- `responsible_role`
- `decision_points`
- `approval_points`
- `exception_paths`
- `expected_output`
- `success_metric`
- `linked_objects`
- `sop_id`
- `draft_runtime_targets`

## 15.3 SOP schema

Each SOP must contain:
- `sop_id`
- `title`
- `business_goal`
- `trigger`
- `preconditions`
- `required_inputs`
- `steps`
- `decision_points`
- `approval_points`
- `exception_paths`
- `completion_criteria`
- `owner_role`
- `reporting_output`
- `linked_objects`
- `linked_actions`

Each SOP step must contain:
- `step_number`
- `actor`
- `instruction`
- `input`
- `output`
- `approval_required`
- `fallback_if_failed`

---

# 16. Detailed workflow execution logic

## 16.1 ChiefOfStaffWorkflow exact behavior

Input:
- `tenant_id`
- `engagement_id`
- `workspace message`
- optional `phase`

Steps:
1. Load `EngagementState`.
2. If no state exists, initialize phase=`discovery`.
3. Determine intent category:
   - discovery input,
   - ontology mapping request,
   - truth analysis request,
   - workflow design request,
   - governance request,
   - deployment planning request,
   - handoff request.
4. Route to one or more specialist workflows.
5. Collect typed outputs.
6. Deterministically merge valid patches into `EngagementState`.
7. Produce concise workspace summary and next step.
8. Return `SpecialistResponse` as `ChiefOfStaff`.

## 16.2 DiscoveryWorkflow exact behavior

Input:
- `tenant_id`
- `engagement_id`
- workspace messages
- uploaded files
- transcript summaries
- spreadsheet summaries
- connector-fed records
- note bundles

Steps:
1. Validate at least one evidence source exists.
2. Normalize input into `DiscoveryInput`.
3. Extract:
   - candidate parties,
   - candidate engagements,
   - candidate money facts,
   - candidate issues,
   - candidate messages,
   - SOP fragments,
   - process hints,
   - unresolved questions.
4. Ask targeted follow-up questions only when required fields cannot be inferred safely.
5. Mark each extraction with confidence and provenance.
6. Do not create canonical ontology objects yet.
7. Return patch into `EngagementState.discovery_notes`.

## 16.3 OntologyMappingWorkflow exact behavior

Input:
- discovery notes
- optional existing ontology state

Steps:
1. Load discovery findings.
2. Convert candidates into canonical object instances.
3. Validate object field completeness.
4. Create required links where evidence exists.
5. Add source references.
6. If ambiguity exists, keep unresolved question instead of inventing structure.
7. Return patch to `ontology_objects`, `ontology_links`, and `unresolved_questions`.

## 16.4 TruthAnalysisWorkflow exact behavior

Input:
- current ontology snapshot

Steps:
1. Load all ontology objects and links.
2. Compute deterministic findings first:
   - missing owners,
   - overdue money events,
   - blocked engagements,
   - unresolved critical issues,
   - unacted messages,
   - orphaned records.
3. Use LLM only for synthesis across findings.
4. Produce:
   - truth report,
   - contradiction list,
   - stuck-state findings,
   - candidate actions,
   - unresolved information requests.
5. Return patch to `truth_findings` and optional draft `planned_actions`.

## 16.5 WorkflowBuilderWorkflow exact behavior

Input:
- truth findings
- ontology snapshot

Steps:
1. Identify top-priority operational breakdowns.
2. For each selected breakdown, generate a reusable workflow spec.
3. Generate SOP.
4. Generate runtime-target recommendations:
   - `n8n` if connector-heavy and deterministic,
   - `custom_agent` if dynamic reasoning remains necessary.
5. If execution or implementation is proposed, emit `PlannedAction` draft.
6. If exportable, generate `ExecutableWorkflowDraft` in draft state.
7. Return patch to `workflow_specs`, `planned_actions`, and `executable_workflow_drafts`.

## 16.6 GovernanceWorkflow exact behavior

Input:
- one or more planned actions
- optional executable workflow drafts

Steps:
1. Validate schemas.
2. Determine blast radius.
3. Determine whether approval is required.
4. If low-risk and allowed, mark exportable or executable.
5. If medium/high risk, create pending approval state and block.
6. Record audit metadata.
7. Only GovernanceWorkflow may mark external action as `executing`, `completed`, `exported`, or `activated`.
8. Return patch to `planned_actions`, `executable_workflow_drafts`, and HITL state.

---

# 17. Runtime selection logic

> **Locked decision (see §20.4):** n8n is the **invisible execution runtime** — it is reached only through the deterministic compiler + API/webhook, never through an exposed n8n editor in the first release (OEM/Embed license required). The client-facing canvas is OntologyAI-owned and persists every edit into `ExecutableWorkflowDraft`. The 12-node canonical vocabulary (§20.4.6) is the authoring surface; it maps to n8n during compilation.

## 17.1 n8n should be preferred when

- trigger/condition/action can be explicitly specified,
- third-party SaaS connectors are required,
- side effects are deterministic,
- branching is limited and inspectable.

Examples:
- invoice overdue reminders,
- CRM status sync,
- task creation on flagged issue,
- Slack/email notification workflows.

## 17.2 custom agent runtime should be preferred when

- reasoning over ambiguous text is still needed,
- dynamic context assembly is required,
- multiple evidence sources must be synthesized before action,
- human approval checkpoints are deeply integrated.

Examples:
- classify inbound operational chaos from chat + uploads,
- create a triaged action plan from mixed evidence,
- draft escalation with business context,
- propose routing when ownership is unclear.

## 17.3 compilation rule

LLM may propose workflow structure.
Deterministic compiler code must build final runtime payload.

## 17.4 deployment target rule

- Approved drafts compile to n8n JSON via `runtime/n8n_compiler.py`.
- Deploy to the **client's own n8n instance** or a **managed n8n runtime only after** the appropriate commercial agreement.
- Run state, errors, and activation status are reflected back into OntologyAI read-only; the native n8n editor is not surfaced to clients in V5.1 first release.

---

# 18. HITL and governance policy

## 18.1 Approval rules

Approval is required when:
- blast radius is `medium` or `high`,
- action changes external system state,
- action changes money state,
- action changes ownership,
- action sends outbound communication,
- action closes an issue without evidence,
- action activates executable workflows with side effects.

## 18.2 Auto-allowed low-risk examples

Allowed without approval only if policy says so:
- add internal note,
- tag object as needs review,
- create draft workflow spec,
- create draft message object,
- create draft planned action,
- create draft executable workflow,
- export non-activated artifact for review.

## 18.3 Execution restriction

No workflow except `GovernanceWorkflow` may finalize external execution.

---

# 19. UI/UX specification

This is a **shared agentic workspace**, not a passive dashboard.

It must support both:
- an FDE/operator running a pilot with the client, and
- a client operating the system directly through a workspace link.

## 19.1 UX goals

- the user should feel they are collaborating with a structured agent team,
- discovery should feel conversational, not like a rigid form,
- process truth should become visible progressively,
- approvals should be obvious and safe,
- outputs should be exportable and inspectable.

## 19.2 Primary screens

1. Workspace Overview
2. Conversational Intake Panel
3. Uploads and Connected Data Sources Panel
4. Discovery Evidence Queue
5. Ontology Explorer / Process Map
6. Truth Findings Panel
7. Workflow Specs Panel
8. Executable Workflow Drafts Panel
9. Planned Actions / Approvals Queue
10. Artifacts and Exports Panel
11. Session / Conversation Log

## 19.3 Primary user actions

- create workspace
- choose mode: FDE-assisted or client self-serve
- chat with system
- upload documents / exports / screenshots
- connect third-party tools
- answer targeted follow-up questions
- approve / reject action
- approve / reject workflow activation
- export truth map
- export workflow pack
- export SOP pack
- export executable draft
- view unresolved questions

## 19.4 UI components

### Workspace overview
- phase badge
- progress tracker
- unresolved question count
- pending approval count
- active draft count
- latest truth summary

### Chat panel
- message stream
- suggested replies
- evidence prompts
- agent speaker badges
- “why are you asking?” explanation UI

### Data sources panel
- upload zone
- source cards
- connector status
- freshness indicator
- provenance viewer

### Ontology explorer
- object list
- relationship graph
- object detail drawer
- source references
- confidence tags

### Truth findings panel
- severity filters
- stuck/risk/missing tabs
- findings grouped by object
- recommended next actions

### Workflow panel
- workflow cards
- spec detail modal
- SOP preview
- runtime target badge (`n8n` / `adk_go` / `pydantic_ai` / `python_agent`)
- compile/export actions

### Governance panel
- approval tasks
- blast radius badge
- side effect summary
- audit trail
- approve / reject / request edits

## 19.5 UI behavior rules

- never hide approval requirements,
- always show provenance for extracted facts,
- always show draft vs activated status clearly,
- never represent assumptions as confirmed truth,
- default to explanation over magic.

---

# 20. Architecture

## 20.1 High-level architecture

Layers:

1. **Interface layer**
   - web workspace
   - chat interface
   - upload panel
   - approval UI
   - exports UI

2. **Control plane**
   - ChiefOfStaff workflow
   - route mapping
   - session context loading
   - deterministic state merge
   - workspace phase management

3. **Specialist workflow layer**
   - Discovery
   - Ontology Mapping
   - Truth Analysis
   - Workflow Builder
   - Governance

4. **Data and memory layer**
   - PostgreSQL
   - Redis
   - Qdrant
   - Neo4j / Graphiti
   - artifact storage

5. **Runtime/export layer**
- n8n export compiler
- ADK-Go compiler
- PydanticAI compiler
- smolagents compiler
- custom agent config compiler
   - governance activation gate

6. **Observability and controls**
   - Langfuse
   - audit logs
   - tracing
   - approval history
   - evaluation hooks

## 20.2 System design principles

- federated logical design over one monolith of business semantics,
- central control plane with domain-specialist workflows,
- source-aligned storage plus semantic overlay,
- governance before side effects,
- runtime-specific export behind deterministic compilers (4 targets via `RuntimeCompiler` ABC).

## 20.3 Control plane behavior

The control plane should:
- own identity and workspace routing,
- own state lifecycle,
- own workflow registration,
- own approvals and activation rights,
- expose a single user-facing interface.

## 20.4 Architecture Decision — Runtime & Canvas (locked V5.1)

This decision is **final and locked** for V5.1 (committed in PR #33, branch `feature/ontologyai-v5.1`). It does not replace any earlier V5.1 decision (the 6-workflow roster, the 6 object types, governance exclusivity, and compiler purity all remain in force). It clarifies *which layers we build versus which we reuse*.

### 20.4.1 Core principle

**Do NOT build the workflow engine or canvas from scratch.** Reuse **n8n** as the execution/runtime layer, but build **OntologyAI's own client-facing AI workspace and live workflow canvas** on top of the canonical `ExecutableWorkflowDraft` model.

### 20.4.2 Final architecture split

| Layer | Decision | Why |
|---|---|---|
| Client experience | Build your own | Differentiation: conversation, transcript extraction, evidence, AI suggestions, FDE collaboration, governance, pilot creation |
| Workflow data model | Build your own typed canonical model | Lets the AI generate/validate/explain/version/govern workflows deterministically |
| Compiler layer | Build your own `RuntimeCompiler` ABC + factory | 4 deterministic compilers (n8n, ADK-Go, PydanticAI, smolagents) from one canonical draft |
| Execution runtime | Reuse n8n first | n8n provides execution, integrations, retries, scheduling, credentials, ops tooling |
| Agent orchestration | Keep existing Temporal/Python | 6 workflow roles, typed shared state, governance, deterministic compilers already exist |
| Agent framework | Use one, not two | Do not add ADK merely because fashionable; smolagents only sandboxed utility |

### 20.4.3 Do NOT embed the n8n editor (licensing constraint)

- **Do NOT expose the native n8n editor directly to clients in the first release.** The n8n OEM/Embed license is required to surface the native editor to external users; this is out of scope for V5.1 first release.
- Build an **OntologyAI workflow canvas** that *looks and behaves like* a simplified n8n canvas (node graph, connections, properties panel) but is fully OntologyAI-owned.
- Save every edit into OntologyAI's own `ExecutableWorkflowDraft` (the single source of truth).
- Compile an approved draft to n8n JSON via the deterministic `n8n_compiler.py`.
- Deploy to **either**:
  - the client's own n8n instance, **or**
  - a managed n8n runtime **only after** the appropriate commercial agreement is in place.
- Show run state, errors, and activation status back inside OntologyAI (read-only reflection of the runtime, not a live editor).

### 20.4.4 Recommended V5.1 stack ownership

**OntologyAI owns:**
- shared client + FDE workspace,
- chat / meeting-transcript ingestion,
- file / SOP / document intake + provenance,
- evidence extraction + ambiguity questions,
- ontology + truth-map generation,
- workflow canvas + node editor,
- AI-proposed nodes / branches / approvals / fallbacks,
- governance + approval UI,
- workflow versioning + pilot-readiness checks,
- compile / export button.

**n8n owns:**
- trigger execution,
- integrations / connectors,
- scheduled runs / queues / retries,
- credential handling on the client instance where possible,
- webhook / API integration for deployed pilots.

**Python owns:**
- extraction pipelines,
- retrieval,
- typed schema validation,
- deterministic workflow compilation,
- policy evaluation + approval gates,
- agent coordination,
- audit trail + provenance.

### 20.4.5 Multi-runtime compiler rule (ADR-008)

- **Temporal + typed Python domain logic = system backbone.**
- **ADK = optional orchestration enhancement** — adopt only if it materially improves the current orchestration; do **not** add merely because it is fashionable.
- **smolagents = sandboxed utility worker** — document exploration, safe spreadsheet/data transforms, connector research, isolated code analysis. Code generated by an agent **must NOT** run with access to production network, credentials, database, or the n8n instance.
- **n8n = workflow execution runtime** (automation, integrations, scheduling).
- **ADK-Go = Go-native agent runtime** (for clients on Go stacks).
- **PydanticAI = typed Python agent runtime** (typed outputs, tool-heavy Python agents).
- **smolagents = sandboxed utility agent runtime** (code-first, isolated tasks).
- **OntologyAI UI = the product.**
- All four runtimes are reached only through deterministic compilers from the canonical `ExecutableWorkflowDraft`. See [ADR-008](./docs/adr/ADR-008-multi-runtime-compilers.md).

### 20.4.6 Canonical node vocabulary (12 nodes)

The V5.1 canvas uses a **small, high-quality canonical node vocabulary**. New integrations and dozens of bespoke nodes come later. Each canonical node maps to n8n during compilation.

1. **Trigger** — entry point / schedule / webhook.
2. **Human input / form** — collect structured input from a person.
3. **AI extraction or classification** — LLM-based extraction/labeling (LLM-in-safe-lane only).
4. **Condition / branch** — deterministic routing on data.
5. **HTTP / API action** — call an external endpoint.
6. **Send message** — outbound notification (governance-gated).
7. **Create / update record** — write to a system of record.
8. **Approval gate** — HITL checkpoint (maps to `GovernanceWorkflow`).
9. **Delay / schedule** — wait or defer.
10. **Transform data** — deterministic reshape/map.
11. **Error / fallback** — exception path.
12. **End / success metric** — terminal node + measured outcome.

### 20.4.7 "Finish the product" pilot path (success criteria narrative)

1. FDE and client enter a shared workspace.
2. Client explains an operational pain point in chat, or joins a meeting whose transcript is ingested.
3. AI extracts actors, systems, events, existing steps, exceptions, missing facts.
4. Client uploads SOPs / templates / exports / examples as evidence.
5. OntologyAI asks only important unresolved questions.
6. Workflow canvas appears and updates live with proposed triggers, steps, branches, owners, approvals, fallback paths.
7. Client / FDE edits or accepts the proposed workflow.
8. Governance marks actions needing approval.
9. OntologyAI compiles the approved workflow to the appropriate runtime target (n8n JSON, ADK-Go source, PydanticAI agent, or smolagents worker).
10. Workflow deployed to the client's n8n instance or exported as an importable pilot package.

---

# 21. Technical stack

The stack should stay close to your existing system wherever possible, because that is already validated in your codebase and prior PRDs. [file:556]

## 21.1 Core application stack

| Layer | Choice |
|---|---|
| Primary AI app | Python |
| Control / gateway | Go (existing server and routes where already present) |
| Workflow orchestration | Existing Temporal + Python runtime (system backbone) |
| Scheduling | APScheduler |
| Validation | Pydantic / Pydantic AI |
| State + transactional data | PostgreSQL |
| Cache / working memory | Redis |
| Vector / episodic memory | Qdrant |
| Semantic / temporal graph | Neo4j + Graphiti |
| Observability | Langfuse |
| UI | OntologyAI-owned client workspace + live workflow canvas (HTMX / server-rendered, layered later); **n8n editor not exposed to clients** |
| Workflow data model | `ExecutableWorkflowDraft` (canonical, OntologyAI-owned) |
| Workflow execution runtime | n8n (invisible; reached via deterministic compiler + API/webhook) |
| Agent runtimes | ADK-Go (Go-native agents), PydanticAI (typed Python agents), smolagents (sandboxed utility) — all reached via `RuntimeCompiler` ABC + factory |
| Agent framework | Temporal + typed Python = backbone; ADK optional enhancement only; smolagents sandboxed utility only |
| Transport / streaming | existing SSE transport |
| Deployment | existing Docker / Compose / k3d patterns |

## 21.2 LLM/model strategy

- external LLMs for low-sensitivity extraction and synthesis,
- private/on-prem models later for sensitive deployments,
- structured output enforced on all consequential responses.

## 21.3 Why this stack

- It reuses proven parts of Sarthi,
- it fits the thin-LLM/fat-code pattern,
- it supports typed contracts and governance,
- it is credible for an FDE portfolio project, [file:556][file:489]
- it follows the locked §20.4 split: build the client experience + canonical model + canvas; reuse n8n as the invisible execution runtime; keep Temporal/Python as the backbone; treat ADK as optional and smolagents as sandboxed-only.

---

# 22. Data persistence spec

## 22.1 Required tables

Keep or create:
- `engagement_states`
- `planned_actions`
- `executable_workflow_drafts`
- `workflow_specs`
- `approvals`
- `session_messages`
- `artifact_exports`
- `data_sources`

## 22.2 engagement_states

Fields:
- `id UUID PK`
- `tenant_id UUID`
- `engagement_id TEXT UNIQUE`
- `workspace_mode TEXT`
- `phase TEXT`
- `state JSONB NOT NULL`
- `updated_at TIMESTAMPTZ`

## 22.3 workflow_specs

Fields:
- `id UUID PK`
- `tenant_id UUID`
- `engagement_id TEXT`
- `workflow_name TEXT`
- `spec JSONB NOT NULL`
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`

## 22.4 executable_workflow_drafts

Fields:
- `id UUID PK`
- `tenant_id UUID`
- `engagement_id TEXT`
- `runtime TEXT`
- `name TEXT`
- `status TEXT`
- `draft JSONB NOT NULL`
- `export_payload JSONB`
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`

## 22.5 approvals

Fields:
- `id UUID PK`
- `tenant_id UUID`
- `engagement_id TEXT`
- `target_type TEXT`
- `target_id TEXT`
- `status TEXT`
- `requested_by TEXT`
- `approved_by TEXT NULL`
- `reason TEXT NULL`
- `created_at TIMESTAMPTZ`
- `resolved_at TIMESTAMPTZ NULL`

## 22.6 artifact_exports

Fields:
- `id UUID PK`
- `tenant_id UUID`
- `engagement_id TEXT`
- `artifact_type TEXT`
- `content JSONB`
- `created_at TIMESTAMPTZ`

## 22.7 data_sources

Fields:
- `id UUID PK`
- `tenant_id UUID`
- `engagement_id TEXT`
- `source_type TEXT`
- `source_name TEXT`
- `status TEXT`
- `freshness JSONB`
- `metadata JSONB`
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`

---

# 23. File and module plan

## 23.1 New or canonical modules

Create or standardize:
- `apps/ai/src/ontology/__init__.py`
- `apps/ai/src/ontology/object_types.py`
- `apps/ai/src/ontology/link_types.py`
- `apps/ai/src/ontology/action_types.py`
- `apps/ai/src/ontology/workflow_drafts.py`
- `apps/ai/src/ontology/adapter.py`
- `apps/ai/src/ontology/governance.py`
- `apps/ai/src/schemas/engagement_state.py`
- `apps/ai/src/schemas/specialist_response.py`
- `apps/ai/src/schemas/workflow_spec.py`
- `apps/ai/src/schemas/sop.py`
- `apps/ai/src/schemas/executable_workflow_draft.py`
- `apps/ai/src/workflows/discovery_workflow.py`
- `apps/ai/src/workflows/ontology_mapping_workflow.py`
- `apps/ai/src/workflows/truth_analysis_workflow.py`
- `apps/ai/src/workflows/workflow_builder_workflow.py`
- `apps/ai/src/workflows/governance_workflow.py`
- `apps/ai/src/runtime/base.py` (`RuntimeCompiler` ABC)
- `apps/ai/src/runtime/n8n_compiler.py`
- `apps/ai/src/runtime/n8n.py` (`N8NCompiler` wrapper)
- `apps/ai/src/runtime/adk_go_compiler.py`
- `apps/ai/src/runtime/pydantic_ai_compiler.py`
- `apps/ai/src/runtime/python_agent_compiler.py`
- `apps/ai/src/runtime/custom_agent_compiler.py`

## 23.2 Existing modules to refactor, not duplicate

Refactor instead of duplicate where possible:
- `apps/ai/src/workflows/__init__.py`
- `apps/ai/src/worker.py`
- existing agent graph modules
- authority manifest
- route mapping code
- dashboard handlers/templates
- mission-state endpoints
- session context loaders
- existing approval lifecycle plumbing
- existing artifact export plumbing

---

# 24. Leveraging existing code

This is mandatory.
The project should be built primarily by refactoring and re-skinning validated infrastructure from Sarthi, not by greenfield rewriting everything. That reuse path is directly supported by the existing V5 checklist and the prior Sarthi architecture. [file:806][file:556]

## 24.1 Reuse directly if present

Reuse existing modules/patterns where available for:
- worker bootstrap and workflow registration pattern,
- Pydantic schema conventions,
- MissionState read/write pattern,
- HITL approval blocking pattern,
- planned action persistence,
- SSE update transport,
- session memory/context loading,
- audit logging,
- workflow wrappers,
- deterministic routing helpers,
- test structure and fixtures,
- Redis/Qdrant/Postgres clients,
- Langfuse tracing,
- HTMX dashboard patterns.

## 24.2 Reuse with rename/refactor

Refactor old modules instead of duplicating:
- cofounder router -> ChiefOfStaff orchestration,
- finance/bi/ops/comms graphs -> discovery/analysis/builder/governance shells,
- mission state schema -> engagement state schema,
- specialist response schema -> FDE specialist response schema,
- dashboard pages -> shared workspace views,
- route maps -> engagement workflow routes,
- guardian-style explanation cards -> truth finding cards,
- decision journal -> action register,
- existing internal dashboard -> approvals + artifacts cockpit.

## 24.3 Keep as infrastructure, change semantics

Keep:
- APScheduler,
- PostgreSQL persistence,
- Redis working memory,
- Qdrant episodic memory,
- Neo4j/Graphiti semantic memory,
- Langfuse tracing,
- Go gateway if already serving routes,
- test harness utilities.

Change:
- product naming,
- top-level workflow semantics,
- user-facing copy,
- route aliases,
- data contracts,
- dashboard information architecture.

## 24.4 Deprecate from active surface

Deprecate or remove:
- founder guardian/watchlist branding,
- startup fundraising-specific copy,
- investor-first framing,
- startup-only route logic,
- hiring specialist references,
- domain-specific persona names that conflict with OntologyAI V5.1.

## 24.5 Do not rewrite without need

Avoid unnecessary rewrites of:
- DB connection layer,
- approval lifecycle plumbing,
- existing schema helpers,
- streaming transport,
- observability hooks,
- container/deployment setup,
- any validated integration client already working.

---

# 25. Route map

## 25.1 Default route

- `@ontologyai`
- `@agent`
- `@ask`
- `@chief`

-> `ChiefOfStaffWorkflow`

## 25.2 Specialist aliases

- `@discover` -> `DiscoveryWorkflow`
- `@map` -> `OntologyMappingWorkflow`
- `@truth` -> `TruthAnalysisWorkflow`
- `@build` -> `WorkflowBuilderWorkflow`
- `@govern` -> `GovernanceWorkflow`

## 25.3 Backward compatibility aliases

Allowed for one version window:
- `@sarthi` -> `ChiefOfStaffWorkflow`
- `@finance`, `@fpa` -> `TruthAnalysisWorkflow` if money-centric
- `@ops` -> `WorkflowBuilderWorkflow` or `TruthAnalysisWorkflow`
- `@comms` -> `DiscoveryWorkflow` or `WorkflowBuilderWorkflow`

---

# 26. SOPs

## 26.1 Product build SOP

1. Normalize naming to OntologyAI.
2. Preserve existing infrastructure.
3. Add new schemas first.
4. Add failing tests.
5. Implement workflow shells.
6. Wire deterministic state merge.
7. Implement specialist logic.
8. Implement runtime compilers.
9. Update UI.
10. Run full regression.

## 26.2 Workspace onboarding SOP

1. Create workspace.
2. Choose mode: `fde_assisted` or `client_self_serve`.
3. Collect goal statement.
4. Ask for first evidence source.
5. Extract discovery findings.
6. Build initial ontology.
7. Surface missing questions.
8. Produce first truth summary.
9. Generate first workflow draft.
10. Request governance approval if needed.

## 26.3 Workflow compilation SOP

1. Select workflow spec.
2. Choose runtime target.
3. Validate required fields.
4. Compile deterministic export payload.
5. Create `ExecutableWorkflowDraft`.
6. Run governance policy checks.
7. Export or activate only when permitted.

---

# 27. Checklists

## 27.1 Build checklist

- [ ] Naming normalized to OntologyAI
- [ ] Exactly 6 workflows exist
- [ ] Exactly 6 ontology object types exist
- [ ] `ExecutableWorkflowDraft` schema exists
- [ ] `EngagementState` includes workspace mode and executable drafts
- [ ] Deterministic patch merge exists
- [ ] Governance is sole executor of final external side effects
- [ ] UI supports chat, uploads, connectors, ontology, workflows, approvals, artifacts
- [ ] RuntimeCompiler ABC exists in `runtime/base.py`
- [ ] Runtime compiler exists for n8n (`N8NCompiler`)
- [ ] Runtime compiler exists for ADK-Go (`ADKGoCompiler`)
- [ ] Runtime compiler exists for PydanticAI (`PydanticAICompiler`)
- [ ] Runtime compiler exists for smolagents/python_agent (`PythonAgentCompiler`)
- [ ] Runtime compiler factory `get_compiler()` routes correctly
- [ ] `test_runtime_compilers.py` (15 tests) passes
- [ ] Artifacts export successfully
- [ ] Existing reusable infrastructure preserved

## 27.2 Governance checklist

- [ ] Blast radius computed
- [ ] Approval required when rules trigger
- [ ] Outbound comms gated
- [ ] Money state changes gated
- [ ] Ownership changes gated
- [ ] Workflow activation gated
- [ ] Audit trail recorded

## 27.3 UX checklist

- [ ] User can create workspace
- [ ] User can choose workspace mode
- [ ] User can chat with system
- [ ] User can upload files
- [ ] User can inspect provenance
- [ ] User can see ontology graph
- [ ] User can see truth findings
- [ ] User can review workflow specs
- [ ] User can review executable drafts
- [ ] User can approve/reject actions
- [ ] User can export artifacts

---

# 28. Test plan

## 28.1 Must-have test files

- `test_ontology_schema.py`
- `test_link_and_action_registry.py`
- `test_engagement_state.py`
- `test_specialist_response.py`
- `test_workflow_spec_schema.py`
- `test_sop_schema.py`
- `test_executable_workflow_draft.py`
- `test_discovery_workflow.py`
- `test_ontology_mapping_workflow.py`
- `test_truth_analysis_workflow.py`
- `test_workflow_builder_workflow.py`
- `test_governance_workflow.py`
- `test_n8n_compiler.py`
- `test_custom_agent_compiler.py`
- `test_runtime_compilers.py` (15 tests: ABC contract, ADK-Go, PydanticAI, PythonAgent, factory)
- `test_workflow_names.py`
- `test_route_map.py`
- `test_hitl_governance.py`
- `test_workspace_mode.py`
- `test_artifact_exports.py`

## 28.2 Non-negotiable assertions

Test at minimum:
- strict schema validation,
- unknown-field rejection,
- workflow name exactness,
- route alias correctness,
- merge-safe state patching,
- governance exclusivity for external execution,
- approval requirement behavior,
- graceful handling of missing data,
- artifact generation shape,
- executable draft state transitions,
- deterministic compiler output (all 4 targets),
- multi-runtime factory correctness,
- zero regression in old reusable infrastructure.

## 28.3 Integration tests

- chat -> discovery findings -> ontology patch
- ontology snapshot -> truth findings
- truth findings -> workflow spec + SOP
- workflow spec -> executable draft
- executable draft -> governance approval path
- governance approval -> exportable payload
- artifact export end-to-end

## 28.4 UI tests

- workspace creation
- mode selection
- file upload flow
- follow-up question rendering
- ontology graph visibility
- workflow draft review
- approval action buttons
- artifact export buttons

---

# 29. Implementation plan

## Phase 0 — Surface cleanup
1. Normalize naming to OntologyAI.
2. Keep compatibility aliases only where required.
3. Update docs and route names.

## Phase 1 — Contracts first
1. Write failing tests for ontology objects, links, actions, workflow spec, SOP, executable workflow draft, engagement state, specialist response.
2. Implement schemas only after tests fail.

## Phase 2 — Workflow shells
1. Write workflow-name and registration tests.
2. Create or refactor 6 final workflow classes.
3. Register them without changing core runtime model.

## Phase 3 — Shared state wiring
1. Refactor MissionState into typed EngagementState adapter.
2. Ensure workflows read/write patches only.
3. Add deterministic patch merge.
4. Add workspace mode and phase transitions.

## Phase 4 — Specialist behavior
1. Implement discovery extraction.
2. Implement ontology mapping.
3. Implement truth analysis.
4. Implement workflow builder.
5. Implement governance restrictions.

## Phase 5 — Runtime compilers
1. Implement `RuntimeCompiler` ABC (`runtime/base.py`).
2. Implement n8n compiler (`N8NCompiler` wrapper in `runtime/n8n.py`).
3. Implement ADK-Go compiler (`runtime/adk_go_compiler.py`).
4. Implement PydanticAI compiler (`runtime/pydantic_ai_compiler.py`).
5. Implement smolagents/python_agent compiler (`runtime/python_agent_compiler.py`).
6. Implement `get_compiler()` factory (`runtime/__init__.py`).
7. Write `test_runtime_compilers.py` (15 tests) — TDD: RED (failing imports) → GREEN (all pass).
8. Ensure deterministic export payload generation for all 4 targets.

## Phase 6 — UI and artifacts
1. Update workspace views.
2. Add artifact exports.
3. Add executable draft panel.
4. Add approvals and governance UX.

## Phase 7 — Final verification
1. Run Python unit tests.
2. Run Go build/tests if route/UI changed.
3. Verify workflow count = 6.
4. Verify ontology object count = 6.
5. Verify only Governance can finalize execution.
6. Verify executable drafts compile/export correctly.
7. Verify artifacts exist.

---

# 30. No-hallucination rules for the coding agent

1. Do not invent new agents beyond the 5 operational agents + ChiefOfStaff.
2. Do not invent new ontology object types unless explicitly requested later.
3. Do not preserve old department naming if it conflicts with V5.1.
4. Do not write directly to engagement state without schema validation.
5. Do not let non-governance workflows finalize external execution.
6. Do not add new databases or orchestration engines unless absolutely required.
7. Do not replace deterministic code with LLM logic where code can handle it.
8. Do not create duplicate parallel workflow systems.
9. Do not broaden scope into full production connector coverage for V5.1.
10. Do not describe features as implemented unless code and tests exist.
11. Do not freehand workflow export payloads in the LLM path.
12. Do not discard existing tested infrastructure without specific reason.

---

# 31. Final acceptance criteria

The build is only correct if all of the following are true:

1. The system exposes exactly these workflows:
   - `ChiefOfStaffWorkflow`
   - `DiscoveryWorkflow`
   - `OntologyMappingWorkflow`
   - `TruthAnalysisWorkflow`
   - `WorkflowBuilderWorkflow`
   - `GovernanceWorkflow`

2. The system exposes exactly these ontology object types:
   - `Party`
   - `Engagement`
   - `MoneyEvent`
   - `Issue`
   - `Message`
   - `PlannedAction`

3. `EngagementState` is the canonical shared state shape.

4. `ExecutableWorkflowDraft` exists and is validated.

5. Every workflow returns a valid `SpecialistResponse`.

6. Only `GovernanceWorkflow` may finalize external execution state.

7. Medium/high blast-radius actions require approval.

8. Workflow activation is governance-gated.

9. Shared workspace views exist for chat, uploads, ontology, truth findings, workflows, executable drafts, approvals, and artifacts.

10. The system can export:
   - truth map,
   - ontology snapshot,
   - workflow pack,
   - SOP pack,
   - action register,
   - executable workflow draft.

11. Tests for schema, workflows, routes, compilers, governance, and exports all pass.

12. Existing reusable infrastructure is preserved wherever practical.

13. The codebase reads like a self-serve FDE companion and FDE operating system, not a founder alert bot.

---

# 32. Final build summary

Build OntologyAI V5.1 as a **self-serve FDE companion and multi-agent FDE operating system**.

Keep the reusable infrastructure.  
Refactor the semantics.  
Implement the shared workspace lifecycle.  
Center the ontology.  
Type every output.  
Govern every action.  
Generate reusable handoff artifacts.  
Generate executable workflow drafts.  
Compile deterministically.  
Activate only through governance.

That is the final spec.
