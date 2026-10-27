# Testing Strategy — OntologyAI

Branch: `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05` · intended base `18f73f1`

This document states the strategy the P0 work actually follows. Where a strategy
is asserted but not enforced by a test, the enforcement column says so.

---

## 1. The one principle

**Deterministic infrastructure must never depend on an LLM. LLM output is
untrusted input.**

Consequences, each enforced by an executable test:

| Consequence | Enforcement |
|---|---|
| A deterministic control-plane path cannot reach a model | `tests/test_p0_no_llm_in_security_suite.py` patches `src.config.llm` (7 tests) |
| Model output may *propose* an action | `src/control_plane/contracts.py` — `ActionIntent` is the proposal carrier |
| Model output can never establish **authority** | `src/control_plane/authorization.py:95` — `_assert_authorized` |
| Model output can never establish **policy state** | `src/control_plane/policy.py:48` — `_trusted_params` excludes `requested_parameters` |
| Model output can never establish **execution success** | `src/control_plane/ingress.py:191` — verified flag comes from `verify_execution`, not the executor return |
| Model output can never establish **business outcome** | `src/mission/roi_measurement.py:133` — `evidenced` requires `evidence_refs` from both sides |

The split is enforced statically, not by credential sniffing, so a suite cannot
silently flip between "regression" and "evaluation" depending on the environment
(`pyproject.toml:80-88`).

```
deterministic regression gate : pytest -m "not llm"
live-model evaluation gate    : pytest -m llm
```

---

## 2. Suite tiers

| Tier | Marker | Runs without credentials | Count (measured) | Purpose |
|---|---|---|---|---|
| P0 execution surface | none | yes | 145 (`tests/test_p0_*.py`, all passing) | The release gate. See `RELEASE_GATE.md`. |
| Deterministic behavioural | none | yes | 287 collected (`tests/deterministic/`) | Domain contracts, golden trajectories, state transitions |
| Adversarial | none | yes | 16 collected (`tests/adversarial/`) — **5 failing, Category D** | Approval, concurrency, replay, recovery, tenant isolation |
| Security | none | yes | `tests/security/test_type_safety.py` | Type-boundary checks |
| Live-model evaluation | `llm` | **no** | 6 files declare `pytestmark = pytest.mark.llm` | Semantic/model quality |
| Integration / E2E | `integration`, `e2e` | no (containers) | `tests/integration/`, `tests/e2e/` | Real services, mocked third-party APIs |

Measured with `pytest --collect-only` and a full run of `tests/test_p0_*.py`
under `env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT`.

---

## 3. The standard for a fix

Every P0 fix in this branch was written to this sequence. The RED commits exist
in history and are individually inspectable.

```
1. RED exploit test      — write the test that fails against current code
2. Prove the exploit     — run it; capture the failing output
3. Deterministic fix     — change application code only, no LLM dependency
4. Stress test           — the exploit at n = 2 / 4 / 10 / 100
5. Prove it closed       — re-run; exploit no longer reproduces
6. Regression test       — pin the closed behaviour so it cannot reopen
7. Commit                — RED commit and fix commit are separate
```

Worked example — atomic idempotency:

| Step | Evidence |
|---|---|
| RED | commit `63eb97e` `test(security): RED — at-most-once must hold under concurrency` |
| Exploit measured | 4 concurrent submissions of one key = **4 side effects** (documented `src/control_plane/idempotency.py:12-16`) |
| Fix | commit `6619d1a` — `claim`/`commit`/`release` with owner token, lease, payload hash (`src/control_plane/idempotency.py:112-176`) |
| Stress | `tests/test_p0_idempotency_concurrency_e2e.py::test_at_most_one_execution_under_concurrency[2\|4\|10\|100]` — 1 execution at every n |
| Closed | 23 + 5 tests passing |
| Regression | `tests/test_p0_composed_attack_regression.py` (10) pins the full chain |

---

## 4. What a green suite does and does not mean

**A Temporal test that only proves workflow code reaches a branch in the
in-memory test environment does NOT establish production durability.**

`go.temporal.io/sdk/internal/internal_workflow_testsuite.go` is a mock. It does
not deliver task-queue messages, does not persist workflow state, does not
survive a restart.

Production claims therefore require **at least one real-worker test** covering:

- [ ] task-queue delivery on the canonical queue
- [ ] workflow continuation
- [ ] state persistence across Continue-As-New
- [ ] retry behaviour
- [ ] restart / recovery

| Claim | Status on this branch |
|---|---|
| Task-queue delivery on `ONTOLOGYAI-MAIN-QUEUE` | Proven **live** — worker polls it and reports the real registry on `/health/ready` (`src/worker.py:383-391`) |
| Continue-As-New guard executes | **UNVERIFIED** — `TestContinueAsNewAt5000Events` hangs because all 5001 signals are sent after the blocking `ExecuteWorkflow` (`apps/core/internal/workflow/business_os_workflow_test.go:94`); `activity invocations: 0`. Issue #68 |
| State persistence across Continue-As-New | **UNVERIFIED** — depends on the above |
| Retry behaviour on a real worker | **UNVERIFIED** — no committed test |
| Restart / recovery | **UNVERIFIED** — and the audit/idempotency/version stores are process-local, see `PERSISTENCE_BOUNDARY.md` |

