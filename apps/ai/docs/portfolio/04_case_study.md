# OntologyAI: Engineering Case Study

## 1. Business Problem

B2B companies with 20-250 employees increasingly outsource IT services to
multiple vendors: managed service providers, cloud infrastructure providers,
SaaS platforms, and specialized contractors. When a vendor incident occurs --
a payment gateway goes down, a deployment blocks a delivery, a security alert
fires -- the company must investigate, coordinate, and verify recovery across
disparate communication channels (Slack, Jira, email, vendor dashboards).

The core problem is coordination latency. A blocked delivery requires:
identifying which vendor is responsible, gathering evidence from multiple
channels, determining the business impact, escalating to the right person,
tracking the vendor's response, and verifying that the fix actually works.
For a 50-person company, this process can consume 4-8 hours of engineering
time per incident, with most of that time spent on context switching and
status updates rather than resolution.

## 2. Why Existing ITSM Is Not Enough

ITSM ticketing systems (Jira Service Management, Freshservice, Zendesk)
provide incident tracking and SLA monitoring. They do not:

- **Investigate**: A ticket records that an incident exists; it does not
  gather evidence from Slack, Jira comments, vendor status pages, and
  internal monitoring to build a coherent picture.
- **Verify**: A ticket can be marked "resolved" when a vendor says it is
  fixed; it does not check whether error rates actually dropped, latency
  returned to baseline, or the affected service is healthy.
- **Escalate proactively**: A ticket follows a predefined escalation matrix;
  it does not reason about whether the escalation is appropriate given the
  specific business context, vendor history, and current risk level.
- **Coordinate across channels**: A ticket lives in one system; the evidence
  lives in Slack threads, Jira comments, vendor emails, and monitoring
  dashboards.

## 3. Discovery Assumptions and Validation

| Assumption | Validated? | Evidence |
|------------|------------|----------|
| Vendor incidents arrive via multiple channels | Yes | EventEnvelope supports Slack, Jira, ERPNext, HubSpot, Razorpay sources |
| Evidence is inherently untrusted | Yes | Evidence model (extra="forbid") treats all external text as attributed data |
| LLMs can reason over ambiguous vendor communication | Yes | 65 LLM evaluation tests across 8 scenarios (E1-E8) |
| LLMs cannot be trusted to execute actions | Yes | ActionIntent (extra="forbid") cannot carry authority fields |
| Deterministic infrastructure should control execution | Yes | 9-module control plane with authorization, policy, idempotency, approval |
| False recovery is a real problem | Yes | Predicate-based verification rejects vendor claims that do not match observed state |
| Tenant isolation is non-negotiable | Yes | Cross-tenant evidence rejected at checkpoint assembly; cross-tenant missions denied |

## 4. Domain Model

### Situation as First-Class Aggregate

A `Situation` is the business-problem aggregate. It outlives any single
mission attempt. Types: `DELIVERY_BLOCKER`, `RESOURCE_RISK`,
`DEPENDENCY_DELAY`, `QUALITY_DEFECT`, `SCOPE_DRIFT`, `VENDOR_INCIDENT`,
`SLA_RISK`, `VENDOR_PERFORMANCE_ISSUE`.

```
Event/Evidence --> Situation --> Mission --> Action --> Outcome
```

The Situation persists across agent retries, shift changes, and tool
failures. Missions link in via `Mission.situation_id`. This separation
means the business can track open problems independently of agent execution
state.

### Evidence as Untrusted Data

`Evidence` is a Pydantic model with `extra="forbid"`. It contains `raw_text`
and `normalized_text` but explicitly rejects `instruction`, `authority`, and
`execute` fields. External text is normalized as a third-party report with
provenance attribution (`[slack report by vendor in #channel]: ...`).

The critical property: Evidence is data, never instruction. This is enforced
at the schema level, not by convention.

### Mission as Workflow Container

A `Mission` is a bounded AI work unit operating within one onboarding. It
carries `title`, `status`, `priority`, `owner_id`, `employee_role`, and
`situation_id`. The mission lifecycle (`pending`, `active`, `stalled`,
`completed`, `failed`, `archived`) maps to Temporal workflow states.

## 5. Architecture

### Control Plane Pattern

The control plane is a 9-module pipeline. Every action intent must pass
through:

```
ingress --> authorize --> policy --> idempotency --> approval --> execute --> verify --> audit
```

No module may bypass this pipeline. The executor (`executor.py`) is the only
module with connector imports. This is enforced by import structure, not by
convention.

### Capability Binding

