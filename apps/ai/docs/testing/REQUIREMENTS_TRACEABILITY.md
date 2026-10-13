# Requirements Traceability — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05` · base `18f73f1`

Requirement → implementation (`file:line`) → test (`file::name`) → test type →
release gate → status.

**Status is never inferred from the existence of code.** It is inferred from an
executed, passing test, or it is not VERIFIED.

| Status | Meaning |
|---|---|
| **VERIFIED** | A named test was executed and passed on this branch |
| **PARTIAL** | Some cases proven; the requirement is broader than the tests |
| **KNOWN GAP** | The requirement is not met; the gap is named and pinned |
| **UNVERIFIED** | No executed evidence either way |

---

## 1. Control-plane security

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R1 | Authorization denies by default | `src/control_plane/authorization.py:62-66` | `test_p0_authorization_boundary.py::test_authorize_raises_when_no_allowlist` | unit | G1 | **VERIFIED** |
| R2 | An empty allowlist denies | `authorization.py:62-66` | `::test_empty_permissions_rejects` | unit | G1 | **VERIFIED** |
| R3 | An absent allowlist denies | `authorization.py:44-50`, `:62` | `::test_absent_permissions_rejects` | unit | G1 | **VERIFIED** |
| R4 | Operation must be in the trusted allowlist | `authorization.py:67-70` | `::test_operation_outside_allowlist_is_denied` | unit | G1 | **VERIFIED** |
| R5 | A denied op never reaches the executor | `ingress.py:69-78` | `::test_unauthorized_op_does_not_reach_executor` | unit | G1 | **VERIFIED** |
| R6 | A legitimate allowlisted op still permits | `authorization.py:105-117` | `::test_allowlisted_op_is_permitted` | unit | G1 | **VERIFIED** |
| R7 | Identity comes from trusted state only | `authorization.py:99-110` (`_require`) | `test_p0_composed_attack_regression.py::test_authorize_refuses_the_injected_intent` | regression | G6 | **VERIFIED** |
| R8 | Policy risk from trusted state only | `src/control_plane/policy.py:33-38`, `:48` | `test_p0_policy_trust_boundary.py::test_no_role_config_still_ignores_intent_risk_tier` | unit | G2 | **VERIFIED** |
| R9 | Intent-supplied `risk_tier` ignored at any value | `policy.py:41-48` | `::test_claimed_tier_never_influences_classification` | unit | G2 | **VERIFIED** |
| R10 | An injected LOW tier cannot bypass the approval gate | `policy.py:56-60` | `::test_low_claim_cannot_bypass_approval_gate` | unit | G2 | **VERIFIED** |
| R11 | An injected LOW tier cannot bypass the CRITICAL block | `policy.py:63-67` | `::test_low_claim_cannot_bypass_critical_block` | unit | G2 | **VERIFIED** |
| R12 | Trusted HIGH requires approval | `policy.py:56-60` | `::test_high_trusted_tier_requires_approval` | unit | G2 | **VERIFIED** |
| R13 | Trusted CRITICAL blocks execution | `policy.py:63-67` | `::test_critical_trusted_tier_blocks` | unit | G2 | **VERIFIED** |
| R14 | No trusted risk source → MEDIUM (fail-closed default) | `policy.py:30`, `:38` | `::test_no_role_config_still_ignores_intent_risk_tier` | unit | G2 | **VERIFIED** |
| R15 | Capability registry denies when `role_caps is None` | `src/mission/capability_ops.py:426-428` | `test_p0_capability_allowlist.py::test_none_allowlist_denies` | unit | G3 | **VERIFIED** |
| R16 | Capability registry denies when `role_caps == []` | `capability_ops.py:429-432` | `::test_empty_allowlist_denies` | unit | G3 | **VERIFIED** |
| R17 | Registry denies through `execute`, not just `assert_allowed` | `capability_ops.py:437-450` | `::test_execute_with_none_allowlist_denies`, `::test_execute_with_empty_allowlist_denies` | unit | G3 | **VERIFIED** |
| R18 | An unlisted op is denied; a listed op is allowed | `capability_ops.py:433-436` | `::test_unlisted_op_still_denied`, `::test_listed_op_is_allowed` | unit | G3 | **VERIFIED** |

