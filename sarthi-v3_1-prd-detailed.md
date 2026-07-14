# SARTHI V3.1 — PRODUCT REQUIREMENTS DOCUMENT

Version: 3.1  
Date: July 8, 2026  
Status: Updated for Build  
Product Type: Vertical AI Operating System for solo technical SaaS founders  
ICP: Solo technical SaaS founder, seed stage, 6–18 months to Series A  
Primary Stack: Python, Go, APScheduler, PostgreSQL, Graphiti, Neo4j, Qdrant, Redis, Slack, HTMX, Langfuse, Pydantic AI  
Secondary Demo Stack: Docker Compose, OpenTelemetry, Jaeger, Grafana, optional k3d/Helm showcase path  

---

## 1. Product Truth

OntologyAI is a **guardian**, not an assistant.

Most founder tools operate in the known-knowns layer. They answer questions the founder already knows to ask. A first-time solo technical founder usually does not know the hidden operating patterns that kill a seed-stage SaaS company before the next raise. They may not know that 3% monthly churn compounds into a structurally weak business. They may not know that a few concentrated customers can make revenue look healthier than it is. They may not know that support growth, AWS growth, or investor silence often become financing problems before they become obviously visible business problems.

OntologyAI exists to watch what the founder is unlikely to watch consistently, interpret it in context, and intervene early enough to matter.

The product thesis remains:

> **An assistant waits to be asked. A guardian knows to watch before you know to look.**

V3.1 extends this thesis one level deeper. OntologyAI must not only guard the founder's business. It must also guard its own operation. That means the system itself must become observable, governable, auditable, and capable of bounded self-correction.

This is the key shift from V3.0 to V3.1:

- V3.0 defined the guardian product.
- V3.1 defines the guardian's operating system.

---

## 2. Product Category

OntologyAI is **not** a generic multi-agent framework.

It is a **vertical AI operating system** for one tightly defined use case:
- one founder,
- one company,
- one operating context,
- one watchlist-driven risk model,
- one core delivery surface.

The goal is not to demonstrate that many agents can talk to each other. The goal is to build a product that continuously converts operational telemetry into trusted founder guidance.

The architecture may borrow patterns from multi-agent systems such as typed role contracts, workflow validation, collaboration protocols, traceability, and learning loops. But these patterns are means, not the product itself.

### Non-goal

OntologyAI must not evolve into:
- a general AI employee marketplace,
- a software-factory generator,
- a generic orchestration toolkit,
- a horizontal agent platform for arbitrary workflows.

Any architectural decision that improves breadth while weakening the guardian's clarity is wrong.

---

## 3. ICP — Locked

### Primary ICP

OntologyAI V1–V3.1 is for:

> **A solo technical founder building a SaaS product on Stripe + PostgreSQL, at seed stage, who is 6–18 months from institutional fundraising, and who wants a system that proactively surfaces hidden business risks before they become financing or operating crises.**

### Why this ICP is correct

| Qualifier | Why it matters |
|---|---|
| Solo founder | No delegation buffer; every decision, alert, and missed signal lands directly on one person. |
| Technical | Can self-serve setup, data access, integrations, and light ops complexity. |
| SaaS | The operating patterns are measurable and relatively consistent across MRR, retention, usage, support, and infra cost. |
| Seed stage | The failure modes are sharp, recurring, and watchlist-able. |
| 6–18 months to raise | Urgency windows can be framed around future investor scrutiny, not generic best practice. |

### Explicitly in scope

- B2B or prosumer SaaS
- Revenue tracked in Stripe or Stripe-like structure
- Product and behavioral data in PostgreSQL
- Slack as primary operating surface
- Founders who already have some instrumentation but inconsistent interpretation

### Explicitly out of scope

- D2C / ecommerce operators
- Agencies and service businesses
- Multi-founder teams with complex role politics
- Mobile-first products with fragmented event schemas as the default path
- Pre-product founders with no telemetry to watch
- Founders requiring heavy enterprise governance from day one

---

### 3.1 V3.1 Direction — Self-Correcting Operating Layer

V3.1 makes the following directional commitments:

**The system must guard itself.**
If OntologyAI is a guardian for the founder, it must also be a guardian of its own operation. Every agent action, every policy violation, every model choice, every data access, and every drift from expected behavior must be observable, auditable, and — where safe — automatically correctable.

**Self-correction does not mean full autonomy.**
Self-correction is bounded by blast radius, reversibility, and risk classification. Most corrective actions require HITL approval. Only low-risk, reversible, pre-audited actions may auto-apply. The system must never auto-correct a decision it cannot fully undo.

**The operating layer is a product surface, not just infrastructure.**
Policy state, risk state, self-guardian alerts, and the remediation history are first-class product surfaces. They appear in the HTMX dashboard alongside business metrics. The founder must be able to inspect why the system made a decision, what policies were applied, and whether the system is behaving safely.

**Blast radius limits are the first design principle.**
Every subsystem, every corrective action, and every agent is designed with explicit blast radius constraints: what it can affect, what it cannot affect, what requires approval, and what is forbidden entirely.

> The cumulative effect of these commitments is that V3.1 should feel to the founder like a system that is watching itself with the same vigilance with which it watches their business — so that the system can give the founder confidence that OntologyAI is acting within safe, bounded, auditable parameters at all times.

---

## 4. Problem Statement

The founder's real problem is not lack of dashboards. It is lack of interpretation, prioritization, continuity, and disciplined follow-through.

The modern solo founder has access to:
- analytics dashboards,
- payment dashboards,
- infrastructure dashboards,
- support inboxes,
- issue trackers,
- banks,
- investor notes,
- deployment logs.

But all of these systems assume the founder already knows:
- what matters now,
- what matters later,
- which weak signal becomes material at Series A,
- which pattern is transient noise versus structural decay,
- which action should happen this week,
- and which decision must be logged because future context will depend on it.

OntologyAI solves this by providing:
- persistent watchfulness,
- contextual pattern detection,
- synthesized recommendations,
- memory of past signals and founder responses,
- human-in-the-loop control for consequential actions,
- and now, in V3.1, a system layer that can inspect and improve its own operating quality.

---

## 5. Core Value Proposition

OntologyAI gives a solo founder a persistent, opinionated, memory-backed operating partner that:

