# E2E Test Plan — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

What an end-to-end proof must cover, and what is covered today. The governing
constraint is in `TESTING_STRATEGY.md` §4: a mock-environment test does not
establish production durability.

---

## 1. E2E tiers

| Tier | Environment | Real services | Marker | Status |
|---|---|---|---|---|
| **T1 — Deterministic path** | in-process | none | none | 145 P0 tests, all passing |
| **T2 — Container integration** | Docker | Postgres, Temporal, Qdrant | `integration` | exists; see §4 |
| **T3 — Real worker** | Docker | Temporal + real worker process | `e2e` | **UNVERIFIED** — no committed real-worker durability test |
| **T4 — Live model** | + provider credentials | + live LLM | `llm` | excluded from the gate by design |

The release gate is **T1**. T2–T4 are corroborating evidence, never a substitute
for T1.

---

## 2. The canonical happy path

The path a founder actually walks. Every step must be traceable end to end.

| # | Step | System component | Deterministic proof today |
|---|---|---|---|
| 1 | Onboarding intake | `src/session/` | `test_p0_*` trusted-context construction |
| 2 | MissionState established | `src/session/mission_state.py` | session tests (no P0 coverage of the DB write path) |
| 3 | Agent proposes an action | `src/control_plane/contracts.py` `ActionIntent` | `test_p0_composed_attack_regression.py` |
| 4 | **Authorisation** against trusted state | `authorization.py:53-70` | `test_p0_authorization_boundary.py` (9) |
| 5 | **Risk classification** from trusted state | `policy.py:33-53` | `test_p0_policy_trust_boundary.py` (13) |
| 6 | Atomic claim | `idempotency.py:112-176` | 23 + 5 |
| 7 | Approval gate (HIGH/CRITICAL) | `ingress.py:136-167` | `tests/adversarial/test_approval_failure.py` — **5 failing, Category D** |
| 8 | Governed write via capability registry | `capability_ops.py:437-450` | `test_p0_capability_allowlist.py` (8) |
| 9 | **Read-back verification** under the same authority | `verify.py:116-215`, `step_runners.py:172-194` | `test_p0_verify_readback_authority.py` (9) |
| 10 | Commit claim; emit audit event | `ingress.py:190-193` | `test_p0_no_misleading_claims.py` (18) |
| 11 | Recovery + resolution | `incident_activities.py:396-427` | `test_p0_no_misleading_claims.py` |
| 12 | ROI with provenance | `roi_measurement.py:86-134` | `test_p0_no_misleading_claims.py` |

**Step 7 is the one gap.** The approval-gate E2E currently fails because
`_high_intent()` sets `risk_tier` inside `requested_parameters`
(`tests/adversarial/test_approval_failure.py:72`), which `policy.py:41-48` now
correctly ignores. The tests encode the pre-fix contract. Closing this requires a
test that derives HIGH from `role_config.risk_threshold` — trusted state. That
test does not exist.

---

## 3. Required T3 coverage — all currently UNVERIFIED

Per `TESTING_STRATEGY.md` §4, a production durability claim needs at least one
real-worker test covering all five.

| # | Requirement | Why it cannot be mocked | Status |
|---|---|---|---|
| 3.1 | **Task-queue delivery** on `ONTOLOGYAI-MAIN-QUEUE` | The in-memory test environment never delivers a queue message | **UNVERIFIED.** Live observation: the worker polls the canonical queue and reports its registry on `/health/ready` (`src/worker.py:383-391`). Not committed. |
| 3.2 | **Workflow continuation** | Mock env executes synchronously in-process | **UNVERIFIED** |
| 3.3 | **State persistence across Continue-As-New** | The mock does not persist workflow state | **UNVERIFIED — and blocked.** `TestContinueAsNewAt5000Events` hangs: `env.ExecuteWorkflow(...)` at `apps/core/internal/workflow/business_os_workflow_test.go:79` blocks, so all 5001 signals sent at `:82-94` are discarded and the guard is never reached (`activity invocations: 0`). Category D, issue **#68**. |
| 3.4 | **Retry behaviour** | The mock has no retry policy | **UNVERIFIED** |
| 3.5 | **Restart / recovery** | The mock has no process lifecycle | **UNVERIFIED** — and materially blocked by process-local state. See §6. |

