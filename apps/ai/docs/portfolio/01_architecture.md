# OntologyAI Architecture

## System Overview

OntologyAI is an AI Vendor Operations Desk for 20-250 employee B2B companies
outsourcing IT services. It investigates vendor incidents, coordinates responses,
and verifies recovery. LLMs propose actions; deterministic infrastructure decides.

## Data Flow

```
External Events
      |
      v
 +-----------+     +-----------+     +------------+     +-------------+
 | Evidence   | --> | Ontology  | --> | Situation  | --> | Checkpoint  |
 | (untrusted)|     | (typed)   |     | (aggregate)|     | (context)   |
 +-----------+     +-----------+     +------------+     +-------------+
                                                                |
                                                                v
 +-----------+     +------------+     +-------------+     +----------+
 | Outcome   | <-- | Capability | <-- | CONTROL     | <-- | Agent    |
 | (verified)|     | (bound)    |     | PLANE       |     | (LLM)    |
 +-----------+     +------------+     +-------------+     +----------+
       |                                     |
       v                                     v
 +-----------+                         +-------------+
 | ROI       |                         | ActionIntent|
 | (measured)|                         | (untrusted) |
 +-----------+                         +-------------+
```

## Components

### 1. External Events

Vendor notifications, Slack messages, Jira tickets, and system monitoring alerts
arrive as raw event envelopes. Each event is wrapped in an `EventEnvelope` with
tenant scoping, idempotency keys, and trace IDs. Events are the only entry point
into the system; nothing is polled.

**Why it exists:** B2B companies receive vendor status updates through
inconsistent channels. Normalizing them into a single envelope format eliminates
channel-specific logic downstream.

**What breaks without it:** Ingestion becomes ad hoc per vendor. Duplicate events
produce duplicate investigations. Cross-tenant data bleeds.

### 2. Evidence

Raw event text is converted into `Evidence` objects with provenance attribution.
The `Evidence` model (Pydantic `extra="forbid"`) contains `raw_text` and
`normalized_text` but no `instruction`, `authority`, or `execute` fields. External
text is preserved as attributed data, never elevated to an instruction.

**Why it exists:** LLMs process evidence during investigation. If external text
arrives as instructions rather than data, prompt injection succeeds. The Evidence
model enforces the trust boundary at the schema level.

**What breaks without it:** Prompt injection strings in vendor messages become
executable instructions. Cross-tenant evidence enters investigations undetected.

### 3. Ontology

Typed object models (`Party`, `Engagement`, `MoneyEvent`, `Issue`, `Message`,
`PlannedAction`, `Situation`, `Mission`, etc.) define the business domain. All
26 canonical Object Types use `ConfigDict(extra="forbid", strict=True)` to reject
unknown fields and disable type coercion. Graph models hold reference IDs only,
never embedded mutable objects.

**Why it exists:** Vendor operations require a shared vocabulary. Without typed
models, each connector invents its own schema and cross-system reasoning fails.

**What breaks without it:** Schema drift. Connector output interpreted
differently by different modules. Governance rules have no stable target to
enforce.

### 4. Situation

A `Situation` is a durable business-problem aggregate detected from evidence.
It outlives any single mission attempt. Types include `DELIVERY_BLOCKER`,
`RESOURCE_RISK`, `DEPENDENCY_DELAY`, `QUALITY_DEFECT`, `SCOPE_DRIFT`,
`VENDOR_INCIDENT`, `SLA_RISK`, and `VENDOR_PERFORMANCE_ISSUE`. Missions link
in via `Mission.situation_id`.

**Why it exists:** A blocked delivery is a business fact that persists across
agent retries, shift changes, and tool failures. Without a first-class
Situation, the business problem is lost when the agent context resets.

**What breaks without it:** Investigations restart from scratch on each retry.
The business cannot track open problems independently of agent execution.

### 5. Checkpoint

`assemble_checkpoint` compiles Evidence, Onboarding state, and mission context
into a structured checkpoint. The checkpoint gates cross-tenant evidence at
assembly time: evidence from tenant A in tenant B's checkpoint raises
`ValueError("cross-tenant evidence rejected")`.

**Why it exists:** The agent needs a coherent, tenant-safe context window.
Assembling it from raw sources on every LLM call would be expensive and
error-prone.

**What breaks without it:** Agents receive raw, unvalidated context. Cross-tenant
evidence leaks into prompts. The LLM processes inconsistent context shapes.

### 6. Agent

Agents reason over evidence and propose `ActionIntent` objects. They never
directly execute operations, instantiate `AuthorizedAction`, or bypass the control
plane. The agent is an LLM-backed reasoning module that receives a checkpoint and
outputs a structured intent with `capability`, `operation`, `target_reference`,
`requested_parameters`, `reason`, `evidence_ids`, `expected_outcome`, `confidence`,
and `requested_by`.