1. Watches the business continuously.
2. Detects known seed-stage failure patterns.
3. Interprets those patterns in founder-specific context.
4. Delivers bounded, useful, non-generic guidance in Slack.
5. Logs decisions and reactions so the system learns over time.
6. Monitors its own quality, policy compliance, and operational drift.

### The promise

OntologyAI should help the founder avoid failure modes they would otherwise detect too late.

### The product feeling

OntologyAI should feel like:
- a trusted operator,
- a calm chief of staff,
- a watchful domain-aware colleague,
- never a noisy notification engine,
- never a generic chatbot.

---

## 6. Product Principles

### 6.1 Guardian, not assistant

The product leads with proactive detection, not reactive Q&A.

### 6.2 Vertical over horizontal

Every design choice optimizes for one founder archetype, not generality.

### 6.3 Thin LLM, fat deterministic core

The LLM is used only where judgment, synthesis, language, or ambiguity handling is genuinely required.

### 6.4 Typed contracts over prompt chaos

Every important boundary uses explicit schemas, deterministic validation, and testable behavior.

### 6.5 HITL for trust, not decoration

Human approval is a product trust mechanism, not a compliance afterthought.

### 6.6 Full traceability

Every instruction, decision, alert, policy result, and remediation must be auditable.

### 6.7 Graceful degradation

A subsystem may fail; the guardian must continue to provide bounded value wherever possible.

### 6.8 Code correctness before autonomy

Self-correcting behavior is forbidden where local validation and policy confidence are weak.

---

## 7. Product Vision

The long-term vision is for OntologyAI to become the founder-facing operating layer for seed-stage execution.

That means a system that can:
- understand the founder's business state,
- detect weak signals across finance, product, and ops,
- remember which advice was useful,
- coordinate multiple specialist agents safely,
- expose everything through a compact operating surface,
- and continuously improve without becoming unstable.

V3.1 is the first version that makes this vision structurally credible because it adds:
- a control plane,
- policy and risk gates,
- local CI discipline,
- role registration,
- mode-aware runtime profiles,
- and a self-guardian loop that turns traces and audit history into corrective action.

---

### 7.1 Control Plane

The control plane is V3.1's central nervous system for governance. It is not a separate service. It is a lightweight, importable Python module that sits between every agent action, every tool call, and every policy check.

**What it owns:**

- Agent identity registration — every agent must declare itself before it can act.
- Policy evaluation — every agent action is checked against the policy matrix before execution.
- Audit commitment — every policy decision, pass or fail, is committed to the audit log.
- Blast radius enforcement — before any action, the control plane checks the authority manifest to confirm the action is within the agent's allowed scope.

**What it does not own:**

- It does not run agents.
- It does not generate content.
- It does not decide what to do next — it only validates and records what agents attempt to do.
- It does not bypass the founder's direct operating context.

**Authority manifest:**

Every agent has a declared set of permissions in the `AuthorityManifest`:
- which tools it may call,
- which data classifications it may access,
- whether it may communicate externally (Slack, email),
- which LLM models it may use,
- what blast radius its actions have,
- whether its output requires HITL approval before delivery.

The control plane reads this manifest, evaluates each action against it, and either passes, blocks, or routes to HITL before the action proceeds.

---

## 8. Positioning

### What OntologyAI is

- A guardian for solo SaaS founders
- A vertical AI operating system
- A Slack-native operating surface
- A deterministic watchlist engine with bounded LLM judgment
- A portfolio-grade applied AI system with real observability and HITL

### What OntologyAI is not

- Not a general chatbot
- Not a generic dashboard
- Not a broad autonomous agent company builder
- Not a no-code orchestration platform
- Not a software generation framework

---

### 8.1 Self-Guardian Loop

The self-guardian is the mechanism by which OntologyAI watches itself. It is a continuous, asynchronous loop that ingests traces, agent observations, and policy decisions; detects deviations from expected behavior; and produces structured alerts and remediation proposals.

**High-level flow:**

1. Trace ingest — Langfuse traces, agent audit events, and runtime metrics are collected into a unified observation stream.
2. Self-guardian watchlist — a set of deterministic rules and patterns that define what normal operation looks like for this system, expressed as a manifest of allowed deviations, thresholds, and invariants.
3. Detection — the self-guardian evaluator compares observed behavior against the watchlist to produce a deviation report with severity levels.
4. Fix planning — for each actionable deviation, a fix planner proposes a structured remediation response: what action, who must approve it, what blast radius, and what rollback looks like.
5. Remediator — the remediation executor applies approved fixes and logs the outcome.
6. Re-evaluation — after remediation, the system re-enters the observation cycle.

**Key invariants:**

- Self-correction is always bounded by the authority manifest. A self-guardian remediation may not exceed the permissions of the agent or system component it is correcting.
- Self-correction is always revertible, or it is not self-correction — it is a system change requiring external approval.
- The self-guardian watchlist itself is governed by the same CRD as any other component. Changes to watchlist definitions require PR review and merge.

---

## 9. User Jobs To Be Done

### Functional jobs

- Tell me what is going wrong before it becomes expensive.
- Tell me which metric change actually matters.
- Tell me what action to take this week.
- Remember my previous decisions and adjust future advice.
- Draft important internal and external communications safely.
- Keep track of pending decisions without me rebuilding context.

### Emotional jobs

- Reduce the sense that important things are being missed.
- Replace scattered tools with a calmer operating rhythm.
- Make difficult signals easier to face because they are framed clearly.
- Increase confidence before investor conversations.

### System-level jobs in V3.1

- Show me why the system said what it said.
- Show me whether the system is behaving safely.
- Show me what changed in the system and why.
- Keep self-correction bounded, reviewable, and reversible.

---

### 9.1 Sensitive Workflow Governance

Some workflows carry higher risk than others. These workflows require additional governance layers.

**What makes a workflow sensitive:**

- It communicates externally (Slack DMs, email, investor briefs).
- It modifies business state (drafts financial reports, initiates data exports, pauses payment retries).
- It uses founder identity or authority to act.
- It involves investor, hiring, or compliance-adjacent actions.

**Governance requirements for sensitive workflows:**

- Every sensitive workflow must declare an `authority_scope` that maps to a manifest entry.
- Every sensitive workflow output must pass output risk scan before delivery.
- Every sensitive workflow action that modifies external state must go through HITL.
- Every sensitive workflow must have an explicit rollback or undo path declared in its workflow definition.
- Every sensitive workflow invocation must be logged to the audit trail with the full decision context.

