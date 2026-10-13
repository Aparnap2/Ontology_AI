# Observability Checklist — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

What must be observable for an operator to answer "what happened, who authorised
it, and what was the outcome" without reading application logs.

---

## 1. Health probes

| Probe | Contract | Implementation | Dependency calls? |
|---|---|---|---|
| `/health` | Liveness — "is this process running?" | `apps/core/internal/api/handlers.go:362-367` | **none, by design** |
| `/health/ready` | Readiness — "can this serve traffic?" | `handlers.go:375-455` | Postgres, Temporal (required); Redpanda (reported) |
| Python worker `/health` | Liveness, always 200 | `src/worker.py:379-380` | none |
| Python worker `/health/ready` | 503 until the worker starts; then 200 with the registry | `src/worker.py:383-391` | none — reports a local `asyncio.Event` |

**Why liveness has no dependency checks** (`handlers.go:355-360`): a liveness
probe that fails when Postgres or Temporal is down causes the orchestrator to
restart the entire fleet during a dependency outage, turning a recoverable
degradation into a cascading outage.

**Requiredness map** (`handlers.go:383`):
`required = {"postgres": true, "temporal": true, "redpanda": false}`.
Redpanda is reported but not required — the HTTP API and the Temporal workflow
path remain usable without an event bus.

Observed live: readiness 200 → 503 (Temporal stopped) → 200, liveness 200
throughout.

---

## 2. Worker registry reporting

`src/worker.py:352-364 _registry_report()` returns:

```json
{
  "task_queue": "ONTOLOGYAI-MAIN-QUEUE",
  "workflows": ["...", "..."],
  "activities": ["...", "..."]
}
```

This is the registry Temporal **actually accepted** at construction time — not an
intended list. That distinction is the point: before the fix, five registered
"workflows" were plain classes and the worker was unconstructable, so nothing
polled at all.

Canonical queue resolution — `src/orchestration/queue.py:25-38`:
`TEMPORAL_TASK_QUEUE` → `ONTOLOGYAI-MAIN-QUEUE`. Pinned by
`tests/test_p0_worker_startup.py::TestCanonicalTaskQueue`.

---

## 3. Audit events

`src/control_plane/audit.py:17-46`. Every decision emits an event.

| Field | Meaning |
|---|---|
| `mission_id`, `action_id` | correlation |
| `intent` | the proposal (untrusted — preserved as a **claim**, never as authority) |
| `decision` | `permit:executed`, `deny:unauthorized:...`, `deny:blocked`, `deny:duplicate`, `deny:idempotency_key_conflict`, `deny:stale_version`, `deny:stale_context`, `deny:approval_expired`, `deny:approval_rejected`, `deny:invalid_trusted_context:...`, `require_approval:no_handler` |
| `result` | executor output, where applicable |
| `verified` | from `verify_execution`, never from the executor return |

Every `return` in `src/control_plane/ingress.py:75-193` calls `append_event`.

**Critical limitation.** `audit.py:14` is
`AUDIT_LOG: list[dict[str, Any]] = []` — a module-level list in the process
address space. A restart erases it. This is a debugging aid, not an audit trail.
See `PERSISTENCE_BOUNDARY.md`.

---

## 4. Tracing

| Surface | Implementation | Exported? |
|---|---|---|
| OpenTelemetry init / tracer | `src/services/tracing/__init__.py:25` `init_tracing`, `:85` `get_tracer` | Yes — OTLP endpoint from `get_otlp_endpoint()` (`:13`) |
| In-process execution trace | `src/mission/observability.py:47` `ExecutionTrace` | No — spans held in memory (`start_span` `:58`, `to_timeline` `:95`) |
| LLM call record | `src/mission/observability.py:34` `LLMCallRecord`, `:100` `llm_call_record` | No |

`ExecutionTrace` is an in-memory structure. It is useful within a request and
gone after it.

---

## 5. Cost and latency

`src/mission/cost_latency.py:68` `CostLatencyTracker`.