### The Continue-As-New guard, precisely

Issue #69 additionally records that `BusinessOSWorkflow` spawns every child with
a `WorkflowID` derived only from event type and tenant, onto a task queue
(`AI_TASK_QUEUE`) that is not the canonical queue — so two same-type events for
one tenant request the **same child WorkflowID**, and nothing in the Go test
suite services that queue.

The guard logic itself was verified working at a lowered threshold with correct
signal delivery. That is a code-level check, not a durability proof.

---

## 4. Container integration — what exists

| File | Scope | Marker |
|---|---|---|
| `tests/integration/test_mission_live_infra.py` | live infra against the worker container (Postgres on localhost:5433 by default) | — |
| `tests/integration/test_session_context.py` | session + context against real Postgres | — |
| `tests/integration/test_mission_state.py` | MissionState persistence | — |
| `tests/integration/test_mockoon_pipeline.py`, `test_mockoon_endpoints.py` | connector pipeline against Mockoon | — |
| `tests/integration/test_slackbot_wiring.py` | Slack wiring | — |
| `tests/integration/test_startup_guardian_e2e.py` | startup guardian | — |
| `tests/integration/hardening/test_pipeline_e2e.py` | connector event → timeline trace-id; duplicate correlation-id handling | `llm` on the whole module (`:55`) |
| `tests/e2e/conftest.py` | service connectivity checks for Postgres, Qdrant, Redpanda, Ollama, Temporal (`:267`) | — |
| `tests/e2e/test_strategic_pipeline.py` | strategic pipeline | — |

Orchestration files: `tests/docker-compose.test.yml`,
`tests/docker-compose.integration.yml`, `tests/Dockerfile.test`,
`tests/health_check.sh`.

**Constraint:** `tests/integration/hardening/test_pipeline_e2e.py` is marked
`llm` at module level, so the two most relevant hardening assertions
(`test_connector_event_to_timeline_carries_trace_id`,
`test_duplicate_correlation_id_does_not_duplicate_timeline`) are **excluded from
the deterministic gate**. They are deterministic in substance; the marker is
stricter than necessary.

---

## 5. E2E plan — work to close the gaps

Ordered by what unblocks the most claims.

| # | Work | Unblocks | Dependency |
|---|---|---|---|
| E1 | Rewrite the approval-gate E2E to derive HIGH from `role_config.risk_threshold` (trusted state) instead of `requested_parameters` | Step 7 of §2; closes the 5 Category D failures | none |
| E2 | Fix `TestContinueAsNewAt5000Events` — start the workflow, signal inside it (e.g. an activity that signals), so signals are actually delivered | 3.2, 3.3 | issue #68 |
| E3 | Give child workflows distinct IDs and route them to the canonical queue | unblocks any real-worker multi-workflow test | issue #69 |
| E4 | One real-worker test: start the worker, execute a workflow on `ONTOLOGYAI-MAIN-QUEUE`, assert delivery, continuation, and termination | 3.1, 3.2 | E2, E3 |
| E5 | One real-worker Continue-As-New test at a lowered threshold, asserting state carried across the boundary | 3.3 | E4 |
| E6 | One real-worker test: kill the worker mid-workflow, restart, assert retry and completion | 3.4, 3.5 | E4 |
| E7 | Un-mark the two hardening tests so they run under `-m "not llm"`, or split the module | brings connector→timeline assertions into the gate | none |
| E8 | Bound the hanging test with `-timeout` in CI so it fails rather than blocks | release hygiene | none |

---

## 6. What no E2E test can currently prove

Even with E1–E8 complete, the following remain unprovable until the persistence
boundary changes. This is not a testing gap — it is an architecture gap, and no
test can close it.

| Claim | Why no test can prove it today |
|---|---|
| At-most-once survives a restart | `idempotency.py:269` is a process singleton. A restart empties it. |
| The audit trail survives a restart | `audit.py:14` is a module-level list. |
| Optimistic-concurrency versions survive a restart | `concurrency.py:40` is a process singleton. |
| Cost/latency metrics survive a restart | `cost_latency.py:83` is an instance dict. |

Any E2E test that restarts the process and asserts at-most-once **will fail**,
because the guarantee genuinely does not hold. That is the correct result. See
`PERSISTENCE_BOUNDARY.md`.