**Non-sensitive workflows that are explicitly excluded from above:**

- Read-only queries against public or internal data.
- Watchlist evaluation without external action.
- Internal state transitions that do not affect the founder's operating context.
- Scheduled pulses that have been pre-audited and approved via the policy engine.

**Listing of sensitive workflows under this governance:**

- Finance: pause payment retry (Stripe write), draft investor update (external comms).
- Data: none currently — all data workflows are read-only.
- Ops: schedule customer check-in (external comms), flag churn segment (notification).
- Comms: any Slack DM to the founder that carries a recommendation with a call to action.
- Hiring: any communication with candidates or decision logging.

---

## 10. User Experience Principles

OntologyAI's experience should be:

- **Concise**: no long rambling agent monologues.
- **Grounded**: numbers are injected, never invented.
- **Contextual**: guidance references founder reality, not generic startup advice.
- **Layered**: the founder sees the right amount of detail first, with drill-downs available.
- **Trustworthy**: every consequential step is explainable and auditable.
- **Non-noisy**: silence is preferred over low-value chatter.
- **Operational**: the default output is an action, not a motivational paragraph.

---

## 11. V3.0 to V3.1 Delta

V3.0 established the guardian pattern and ACE session model.

V3.1 adds the operating layer needed to make the guardian production-credible.

### V3.0 foundations retained

- Guardian watchlist-first product structure
- Slack as the persistent shared operating surface
- Co-founder agent plus three specialist employee agents
- MissionState shared context
- Graphiti-based semantic learning loop
- Thin LLM / fat deterministic core
- HITL routing
- Langfuse traces and evaluation loop
- HTMX internal dashboard

### V3.1 additions

- Runtime profiles: `dev`, `llmops`, `showcase`
- Local-first CI and pre-push validation
- Lightweight control plane
- Agent registry and policy layer
- Prompt Risk and Output Risk modules
- Expanded MissionState with system-state fields
- Self-guardian subsystem
- Safe auto-remediation rules
- Dashboard expansion for policy, risk, and remediation state

---

### 11.1 MissionState Expansion

MissionState is the shared context object that travels with every session. V3.1 expands it to carry system-level state alongside business-level state.

**New fields added in V3.1:**

| Field | Type | Purpose |
|---|---|---|
| `policy_state` | `dict` | Snapshot of which policies applied during this session |
| `risk_state` | `dict` | Snapshot of risk scan results for the session |
| `latest_policy_state` | `PolicyState` | Last known policy evaluation result |
| `latest_risk_state` | `RiskState` | Last known risk scan result |
| `open_system_incidents` | `list[SystemIncident]` | Active self-guardian deviations affecting this context |
| `prepared_brief` | `str | None` | LLM-generated 2-sentence summary of state changes |
| `pending_decisions` | `list[str]` | Decisions awaiting founder response |
| `last_updated_by` | `str` | Agent identity that last mutated MissionState |
| `last_update_reason` | `str` | Why the state was updated |
| `last_changed_fields` | `list[str]` | Which fields changed in the last update |
| `active_agent_roles` | `list[str]` | Which agents are currently active in this session |

**Write path:**

MissionState is written from Python on every meaningful state change. The Go gateway reads it for dashboard display. The write path is POST to `backend API /api/mission-state` and goes through the control plane policy engine.

---

## 12. System Overview

OntologyAI V3.1 has two layers:

### 12.1 Product layer

This is the founder-facing guardian system:
- Finance Guardian
- BI Analyst
- Ops Watch
- Co-founder Agent
- Slack delivery
- watchlist engine
- decision journal
- investor and briefing flows

### 12.2 Operating layer

This is the system-facing governance and self-correction layer:
- control plane
- agent registry
- policy engine
- audit log
- prompt risk scanning
- output risk scanning
- trace ingest
- self-guardian watchlist
- fix planning
- bounded remediation
- expanded dashboard / HITL surface

The product layer creates value for the founder.
The operating layer creates trust, resilience, and controlled evolution.

---

## 13. Core Architecture

### 13.1 Architectural stance

OntologyAI remains a modular distributed system with strong deterministic boundaries.

### 13.2 Core services

- Go gateway for webhook and UI edge handling
- Python AI/decision worker for guardian logic
- PostgreSQL for state, jobs, audit, procedural memory
- Qdrant for episodic and compressed memory
- Graphiti + Neo4j for semantic temporal context and evolving strategy nodes
- Redis or fallback in-memory working state
- Slack for delivery and HITL interaction
- Langfuse for traces and evaluation artifacts
- HTMX internal dashboard for ops visibility

### 13.3 Optional showcase services

- OpenTelemetry collector
- Jaeger
n- Grafana
- Redpanda / Temporal in showcase mode where needed for portfolio depth

### 13.4 Design constraint

The architecture may be rich, but the daily local runtime must remain selective and practical.

---

### 13.1 HITL Surface Expansion

V3.1 expands HITL from a simple approve/hold Slack button to a richer multi-surface system.

**HITL surfaces in V3.1:**

1. Slack approval buttons — existing, unchanged.
2. Dashboard HITL panel — HTMX partial showing pending approvals with drill-down to full context.
3. Temporal signal-based HITL — `SignalWorkflow("hitl-approval")` unblocks `AwaitWithTimeout` in specialist workflows.
4. Risk-gated HITL — when `external_facing=true` or `blast_radius=high`, the risk module auto-escalates to HITL before generation.
5. Remediation HITL — self-guardian fix proposals require HITL approval unless blast radius is low AND action is reversible.

**HITL response model:**

| Response | Meaning | Action |
|---|---|---|
| `approve` | Proceed with proposed action | Execute and log |
| `hold` | Defer decision | Log hold reason, re-notify after timeout |
| `deny` | Reject action | Log denial and context, do not execute |
| `escalate` | Route to emergency contact (future) | Not implemented in V3.1 |

**HITL timeout behavior:**

- Timeout default: 24 hours.
- After timeout: the action is automatically denied with a logged reason.
- Timeout is configurable per workflow type via the policy engine.
- The founder is reminded once at the midpoint (12 hours) and once at expiry (1 hour before).

---

## 14. Runtime Profiles

A major V3.1 requirement is that the repo must support multiple runtime profiles aligned to actual work modes.

### 14.1 Why this matters

The development machine has 16GB RAM. Daily development cannot depend on booting the full showcase stack. A portfolio system that only works when every service is running is operationally dishonest.