---

## 2. Idempotency

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R19 | Idempotency is an atomic claim, not check-then-act | `src/control_plane/idempotency.py:112-153` | `test_p0_idempotency_atomicity.py::test_concurrent_claims_yield_exactly_one_winner` | concurrency | G4 | **VERIFIED** |
| R20 | Exactly one winner at high concurrency | `idempotency.py:131-153` | `::test_many_concurrent_claims_single_winner` | concurrency | G4 | **VERIFIED** |
| R21 | One execution at n = 2 / 4 / 10 / 100 | `idempotency.py:131-153` | `test_p0_idempotency_concurrency_e2e.py::test_at_most_one_execution_under_concurrency[2\|4\|10\|100]` | stress | G5 | **VERIFIED** |
| R22 | First claim wins; second is refused | `idempotency.py:133-145` | `::test_first_claim_wins`, `::test_second_claim_is_refused` | unit | G4 | **VERIFIED** |
| R23 | A committed key can never be reclaimed | `idempotency.py:141-142`, `:165` | `::test_commit_then_claim_is_refused`, `::test_committed_key_survives_lease_expiry` | unit | G4 | **VERIFIED** |
| R24 | Release permits a retry | `idempotency.py:167-176` | `::test_release_allows_retry` | unit | G4 | **VERIFIED** |
| R25 | Commit/release require the matching owner token | `idempotency.py:232-241` | `::test_commit_requires_matching_owner`, `::test_release_requires_matching_owner`, `::test_non_owner_cannot_release` | unit | G4 | **VERIFIED** |
| R26 | **Payload-conflict detection** | `idempotency.py:135-140` | `::test_same_key_different_payload_raises_conflict` | unit | G4 | **VERIFIED** |
| R27 | Same key + same payload is a plain duplicate, not a conflict | `idempotency.py:135-136` | `::test_same_key_same_payload_is_plain_duplicate` | unit | G4 | **VERIFIED** |
| R28 | A conflict reaches the caller as a denial | `ingress.py:119-123` | `test_p0_composed_attack_regression.py::test_ingress_rejects_the_chain` | regression | G6 | **VERIFIED** |
| R29 | Different tenants hold independent keys | `idempotency.py:39-48` | `::test_different_tenants_are_independent` | unit | G4 | **VERIFIED** |
| R30 | Different missions execute independently | `idempotency.py:39-48` | `test_p0_idempotency_concurrency_e2e.py::test_different_missions_execute_independently` | integration | G5 | **VERIFIED** |
| R31 | **Lease recovery** — a PENDING claim under a live lease is not reclaimable | `idempotency.py:143-145` | `::test_pending_claim_without_lease_is_not_reclaimable` | unit | G4 | **VERIFIED** |
| R32 | **Lease recovery** — an expired lease is reclaimable | `idempotency.py:143-145`, `:192-206` | `::test_expired_lease_is_reclaimable` | unit | G4 | **VERIFIED** |
| R33 | Claim state is observable | `idempotency.py:180-190` | `::test_state_transitions_are_observable` | unit | G4 | **VERIFIED** |
| R34 | Lease recovery on **worker death** (real crash, not clock expiry) | `idempotency.py:143-145` | none | — | — | **PARTIAL** — expiry is proven with a clock; no test kills a worker |
| R35 | **At-most-once survives a process restart** | `idempotency.py:269` (process singleton) | none | — | G16 | **KNOWN GAP** — not restart-safe |

---