`CapabilityOpRegistry` exposes a frozen set of operations over external
systems (Jira, Slack, ERPNext, HubSpot). `assert_allowed` enforces
role-level allowlists. Unknown operations raise `UnknownCapabilityOpError`.

The binding between an agent role and its allowed operations is defined in
`EmployeeRoleConfig`. The agent never sees the full capability set; it only
sees what its role permits.

### Temporal Waiting

HIGH-risk actions require human approval. The control plane emits a
`hitl-approval` signal and suspends via `await_approval`. In production,
Temporal binds this to a real workflow signal. The approval timeout
(`approval_timeout_seconds`) returns `deny:approval_expired` if no human
responds.

## 6. Why Agents Are Used

Vendor incident investigation requires reasoning over:
- Ambiguous vendor language ("we are looking into it", "no ETA yet")
- Conflicting evidence (vendor says resolved, monitoring still shows errors)
- Incomplete information (missing context from prior interactions)
- Business-specific impact (this delivery blocks a $50K deal)

Deterministic rules cannot handle this open-ended reasoning. The agent
(LLM-backed) receives a compiled checkpoint and proposes an `ActionIntent`
with capability, operation, target, parameters, reason, evidence IDs,
expected outcome, confidence, and requester.

## 7. Why Agents Are NOT Trusted

LLMs hallucinate. They follow injected instructions. They produce structurally
invalid output. They sometimes assert authority they do not have.

The system is designed so that no LLM error can produce an unauthorized side
effect:

- `ActionIntent` uses `extra="forbid"` -- fields like `approved`,
  `bypass_policy`, `tenant_id` are rejected at construction time
- The agent never instantiates `AuthorizedAction` -- it is created only by
  the control plane via `authorize()`
- `ActionIntent.requested_by` is a claim, not an identity -- the control
  plane derives identity from trusted server state
- The agent never calls external systems directly -- it proposes intents;
  the control plane executes

## 8. Control Plane: The 9-Module Gate

| Module | Responsibility | Key Property |
|--------|---------------|--------------|
| ingress | Single entry point for all intents | All callers use `submit_intent()` |
| authorize | Derives tenant/mission/employee from trusted state | Never from `ActionIntent.requested_by` |
| policy | Risk classification and execution blocking | CRITICAL tier = hard block |
| idempotency | `SeenSet` replay guard | Business-scoped keys, not thread+sequence |
| approval | HITL signal emission and suspension | HIGH/CRITICAL require human decision |
| execute | Calls `CapabilityOpRegistry` | Only module with connector imports |
| verify | Read-back comparison after execution | Empty predicates fail closed |
| audit | Append-only event log | Every decision recorded |
| concurrency | Optimistic version gating | Stale versions rejected |

The pipeline is synchronous within a single request. Each module returns a
decision or passes execution to the next. The audit log captures every
decision, creating a complete trace of every action attempt.

## 9. SLA/Temporal Design

### 7-State Machine

Mission lifecycle: `pending` -> `active` -> `stalled` | `completed` |
`failed` -> `archived`. Temporal workflows manage state transitions with
explicit signal handling for HITL approval.

### Escalation Ladder

Actions escalate through risk tiers:
- **LOW**: Execute without approval (internal notes, draft creation)
- **MEDIUM**: Execute with governance logging (ownership changes, issue
  status updates)
- **HIGH**: Require human approval via HITL signal (sending communications,
  money state changes)
- **CRITICAL**: Block execution entirely (no skill runs)

### Waiting Patterns

`AwaitWithTimeout` suspends the workflow until a human resolves the approval
signal or the timeout expires. On timeout, the action is marked
`deny:approval_expired` and the idempotency key is marked (preventing
duplicate execution on retry).

## 10. Recovery Verification

Recovery is predicate-based, not claim-based. When a vendor reports
"resolved", the system evaluates `RecoveryPredicate` objects against observed
system state:

```python
predicates = [
    RecoveryPredicate(field="error_rate", op="lt", threshold=0.01),
    RecoveryPredicate(field="latency_p99_ms", op="lt", threshold=500),
]
outcome = evaluate_predicates(predicates, observed)
# outcome.verified = True only if ALL predicates pass
```

Key properties:
- **Fail-closed**: Empty predicates yield INDETERMINATE, never silent success
- **Predicate-based**: Every predicate must pass against observed state
- **Vendor claims are data**: The vendor's "resolved" status is one input;
  it does not override monitoring evidence

## 11. Security Model

### Adversarial Testing

23 security adversarial tests across 5 categories prove the system resists
attack vectors. All tests are deterministic (no real LLM, no real network).

### Prompt Injection Defense