### 14.2 Required profiles

#### `make dev`
Minimum day-to-day developer mode.

Must include only the core services necessary for:
- normal coding,
- unit testing,
- local feature work,
- basic workflow debugging.

Likely includes:
- API gateway or local stub
- Python worker
- PostgreSQL
- Qdrant if required by the feature
- lightweight Slack mock or delivery stub

#### `make llmops`
Observability and evaluation mode.

Adds the components required for:
- traces,
- eval loops,
- quality scoring,
- prompt and output risk validation,
- self-guardian testing.

Likely includes:
- Langfuse
- supporting observability stack
- selected trace and eval workers

#### `make showcase`
Full portfolio/demo mode.

Used for:
- live interviews,
- end-to-end architecture walkthroughs,
- distributed tracing demos,
- resilience and degradation demonstrations.

May include:
- full observability stack,
- optional event bus,
- showcase-only infra,
- richer UI and demo surfaces.

### 14.3 Rule

The system architecture is full-featured, but the default local workflow must remain practical. No developer task should require full-stack startup unless that task explicitly belongs to showcase or LLMOps work.

---

### 14.1 Runtime Profiles

Each profile has a strict resource budget:

| Profile | Memory Budget | Services | When to use |
|---|---|---|---|
| dev | ~2GB | PostgreSQL, Python worker | Daily coding, most test suites |
| llmops | ~4-5GB | dev + Qdrant + Langfuse | Langfuse eval, embedding, curator tests |
| showcase | ~9GB | llmops + Neo4j + Graphiti + Grafana stack | Portfolio demo, temporal integration tests |

**Rule:** Default local workflow must use the `dev` profile. Only switch to `llmops` or `showcase` when the task explicitly requires those services. This is enforced by developer discipline, not tooling — but the Makefile provides `make up-dev`, `make up-llmops`, `make up-showcase` as explicit targets with no ambiguity about which profile is active.

---

## 15. DevOps and LLMOps Discipline

V3.1 makes local validation a product requirement, not just an engineering preference.

### 15.1 DevOps rules

- `main` must remain releasable.
- Work must happen in short-lived branches.
- Commits should be atomic and reversible.
- Pull requests should stay small.
- Local validation must catch obvious workflow, syntax, and config issues before push.

### 15.2 Required commands

- `make ci-fast`
- `make ci-local`
- `make smoke`
- `make eval`
- `make demo-check`

### 15.3 Local CI responsibilities

#### `ci-fast`
Runs:
- formatting,
- linting,
- unit tests,
- schema checks,
- workflow linting,
- static validation.

#### `ci-local`
Runs:
- `ci-fast`, plus
- targeted integration tests,
- selected workflow execution checks,
- higher-confidence local validation before push.

### 15.4 Required tooling

- `actionlint` for GitHub Actions validation
- `act` for selected local Actions runs
- pre-push hook to block clearly broken pushes

### 15.5 Why this is a PRD issue

The self-correcting operating layer cannot be trusted if the repository itself regularly allows broken workflow definitions, syntax errors, or invalid configuration to survive until remote CI.

### 15.6 LLMOps rules

The system must trace and evaluate:
- LLM calls,
- tool calls,
- schema compliance,
- retry rates,
- token costs,
- output quality,
- founder response outcomes,
- policy and risk decisions.

The closed-loop model is:

`code -> local CI -> PR CI -> deploy -> trace -> eval -> incident -> fix proposal -> review/apply -> re-evaluate`

---

### 15.1 DevOps and LLMOps Discipline

**CI/CD pipeline requirements (V3.1):**

1. **Local CI must pass before push.** Every developer runs `make ci-fast` before pushing. The pre-push hook enforces this for `main` branch.
2. **PR CI must pass before merge.** GitHub Actions runs: lint (Go + Python), typecheck (Python + Go), unit tests (Go + Python), build (Go), and actionlint on workflow files.
3. **`actionlint` is required on all workflow file changes.** Workflow YAML errors waste significant CI time and must be caught locally.
4. **`act` is the local CI runner.** Use `act -P ubuntu-latest=node:20-slim` to run CI jobs locally without Docker-in-Docker overhead. The `astral-sh/setup-uv@v5` action replaces `actions/setup-python@v5` for slim container compatibility.
5. **Langfuse traces are reviewed periodically.** At least once per sprint, the developer reviews recent Langfuse traces for anomaly patterns, latency outliers, and unexpected LLM calls.

**Makefile targets for CI:**

```
make ci-fast          # Quick local check: actionlint + Go build + Python import check
make ci-actionlint    # Run actionlint on all workflow files
make ci-local         # Run all CI jobs via act (simulates GitHub Actions)
make ci-setup-hooks   # Configure pre-push hook (git config core.hooksPath .githooks)
```

---

## 16. Interaction Model

### 16.1 Shared operating surface

Slack remains the primary founder-facing interface.

One channel, `#sarthi`, acts as the persistent shared session where:
- the founder speaks naturally,
- agents self-activate when relevant,
- decisions are logged,
- relevant follow-ups are attached to prior operating context.

### 16.2 Internal operating surface

The HTMX dashboard evolves into an operator console for:
- watchlist state,
- active alerts,
- HITL queue,
- policy decisions,
- risk scan results,
- system incidents,
- fix proposals,
- recent agent activity,
- trace-linked operating evidence.

### 16.3 Delivery style

Messages must sound like:
- a trusted operator,
- a sharp finance or product colleague,
- grounded in numbers,
- free of generic motivational tone,
- never like a notification system or vague assistant.

---

## 17. Agent Model

### 17.1 Agent roles

| Agent | Role | Function |
|---|---|---|
| OntologyAI | Co-founder agent | Routes, synthesizes, escalates, reflects, curates |
| OntologyAI · Finance | Finance guardian | Revenue, burn, runway, customer concentration, payments |
| OntologyAI · Data | BI analyst | Trends, cohorts, retention, feature usage, NL metric Q&A |
| OntologyAI · Ops | Ops watch | Errors, support, deploy cadence, infra efficiency, product friction |

### 17.2 V3.1 rule: agent registration required

No agent may operate as a first-class system actor unless it is registered in the control plane.

### 17.3 Registration contract

Every agent must declare:
- name
- role
- allowed tools
- allowed models
- authority level
- mutability permissions
- whether external-facing output is possible
- whether HITL is required by default

### 17.4 Typed SOP contracts

