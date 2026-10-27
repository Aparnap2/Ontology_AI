# Failure Matrix — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

How the system behaves when a dependency is unavailable. Each operation class
gets exactly one verdict per dependency.

---

## 1. The governing rule

> **An agent may operate on incomplete information only when the missing
> information cannot invalidate the safety or correctness of the proposed action.**

Everything below follows from that sentence. If a missing dependency can change
whether an action is safe, permitted, or correct, the verdict is DENY or ESCALATE.
If it cannot, the verdict may be DEGRADE or CONTINUE.

The second rule, from `src/mission/verify.py:61-67`:

> **INDETERMINATE must never become SUCCESS.**

`verified` is computed strictly as `state == "VERIFIED"`. There is no path from
`INDETERMINATE` to `VERIFIED`.

---

## 2. Verdict vocabulary

| Verdict | Meaning |
|---|---|
| **CONTINUE** | The operation proceeds unaffected; the dependency is not on its path |
| **DEGRADE** | The operation proceeds with reduced scope, and the reduction is recorded |
| **WAIT** | The operation blocks until the dependency returns, with a bounded timeout |
| **RETRY** | The operation is retried with backoff, up to a hard cap of 3 attempts |
| **ESCALATE** | A human is engaged; the operation does not proceed unattended |
| **DENY** | The operation is refused. No side effect. An audit event is emitted |

---

## 3. The matrix

| Dependency | Read / query | Governed write | Verification / read-back | Approval gate | Long-running workflow | Reporting / analytics |
|---|---|---|---|---|---|---|
| **Memory / state** (audit, idempotency, versions) | DEGRADE | **DENY** | DEGRADE | DEGRADE | DEGRADE | DEGRADE |
| **Vector store** (Qdrant) | DEGRADE | CONTINUE | DEGRADE | CONTINUE | DEGRADE | DEGRADE |
| **Redis** (cache, events) | CONTINUE | DEGRADE | CONTINUE | CONTINUE | DEGRADE | DEGRADE |
| **Temporal** | WAIT | **ESCALATE** | WAIT | ESCALATE | WAIT | CONTINUE |
| **Object storage** | CONTINUE | DEGRADE | DEGRADE | CONTINUE | DEGRADE | CONTINUE |
| **Redpanda** | CONTINUE | DEGRADE | CONTINUE | CONTINUE | DEGRADE | DEGRADE |

---

## 4. Why each row is what it is

### 4.1 Memory / state

Backing today is process-local: `audit.py:14 AUDIT_LOG: list`,
`idempotency.py:269 _seen = SeenSet()`, `concurrency.py:40 _store = VersionStore()`,
`cost_latency.py:83 _missions: dict[str, MissionMetrics]`.

| Op class | Verdict | Reason |
|---|---|---|
| Governed write | **DENY** | Without the idempotency claim there is no at-most-once guarantee. Issuing a write that may execute twice is not a degraded write — it is an uncontrolled side effect. `ingress.py:112-122` cannot claim, so it cannot proceed. |
| Read-back | DEGRADE | Returns `INDETERMINATE`, never `VERIFIED` (`verify.py:61-67`). |
| Approval gate | DEGRADE | The claim is released on every non-execute path (`ingress.py:136-167`), so a retry is permitted — availability degrades, safety does not. |
| Long-running | DEGRADE | Workflow code proceeds; history is lost. |

**Critical consequence:** a process restart loses all of this state. At-most-once
does **not** survive a restart. The lease (`idempotency.py:62,143-145`) makes an
*in-process crash* recoverable by another worker in the same process — it does not
make a restart safe. See `PERSISTENCE_BOUNDARY.md`.

### 4.2 Vector store (Qdrant)

Semantic retrieval feeds context, not authority.

| Op class | Verdict | Reason |
|---|---|---|
| Governed write | CONTINUE | A governed write is authorised by the allowlist (`authorization.py:53-70`) and claimed atomically. Retrieval is not on the write's correctness path — the missing information cannot invalidate the safety of an action that was already authorised by trusted state. |
| Read-back | DEGRADE | Read-back for connector writes uses `READ_COUNTERPART` (`verify.py:28-34`), not the vector store. Vector-backed memory is a separate concern; its absence degrades recall, not verification. |
| Everything else | DEGRADE | Recall drops; the reduction must be recorded, not silent. |

### 4.3 Redis (cache, event bus)

Cache. Absence costs latency and history, never correctness.

| Op class | Verdict | Reason |
|---|---|---|
| Governed write | DEGRADE | The idempotency claim is in-process, not Redis-backed, so the atomicity guarantee does not depend on Redis. |
| Reporting | DEGRADE | Events are lost. |
| Reads | CONTINUE | Cache miss is the normal path. |