Three layers:
1. **Schema level**: `Evidence` model (extra="forbid") rejects `instruction`
   and `authority` fields
2. **Normalization level**: External text is quoted as third-party report with
   provenance, never passed as system prompt
3. **Checkpoint level**: `assemble_checkpoint` places injection text inside
   `RelevantEvidence.excerpt` as data citation

### Tenant Isolation

- Cross-tenant evidence: `ValueError("cross-tenant evidence rejected")` at
  checkpoint assembly
- Cross-tenant missions: `authorize()` derives tenant from trusted context,
  not from `ActionIntent.requested_by`
- Fail-closed: One foreign-tenant evidence in a batch rejects the entire batch

## 12. Evaluation Strategy

1. **Deterministic first**: Model contracts, boundary tests, config
   validation. No external dependencies. Runs in seconds.
2. **Adversarial second**: Prompt injection, tenant escape, capability
   escalation, approval spoofing, replay. All mocked.
3. **LLM evaluation third**: Real Azure OpenAI calls against 8 scenarios
   with judge prompts and confidence thresholds. Separate pipeline.

This ordering ensures that the foundation is solid before testing
probabilistic behavior. If deterministic tests fail, no LLM evaluation
is needed.

## 13. Failure Injection

Every layer is tested against realistic failures:

| Layer | Failures Tested |
|-------|----------------|
| Event | Duplicate, out-of-order, malformed, unknown type |
| Vendor | HTTP 500, HTTP 429, timeout, invalid payload, connection refused, partial response |
| Database | Optimistic concurrency conflict, stale checkpoint, duplicate write |
| Control plane | Idempotency under retry, approval timeout, version gate |

All failure tests are deterministic (mocked, no network). The property
proven: no failure produces a crash, a duplicate side effect, or a silent
pass.

## 14. Observability

### Execution Traces

`ExecutionTrace` records spans with parent-child relationships, timing,
status, and events. `LLMCallRecord` captures model, prompt version,
token counts, latency, and decision for every LLM call.

### Timeline Export

Traces export to sorted timelines for debugging and analysis. All models
use `extra="forbid"` to prevent schema drift.

### Cost Tracking

`CostLatencyTracker` computes per-call and per-mission costs using model
pricing tables. Metrics include resolution ratio (verified / total
outcomes) and multi-mission cost independence.

## 15. ROI

Measured outcomes:

| Metric | Measurement |
|--------|-------------|
| Response time | Event receipt to investigation start (from audit log timestamps) |
| Resolution time | Investigation start to verified recovery (from verification outcomes) |
| Human interventions | Count of HITL approvals requested and resolved |
| Cost per mission | LLM token cost + infrastructure cost per mission lifecycle |
| False recovery rate | Percentage of vendor "resolved" claims rejected by verification |

The system does not claim to replace human judgment. It claims to reduce
coordination latency, eliminate context-switching overhead, and provide
verified (not claimed) recovery.

## 16. Trade-offs

| Sacrificed | For |
|------------|-----|
| LLM autonomy | Deterministic governance (every action passes 9-module control plane) |
| Speed of execution | Safety (approval gating adds latency for HIGH/CRITICAL actions) |
| Full vendor API coverage | Security (frozen 10-op capability set, not arbitrary API calls) |
| Real-time streaming | Idempotency (synchronous pipeline ensures at-most-once) |
| Simple architecture | Trust boundary (separate LLM reasoning from infrastructure execution) |
| Comprehensive monitoring | Cost (execution traces add storage overhead per mission) |

## 17. What Remains Unsolved

The following limitations are explicit and documented:

1. **Does not replace monitoring**: The system reacts to events; it does not
   generate alerts from metrics. It depends on external monitoring to produce
   events.

2. **Does not guarantee vendor cooperation**: The system can investigate,
   escalate, and verify, but it cannot force a vendor to respond or fix an
   issue.

3. **Does not autonomously perform material changes**: CRITICAL-tier actions
   are blocked. The system proposes; a human decides.

4. **Cannot infer missing contractual facts**: SLA terms, escalation
   contacts, and vendor obligations must be configured. The system does not
   extract these from contracts.

5. **LLM decisions remain probabilistic**: Even with evaluation, grounding,
   and safety tests, LLM output is not deterministic. The control plane
   ensures that probabilistic output cannot produce unauthorized effects,
   but it cannot ensure the output is always optimal.

6. **ROI measurements limited to instrumented effects**: Response time,
   resolution time, and cost are measured from system traces. Business
   outcomes (revenue protected, customer satisfaction) are not directly
   measured.