All agent roles must use typed SOP-style contracts. No free-form “agent personality” may substitute for explicit input/output structure.

---

## 18. Relevance and Activation

OntologyAI should never respond to everything.

### 18.1 Relevance gate

The relevance gate remains pure code, not LLM-driven.

It determines whether an agent should activate based on:
- keyword relevance,
- active alerts,
- explicit founder question shape,
- pending decisions,
- recent contextual state in MissionState.

### 18.2 Anti-noise rule

If no domain is clearly implicated and no active decision context exists, silence is preferred.

### 18.3 Future extension

The relevance gate may be enriched with system-state signals in V3.1, such as:
- recent policy violations,
- risk-gated outputs waiting on approval,
- recurring self-guardian incidents tied to a workflow.

---

## 19. MissionState

MissionState becomes more central in V3.1.

### 19.1 Purpose

MissionState is the shared, typed context object that all relevant agents may read and selected agents may write.

### 19.2 V3.0 business fields retained

- runway state
- burn severity
- MRR trend
- churn risk
- error spike state
- active alerts
- founder focus

### 19.3 V3.1 system fields added

- `prepared_brief`
- `pending_decisions`
- `last_updated_by`
- `last_update_reason`
- `last_changed_fields`
- `active_agent_roles`
- `latest_policy_state`
- `latest_risk_state`
- `open_system_incidents`
- `latest_fix_proposal`
- `latest_fix_execution_state`

### 19.4 Write discipline

Every MissionState write must record:
- who changed it,
- why it changed,
- which fields changed,
- whether the write passed policy,
- whether a risk gate influenced the write.

### 19.5 Product effect

MissionState should allow the system to present a founder with a coherent operating picture without forcing context reconstruction from multiple channels or hidden traces.

---

## 20. Data Contract

### 20.1 Required V1/V3.1 minimum

#### Stripe
- MRR
- churn events
- new customers
- failed payments
- plan distribution
- customer concentration

#### PostgreSQL
- users
- events / sessions
- feature usage
- cohorts
- internal read-only operating data tables

### 20.2 Optional enrichments

- Plaid / Mercury for bank balance and burn
- Sentry for error and segment correlation
- internal feedback systems for qualitative pattern enrichment
- deployment events and infra usage where available

### 20.3 System-layer telemetry inputs in V3.1

- Langfuse traces
- eval outputs
- retry counts
- tool failure metrics
- workflow latency
- token spend
- risk gate outcomes
- policy decisions
- HITL outcomes
- audit events

### 20.4 Out of scope for now

- highly custom schema onboarding across many analytics systems
- enterprise identity and compliance stacks
- external generalized action platforms

---

## 21. Guardian Watchlist

The founder-facing guardian watchlist remains the product's core detection mechanism.

### 21.1 Finance patterns

- silent churn death
- burn multiple creep
- customer concentration risk
- runway compression acceleration
- failed payment cluster
- payroll revenue ratio breach

### 21.2 BI patterns

- leaky bucket activation
- power user MRR masking
- feature adoption post-deploy drop
- cohort retention degradation
- NRR below 100 at seed stage
- trial activation wall

### 21.3 Ops patterns

- error rate by user segment correlation
- support volume outpacing growth
- cross-channel bug convergence
- deploy frequency collapse
- infrastructure unit economics divergence

### 21.4 Product rule

The first valuable alert must come from a watchlist-worthy pattern, not from synthetic optimism or generic commentary.

---

## 22. Self-Guardian Watchlist

V3.1 introduces a second watchlist: one aimed at the system itself.

### 22.1 Why it exists

If OntologyAI is to become a real operating system, it must detect when its own behavior is drifting, degrading, or becoming unsafe.

### 22.2 Example system incidents

- token cost regression
- schema retry cluster
- timeout cluster
- tool failure cluster
- fallback model overuse
- low HITL acceptance rate
- eval score drop
- dead alert pattern
- policy denial spike
- risk-scan block spike
- degraded relevance gate precision
- unusually high narrative-to-action mismatch

### 22.3 Detection rule

System incident detection must be deterministic-code-first.

The LLM may only be used when needed for:
- bounded clustering,
- summarization of related incidents,
- remediation explanation,
- grouping of ambiguous trace failures.

---

## 23. Thin LLM, Fat Deterministic Core

This remains a non-negotiable architecture principle.

### 23.1 LLM-allowed tasks

The LLM may be used for:
- anomaly judgment where rules need contextual weighting,
- narrative generation,
- intent parsing,
- bounded synthesis,
- remediation explanation where deterministic wording is insufficient.

### 23.2 Deterministic-only tasks

Must stay in code or SQL:
- fetching data,
- computing metrics,
- threshold checks,
- routing,
- tool authorization,
- policy enforcement,
- risk gate invocation,
- workflow validation,
- audit logging,
- schedule mutation,
- state mutation rules,
- Slack payload construction,
- trace ingestion.

### 23.3 Boundary test

Before every LLM call, apply:

1. Could `if/elif` answer this?  
2. Could SQL answer this?

If yes to either, do not use the LLM.

---

## 24. Control Plane

V3.1 adds a lightweight control plane.

### 24.1 Purpose

The control plane governs how agents are allowed to operate. It is not there to make the architecture enterprise-theatrical. It exists because self-correcting and multi-role systems become unsafe when role boundaries, tool permissions, model routing, and audit lineage remain implicit.

### 24.2 Responsibilities

- agent registration
- tool allowlists
- model routing policy
- authority checks
- mutable state permissions
- audit event capture
- health and status inspection
- policy lookup for external-facing workflows

### 24.3 Core contracts

#### `AgentRegistration`
Defines:
- agent identity
- role
- owned domain
- allowed tools
- allowed models
- authority level
- mutable resources
- external-facing capability flag
- default HITL tier

#### `PolicyDecision`
Defines:
- request context
- requesting agent
- requested action
- allow / deny / escalate result
- reason code
- policy rule triggered
- required HITL tier
- timestamp

#### `AuditEvent`
Defines:
- event type
- actor
- target object
- pre-state reference
- post-state reference
- policy result
- risk result
- trace correlation ID
- timestamp

### 24.4 Control plane rule

No agent may:
- send sensitive outputs,
- modify shared state,
- propose external-facing communication,
- or trigger remediation,

unless it is registered and policy-approved.

---

## 25. Policy Layer

### 25.1 Policy goals

