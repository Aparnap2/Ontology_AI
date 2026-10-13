# Control Plane Checklist — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

Every row states the check, the implementation site, the test, and whether the
test is currently passing. **VERIFIED** means executed and green. Anything else is
labelled honestly.

---

## 1. Request path — what must happen, in order

Implemented at `src/control_plane/ingress.py:55-193`.

| # | Step | Implementation | Test | Status |
|---|---|---|---|---|
| 1 | Identity derived from trusted state only | `authorization.py:99-110` — `_require(trusted_context, ...)` | `test_p0_authorization_boundary.py` | VERIFIED (9) |
| 2 | Operation inside trusted allowlist | `authorization.py:53-70` | same | VERIFIED |
| 3 | Empty/absent allowlist denies | `authorization.py:62-66` | `TestEmptyAllowlistFailsClosed` | VERIFIED |
| 4 | Risk tier from trusted state | `policy.py:33-38`, `:48` | `test_p0_policy_trust_boundary.py` | VERIFIED (13) |
| 5 | Intent-supplied `risk_tier` ignored at any value | `policy.py:41-48` | `TestIntentSuppliedRiskTierIgnored` | VERIFIED |
| 6 | Stale version gate | `ingress.py:96-103`, `:128-134` | `test_adversarial/test_concurrency.py` | VERIFIED |
| 7 | CRITICAL block before execution | `ingress.py:105-110` — `is_blocked` | `test_p0_policy_trust_boundary.py::TestComposedEscalationBlocked` | VERIFIED |
| 8 | **Atomic** idempotency claim | `ingress.py:112-122`, `idempotency.py:112-153` | `test_p0_idempotency_atomicity.py` | VERIFIED (23) |
| 9 | Payload-hash conflict detection | `idempotency.py:135-140`, `ingress.py:119-123` | `TestPayloadConflict` | VERIFIED |
| 10 | Lease recovery for a dead holder | `idempotency.py:143-145`, `:192-206` | `TestLeaseRecovery` | VERIFIED — **in-process only, see `PERSISTENCE_BOUNDARY.md`** |
| 11 | Approval gate releases the claim on every non-execute path | `ingress.py:136-167` | `test_p0_idempotency_atomicity.py::TestOwnership` | VERIFIED |
| 12 | Executor runs under the *same* allowlist authorize validated | `ingress.py:93-95` | `test_p0_authorization_boundary.py::test_capability_allowlist_also_enforced` | VERIFIED |
| 13 | Read-back verification under the same authority | `step_runners.py:172-194` | `test_p0_verify_readback_authority.py` | VERIFIED (9) |
| 14 | Claim committed only after verification | `ingress.py:190` | `test_p0_idempotency_atomicity.py` | VERIFIED |
| 15 | Claim **released** (not committed) on unknown outcome | `ingress.py:170-176` | `TestOwnership` | VERIFIED |

---

## 2. Fail-closed checklist

The single question for each row: *if the input is absent, empty, malformed, or
attacker-controlled, what happens?*

| Input condition | Behaviour | Implementation |
|---|---|---|
| `role_caps is None` | DENY | `capability_ops.py:426-428` |
| `role_caps == []` | DENY | `capability_ops.py:429-432` |
| op not in `role_caps` | DENY | `capability_ops.py:433-436` |
| authorization allowlist empty | DENY (`PermissionError`) | `authorization.py:62-66` |
| op not in authorization allowlist | DENY (`PermissionError`) | `authorization.py:67-70` |
| missing `tenant_id`/`mission_id`/`employee_id`/`actor_identity` | DENY (`KeyError`) | `authorization.py:21-26` |
| no trusted risk source | `DEFAULT_RISK_TIER = "MEDIUM"` | `policy.py:30`, `:38` |
| `expected == {}` at verification | `INDETERMINATE` | `verify.py:142-149` |
| read-back denied by allowlist | `INDETERMINATE` + `read_back_not_permitted` | `verify.py:198-211` |
| no read counterpart for the op | `verified=False` + rollback metadata | `verify.py:133-141` |
| `recovery.verified is not True` | `resolution_refused`, never `RESOLVED` | `incident_activities.py:408-420` |
| no recovery predicates | `verified=False`, `mismatches=["no_predicates"]` | `recovery_verification.py:58` |
| ROI evidence refs empty on either side | `evidenced=False` | `roi_measurement.py:133` |
| same key, different payload | `IdempotencyConflictError` → deny | `idempotency.py:135-140` |
| non-claim owner calls commit/release | `PermissionError` | `idempotency.py:232-241` |
| claim held for a key that does not exist | `KeyError` | `idempotency.py:235` |

**No row in this table has an "allow" branch.**

---

## 3. Audit checklist