A live run *was* observed for: Temporal on `localhost:7233` (`temporal operator
namespace list` → 3 namespaces, healthy), Postgres reachable, worker polling the
canonical queue, Go server honouring `LISTEN_ADDR`, readiness observed going
200 → 503 (Temporal stopped) → 200 while liveness stayed 200. That is an
observation, not a committed test. Nothing above is therefore marked VERIFIED on
the strength of it alone.

---

## 5. Rules

| Rule | Rationale |
|---|---|
| Regression is measured against the merge-base, never by absolute failure counts | A base with 200 failures makes any branch look clean |
| Failures are classified A/B/C/D, never hidden | See the classification table below |
| Mocks prove contracts, not production integration | A mock cannot fail the way a socket can |
| INDETERMINATE must never become SUCCESS | `src/mission/verify.py:198-211` — a denied read-back returns `INDETERMINATE` + `read_back_not_permitted`, never `VERIFIED` and never a bare mismatch |
| Absence of evidence is not evidence | Empty `expected` → `INDETERMINATE`, not pass (`src/mission/verify.py:142-149`) |
| An unevidenced figure may be a number but never a claim | `src/mission/roi_measurement.py:63` |

### Failure classification

| Cat | Meaning | Example on this branch |
|---|---|---|
| **A** | Branch regression — introduced by this work | none identified in the P0 surface |
| **B** | Pre-existing — fails identically on base and branch | `internal/api`, `internal/db`, `internal/redpanda`, `internal/web` all FAIL; base `e4fb0f0` cannot build Go at all (`gen/go/go.mod` was untracked), so the comparison is made against the last buildable base |
| **C** | Environment — credentials/services absent | `tests/test_agentic_capability.py`, 40× `openai 401`; now classified behind `-m llm` (`tests/test_agentic_capability.py:38`) |
| **D** | Stale contract — the test asserts behaviour that was correctly removed | 5 failures in `tests/adversarial/test_approval_failure.py` — see below |

#### The Category D failures, stated plainly

`tests/adversarial/test_approval_failure.py` builds `_high_intent()` with
`requested_parameters["risk_tier"] = "HIGH"` (`:72`) and asserts
`deny:approval_rejected` (`:117`). That intent-supplied tier is now **ignored by
design** — `src/control_plane/policy.py:41-48`. The tests therefore no longer
reach the approval gate.

This is the correct outcome. The tests encode the pre-fix contract in which an
LLM could set its own risk tier. They are not suppressed, not deleted, and not
counted as passing. Reinstating approval-gate coverage requires a test that
derives HIGH from **trusted** state (`role_config.risk_threshold`), which does
not yet exist. Tracked as an open coverage gap.

---

## 6. What this strategy explicitly does not claim

- It does not claim `derive_expected` proves semantic correctness. See §7.
- It does not claim the audit trail survives a restart. See `PERSISTENCE_BOUNDARY.md`.
- It does not claim the "agent never holds DB credentials" boundary is enforced. See §7.

---

## 7. Known limitations, stated not buried

### Read-back proves transport fidelity, not correctness

`src/mission/verify.py:88-104` `derive_expected` builds the expected predicates
**from the write params**. A read-back that passes therefore proves only: *"the
fields I sent are the fields that arrived."* It cannot prove the change was
semantically right.

The outcome is now labelled `expectation_source="derived_from_write"`
(`src/mission/verify.py:57-59`, `:219-242`), so it cannot be misread as
independent confirmation. **The underlying limitation stands.** Labelling is
honesty, not a fix.

### The DB-credential boundary is prose, not enforcement

`src/agents/bi/nodes.py:679,683`, `src/session/mission_state.py:104,170`,
`src/session/context.py:53,104` read `DATABASE_URL` and issue raw SQL from agent
and session modules.

The stated boundary — *an agent never holds DB credentials or issues arbitrary
SQL* — is **documented prose only and is NOT enforced by any test.**

### Process-local state

`CapabilityOpRegistry._ops` (`src/mission/capability_ops.py:388`) is an in-memory
class attribute, so the capability registry is process-local.

`test_agentic_capability` 40× `openai 401` failures were environment, not
defects; they are now behind `-m llm` and are not counted as a code defect.

---

## Related documents

| Document | Scope |
|---|---|
| `TESTING_STANDARDS.md` | The rules as a checklist a reviewer can run |
| `FAILURE_MATRIX.md` | Per-dependency degradation behaviour |
| `AGENT_EVALUATION.md` | Model-quality evaluation, separated from regression |
| `SECURITY_TESTING.md` | The 9 P0 invariants and their tests |
| `RELEASE_GATE.md` | What actually blocks a release |
| `REQUIREMENTS_TRACEABILITY.md` | Requirement → code → test → gate → status |