The policy layer should answer:
- Can this agent do this action?
- Under what conditions?
- Does this require HITL?
- Is this allowed in the current mode?
- Does blast radius exceed auto-remediation limits?

### 25.2 Policy examples

- Finance Guardian may generate an alert narrative but not auto-send an investor update draft without approval.
- Co-founder agent may synthesize low-severity internal signals but must escalate low-confidence or external-facing outputs.
- Self-guardian may pause a flaky schedule if classified as low blast radius, but may not change model strategy globally without approval.

### 25.3 Policy outputs

- allow
- deny
- allow with HITL-review
- allow with HITL-approve
- allow auto-apply if low blast radius and reversible

---

## 26. Risk Gates

Two explicit risk modules become first-class in V3.1.

### 26.1 Prompt Risk

Scans inputs before model invocation.

Purpose:
- detect confidential material,
- detect disallowed content,
- detect unsafe or excessive data inclusion,
- detect restricted action requests,
- ensure external-facing prompts are operating within policy.

### 26.2 Output Risk

Scans generated drafts before release.

Purpose:
- detect hallucinated claims,
- detect unsupported promises,
- detect pricing commitments,
- detect investor or customer misstatements,
- detect language that overstates certainty.

### 26.3 Hard rule

If `external_facing = true`, HITL tier is always `approve`.

No agent may bypass this rule.

### 26.4 Typical affected workflows

- investor updates
- customer-facing drafts
- pricing change communication
- hiring or candidate communication
- high-confidence recommendations stated as factual guarantees

---

## 27. Audit Log

The audit log becomes foundational in V3.1.

### 27.1 Why it matters

The self-guardian loop requires a trustworthy stream of structured evidence. Traces alone are not enough. The system needs semantic, action-level records of:
- who acted,
- what changed,
- why it changed,
- what policy decided,
- what risk gates returned,
- and how the founder responded.

### 27.2 What must be logged

- all meaningful agent actions
- state mutations
- policy checks
- risk scans
- HITL decisions
- remediation proposals
- remediation applications
- workflow pauses and resumes
- schedule modifications
- prompt/version rollbacks

### 27.3 Audit principle

Every important action should be explainable after the fact without replaying hidden internal context from memory.

---

## 28. Self-Guardian Subsystem

This is the defining V3.1 addition.

### 28.1 Product intent

OntologyAI must guard the founder's business, but it must also guard the quality of its own operation. The self-guardian subsystem consumes traces, evaluations, incidents, and outcomes to produce bounded corrective action.

### 28.2 Submodules

- `trace_ingest`
- `watchlist`
- `analyzer`
- `fix_planner`
- `remediator`
- `schemas`

### 28.3 Inputs

- Langfuse traces
- eval scores
- schema retries
- model fallback counts
- tool failure events
- latency distributions
- token cost
- audit log
- founder HITL outcomes
- policy denial patterns
- risk gate patterns

### 28.4 Outputs

#### `SystemIncident`
A typed record representing a detected system failure mode or drift pattern.

#### `FixProposal`
A typed proposed corrective action with reason, evidence, blast radius estimate, reversibility status, and required approval mode.

#### `FixExecutionResult`
A typed record capturing whether a remediation ran, how it ran, what changed, and what the immediate outcome was.

### 28.5 Low-blast-radius auto-remediations allowed

- prompt rollback
- model fallback switch
- idempotent rerun
- schedule pause
- feature-flagged tool disable

### 28.6 Not allowed without HITL

- broad prompt rewrites
- role authority changes
- large policy changes
- cross-agent tool expansion
- customer/investor communication release
- major data path mutations

### 28.7 Principle

Self-correction is allowed only when:
- the blast radius is low,
- the action is reversible,
- evidence quality is high,
- policy allows it,
- and the action is fully auditable.

---

## 29. HITL Model

### 29.1 HITL tiers

OntologyAI keeps three core tiers:
- auto
- review
- approve

### 29.2 Meaning

- **auto**: may proceed automatically if policy allows and blast radius is low.
- **review**: human should inspect, but the action is usually internal or advisory.
- **approve**: no release or mutation without explicit human approval.

### 29.3 V3.1 additions

The HITL surface now also supports system operations, not just business outputs.

Required actions:
- Approve
- Reject
- Dry run
- Pause workflow
- Open PR
- Ignore for 24h

### 29.4 Hard trust rule

External-facing outputs always require `approve`.

---

## 30. Dashboard Requirements

The HTMX dashboard evolves from a simple ops panel into a full operating console.

### 30.1 Must show

- prepared brief
- pending decisions
- active founder alerts
- alert lineage
- recent policy results
- recent risk scan results
- system incidents
- fix proposals
- remediation history
- recent agent activity
- trace and audit references
- eval score trends

### 30.2 Design goal

The dashboard should make it possible to answer three questions quickly:

1. What is happening in the founder's business?
2. What is happening in OntologyAI itself?
3. What action is waiting on a human?

### 30.3 Surface philosophy

This is not a generic admin dashboard. It is an operator cockpit for a vertical AI system.

---

## 31. Founder-Facing Message Protocol

The core guardian message protocol remains intact.

Every alert must include:
1. pattern name,
2. injected number,
3. why it matters,
4. what the founder probably does not know yet,
5. urgency horizon,
6. what founders typically miss here,
7. one concrete action.

### Constraints

- max 200 words,
- starts with pattern, not number,
- ends with action,
- prose only,
- no invented quantities,
- no generic “keep monitoring” endings,
- no alert spam.

---

## 32. Memory Architecture

### 32.1 Working memory

Short-lived context for active session and workflow execution.

### 32.2 Episodic memory

Past events, alerts, founder responses, operating incidents, and similar cases.

### 32.3 Semantic temporal memory

Graphiti + Neo4j store higher-order relationships such as:
- decision → consequence,
- alert → founder response,
- strategy → observed outcome,
- risk pattern → remediation path.

### 32.4 Procedural memory

PostgreSQL stores:
- jobs,
- decisions,
- eval scores,
- feedback outcomes,
- audit records,
- registered agent metadata,
- policy state.

### 32.5 Compression

Compressed long-tail summaries remain useful for retrieval efficiency and pattern continuity.

---

## 33. ACE Loop and Learning

OntologyAI keeps the Generator -> Reflector -> Curator loop, but V3.1 clarifies that learning must remain structured and bounded.

### 33.1 Generator

Runs the current domain strategy to produce outputs.