**Why it exists:** Vendor incident investigation requires reasoning over ambiguous,
conflicting, and incomplete evidence. Deterministic rules cannot handle the
open-ended nature of vendor communication.

**What breaks without it:** Investigations require human analysts for every
vendor interaction. Response times are bounded by human availability.

### 7. ActionIntent

`ActionIntent` is the untrusted output of the agent. It uses Pydantic
`extra="forbid"` and `strict=True`, which means fields like `approved`,
`bypass_policy`, `tenant_id`, and `permissions` are rejected if present. The
intent carries a claim (`requested_by`) but no authority.

**Why it exists:** The trust boundary between LLM and infrastructure must be
enforced at the type level. A Pydantic schema with `extra="forbid"` is a hard
compile-time guarantee that the LLM cannot self-assert authority.

**What breaks without it:** The LLM can inject `approved: true` or
`bypass_policy: true` into its output and bypass all governance.

### 8. Control Plane

The 9-module control plane is the single choke point for all execution:

```
ingress --> authorize --> policy --> idempotency --> approval --> execute --> verify --> audit
```

Modules:
- `ingress.py` - Single entry point (`submit_intent`)
- `authorization.py` - Derives tenant/mission/employee/permissions from trusted state
- `policy.py` - Risk classification and execution blocking
- `idempotency.py` - `SeenSet` replay guard with business-scoped keys
- `approval.py` - HITL signal emission and suspension
- `executor.py` - Only module that calls `CapabilityOpRegistry`
- `verification.py` - Read-back verification after execution
- `audit.py` - Append-only event log
- `concurrency.py` - Optimistic version gating

**Why it exists:** Every side effect must pass through authorization, policy,
idempotency, approval, execution, verification, and audit. No module may bypass
this pipeline. The executor is the only module with connector imports.

**What breaks without it:** Direct connector calls bypass governance. Duplicate
executions occur. No audit trail. No approval gating for high-risk operations.

### 9. Capability

Capabilities are the binding between the control plane and external systems
(Jira, Slack, ERPNext, HubSpot). `CapabilityOpRegistry` exposes a frozen set of
operations; `assert_allowed` enforces role-level allowlists. Unknown operations
raise `UnknownCapabilityOpError`.

**Why it exists:** The agent must not call external systems directly. The
capability registry is the only path to vendor systems, and it enforces a fixed
allowlist per role.

**What breaks without it:** Agents call arbitrary APIs. Role-based access control
is unenforceable. No circuit breaker or retry taxonomy.

### 10. Verification

After execution, `verify_execution` reads back the written state and compares it
against expected outcomes. Mismatches yield `verified=False` with rollback
metadata. Empty predicates fail closed (INDETERMINATE), never silent success.

**Why it exists:** A vendor claiming "fixed" while monitoring still shows errors
must be rejected. Verification is predicate-based: every predicate must pass
against observed system state.

**What breaks without it:** False recoveries are accepted. The system reports
success when the underlying problem persists.

### 11. ROI

Measured outcomes include response time (event-to-investigation), resolution time
(investigation-to-verified-recovery), human intervention count, and cost per
mission. All measurements are derived from execution traces and audit logs.

**Why it exists:** Without measurement, the system's value is a claim, not a
fact. ROI tracking ties system behavior to business outcomes.

**What breaks without it:** No way to demonstrate value. No basis for capacity
planning or cost optimization.

## Trust Boundary

```
+-------------------------------------------------------------+
|                    LLM (UNTRUSTED)                          |
|                                                             |
|  Agent receives checkpoint, outputs ActionIntent            |
|  ActionIntent: extra="forbid", strict=True                  |
|  No tenant_id, no permissions, no approved, no bypass       |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|                 CONTROL PLANE (TRUSTED)                     |
|                                                             |
|  authorize: derives tenant/mission/employee from trusted    |
|             state, NOT from ActionIntent.requested_by       |
|  policy:    classifies risk tier, blocks CRITICAL           |
|  idempotency: SeenSet replay guard                          |
|  approval:  HITL signal for HIGH/CRITICAL                   |
|  execute:   CapabilityOpRegistry with role allowlist        |
|  verify:    read-back comparison, fail-closed               |
|  audit:     append-only event log                           |
+-------------------------------------------------------------+
```

The critical invariant: `ActionIntent.requested_by` is a claim, not an identity.
The `authorize` function derives `tenant_id`, `mission_id`, `employee_id`, and
`actor_identity` from `trusted_context`, never from prompt output. The
`AuthorizedAction` can only be constructed via `from_intent()` inside the control
plane.