## 3. Honest execution and verification

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R36 | A rejection is never reported as submitted | `src/control_plane/ingress.py:69-110` | `test_p0_control_plane_result.py::test_unauthorized_intent_is_not_submitted` | unit | G9 | **VERIFIED** |
| R37 | A duplicate is never reported as submitted | `ingress.py:124-127` | `::test_duplicate_intent_is_not_submitted` | unit | G9 | **VERIFIED** |
| R38 | A blocked intent is never reported as submitted | `ingress.py:105-110` | `::test_blocked_intent_is_not_submitted` | unit | G9 | **VERIFIED** |
| R39 | A control-plane crash is not a success | `ingress.py:170-176` (release + re-raise) | `::test_control_plane_crash_is_not_reported_as_success` | unit | G9 | **VERIFIED** |
| R40 | A genuine execution does report success | `ingress.py:190-193` | `::test_authorized_execution_reports_submitted` | unit | G9 | **VERIFIED** |
| R41 | The workflow gates execution on acceptance | `src/activities/incident_activities.py` | `::test_workflow_gates_execution_on_acceptance` | unit | G9 | **VERIFIED** |
| R42 | **Read-back runs under the same authority as the write** | `src/mission/step_runners.py:182-189` | `test_p0_verify_readback_authority.py::TestRoleCanVerifyItsOwnWrite::test_write_implies_granting_its_read` (parametrized over every entry in `READ_COUNTERPART`) | unit | G7 | **VERIFIED** |
| R43 | A write-only role is denied its own read-back | `verify.py:151-154` | `::test_write_only_role_is_denied_the_read_back` | unit | G7 | **VERIFIED** |
| R44 | A denied read-back is INDETERMINATE, never a bare mismatch | `verify.py:198-211` | `::test_denied_readback_is_not_silently_not_verified` | unit | G7 | **VERIFIED** |
| R45 | Every write op declares a read counterpart | `verify.py:28-34` | `::test_every_write_op_declares_its_read_counterpart` | unit | G7 | **VERIFIED** |
| R46 | A write with no counterpart is documented, not silent | `verify.py:133-141` | `::test_write_without_counterpart_is_documented_not_silent` | unit | G7 | **VERIFIED** |
| R47 | **Independent verification** — expectations labelled by provenance | `verify.py:57-59`, `:219-242` | `test_p0_no_misleading_claims.py::test_verify_outcome_declares_expectation_provenance` | unit | G8 | **VERIFIED** |
| R48 | Derived expectations are labelled `derived_from_write` | `verify.py:237-239` | `::test_derived_expectations_are_labelled_derived` | unit | G8 | **VERIFIED** |
| R49 | Caller-supplied expectations labelled as such | `verify.py:237` | `::test_caller_supplied_expectations_are_labelled_caller_supplied` | unit | G8 | **VERIFIED** |
| R50 | **A derived expectation cannot prove semantic correctness** | `verify.py:88-104` | `::test_derived_expectation_cannot_prove_semantic_correctness` | unit | G8 | **VERIFIED** — the limitation is proven, which is the requirement |
| R51 | The label reaches the end-to-end control-plane outcome | `ingress.py:186-188` | `::test_control_plane_labels_derived_verification_end_to_end` | regression | G8 | **VERIFIED** |
| R52 | **Read-back proves semantic correctness** | `verify.py:88-104` derives from the write | — | — | — | **KNOWN GAP** — not achievable by this design |
| R53 | Empty `expected` fails closed as INDETERMINATE | `verify.py:142-149` | `test_p0_verify_readback_authority.py::test_denied_readback_is_not_silently_not_verified` | unit | G7 | **VERIFIED** |
| R54 | **Recovery fails closed** — a vendor claim alone cannot certify | `src/mission/recovery_verification.py:58`, `:80` | `test_p0_no_misleading_claims.py::test_vendor_claim_alone_cannot_certify_recovery` | unit | G8 | **VERIFIED** |
| R55 | Total outage never reports verified | `recovery_verification.py` | `::test_total_outage_never_reports_verified` | unit | G8 | **VERIFIED** |
| R56 | An empty observation is not evidence | `recovery_verification.py:58` | `::test_empty_observed_is_not_evidence` | unit | G8 | **VERIFIED** |
| R57 | A healthy observation verifies **with** evidence | `recovery_verification.py:80` | `::test_healthy_observation_verifies_with_evidence` | unit | G8 | **VERIFIED** |
| R58 | `resolve_situation` refuses RESOLVED without `recovery.verified is True` | `src/activities/incident_activities.py:408-420` | `::test_resolve_situation_requires_verified_recovery` | unit | G8 | **VERIFIED** |
| R59 | `resolve_situation` accepts a verified recovery | `incident_activities.py:424-427` | `::test_resolve_situation_accepts_verified_recovery` | unit | G8 | **VERIFIED** |
| R60 | **ROI provenance** — savings are unevidenced without refs | `src/mission/roi_measurement.py:63-65`, `:133` | `::test_roi_savings_are_not_evidenced_without_provenance` | unit | G8 | **VERIFIED** |
| R61 | Savings are evidenced with refs on both sides | `roi_measurement.py:133` | `::test_roi_savings_are_evidenced_with_provenance` | unit | G8 | **VERIFIED** |
| R62 | ROI metrics reject unevidenced source events | `roi_measurement.py:32-37` | `::test_roi_metrics_rejects_unevidenced_source_events` | unit | G8 | **VERIFIED** |
| R63 | INDETERMINATE never becomes SUCCESS | `verify.py:61-67` | `test_p0_no_misleading_claims.py::test_total_outage_never_reports_verified` | unit | G8 | **VERIFIED** |