### 33.2 Reflector

Reads founder reaction and operational evidence to decide whether the strategy worked.

### 33.3 Curator

Updates the strategy graph incrementally, not through full prompt rewrites.

### 33.4 V3.1 extension

The same pattern now applies at the system level:
- self-guardian detects operational failure,
- bounded reflection groups the evidence,
- controlled curation proposes safe corrections.

---

## 34. Comparative Lessons Incorporated

OntologyAI should learn from leading agent systems without copying their scope.

### 34.1 From SOP-driven multi-agent systems

Adopt typed role contracts and structured deliverables.

### 34.2 From workflow collaboration systems

Adopt workflow validation, visible intermediate states, and true HITL during execution.

### 34.3 From orchestration and accountability systems

Adopt full traceability for instruction, decision, and reply lineage.

### 34.4 Constraint

All imported patterns must strengthen OntologyAI's vertical guardian identity rather than turning it into a broad orchestration product.

---

## 35. Key User Flows

### 35.1 Founder's business alert flow

1. New telemetry arrives.
2. Deterministic rules compute metrics and detect watchlist candidates.
3. Relevant agent assembles typed snapshot.
4. If needed, bounded LLM judgment decides alert-worthiness.
5. Narrative is generated under contract.
6. Policy and risk checks run if needed.
7. Slack message is posted or escalated through HITL.
8. Founder reacts.
9. Reflector records outcome.
10. Curator updates strategy state.

### 35.2 External-facing draft flow

1. Workflow requested.
2. Agent registration and policy checked.
3. Prompt Risk scans input.
4. Draft generated.
5. Output Risk scans result.
6. HITL approve required.
7. Decision and audit event logged.

### 35.3 Self-guardian incident flow

1. Trace and audit signals are ingested.
2. Deterministic watchlist checks detect anomaly or degradation.
3. Incident is typed as `SystemIncident`.
4. Fix planner proposes bounded corrective action.
5. Policy determines whether auto, review, or approve applies.
6. If allowed, remediator executes.
7. Result is logged and linked to follow-up eval.

---

## 36. Functional Requirements

### 36.1 Runtime and repo operations

- System must support `dev`, `llmops`, and `showcase` profiles.
- Compose files or overrides must map cleanly to those profiles.
- Developers must be able to run ordinary feature work without full-stack startup.

### 36.2 Control plane

- All first-class agents must be registered.
- Policy checks must run for protected actions.
- Tool allowlists must be enforceable.
- Audit events must be emitted for important actions.

### 36.3 Risk layer

- Prompt Risk must scan protected model inputs.
- Output Risk must scan protected drafts.
- External-facing content must require HITL approve.

### 36.4 Self-guardian

- System incidents must be typed.
- Fix proposals must estimate blast radius and reversibility.
- Only low-blast-radius fixes may auto-apply.
- All remediations must be auditable.

### 36.5 Dashboard

- Must expose both business state and system state.
- Must support operator actions from the HITL queue.
- Must link actions to lineage evidence where practical.

---

## 37. Non-Functional Requirements

### 37.1 Reliability

The system should degrade gracefully when optional subsystems fail.

### 37.2 Explainability

Important outputs must be traceable to data, policy, and workflow path.

### 37.3 Performance

Daily dev mode should stay lightweight enough for a 16GB machine.

### 37.4 Safety

No external-facing consequential output bypasses risk and approval.

### 37.5 Auditability

Important state changes and automated corrections must be reconstructible.

### 37.6 Testability

Critical logic should be testable without a live full-stack dependency chain.

---

## 38. Fallback and Graceful Degradation

OntologyAI must continue to function in reduced mode when non-core subsystems fail.

### Examples

- If Graphiti is unavailable, continue with empty semantic context.
- If MissionState fetch fails, continue with safe defaults.
- If self-guardian is down, founder-facing guardian workflows still function.
- If observability stack is absent in dev mode, core product behavior should still work.

### Rule

Optional intelligence may disappear; the guardian must not collapse unnecessarily.

---

## 39. Data Safety and Tenant Isolation

Even in early-stage architecture, tenant isolation must remain absolute.

### Rules

- Every DB query filters by tenant.
- Every vector query filters by tenant.
- Every key-value state path names tenant explicitly.
- Every graph query stays within tenant scope.
- Every audit and trace link retains tenant context.

---

## 40. Testing Strategy

V3.1 requires TDD or test-alongside-code for critical paths.

### Required test domains

- control plane registration enforcement
- external-facing workflow approval enforcement
- prompt risk blocking
- output risk blocking
- MissionState auditability
- self-guardian incident detection
- safe vs unsafe remediation routing
- dashboard rendering of business + system state
- runtime profile correctness
- local CI parity with intended GitHub workflow behavior

### Example named tests

- `test_agent_must_register_with_control_plane`
- `test_external_facing_outputs_force_hitl_approve`
- `test_prompt_risk_blocks_restricted_content`
- `test_output_risk_blocks_unsupported_claims`
- `test_mission_state_records_update_reason_and_policy_state`
- `test_self_guardian_detects_incident`
- `test_fix_proposal_requires_hitl_when_blast_radius_not_low`
- `test_safe_fix_can_auto_apply`
- `test_dashboard_renders_control_plane_and_self_guardian_state`
- `test_local_ci_profile_matches_github_workflow_intent`

---

## 41. Build Order — V3.1 Strict

### Step 1 — Runtime profiles

Implement:
- `make dev`
- `make llmops`
- `make showcase`
- matching compose files / overrides

### Step 2 — Local CI guardrails

Implement:
- `make ci-fast`
- `make ci-local`
- `actionlint`
- selected `act` runs
- pre-push hook

### Step 3 — Control plane

Implement:
- agent registry
- policy checks
- audit event stream
- authority manifests

### Step 4 — Prompt Risk and Output Risk

Implement:
- input scanning
- draft scanning
- external-facing approval routing

### Step 5 — Self-guardian

Implement:
- trace ingest
- incident watchlist
- analyzer
- fix planner
- remediator
- schemas

### Step 6 — Dashboard expansion

Implement:
- policy visibility
- risk visibility
- system incident visibility
- remediation actions
- richer HITL surface

---

### 41.1 Build Order — V3.1 Strict

V3.1 must be built in strict dependency order. No phase may begin until all prerequisites pass.

