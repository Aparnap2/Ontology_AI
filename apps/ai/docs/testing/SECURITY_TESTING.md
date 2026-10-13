# Security Testing — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05` · base `18f73f1`

Nine security invariants are proven by executable tests. Each had a RED test
written first. Test counts are measured by `pytest --collect-only` and confirmed
by a full passing run.

---

## 1. The invariant table

| # | Invariant | Implementation | Test | Count | Status |
|---|---|---|---|---|---|
| 1 | Authorization denies by default; absent **or** empty allowlist denies; operation must be in the trusted allowlist | `src/control_plane/authorization.py:53-70` | `tests/test_p0_authorization_boundary.py` | 9 | VERIFIED |
| 2 | Policy reads risk from TRUSTED state only; an intent-supplied `risk_tier` inside `requested_parameters` is ignored whatever its value | `src/control_plane/policy.py:33-53` | `tests/test_p0_policy_trust_boundary.py` | 13 | VERIFIED |
| 3 | Capability registry denies when `role_caps` is None or empty | `src/mission/capability_ops.py:418-437` | `tests/test_p0_capability_allowlist.py` | 8 | VERIFIED |
| 4 | Idempotency is an **atomic claim**, not check-then-act | `src/control_plane/idempotency.py:112-176` | `tests/test_p0_idempotency_atomicity.py` + `test_p0_idempotency_concurrency_e2e.py` | 23 + 5 | VERIFIED in-process |
| 5 | Composed attack is rejected end to end; no write, no success audit event | the three files above | `tests/test_p0_composed_attack_regression.py` | 10 | VERIFIED |
| 6 | Read-back runs under the same authority as the write; a denied read-back is `INDETERMINATE` with `read_back_not_permitted` | `src/mission/verify.py:198-211`, `src/mission/step_runners.py:172-194` | `tests/test_p0_verify_readback_authority.py` | 9 | VERIFIED |
| 7 | No misleading verification or recovery claims | `src/mission/recovery_verification.py`, `src/activities/incident_activities.py:408`, `src/mission/roi_measurement.py:133`, `src/mission/verify.py:219-242` | `tests/test_p0_no_misleading_claims.py` | 18 | VERIFIED |
| 8 | Worker startup contract: every workflow satisfies `must_from_class`, every activity is a coroutine | `src/worker.py:206-217` | `tests/test_p0_worker_startup.py` | 17 | VERIFIED |
| 9 | Deployment contract: no nonexistent `cmd/demo`, single port source, real health/readiness, migrations via `cmd/migrate` | `apps/core/cmd/server/main.go:44-66`, `apps/core/internal/api/handlers.go:355-455` | `tests/test_p0_deployment_contract.py` | 14 | VERIFIED |

Supporting: `tests/test_p0_clean_clone_build.py` (6),
`tests/test_p0_no_llm_in_security_suite.py` (7),
`tests/test_p0_control_plane_result.py` (6).

**Measured total: 145 P0 tests, 145 passing**, run with all LLM credentials
unset. All 9 security invariants above are VERIFIED.

---

## 2. Invariant detail

### 2.1 Authorization fails closed

`src/control_plane/authorization.py:62-66` raises `PermissionError` when the
allowlist is empty. `:67-70` raises when the operation is not a member. The
allowlist is built at `:44-50` from `role_config.capabilities` +
`role_config.permissions` (or the trusted context fallback) — never from the
intent.

Tests: `TestUnauthorizedOperationRejected`,
`test_unauthorized_op_does_not_reach_executor`,
`test_capability_allowlist_also_enforced`,
`TestEmptyAllowlistFailsClosed::test_absent_permissions_rejects`,
`::test_empty_permissions_rejects`.

### 2.2 Policy reads trusted state only

`src/control_plane/policy.py:41-48` builds the policy input from
`_trusted_risk_tier()` alone. `intent.requested_parameters` is **structurally
absent** from the dict — there is no code path by which it can be read.

Before the fix this allowed a prompt-injected planner to set
`requested_parameters["risk_tier"] = "LOW"` and bypass both the approval gate
and the CRITICAL execution block (documented at `policy.py:7-12`).

Tests: `TestIntentSuppliedRiskTierIgnored`,
`TestTrustedTiersStillGovern`, `TestComposedEscalationBlocked`.

### 2.3 Capability registry denies on absence

