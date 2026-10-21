# Testing Standards — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

A reviewer can execute every item below. Every claim cites a file or a test id.

---

## 1. LLM isolation

| # | Standard | How to check | Result on this branch |
|---|---|---|---|
| 1.1 | Deterministic tests must not import or call a live provider | `pytest -m "not llm"` with all credentials unset | PASS — 145 P0 tests pass under `env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT` |
| 1.2 | The guard patches the production boundary, not the vendor SDK | `tests/test_p0_no_llm_in_security_suite.py:29-37` patches `src.config.llm` attributes | PASS (7 tests) |
| 1.3 | Suite classification is static, not credential-derived | `pyproject.toml:80-88` comment states this explicitly | PASS |
| 1.4 | Direct SDK construction is also blocked, since it bypasses the factory | `tests/test_p0_no_llm_in_security_suite.py:68+` | PASS |
| 1.5 | Every LLM-dependent suite declares `-m llm` | `pytestmark = pytest.mark.llm` in 6 files | PASS |

LLM-marked files (verified by grep):

```
tests/e2e/test_agentic_pipeline.py:35
tests/e2e/test_rag_evaluation.py:31
tests/test_agentic_capability.py:38
tests/integration/test_real_llm_integration.py:16
tests/integration/hardening/test_pipeline_e2e.py:55
tests/agentic/test_agentic_ai.py:45
```

---

## 2. Fix standard — RED before GREEN

| # | Standard | Evidence on this branch |
|---|---|---|
| 2.1 | Every P0 fix has a RED commit that precedes the fix commit | `63eb97e`→`6619d1a` (idempotency); `57d37ff`→`a9fdd3e` (deployment); `36946a1`→`91d30bd` (clean clone); `05042a7`→`322d909` (worker); `12b2e93`→`87e03ed` (capability) |
| 2.2 | The RED test proves the *exploit*, not just a missing function | Idempotency: 4 concurrent submissions produced 4 side effects — a measured exploit, recorded at `src/control_plane/idempotency.py:12-16` |
| 2.3 | The fix is deterministic — no LLM added | All P0 fixes are pure-Python; enforced by 1.1 |
| 2.4 | A concurrency fix is stress-tested at more than n=2 | `test_at_most_one_execution_under_concurrency[2\|4\|10\|100]` |
| 2.5 | A composed regression test pins the whole chain, not one link | `tests/test_p0_composed_attack_regression.py` (10 tests) |

### The composed-attack mutation check

Reverting the three control-plane files (`authorization.py`, `policy.py`,
`idempotency.py`) to pre-fix code makes **9 of 10** composed-attack tests fail,
including `no capability write occurred` and `no success audit event emitted`.

This is the strongest form of evidence in the branch: it shows the test is
load-bearing, not merely green.

---

## 3. Fail-closed standard

Every boundary below denies by default. An absent or empty allowlist is a deny,
never a permit.

| Boundary | Implementation | Test |
|---|---|---|
| Authorization | `src/control_plane/authorization.py:62-70` — empty allowlist raises `PermissionError`; operation not in allowlist raises | `tests/test_p0_authorization_boundary.py` (9) |
| Policy | `src/control_plane/policy.py:41-48` — `requested_parameters` excluded from the policy input; `DEFAULT_RISK_TIER = "MEDIUM"` at `:30` | `tests/test_p0_policy_trust_boundary.py` (13) |
| Capability registry | `src/mission/capability_ops.py:418-437` — `None` raises, `[]` raises, absent-from-list raises | `tests/test_p0_capability_allowlist.py` (8) |
| Read-back | `src/mission/verify.py:142-149` — empty `expected` → `INDETERMINATE` | `tests/test_p0_verify_readback_authority.py` (9) |
| Recovery | `src/activities/incident_activities.py:408-420` — `recovery.verified is not True` → `resolution_refused` | `tests/test_p0_no_misleading_claims.py` (18) |

Standard: **absence of configuration is not permission.** A caller that forgets
to supply an allowlist must get a denial, not an unrestricted run.

---

## 4. Honesty standard

| # | Standard | Implementation |
|---|---|---|
| 4.1 | A denial is never reported as success | `src/control_plane/ingress.py:69-88` — every deny path returns an `append_event(..., decision="deny:...", verified=False)` |
| 4.2 | An exception is never swallowed into a success | `src/control_plane/ingress.py:170-176` — on exception the claim is **released** and the error re-raised |
| 4.3 | A denied read-back is `INDETERMINATE`, not a mismatch | `src/mission/verify.py:198-211` — `CapabilityNotAllowedError` / `PermissionError` / "allowlist" in message |
| 4.4 | `INDETERMINATE` never promotes to `VERIFIED` | `src/mission/verify.py:61-67` — `verified` is derived strictly as `state == "VERIFIED"` |
| 4.5 | Recovery requires independent observed evidence | `src/mission/recovery_verification.py:58` — no predicates → `verified=False`; `src/activities/incident_activities.py:408` |
| 4.6 | Expectations derived from the write are labelled as such | `src/mission/verify.py:57-59`, `:219-242` |
| 4.7 | ROI savings carry provenance | `src/mission/roi_measurement.py:63-65`, `:133` — `evidenced` requires non-empty `evidence_refs` on **both** sides |

