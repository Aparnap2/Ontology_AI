# OntologyAI — AI-Powered B2B SaaS Customer Onboarding Operations

> Frozen portfolio vertical: governed AI workforce for B2B SaaS onboarding, Closed-Won to First Value.
>
> Branch: `feature/ontologyai-onboarding-restructure` | Source of truth: `OntologyAI_PRD_28_08.md` (1270 lines, repo root) | 170 Python tests green | ruff clean

## Contents

- [1. Vertical](#1-vertical)
- [2. Integrations](#2-integrations)
- [3. Workforce](#3-workforce)
- [4. Mission Catalog M1-M6](#4-mission-catalog-m1-m6)
- [5. Agentic Boundary](#5-agentic-boundary)
- [6. Founder Workspace](#6-founder-workspace)
- [7. Stack Justification](#7-stack-justification)
- [8. Authority Boundary](#8-authority-boundary)
- [9. Domain Model](#9-domain-model)
- [10. Runtime Scope](#10-runtime-scope)
- [11. Repo Map](#11-repo-map)
- [12. Getting Started](#12-getting-started)
- [13. Tests](#13-tests)
- [14. Scope and ROI Pointer](#14-scope-and-roi-pointer)
- [15. Status and Roadmap](#15-status-and-roadmap)
- [16. Conventions](#16-conventions)

## 1. Vertical

Exact job (PRD quote):

> "Take a newly closed B2B customer from sales handoff to verified onboarding readiness/first-value milestone, while detecting and resolving cross-system blockers"

Owned flow:

```
CLOSED-WON
    |
SALES HANDOFF
    |
+---+---+
|       |
Validate  Extract
data      commitments
|       |
+---+---+
    |
KICKOFF READY?
    |
IMPLEMENTATION
    |
+-----+-----+
|           |
Jira        Slack
delivery    context
|           |
+-----+-----+
    |
BLOCKER DETECTED
    |
INVESTIGATE (Salesforce + Slack + Jira, then Notion SOP)
    |
ROOT CAUSE
    |
ACTION / APPROVAL
    |
EXECUTE
    |
VERIFY
    |
FIRST VALUE READY
    |
MONITOR
```

Why this beats the alternatives:

- Retention is an outcome metric, not a clean operational workflow. Genuine retention automation needs product usage telemetry, billing/subscription data, support systems, health and renewal data — the four chosen systems do not provide that ground truth. Onboarding does.
- RevOps is too broad: lead management, forecasting, pipeline, compensation, attribution, territory, CRM administration. That is another product.
- Whole lifecycle (Closed-Won through renewal/expansion) is too broad for a portfolio. Closed-Won to First Value is narrow enough to finish and rich enough to exercise the architecture.

## 2. Integrations

| System | OntologyAI use |
|--------|----------------|
| Salesforce | customer/deal/handoff truth |
| Jira | implementation/delivery work |
| Slack | human context, commitments, blockers |
| Notion | onboarding SOPs, process rules, definitions of done |

Closed-won handoff example: goals, commitments, stakeholders, technical requirements, and agreed next steps move from Salesforce into onboarding work. Slack cross-checks what was actually promised; the SOP defines what "done" means.

## 3. Workforce

Three analysts, one shared system:

- Handoff Analyst — owns Closed-Won to onboarding-ready handoff. Validates completeness; identifies missing commitments; identifies stakeholders; maps technical requirements; detects contradictions; creates missing onboarding tasks; flags unresolved handoff issues.
- Onboarding Operations Analyst — main agentic employee; keeps implementation moving toward first value. Monitors milestones; detects blockers; investigates cross-system dependencies; identifies owners; coordinates Jira/Slack work; escalates SLA risks; verifies milestone completion.
- Knowledge/Process Analyst — keeps the onboarding process itself accurate. Detects SOP drift; detects repeated exceptions; identifies missing steps; identifies unclear ownership; proposes SOP improvements.

One-runtime principle: Employee Runtime → employee config → Mission → hybrid process/agent execution. Employees differ only by responsibilities, processes, skills, capabilities, scope, authority, KPIs, and SOPs — not by architecture.

## 4. Mission Catalog M1-M6

- M1 — Validate Closed-Won Handoff: Salesforce → validate required handoff fields → cross-check Slack → retrieve onboarding SOP → identify missing data → create onboarding work.
- M2 — Prepare Kickoff: handoff complete → identify stakeholders → validate success criteria → assign owner → create kickoff checklist → mark READY.
- M3 — Investigate Onboarding Blocker: Jira blocked → identify customer → gather Salesforce context → search Slack → retrieve SOP → determine root cause → identify owner → propose/execute remediation → verify. Implemented as `run_blocker_investigation_mission`, 9/9 tests green.
- M4 — Recover Overdue Milestone: milestone overdue → investigate dependency → identify responsible team → coordinate → update Jira → verify progress.
- M5 — Detect Onboarding Process Drift: observed execution vs SOP → detect deviation → determine whether process or execution is wrong → propose correction.
- M6 — First-Value Readiness Review: milestones + tasks + commitments + blockers + owner status → readiness assessment → missing requirements → recommendation → approval if necessary.

M3 is implemented on this branch. M1, M2, M4, M5, M6 are tracked in #64.

## 5. Agentic Boundary

Fixed M3 process: BLOCKER → INVESTIGATE → IDENTIFY CAUSE → RESOLVE/ESCALATE → VERIFY.

The LLM controls only the ambiguous investigation:

1. Which evidence should I inspect?
2. What does this Slack discussion mean?
3. Is Jira issue X actually related?
4. Are these two problems the same?
5. What is the most plausible root cause?
6. What additional evidence is worth retrieving?

It never decides: data access; Jira writes; whether approval is required; tenant eligibility; skipping verification. Those stay deterministic.

Acme context-checkpoint example (assembled before any cognitive call): onboarding Acme; opportunity 120K; customer goal and success criteria; current milestone Data Integration; Jira INT-382 blocked; Slack "customer waiting on SSO configuration"; SOP enterprise onboarding v3.2; owners (AE, implementation); previous actions; current risks; freshness (Salesforce 2m, Jira 30s, Slack 1m, Notion 1d).

Single cognitive call returns JSON only, e.g. finding "SSO configuration is blocking the integration milestone", confidence 0.91, evidence refs, next step escalate owner. Targeted refresh only: the LLM requests more evidence solely when information is missing.

## 6. Founder Workspace

Target of #57 (workspace surface), #61 (live updates), #65 (ROI proof). Desired ACME onboarding view:

```
ACME — ONBOARDING
Overall: At Risk (amber indicator)
First Value: Jun 18
Current Milestone: SSO Integration
BLOCKER: SSO configuration blocked for 3 days
Why: implementation team waiting for customer configuration
Evidence: Salesforce tick, Slack tick, Jira tick, SOP tick
Investigated by: Onboarding Operations Analyst
Recommendation: escalate implementation owner
[Approve] [Reject] [Investigate]
```

Event timeline: 09:12 Salesforce contract closed; 09:13 handoff mission created; 09:14 missing technical requirement detected; 09:16 Slack context retrieved; 09:17 Jira onboarding task created; 10:22 SSO task blocked; 10:23 investigation started; 10:25 root cause identified; 10:27 escalation requested; 10:31 founder approved; 10:32 Jira updated; 10:33 Slack notified; 10:34 verification passed.

## 7. Stack Justification

- Postgres: canonical onboarding/process/mission state.
- Redpanda: continuous event propagation across Salesforce/Jira/Slack/Notion changes.
- Go: concurrent connector ingestion and event processing.
- Redis: hot context checkpoints, entity summaries, dedupe, workspace state.
- Neo4j: Customer → Opportunity → Commitment → Onboarding → Milestone → Jira Task → Owner traversal.
- Qdrant: semantic search over SOPs, Slack discussions, onboarding notes, historical decisions.
- Temporal: long-running missions (waiting for customer, Jira, approval; resume/retry).
- LLM: ambiguity-only — interpret evidence and choose the next reasoning step.
- Pydantic: all contracts.
- IAM/policy: who can see or change which customer and work item.
- Langfuse/OTel/Sentry: LLM/retrieval/tool traces, distributed trace, app failures.
- HTMX/SSE: live onboarding workspace.

## 8. Authority Boundary

Core principle:

> "LLMs propose intent. Deterministic infrastructure decides whether intent is valid, authorized, safe, idempotent, executable, and successfully completed."

Fixed pipeline:

```
Evidence → Context Checkpoint → Employee / Mission / Skill → ActionIntent
  → CONTROL PLANE (schema, auth, RBAC/scopes, policy, evidence gate,
     idempotency, concurrency, approval)
  → AuthorizedAction → Capability Executor → Business Verification
  → Immutable Audit / Timeline → Mission + Memory + Workspace
```

Rules: skills and LLMs emit only `ActionIntent` (untrusted); only the Control Plane produces `AuthorizedAction`; only the Capability Executor touches connectors; every action records reason, evidence IDs, policy decision, approval, idempotency key, verification, audit event; connector payloads never become instructions (see ADR-012).

## 9. Domain Model

`Onboarding` is the first-class aggregate. `Mission` is a bounded AI work unit within one onboarding via `Mission.onboarding_id`. `Task` is planned work; `Issue` is a deviation (blocker, risk, drift) — the two never mix. Connector data is evidence with provenance, never instruction.

References: `docs/adr/ADR-010-onboarding-domain-aggregate.md`, `docs/adr/ADR-011-authority-boundary.md`, `docs/adr/ADR-012-external-data-boundary.md`.

## 10. Runtime Scope

Runtime profile: `onboarding_v6` (see `apps/ai/config/runtime.yaml`). Active: `slack`, `salesforce`, `jira`, `notion`. Legacy (`stripe`, `plaid`, `erpnext`, `hubspot`, `quickbooks`) is archived and fail-closed under this profile.

## 11. Repo Map

- `apps/ai/src/control_plane/` — authority boundary (`ingress.py`, `contracts.py`, `authorization.py`, `policy.py`, `idempotency.py`, `approval.py`, `executor.py`, `verification.py`, `audit.py`).
- `apps/ai/src/mission/skills/onboarding_ops.py` — skill `investigate_onboarding_blocker`; LLM reasons only, then one `ActionIntent`.
- `apps/ai/src/mission/blocker_investigation_mission.py` — runner `run_blocker_investigation_mission`; evidence ingestion, checkpoint, timeline, memory, EmployeeRuntime dispatch.
- Contract tests — `apps/ai/tests/test_action_intent_contract.py`, `apps/ai/tests/test_onboarding_aggregate_contract.py`, `apps/ai/tests/test_task_issue_contract.py`, `apps/ai/tests/test_evidence_guardrail_contract.py`, `apps/ai/tests/mission/test_skill_contracts.py`, `apps/ai/tests/deterministic/test_behavioral_contracts.py`; slice coverage in `apps/ai/tests/test_blocker_investigation_slice.py`.
- `apps/ai/config/runtime.yaml` — declares `runtime_profile: onboarding_v6` plus enabled vs legacy lists.
- Source PRD: `OntologyAI_PRD_28_08.md`. Canonical tracker: `Aparnap2/Ontology_AI`, issues #59–#66.

## 12. Getting Started

### Prerequisites

- Docker (PostgreSQL, Temporal, Qdrant)
- Go 1.24
- Python 3.13 with [`uv`](https://github.com/astral-sh/uv)

### Quickstart

```bash
# 1. Start infrastructure
make up

# 2. Run the Go server
cd apps/core && go run cmd/server/main.go

# 3. Run the Go Temporal worker
cd apps/core && go run cmd/worker/main.go

# 4. Install Python deps and run the Python worker
cd apps/ai && uv sync
cd apps/ai && uv run python -m src.worker

# 5. Open the workspace
#    http://localhost:8080
```

### Environment variables

| Provider | Variables |
|----------|-----------|
| Azure AI Foundry | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| Groq | `GROQ_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Ollama (local) | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` |

Secrets live in a local `.env` file (never committed).

## 13. Tests

```bash
# Go — all packages
cd apps/core && go test ./...

# Python — full suite
cd apps/ai && uv run pytest tests/ -v

# Lint
cd apps/ai && uv run ruff check src tests
```

Current gate on this branch: 170 Python tests green, ruff clean.

## 14. Scope and ROI Pointer

Reality check: 4 integrations, 3 employees, 6 missions, about 15 skills, about 10–12 capabilities, about 20 entities. Baseline is a simulation assumption: about 75 min manual vs about 20 min assisted per onboarding. Track time avoided, autonomy rate, decision latency (Time-to-Context/Decision/Action/Resolution), reliability rates, and AI quality; demo the same scenario twice (manual vs AI employee). Full economics live in #65.

## 15. Status and Roadmap

Completed on this branch: ADRs (010/011/012), canonical contracts, control-plane scaffold, legacy gating via `onboarding_v6`, governed blocker-investigation slice (happy path, duplicate, unauthorized, missing evidence, policy violation, approval resume, connector failure, unverified-200, injection-as-evidence).

Next: evidence checkpoint pipeline (#63), M1–M6 workforce config (#64), ACME E2E/ROI (#65), founder workspace surface (#57), live updates (#61), plus Go SSE wiring, Temporal parity, and migration 013. Issues #59–#66 tracked in `Aparnap2/Ontology_AI`; #59–#62 cover verification and commit of the work above.

## 16. Conventions

- Feature branches: `git checkout -b feature/description` — never commit directly to `main`.
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- Full build/test/style rules live in `AGENTS.md`.