### 4.4 Temporal

The orchestrator itself. This row is where WAIT and ESCALATE earn their place.

| Op class | Verdict | Reason |
|---|---|---|
| Governed write without a live workflow | **ESCALATE** | A write whose approval signal and retry semantics depend on Temporal cannot be executed unattended. Human engagement is required. |
| Approval gate | ESCALATE | Approval arrives as a Temporal signal (`ingress.py:146`). Without Temporal the signal cannot arrive. |
| Workflow scheduling | WAIT | Bounded wait; the readiness probe reports not-ready rather than failing liveness (`apps/core/internal/api/handlers.go:375-455`; `src/worker.py:383-391`). |
| Read/query | WAIT | Wait for the query path; do not fabricate a result. |
| Reporting | CONTINUE | Reporting does not require the orchestrator. |

**Deliberate design:** liveness (`/health`) performs **no** dependency checks.
A liveness probe that fails when Temporal is down causes the orchestrator to
restart the entire fleet during a dependency outage, turning a recoverable
degradation into a cascading outage (`apps/core/internal/api/handlers.go:355-360`).

### 4.5 Object storage

| Op class | Verdict | Reason |
|---|---|---|
| Governed write of a pointer/reference | DEGRADE | The record is written; the artefact is not. The missing artefact does not change whether the record was authorised. |
| Read-back of an artefact-backed write | DEGRADE | Without the artefact the expected state cannot be confirmed → `INDETERMINATE`. |
| Reads of non-artefact data | CONTINUE | |

### 4.6 Redpanda

Reported by readiness but **not required** —
`apps/core/internal/api/handlers.go:383`:
`required = map[string]bool{"postgres": true, "temporal": true, "redpanda": false}`.

The HTTP API and the Temporal workflow path remain usable without an event bus.

| Op class | Verdict | Reason |
|---|---|---|
| Governed write | DEGRADE | The side effect completes; downstream propagation does not. The idempotency claim, not the broker, enforces at-most-once. |
| Reads | CONTINUE | |
| Reporting | DEGRADE | Events queued locally or dropped. |

---

## 5. Error classification

Implemented in `src/mission/capability_ops_vendor.py:72-88`:

| Class | Meaning | Retried? |
|---|---|---|
| `VendorOpError` | Base | no |
| `VendorRetryableError` | Transient — 500, 429, timeout, connection refused | yes, bounded |
| `VendorTerminalError` | Validation / not-found / auth | **never** |

`VendorTerminalError` docstring at `:87-88` states: "Terminal failure
(validation/not-found/auth class): never retried."

Tests: `tests/test_failure_injection.py` —
`TestVendorHTTP500`, `TestVendorHTTP429`, `TestVendorTimeout`,
`TestVendorInvalidPayload`, `TestVendorConnectionRefused`.

Hard retry cap: **3 attempts**, then raise and log. No unbounded retries.

---

## 6. Event-level degradation

`tests/test_failure_injection.py` — the system must continue past bad input:

| Input | Behaviour | Test |
|---|---|---|
| Duplicate event | blocked | `TestDuplicateEvent::test_seen_set_blocks_duplicate` |
| Unique event | allowed | `::test_seen_set_allows_unique` |
| Out-of-order (resolution before detection) | normalised | `TestOutOfOrderEvent::test_resolution_before_detection_normalized` |
| Malformed payload ref | rejected | `TestMalformedEvent` |
| Unknown event type | normalised to `unknown`, system continues | `TestUnknownEventType::test_system_continues_after_unknown` |

---

## 7. Retry safety

A retry is only safe if the operation is idempotent **and** the retry cannot
observe a different authority context.

| Property | Where |
|---|---|
| Claims are released on every non-execute path, so a retry is permitted | `ingress.py:136-167` |
| On unknown outcome the claim is **released, not committed** | `ingress.py:170-176` — a committed key can never run again, and an unknown outcome must be verified before any retry |
| `COMMITTED` is terminal | `idempotency.py:165`, `:195-205` |
| A claim that outlives its lease is reclaimable | `idempotency.py:143-145` |

---

## 8. Matrix items that are UNVERIFIED

No committed test exercises the matrix against a genuinely-down dependency for
every cell. What exists:

| Evidence | Scope |
|---|---|
| `tests/test_failure_injection.py` | Vendor HTTP error classes via doubles — proves the classification, not a real outage |
| Readiness 200 → 503 → 200 observed live with Temporal stopped | One cell of §4.4, observed not committed |
| `src/worker.py:383-391`, `handlers.go:375-455` | The probe implementation is verified; the downstream per-cell behaviour is not |

**A mock proves a contract, not production integration.** Treat §3 as the
specified behaviour, and treat every cell without a committed test as
UNVERIFIED.