| Property | Value |
|---|---|
| Backing | `self._missions: dict[str, MissionMetrics] = {}` (`:82`) — **in-memory, instance-local** |
| Pricing | `MODEL_PRICING` (`:73-78`); unknown models fall back to `_DEFAULT_MODEL = "gpt-4o"` (`:80`) |
| Persistence | none |

Cost figures do not survive a restart and are not visible outside the process.

---

## 6. Operator checklist

To answer a question end to end, the operator needs each row below. The
**Status** column is the honest answer today.

| # | Question | Required signal | Status |
|---|---|---|---|
| 6.1 | Is the process up? | `/health` 200 | VERIFIED — `handlers.go:362-367` |
| 6.2 | Can it serve traffic? | `/health/ready` + per-dependency checks + latency_ms | VERIFIED — `handlers.go:375-455` |
| 6.3 | What did the worker actually register? | `/health/ready` registry payload | VERIFIED — `worker.py:353-391` |
| 6.4 | Which task queue is being polled? | `task_queue` in the registry payload | VERIFIED — `queue.py:25-38` |
| 6.5 | What did a submission decide, and why? | audit `decision` | VERIFIED in-process; **not durable** |
| 6.6 | Was the action executed? | `permit:executed` + `result` | VERIFIED |
| 6.7 | Was the execution verified? | `verified` + `rollback_metadata` | VERIFIED |
| 6.8 | Were expectations supplied or derived? | `expectation_source` | VERIFIED — `verify.py:219-242` |
| 6.9 | Is an at-most-once claim outstanding? | `SeenSet.state_of` / `owner_of` | VERIFIED in-process; **not durable** |
| 6.10 | What is the current version of a contested target? | `VersionStore.current` | VERIFIED in-process; **not durable** |
| 6.11 | How long did the workflow take, where did it stall? | OTel spans exported via OTLP | PARTIAL — `get_tracer` exists (`:85`); no committed test proves spans reach a collector |
| 6.12 | What did the mission cost? | `CostLatencyTracker` | PARTIAL — computed in-memory; not durable, not exported |
| 6.13 | What happened **before a restart**? | durable audit | **NO — process-local** |
| 6.14 | What is the state of a mission after a restart? | durable store | **NO — process-local** |

---

## 7. Alerts the system can raise today

| Alert | Source |
|---|---|
| Burn alert / severity | `src/session/mission_state.py:104+` fields `burn_alert`, `burn_severity` |
| Watchlist alerts | `tests/deterministic/test_trajectory_verification.py:191` `TestWatchlistAlerts` |
| Self-guardian alerts | `apps/core/internal/db/migrations/006_self_guardian_alerts.sql` |
| Approval queue backlog | `src/control_plane/approval.py`; UI partial `command_approvals.html` |
| Worker not ready | `/health/ready` 503 — `src/worker.py:383-391` |
| Dependency down | `/health/ready` 503 with `checks` populated — `handlers.go:445-455` |

---

## 8. Known observability gaps

| Gap | Detail |
|---|---|
| **Nothing is durable** | 6.13 and 6.14. `audit.py:14`, `idempotency.py:269`, `concurrency.py:40`, `cost_latency.py:83` are all process-local. A restart erases the audit trail, the idempotency records, the version state and the metrics. |
| **No committed test proves OTel export** | `get_tracer` returns `Optional[object]` (`tracing/__init__.py:85`) — it may return `None`. No test asserts spans reach a collector. UNVERIFIED. |
| **No tracing across the control plane** | `ExecutionTrace` is a separate in-memory structure (`observability.py:47`) from the OTel path. They are not linked by a committed test. |
| **Read-back semantics not surfaced in logs** | `expectation_source` lives on the `VerifyOutcome` (`verify.py:57-59`). Whether it reaches an operator-facing log or only an in-memory object is UNVERIFIED. |
| **Connectivity, not security, is what `/health/ready` reports** | It answers "can I serve traffic", not "is my authority intact". No probe reports the size or integrity of the audit log or the idempotency store. |