Standard: **never state more than was observed.** An unverifiable claim is
`INDETERMINATE`, not `VERIFIED`, and not `SUCCESS`.

---

## 5. Temporal standard

| # | Standard | Status |
|---|---|---|
| 5.1 | Only genuine `@workflow.defn` classes may be registered | `src/worker.py:206-217` documents that Temporal calls `_Definition.must_from_class` and raises otherwise |
| 5.2 | Every activity must be a coroutine | `tests/test_p0_worker_startup.py::TestProductionWorkerConstructs` |
| 5.3 | One registration path for every entrypoint | `tests/test_p0_worker_startup.py::TestSingleRegistrationPath` — `main.py` may not construct its own `Worker` |
| 5.4 | The worker polls the canonically resolved queue | `src/orchestration/queue.py:25-38` — `TEMPORAL_TASK_QUEUE` → `ONTOLOGYAI-MAIN-QUEUE`; pinned by `TestCanonicalTaskQueue` |
| 5.5 | **A mock-env branch test does not establish durability** | See `TESTING_STRATEGY.md` §4 |

This standard caught **5 "workflows"** that were plain classes with no
`@workflow.defn` (`DiscoveryWorkflow`, `OntologyMappingWorkflow`,
`KnowledgeValidationWorkflow`, `SolutionArchitectWorkflow`, `GovernanceWorkflow`),
each of which made the worker unconstructable. Commits `322d909`, `10f7d72`.

### Real-worker test obligations (all currently UNVERIFIED)

- [ ] task-queue delivery
- [ ] workflow continuation
- [ ] state persistence across Continue-As-New
- [ ] retry behaviour
- [ ] restart / recovery

`TestContinueAsNewAt5000Events`
(`apps/core/internal/workflow/business_os_workflow_test.go:94`) **hangs**: it
calls `env.ExecuteWorkflow(...)` at `:79` and only then sends 5001 signals at
`:82-94`. `ExecuteWorkflow` blocks, so every signal is discarded and the
Continue-As-New guard is never reached — `activity invocations: 0`. Category D,
filed as issue #68. Issue #69 covers the related child-workflow identity
collision and `AI_TASK_QUEUE` divergence.

---

## 6. Deployment standard

| # | Standard | Test |
|---|---|---|
| 6.1 | No artifact references a nonexistent entrypoint | `tests/test_p0_deployment_contract.py::TestEntrypointExists` — only `cmd/server`, `cmd/worker`, `cmd/consumer` are valid |
| 6.2 | `LISTEN_ADDR` is the single port source | `apps/core/cmd/server/main.go:44-49,66`; `TestPortConfiguration` |
| 6.3 | `/health` is liveness only — no dependency calls | `apps/core/internal/api/handlers.go:355-367`; `TestHealthSemantics` |
| 6.4 | `/health/ready` checks Postgres + Temporal, returns 503 | `apps/core/internal/api/handlers.go:375-455` |
| 6.5 | Redpanda is reported but not required on readiness | `handlers.go:383` `required = {"postgres": true, "temporal": true, "redpanda": false}` |
| 6.6 | Migrations run via `apps/core/cmd/migrate` | `TestMigrationsAreApplied`; runner at `cmd/migrate/main.go:41-46` |
| 6.7 | A clean clone can build Go | `tests/test_p0_clean_clone_build.py` (6) — `gen/go/go.mod` + `gen/go/go.sum` tracked |
| 6.8 | Python worker health endpoint is real | `src/worker.py:349-402` — `/health` 200 always, `/health/ready` 503 until the worker starts, then reports the real registry |

Measured: `go build ./...` exit 0, `go vet ./...` exit 0 in `apps/core` on a
clean clone. On the merge-base `e4fb0f0`, **no Go package can build at all** —
`apps/core/go.mod` has `replace .../gen/go => ../../gen/go` but the target was
gitignored. That is the regression this branch fixes.

---

## 7. Reviewer checklist

Run these before accepting any change to the P0 surface.

```bash
cd apps/ai

# 1. Deterministic gate, no credentials. MUST be 145 passed.
env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT \
  .venv/bin/python -m pytest -q -m "not llm" tests/test_p0_*.py

# 2. No live-model leakage into the deterministic gate.
env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT \
  .venv/bin/python -m pytest -q tests/test_p0_no_llm_in_security_suite.py

# 3. Go build + vet from a clean clone.
cd ../core && go build ./... && go vet ./...

# 4. Module metadata is tracked.
git ls-files | grep -E '^gen/go/go\.(mod|sum)$'
```

Expected at HEAD `cd7fe05`: step 1 → `145 passed`; step 2 → `7 passed`;
step 3 → exit 0; step 4 → prints two lines.

If step 1 is anything other than 145 passing, stop and classify the delta as
A/B/C/D before proceeding.