| # | Requirement | Implementation | Status |
|---|---|---|---|
| 3.1 | Every decision emits an event | `ingress.py:75-192` — every return path calls `append_event` | VERIFIED |
| 3.2 | Denials are auditable, not silent | `ingress.py:69-88` | VERIFIED |
| 3.3 | A rejection emits **no** success event | `test_p0_composed_attack_regression.py` — mutation check fails 9/10 when the fix is reverted | VERIFIED |
| 3.4 | `verified` in the audit event comes from verification, not the executor | `ingress.py:191-192` | VERIFIED |
| 3.5 | The claim state transitions are observable | `idempotency.py:180-190` — `state_of`, `owner_of` | VERIFIED |
| 3.6 | **The audit log survives a restart** | `src/control_plane/audit.py:14` — `AUDIT_LOG: list[dict[str, Any]] = []`, a module-level list | **NO — process-local. See `PERSISTENCE_BOUNDARY.md`.** |

3.6 is the single most important row in this document. An in-process audit log
is a debugging aid, not an audit trail.

---

## 4. Honest-claim checklist

| # | Claim type | Rule | Enforced at |
|---|---|---|---|
| 4.1 | Execution success | Only after verification, never from the executor's return value | `ingress.py:181-192` |
| 4.2 | Verification state | `verified = (state == "VERIFIED")` and nothing else | `verify.py:61-67` |
| 4.3 | Verification basis | Labelled `caller_supplied` or `derived_from_write` | `verify.py:219-242` |
| 4.4 | Recovery | Needs independent observed evidence | `recovery_verification.py`, `incident_activities.py:408` |
| 4.5 | ROI | Needs `evidence_refs` on both the run and the baseline | `roi_measurement.py:133` |
| 4.6 | Capability provenance | `assemble` rejects cross-tenant evidence | `tests/adversarial/test_tenant_isolation.py::test_assemble_rejects_cross_tenant_evidence` — VERIFIED |

### 4.3 limitation, stated

`verify.py:88-104 derive_expected` derives expectations **from the write**. A
passing read-back proves transport fidelity only — "the fields I sent are the
fields that arrived" — never semantic correctness. The label exists
(`derived_from_write`); the limitation does not go away.

---

## 5. Worker registration checklist

| # | Requirement | Implementation | Test | Status |
|---|---|---|---|---|
| 5.1 | Every registered workflow satisfies `_Definition.must_from_class` | `worker.py:206-217` | `test_p0_worker_startup.py::TestWorkerIsCapable` | VERIFIED |
| 5.2 | Every activity is a coroutine | `worker.py:_build_activity_list` | `::TestProductionWorkerConstructs` | VERIFIED |
| 5.3 | One registration path across entrypoints | — | `::TestSingleRegistrationPath` | VERIFIED |
| 5.4 | Canonical task queue | `src/orchestration/queue.py:25-38` | `::TestCanonicalTaskQueue` | VERIFIED |
| 5.5 | Main modes still reachable | — | `::TestMainModesStillAvailable` | VERIFIED |
| 5.6 | The worker actually polls the queue in a real runtime | `worker.py:325` `Client.connect(TEMPORAL_HOST)` | none committed — observed live | **UNVERIFIED** |

Total: 17 tests in `test_p0_worker_startup.py`, all passing.

---

## 6. Deployment checklist

| # | Requirement | Implementation | Status |
|---|---|---|---|
| 6.1 | Every artifact names an entrypoint that exists | `apps/core/cmd/{server,worker,consumer,main.go}` | VERIFIED — no `cmd/demo` reference outside the guard test itself |
| 6.2 | `LISTEN_ADDR` is the single port source | `apps/core/cmd/server/main.go:44-49,66` | VERIFIED |
| 6.3 | `/health` performs no dependency call | `apps/core/internal/api/handlers.go:362-367` | VERIFIED |
| 6.4 | `/health/ready` returns 503 when Postgres or Temporal is down | `handlers.go:375-455` | VERIFIED — observed live 200 → 503 → 200 |
| 6.5 | Migrations applied by the deploy path | `apps/core/cmd/migrate/main.go` | VERIFIED (runner exists and is referenced) |
| 6.6 | **A fresh-database bootstrap completes** | see below | **NO — KNOWN GAP** |
| 6.7 | Clean clone builds Go | `gen/go/go.mod`, `gen/go/go.sum` tracked | VERIFIED |

### 6.6 — the migration gap

`cmd/migrate/main.go:142-145` states the problem in the runner's own comment:

- `internal/db/migrations/001_sarthi_sop_runtime.sql:10` creates `raw_events`
  with `founder_id`
- `internal/db/migrations/002_sarthi_v1.sql:20` creates `raw_events` with
  `tenant_id`

Both use `CREATE TABLE IF NOT EXISTS`, so the second is **silently skipped** —
the table keeps `founder_id` and every later query written against `tenant_id`
fails at runtime rather than at migration time. Verified by reading both files;
`002` contains zero `ALTER TABLE` statements, so it cannot reconcile the
difference.

The runner sorts by numeric prefix across both directories
(`cmd/migrate/main.go:177-182`), which is the fix for the *ordering* half of the
problem — `003_saarathi_pivot` is correctly applied after `002_sarthi_v1`. The
*column-shape* half is unresolved. The Python side has no migration mechanism at
all; `apps/core/cmd/migrate` covers Go only.

---

## 7. Sign-off

The control plane is sound **within a single process lifetime**.

It is **not** restart-safe: audit, idempotency, and version state are all
process-local. See `PERSISTENCE_BOUNDARY.md` for the full table and the cost of
each restart.
