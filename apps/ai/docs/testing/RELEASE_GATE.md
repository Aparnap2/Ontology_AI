# Release Gate — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05` · base `18f73f1`

---

## 1. Definition of the gate

> **The gate is: zero unexplained failures in the P0 execution surface, plus an
> explicit, reviewed inventory of classified exclusions.**

It is **not** "every test green". A gate that can only be satisfied by 100%
green across 3680 collected tests is not a gate — it is a wish, and it is
satisfied by nothing.

Two things are required:

1. **Zero unexplained failures.** Every failure in the P0 surface is either fixed
   or classified as A/B/C/D. Unclassified = blocking.
2. **An explicit exclusion inventory.** Every test deliberately outside the gate
   is named, with a category and a reason. Silence = failure. An exclusion that
   nobody can justify is not an exclusion.

---

## 2. The gate command

```bash
cd apps/ai
env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT \
  .venv/bin/python -m pytest -q -m "not llm" tests/test_p0_*.py
```

**Measured at `cd7fe05`: 145 passed, 0 failed.**

Plus, separately:

```bash
cd apps/core && go build ./... && go vet ./...     # both exit 0
```

---

## 3. Gate items

| # | Gate item | Evidence | Status |
|---|---|---|---|
| G1 | Authorization denies by default | `tests/test_p0_authorization_boundary.py` (9) | PASS |
| G2 | Policy reads risk from trusted state only | `tests/test_p0_policy_trust_boundary.py` (13) | PASS |
| G3 | Capability registry denies on absent/empty allowlist | `tests/test_p0_capability_allowlist.py` (8) | PASS |
| G4 | Idempotency claim is atomic | `tests/test_p0_idempotency_atomicity.py` (23) | PASS |
| G5 | At-most-once holds under concurrency | `tests/test_p0_idempotency_concurrency_e2e.py` (5) | PASS |
| G6 | Composed attack rejected; no write, no success event | `tests/test_p0_composed_attack_regression.py` (10) | PASS |
| G7 | Read-back under the write's authority; denied → INDETERMINATE | `tests/test_p0_verify_readback_authority.py` (9) | PASS |
| G8 | No misleading verification/recovery/ROI claims | `tests/test_p0_no_misleading_claims.py` (18) | PASS |
| G9 | Rejection is not success; exceptions not swallowed | `tests/test_p0_control_plane_result.py` (6) | PASS |
| G10 | Worker registration contract | `tests/test_p0_worker_startup.py` (17) | PASS |
| G11 | Deployment contract | `tests/test_p0_deployment_contract.py` (14) | PASS |
| G12 | Clean-clone Go build | `tests/test_p0_clean_clone_build.py` (6) | PASS |
| G13 | Deterministic gate needs no LLM credentials | `tests/test_p0_no_llm_in_security_suite.py` (7) | PASS |
| G14 | `go build ./...` exit 0 | measured in `apps/core` | PASS |
| G15 | `go vet ./...` exit 0 | measured in `apps/core` | PASS |
| G16 | **At-most-once survives a process restart** | process-local singleton (`idempotency.py:269`) | **FAIL — architectural, not fixable by test** |
| G17 | **Audit trail survives a restart** | `AUDIT_LOG: list` (`audit.py:14`) | **FAIL — architectural** |
| G18 | **Fresh-database migration bootstrap completes** | `001_sarthi_sop_runtime.sql:10` (`founder_id`) vs `002_sarthi_v1.sql:20` (`tenant_id`), `CREATE TABLE IF NOT EXISTS` | **FAIL — known gap** |
| G19 | **Real-worker Temporal durability** | no committed test | **UNVERIFIED — blocking for any durability claim** |
| G20 | **Approval-gate E2E coverage** | `tests/adversarial/test_approval_failure.py` — 5 failing, Category D | **FAIL — stale contract** |

**Result: 15 PASS · 5 FAIL · 0 UNEXPLAINED.**

The gate is **NOT CLEARED**. G16–G20 are stated, classified, and owned — which
is what the gate requires — but they are open.

---

## 4. Classified exclusions

Every test outside the gate, with category and reason.