`src/mission/capability_ops.py:426-428` (`None`) and `:429-432` (`[]`) both
raise `CapabilityNotAllowedError`. The docstring at `:419-424` records why:
treating an absent allowlist as "unrestricted" silently disabled the last line of
defence.

Tests: `TestMissingAllowlistFailsClosed`,
`TestExplicitAllowlistStillWorks`.

### 2.4 Idempotency is atomic

**Measured before the fix:** 4 concurrent submissions of one key = **4 side
effects**. Recorded at `src/control_plane/idempotency.py:12-16`.

**After:** exactly 1 execution at n = 2, 4, 10, 100.

Protocol (`idempotency.py:112-176`):

```
CLAIM(key) --+-- already claimed --> DUPLICATE
             +-- claimed          --> EXECUTE
                                          +-- success --> COMMIT
                                          +-- failure --> RELEASE
```

- **Owner token** — `commit`/`release` accept only the holder's token
  (`idempotency.py:232-241`); a stale worker cannot free or complete another's
  claim.
- **Lease** — a PENDING claim is reclaimable after `DEFAULT_LEASE_SECONDS = 300.0`
  (`idempotency.py:62`, `:143-145`), so a worker that dies mid-execution cannot
  wedge the key forever.
- **Payload-hash conflict detection** — the same key with a different payload
  raises `IdempotencyConflictError` (`:135-140`) rather than silently collapsing
  into a duplicate.
- `COMMITTED` is terminal and never released by a lease sweep (`:165`, `:195-205`).

Tests: `TestAtomicClaim`, `TestOwnership`, `TestPayloadConflict`,
`TestLeaseRecovery`, `TestLegacyApiPreserved`,
`test_at_most_one_execution_under_concurrency[2|4|10|100]`,
`test_different_missions_execute_independently`.

**Scope limit:** this is an in-process `threading.Lock` (`idempotency.py:107`).
It holds within one process. It does not hold across a restart. See
`PERSISTENCE_BOUNDARY.md`.

### 2.5 Composed attack regression

The full chain (`tests/test_p0_composed_attack_regression.py:11-19`):

```
prompt injection
  -> model supplies risk_tier = "LOW" in requested_parameters
  -> model requests an operation outside the principal's allowlist
  -> attempts control-plane submission
  -> MUST REJECT, MUST NOT execute, MUST NOT emit a success audit event
```

**Mutation check:** reverting `authorization.py`, `policy.py` and
`idempotency.py` to pre-fix code makes **9 of 10** tests fail, including
"no capability write occurred" and "no success audit event emitted".

This is the load-bearing evidence in the branch: it demonstrates the test
detects the vulnerability, rather than merely passing.

### 2.6 Read-back runs under the write's authority

`src/mission/step_runners.py:182-189` passes
`role_caps=list(state.role.capabilities or []) or None` into `verify_write`.
Previously `role_caps` was omitted entirely and the registry treated an absent
allowlist as unrestricted — verification ran with no authority at all.

`src/mission/verify.py:198-211` now distinguishes an authorization failure from
a data mismatch: `CapabilityNotAllowedError`, `PermissionError`, or an
"allowlist" substring produce `INDETERMINATE` with
`reason: "read_back_not_permitted"`. Never `VERIFIED`, never a bare mismatch.

Tests: `TestReadCounterpartExists`, `TestRoleCanVerifyItsOwnWrite`,
`TestVerificationDistinguishesDeniedFromMismatched`.

### 2.7 No misleading claims

| Claim | Guard | Location |
|---|---|---|
| Recovery requires independent observed evidence | `recovery.verified` derived from predicates, not assertion | `recovery_verification.py:58,80` |
| `resolve_situation` refuses RESOLVED without verified recovery | `recovery.get("verified") is not True` → `resolution_refused` | `incident_activities.py:408-420` |
| Derived expectations are labelled | `expectation_source="derived_from_write"` | `verify.py:57-59`, `:219-242` |
| ROI savings carry provenance | `evidenced` + `evidence_refs` on both sides | `roi_measurement.py:63-65`, `:133` |
| A rejection is not a success | every deny path returns `decision="deny:...", verified=False` | `ingress.py:69-192` |
| Exceptions are not swallowed | claim released, error re-raised | `ingress.py:170-176` |