---

## 4. Composed attack

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R64 | Injected risk tier ignored in the composed chain | `policy.py:41-48` | `test_p0_composed_attack_regression.py::test_injected_risk_tier_is_ignored` | regression | G6 | **VERIFIED** |
| R65 | Injected LOW cannot bypass approval | `policy.py:56-60` | `::test_injected_low_cannot_bypass_approval` | regression | G6 | **VERIFIED** |
| R66 | Injected LOW cannot bypass the block | `policy.py:63-67` | `::test_injected_low_cannot_bypass_block` | regression | G6 | **VERIFIED** |
| R67 | Authorize refuses the injected intent | `authorization.py:53-70` | `::test_authorize_refuses_the_injected_intent` | regression | G6 | **VERIFIED** |
| R68 | Authorize refuses even when risk is permissive | `authorization.py:53-70` | `::test_authorize_refuses_even_when_risk_is_permissive` | regression | G6 | **VERIFIED** |
| R69 | **No capability write occurred** | `capability_ops.py:437-450` | `::test_no_capability_write_occurred` | regression | G6 | **VERIFIED** |
| R70 | **No success audit event emitted** | `audit.py:17-46` | `::test_no_success_audit_event_is_emitted` | regression | G6 | **VERIFIED** |
| R71 | The activity reports rejection, not success | `src/activities/incident_activities.py` | `::test_activity_reports_rejection_not_success` | regression | G6 | **VERIFIED** |
| R72 | A legitimate action still succeeds (no over-denial) | `ingress.py:190-193` | `::test_legitimate_action_still_succeeds` | regression | G6 | **VERIFIED** |
| R73 | **The composed test is load-bearing** | mutation check: revert the 3 control-plane files → 9/10 fail | `test_p0_composed_attack_regression.py` (whole file) | mutation | G6 | **VERIFIED** |

---