| Exclusion | Cat | Count | Reason |
|---|---|---|---|
| `pytestmark = pytest.mark.llm` modules | **C** | 6 files | Requires live provider credentials. Not a security finding — 40× `openai 401` in `test_agentic_capability.py` is a missing key, not a defect. Excluded by static declaration, not by credential sniffing (`pyproject.toml:80-88`). |
| `tests/adversarial/test_approval_failure.py` | **D** | 5 | Stale contract. `_high_intent()` sets `risk_tier` in `requested_parameters` (`:72`), which `policy.py:41-48` now correctly ignores. The tests encode the pre-fix behaviour in which an LLM could set its own risk tier. |
| `apps/core/internal/api` | **B** | package | Fails identically on base and branch. Missing HTMX partials. |
| `apps/core/internal/db` | **B** | package | Fails identically on base and branch. |
| `apps/core/internal/redpanda` | **B** | package | Fails identically on base and branch. |
| `apps/core/internal/web` | **B** | package | Fails identically on base and branch. Missing partials; ontology contract count drift (7 vs 9 object types). |
| `TestContinueAsNewAt5000Events` | **D** | 1 | Hangs. Signals sent after the blocking `ExecuteWorkflow` (`business_os_workflow_test.go:79` then `:82-94`) → `activity invocations: 0`. Issues **#68**, **#69**. |
| `tests/integration/*`, `tests/e2e/*` | — | — | Require container services. Not part of the gate; corroborating only. |
| `tests/test_p0_clean_clone_build.py` subprocess work | — | — | Inside G12; runs `git` and inspects tracking. |

### Regression measurement, stated

The merge-base `e4fb0f0` **cannot build Go at all** — `apps/core/go.mod` has
`replace github.com/Aparnap2/iterate_swarm/gen/go => ../../gen/go` but
`gen/go/go.mod` was gitignored. A clean clone got
`replacement directory ../../gen/go does not exist` and no Go package built.

So "4 Go packages fail" cannot be compared to a buildable base. They were
compared to the last buildable base and fail identically: **Category B, not
Category A**. The branch's Go position is strictly better than the merge-base's.

---

## 5. What the gate does not claim

| Not claimed | Why |
|---|---|
| Production durability | G19 UNVERIFIED. A mock-env test reaching a branch is not a durability proof. |
| Restart safety | G16, G17. Process-local state. See `PERSISTENCE_BOUNDARY.md`. |
| Semantic correctness of governed writes | `verify.py:88-104 derive_expected` derives expectations from the write. Transport fidelity only. |
| "Agents never hold DB credentials" | Prose only. `src/agents/bi/nodes.py:679,683`, `src/session/mission_state.py:104,170`, `src/session/context.py:53,104` do exactly that. No test enforces the boundary. |
| Target-resource tenant isolation | `tests/adversarial/test_tenant_isolation.py:132` pins the gap deliberately. |
| A fresh database bootstraps | G18. |

---

## 6. Clearing G16–G20

| Gate | To clear | Effort |
|---|---|---|
| G16 | Move `SeenSet` to Postgres (`INSERT ... ON CONFLICT DO NOTHING`) or Redis (`SET NX`) — the primitive is already documented at `idempotency.py:94-101` | Architecture change |
| G17 | Same, for `AUDIT_LOG` | Architecture change |
| G18 | Reconcile `001`/`002` column shape, or make the conflict fail loudly instead of silently | Migration change |
| G19 | One real-worker test covering delivery, continuation, Continue-As-New persistence, retry, restart. Blocked on issues #68 and #69 | See `E2E_TEST_PLAN.md` §5 |
| G20 | Rewrite the approval-gate E2E to derive HIGH from `role_config.risk_threshold` | Test change, no product change |

G16/G17/G18/G19 are **not release blockers for a process-local pilot** — they are
blockers for any claim that survives a restart or a multi-replica deployment.
G20 is a test-coverage gap that should be closed before the approval gate is
claimed as covered.

---

## 7. Decision

| Question | Answer |
|---|---|
| Are the 9 P0 security invariants proven? | **Yes** — 145 P0 tests, all passing, no credentials required |
| Are there unexplained failures in the P0 surface? | **No** — 0 |
| Is the exclusion inventory complete and justified? | **Yes** — §4 |
| Is the gate cleared? | **No** — 5 items open, itemised above with owners |
| Can this ship as a single-process, restart-lossy deployment? | **Yes, if the restart-loss is stated to operators** (see `PERSISTENCE_BOUNDARY.md` §4) |
| Can this claim durability or at-most-once across restarts? | **No** |