Tests: `tests/test_p0_no_misleading_claims.py` (18) and
`tests/test_p0_control_plane_result.py` (6).

### 2.8 Worker startup contract

Temporal's `Worker` calls `_Definition.must_from_class` on every registered
entry and raises `ValueError: missing attributes, was it decorated with
@workflow.defn?` otherwise. **One undecorated class makes the whole worker
unconstructable and the process never polls its queue.**

This contract caught **5 "workflows"** that were plain classes:
`DiscoveryWorkflow`, `OntologyMappingWorkflow`, `KnowledgeValidationWorkflow`,
`SolutionArchitectWorkflow`, `GovernanceWorkflow`. Documented at
`src/worker.py:206-217`. Commits `322d909`, `10f7d72`.

It also caught `src/main.py` building its own worker registering exactly one
activity — a process advertising itself as a healthy Temporal worker while being
unable to execute a single V7 incident activity.

Tests: 17 in `tests/test_p0_worker_startup.py`.

### 2.9 Deployment contract

| Sub-invariant | Implementation | Test |
|---|---|---|
| No `cmd/demo` reference (the directory does not exist) | real entrypoints are `cmd/server`, `cmd/worker`, `cmd/consumer` | `TestEntrypointExists` |
| `LISTEN_ADDR` is the single port source | `apps/core/cmd/server/main.go:44-49,66` | `TestPortConfiguration` |
| `/health` is liveness, no dependency calls | `handlers.go:362-367` | `TestHealthSemantics` |
| `/health/ready` checks Postgres + Temporal, returns 503 | `handlers.go:375-455` | `TestHealthSemantics` |
| Migrations run via `apps/core/cmd/migrate` | `cmd/migrate/main.go` | `TestMigrationsAreApplied` |
| Python worker health endpoint is real | `src/worker.py:349-402` | `TestPythonWorkerHealth` |

Observed live: readiness went 200 → 503 (Temporal stopped) → 200, with liveness
staying 200 throughout. That is an observation, not a committed test.

---

## 3. LLM isolation as a security control

| Property | Evidence |
|---|---|
| The deterministic gate runs with no credentials | 145 P0 tests pass under `env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT` |
| Any attempt to reach a provider raises | `tests/test_p0_no_llm_in_security_suite.py` patches `src.config.llm` attributes (`:29-37`) and direct SDK construction |
| The guard uses the production boundary, not the vendor SDK | test docstring `:15-19` — survives provider changes |

A boundary that can only be tested when an API key is valid is not a boundary.

---

## 4. Security-relevant code NOT covered by any test

| Item | Location | Status |
|---|---|---|
| Agent/session modules read `DATABASE_URL` and issue raw SQL | `src/agents/bi/nodes.py:679,683`, `src/session/mission_state.py:104,170`, `src/session/context.py:53,104` | **KNOWN GAP** — the "agent never holds DB credentials or issues arbitrary SQL" boundary is documented prose only, **not enforced by any test** |
| `CapabilityOpRegistry._ops` is a process-local class attribute | `src/mission/capability_ops.py:388` | **KNOWN GAP** — the capability registry is process-local |
| Executor does not match the *target resource's* tenant | `tests/adversarial/test_tenant_isolation.py:132` `test_executor_target_tenant_gap_pinned_for_sprint_f` | **KNOWN GAP** — the test pins the behaviour deliberately so it cannot be silently "fixed"; a `t-acme` intent targeting a foreign record still executes |
| Temporal durability (delivery, persistence, retry, restart) | — | **UNVERIFIED** — no real-worker test exists; see `TESTING_STRATEGY.md` §4 |
| Audit / idempotency / version state across a restart | `audit.py:14`, `idempotency.py:269`, `concurrency.py:40` | **NOT restart-safe** — see `PERSISTENCE_BOUNDARY.md` |
| Fresh-database migration bootstrap completes | `internal/db/migrations/001_sarthi_sop_runtime.sql:10` vs `002_sarthi_v1.sql:20` | **KNOWN GAP** — `CREATE TABLE IF NOT EXISTS` silently keeps `founder_id` where `002` expects `tenant_id` |

---

## 5. Running the security gate

```bash
cd apps/ai
env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT \
  .venv/bin/python -m pytest -q -m "not llm" tests/test_p0_*.py
```

Expected at `cd7fe05`: **145 passed**.