## 5. Audit and tenant isolation

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R74 | Every decision emits an audit event | `src/control_plane/audit.py:17-46`; `ingress.py:75-193` | `test_p0_composed_attack_regression.py::test_no_success_audit_event_is_emitted` | regression | G6 | **VERIFIED** |
| R75 | **Tenant isolation** — a foreign tenant cannot be injected as authority | `ingress.py:75-88`; `authorization.py:99-110` | `tests/adversarial/test_tenant_isolation.py::test_submit_binds_trusted_tenant_audit_has_no_foreign_content` | unit | — | **VERIFIED** |
| R76 | A spoofed tenant survives only as a *claim*, never as authority | `test_tenant_isolation.py:126-131` | same | unit | — | **VERIFIED** |
| R77 | Cross-tenant evidence is rejected on assembly | `src/mission/` assemble path | `::test_assemble_rejects_cross_tenant_evidence` | unit | — | **VERIFIED** |
| R78 | **Target-resource tenant match** (executor checks the target's tenant, not just the request's) | none | `::test_executor_target_tenant_gap_pinned_for_sprint_f` | pinned gap | — | **KNOWN GAP** — the test deliberately pins the current behaviour |
| R79 | The audit trail is durable | `audit.py:14` (module-level list) | none | — | G17 | **KNOWN GAP** — process-local |
| R80 | No fabricated metric literals in recovery output | `recovery_verification.py` | `test_p0_no_misleading_claims.py::test_no_fabricated_metric_literals_remain` | unit | G8 | **VERIFIED** |

---

## 6. Worker, build and deployment

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R81 | `main.py` does not build its own worker | `src/main.py` delegates to `src/worker.py` | `test_p0_worker_startup.py::test_main_does_not_build_its_own_worker` | static | G10 | **VERIFIED** |
| R82 | `main.py` reuses worker registration | `src/main.py` | `::test_main_reuses_worker_registration` | static | G10 | **VERIFIED** |
| R83 | The worker registers many activities, not one | `src/worker.py:_build_activity_list` | `::test_worker_registers_many_activities` | static | G10 | **VERIFIED** |
| R84 | Every registered activity is a coroutine | `worker.py:_build_activity_list` | `::test_every_registered_activity_is_async` | static | G10 | **VERIFIED** |
| R85 | **Temporal worker registration** — every registered workflow satisfies `must_from_class` | `src/worker.py:206-217` | `::test_every_registered_workflow_is_a_real_temporal_workflow`, `::test_temporal_accepts_every_registered_workflow` | contract | G10 | **VERIFIED** |
| R86 | Temporal accepts every registered activity | `worker.py:_build_activity_list` | `::test_temporal_accepts_every_registered_activity` | contract | G10 | **VERIFIED** |
| R87 | The worker constructs against a real registry | `worker.py:create_worker` | `::test_worker_constructs_against_real_registry` | contract | G10 | **VERIFIED** |
| R88 | **Canonical task queue** is used | `src/orchestration/queue.py:25-38` | `::test_task_queue_is_the_canonical_constant`, `::test_worker_uses_canonical_resolver` | static | G10 | **VERIFIED** |
| R89 | `TEMPORAL_TASK_QUEUE` overrides the queue | `queue.py:35-36` | `::test_env_var_overrides_queue` | unit | G10 | **VERIFIED** |
| R90 | The V7 incident activities are registered | `worker.py` | `::test_worker_registers_the_v7_incident_activities` | static | G10 | **VERIFIED** |
| R91 | Main modes remain parseable | `src/main.py` | `::test_modes_are_parseable` | static | G10 | **VERIFIED** |
| R92 | **Clean-clone build** — `gen/go/go.mod` is tracked | `.gitignore:177-181` | `test_p0_clean_clone_build.py::test_gen_go_go_mod_is_tracked` | static | G12 | **VERIFIED** |
| R93 | `gen/go/go.sum` is tracked | `.gitignore:181` | `::test_gen_go_go_sum_is_tracked` | static | G12 | **VERIFIED** |
| R94 | Module path matches the `replace` directive | `apps/core/go.mod` | `::test_module_path_matches_the_replace_directive` | static | G12 | **VERIFIED** |
| R95 | Generated `*.pb.go` stay untracked | `.gitignore:179` | `::test_pb_go_files_are_not_tracked` | static | G12 | **VERIFIED** |
| R96 | Proto sources are tracked | `proto/` | `::test_proto_sources_are_tracked` | static | G12 | **VERIFIED** |
| R97 | `go build ./...` exits 0 from a clean clone | `apps/core` | measured | build | G14 | **VERIFIED** |
| R98 | `go vet ./...` exits 0 | `apps/core` | measured | build | G15 | **VERIFIED** |
| R99 | **Deployment entrypoints** — no artifact references `cmd/demo` | `apps/core/cmd/{server,worker,consumer}` | `test_p0_deployment_contract.py::test_no_manifest_references_cmd_demo`, `::test_cmd_demo_does_not_exist` | static | G11 | **VERIFIED** |
| R100 | The Go server entrypoint builds | `apps/core/cmd/server` | `::test_go_server_entrypoint_builds` | build | G11 | **VERIFIED** |
| R101 | The Procfile starts a real binary | `Procfile` | `::test_procfile_starts_a_real_binary` | static | G11 | **VERIFIED** |
| R102 | The server honours a port env var | `apps/core/cmd/server/main.go:44-49` | `::test_server_honours_a_port_env_var` | static | G11 | **VERIFIED** |
| R103 | API port mapping matches `LISTEN_ADDR` | `main.go:66` | `::test_api_port_mapping_matches_listen_addr` | static | G11 | **VERIFIED** |
| R104 | **Health semantics** — `/health` performs no dependency call | `apps/core/internal/api/handlers.go:362-367` | `test_p0_deployment_contract.py::test_health_does_not_depend_on_external_services` | static | G11 | **VERIFIED** |
| R105 | `/health/ready` reports dependencies | `handlers.go:375-455` | `::test_ready_reports_dependencies` | static | G11 | **VERIFIED** |
| R106 | Both health routes exist | `cmd/server/main.go:167` | `::test_health_liveness_route_exists`, `::test_ready_route_exists` | static | G11 | **VERIFIED** |
| R107 | Python exposes a real health endpoint | `src/worker.py:349-402` | `::test_python_exposes_a_health_endpoint` | static | G11 | **VERIFIED** |
| R108 | The Docker image can run its healthcheck | `apps/ai/Dockerfile` | `::test_dockerfile_installs_healthcheck_dependency_or_uses_http` | static | G11 | **VERIFIED** |
| R109 | Readiness returns 503 on dependency loss | `handlers.go:444-455` | — | manual | G11 | **UNVERIFIED** — observed live, no committed test |
| R110 | **Migration execution** — a migration runner exists | `apps/core/cmd/migrate/main.go` | `test_p0_deployment_contract.py::test_a_migration_runner_exists` | static | G11 | **VERIFIED** |
| R111 | Migration SQL is not split across colliding directories | `cmd/migrate/main.go:177-182` (interleaved ordering) | `::test_migration_sql_is_not_split_across_colliding_directories` | static | G11 | **VERIFIED** — *ordering* |
| R112 | **A fresh-database bootstrap completes** | `internal/db/migrations/001_sarthi_sop_runtime.sql:10` vs `002_sarthi_v1.sql:20` | none | — | G18 | **KNOWN GAP** — `CREATE TABLE IF NOT EXISTS` silently keeps `founder_id` |
| R113 | The Python side has a migration mechanism | — | none | — | — | **KNOWN GAP** — none exists; `cmd/migrate` covers Go only |