```
Phase 1: Infrastructure (prerequisite for everything else)
  ├── 1a. Runtime profiles (docker-compose.*.yml + Makefile targets)
  ├── 1b. Local CI (actionlint, make ci-fast, pre-push hook, act setup)
  └── 1c. CI workflow cleanup (setup-uv, actionlint job, slim container compatibility)

Phase 2: Control Plane (prerequisite for governance)
  ├── 2a. Policy engine (pydantic model + evaluation logic)
  ├── 2b. Audit log (schema + writer + reader)
  ├── 2c. Authority manifest (all agents declared with permissions)
  └── 2d. Control plane integration (registry, audit commitment, policy check)

Phase 3: Risk Gates (prerequisite for safe output)
  ├── 3a. Prompt risk (pre-generation scan, 8+ rules)
  ├── 3b. Output risk (post-generation scan, 10+ rules)
  └── 3c. Risk gated HITL escalation (external_facing + blast_radius checks)

Phase 4: Self-Guardian Loop (prerequisite for self-correction)
  ├── 4a. Schemas (AgentObservation, Deviation, SelfGuardianAlert, SelfGuardianReport)
  ├── 4b. Observation collector (thread-safe ingest, capped buffer)
  ├── 4c. Self-guardian watchlist (deterministic rules + thresholds)
  ├── 4d. Detector (compare observations against watchlist, produce deviations)
  ├── 4e. DB migration + persister (self_guardian_observations + self_guardian_alerts tables)
  ├── 4f. Fix planner (structured remediation proposals with blast radius)
  ├── 4g. Remediator (apply approved fixes, log outcomes)
  ├── 4h. Integration layer (wire into agent lifecycle, Temporal activities)
  └── 4i. Self-guardian dashboard panel (HTMX partial for alerts + remediation state)

Phase 5: Dashboard & HITL Operating Surface
  ├── 5a. Policy state panel (HTMX partial, Go handler)
  ├── 5b. Risk state panel (HTMX partial, Go handler)
  ├── 5c. Operating layer dashboard (combined view with alert lineage)
  ├── 5d. HITL panel (pending approvals, drill-down context)
  └── 5e. MissionState expansion (write path, display fields)

Phase 6: Post-Merge Quality
  ├── 6a. E2E smoke test (real Docker + real LLM, 9 assertions)
  ├── 6b. DB test enablement (requires PostgreSQL container)
  ├── 6c. Webhook test enablement (requires Redpanda container)
  └── 6d. Documentation update (PRD, README, onboarding)
```

Each phase produces a PR. PRs must be merged before the next phase begins. Phase 6 may run in parallel with Phases 4 and 5 but must complete before V3.1 is marked done.

---

## 42. Acceptance Criteria

V3.1 is complete only if all of the following are true:

1. OntologyAI still reads and feels like a focused guardian for a solo founder.
2. Local runtime supports `dev`, `llmops`, and `showcase` cleanly.
3. Local CI catches common syntax, config, and workflow errors before push.
4. Control plane governs agent registration, policy, routing, and audit.
5. External-facing outputs are always risk-scanned and HITL-approved.
6. Self-guardian consumes trace + audit evidence and emits typed incidents and fix proposals.
7. Only low-blast-radius remediations can auto-apply.
8. Dashboard exposes business state, system state, and remediation state coherently.
9. MissionState captures both founder context and system operating context.
10. The system presents as a serious applied AI / FDE-grade portfolio, not a loose multi-agent demo.

---

## 43. Non-Negotiable Rules

### Rule 1
Numbers are never generated by the LLM.

### Rule 2
The founder-facing guardian always starts from the watchlist, not generic commentary.

### Rule 3
The system must prefer silence over low-value output.

### Rule 4
All consequential actions must be typed, logged, and attributable.

### Rule 5
External-facing outputs always require risk scanning and HITL approval.

### Rule 6
OntologyAI is a vertical guardian, not a generic multi-agent platform.

### Rule 7
All new agent roles require typed SOP-style contracts.

### Rule 8
Every instruction, decision, and remediation must be auditable.

### Rule 9
Safe auto-remediation must be low blast radius and reversible.

### Rule 10
Code and config correctness come before autonomy.

---

### 43.1 Additional Non-Negotiable Rules

### Rule 11

Code correctness before autonomy. No self-correcting behavior is permitted where local validation and policy confidence are weak. A self-correction path that has not been validated by at least three observed incidents and two manual reviews may not auto-apply.

### Rule 12

The CI pipeline must be reproducible locally. No CI step may depend on a service or configuration that cannot be run on a developer laptop. This rule exists to prevent CI-only failures that waste hours of iteration time.

### Rule 13

Every agent must have an exit path. If an agent's workflow dependency is unavailable, the agent must degrade gracefully to a documented fallback behavior, not hang or silently fail.

### Rule 14

The system must never auto-correct a decision it cannot fully undo. Reversibility is the gate condition for automation. If an action is not revertible, it must go through HITL regardless of blast radius.

### Rule 15

Every system incident must have an owner. Self-guardian alerts are never ownerless. If a deviation is detected, the fix plan must include a responsible agent or manual operator. Orphaned alerts are re-escalated after the configured grace period.

### Rule 16

Dashboard data must match operational reality. The HTMX dashboard reads MissionState. MissionState is written on every meaningful state change. There is no separate sync mechanism. If MissionState is stale, the dashboard is stale. This is intentional: it prevents a pretty dashboard from masking an unhealthy system state.

---

## 44. Roadmap Framing

### Near-term

- runtime profiles
- CI discipline
- control plane
- risk gates
- self-guardian v1

### Mid-term

- stronger dashboard surface
- richer self-guardian heuristics
- better founder-specific strategy graphs
- stronger trace-to-remediation feedback loops

### Long-term

- mature vertical operating system for seed founders
- stronger institutional memory
- safer bounded autonomy
- higher trust through observability and consistent operating quality

---

## 45. Final Product Statement

OntologyAI V3.1 is a vertical AI operating system for solo technical SaaS founders.

It watches the founder's business, detects known seed-stage failure patterns, converts them into contextual guidance, learns from founder response, and now monitors its own quality through an auditable, policy-governed, self-correcting operating layer.

The product is not trying to prove that agents can collaborate.
It is trying to prove that a tightly scoped AI system can become a trusted operating partner when it is:
- deterministic where it should be,
- intelligent where it must be,
- inspectable end to end,
- and humble enough to ask for approval when trust is on the line.