---

## 7. LLM isolation

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R114 | **LLM test isolation** — the guard actually blocks the boundary | `src/config/llm` patched | `test_p0_no_llm_in_security_suite.py::test_guard_actually_blocks_the_boundary` | unit | G13 | **VERIFIED** |
| R115 | The full control-plane path is LLM-free | `authorization.py`, `policy.py`, `idempotency.py` | `::test_full_control_plane_path_is_llm_free` | unit | G13 | **VERIFIED** |
| R116 | Authorization denial is LLM-free | `authorization.py:53-70` | `::test_authorization_denial_is_llm_free` | unit | G13 | **VERIFIED** |
| R117 | The atomic claim is LLM-free | `idempotency.py:112-153` | `::test_atomic_claim_is_llm_free` | unit | G13 | **VERIFIED** |
| R118 | Live-LLM suites are marked | 6 files | `::test_live_llm_suites_are_marked` | static | G13 | **VERIFIED** |
| R119 | The marker is not silently overwritten | `pyproject.toml:80-88` | `::test_llm_marker_is_not_overwritten` | static | G13 | **VERIFIED** |
| R120 | The `llm` marker is registered | `pyproject.toml:114` | `::test_marker_is_registered` | static | G13 | **VERIFIED** |

---

## 8. Temporal durability — the open column

| # | Requirement | Implementation | Test | Type | Gate | Status |
|---|---|---|---|---|---|---|
| R121 | **Continue-As-New** — the guard executes when the event threshold is crossed | `apps/core/internal/workflow/business_os_workflow.go` | `apps/core/internal/workflow/business_os_workflow_test.go:79-94` | mock-env | G19 | **UNVERIFIED** — signals sent after the blocking `ExecuteWorkflow`; `activity invocations: 0`. Issue #68 |
| R122 | State persists across Continue-As-New | same | none | — | G19 | **UNVERIFIED** — no committed test |
| R123 | Task-queue delivery on `ONTOLOGYAI-MAIN-QUEUE` | `queue.py:25-38`; `worker.py:325` | none committed | — | G19 | **UNVERIFIED** — observed live (worker polls, reports registry on `/health/ready`) |
| R124 | Retry behaviour on a real worker | — | none | — | G19 | **UNVERIFIED** |
| R125 | Restart / recovery of a workflow | — | none | — | G19 | **UNVERIFIED** — and blocked by process-local state |
| R126 | Child workflows get distinct IDs | — | `tests/adversarial/` — none | — | G19 | **KNOWN GAP** — issue #69 (`AI_TASK_QUEUE` divergence + ID collision) |
| R127 | Approval-gate E2E coverage | `ingress.py:136-167` | `tests/adversarial/test_approval_failure.py` (5 failing) | — | G20 | **KNOWN GAP** — Category D stale contract |

---

## 9. Architecture boundaries — stated as gaps

| # | Stated boundary | Reality | Status |
|---|---|---|---|
| R128 | "An agent never holds DB credentials or issues arbitrary SQL" | `src/agents/bi/nodes.py:679,683`, `src/session/mission_state.py:104,170`, `src/session/context.py:53,104` read `DATABASE_URL` and issue raw SQL | **KNOWN GAP** — prose only; no test enforces it |
| R129 | The capability registry is authoritative process-wide | `src/mission/capability_ops.py:388` `_ops: dict[str, CapabilityOp] = {}` | **KNOWN GAP** — process-local class attribute |
| R130 | Audit, idempotency and version state survive a restart | `audit.py:14`, `idempotency.py:269`, `concurrency.py:40` | **KNOWN GAP** — see `PERSISTENCE_BOUNDARY.md` |
| R131 | OpenTelemetry spans reach a collector | `src/services/tracing/__init__.py:85` returns `Optional[object]` | **UNVERIFIED** — no committed test |
| R132 | Cost/latency metrics are durable | `src/mission/cost_latency.py:83` in-memory dict | **KNOWN GAP** — process-local |

---

## 10. Summary

| Status | Count | Requirement ids |
|---|---|---|
| **VERIFIED** | 112 | R1–R31, R36–R51, R53–R80 (excl. R35), R81–R108, R110–R111, R114–R120 |
| **PARTIAL** | 1 | R34 |
| **KNOWN GAP** | 12 | R35, R52, R78, R79, R112, R113, R126, R127, R128, R129, R130, R132 |
| **UNVERIFIED** | 7 | R109, R121, R122, R123, R124, R125, R131 |
| **Total** | 132 | R1–R132 |

Every VERIFIED row names a test that was executed and passed on this branch as
part of the 145-test P0 run
(`env -u GROQ_API_KEY -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY -u AZURE_OPENAI_ENDPOINT pytest -m "not llm" tests/test_p0_*.py`)
plus the two Go build checks and the adversarial tenant-isolation tests.

The 20 non-VERIFIED rows are the honest state of the system. They are itemised
in `RELEASE_GATE.md` §3 (G16–G20) and `FAILURE_MATRIX.md` §8.