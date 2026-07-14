# V3.1 Release-Readiness Checklist

## 1. E2E Scenario Validation

### 1.1 Risk Detection → Dashboard
- [ ] `scan_prompt()` blocks API keys, PII, external-send actions
- [ ] `scan_output()` blocks unsupported claims, pricing commitments
- [ ] Risk dashboard panel renders scan counts + recent events
- [ ] Empty state renders when no scans exist

### 1.2 Trace Ingestion → Self-Guardian Observation
- [ ] `map_trace_to_observation()` handles full Langfuse trace dict
- [ ] Handles minimal/partial trace with defaults
- [ ] Handles malformed input gracefully (returns None, logs warning)
- [ ] Deduplication by trace_id within window
- [ ] Dedup allows re-ingest outside window

### 1.3 Observation → Fix Proposal
- [ ] `FixPlanner.plan()` produces typed `FixProposal` with blast radius
- [ ] Unauthorized tool → `disable_tool`, HIGH blast, requires approval
- [ ] State corruption → `rerun_workflow`, LOW blast, auto-apply
- [ ] Confidence drop → `switch_model`, LOW blast, auto-apply
- [ ] External-facing violation → `notify_operator`, HIGH blast, requires approval
- [ ] `plan_batch()` deduplicates by (agent, deviation_type)

### 1.4 Fix Proposal → HITL Approval
- [ ] Pending fix proposals appear in approvals dashboard panel
- [ ] Remediation items show blast radius badge + "fix" label
- [ ] Business approvals and remediation approvals visually distinct
- [ ] Approve action updates status
- [ ] Hold action updates status

### 1.5 Fix Execution → Result Persistence
- [ ] `Remediator.execute()` rejects unapproved proposals with `requires_approval=True`
- [ ] Executes approved proposals successfully
- [ ] Auto-applies proposals with `requires_approval=False`
- [ ] Timestamps populated on execution result

## 2. Graceful Degradation

### 2.1 Nil/Empty Database
- [ ] Operating layer panel renders without DB crash
- [ ] Control plane panel renders without DB crash
- [ ] Risk status panel renders without DB crash
- [ ] Self-guardian panel renders without DB crash
- [ ] Approvals panel renders without DB crash

### 2.2 Langfuse Unavailable
- [ ] `ingest_from_langfuse()` returns empty list, logs warning
- [ ] No exception propagates to caller

### 2.3 Partial/Malformed Data
- [ ] Malformed trace returns None (not exception)
- [ ] Empty observation buffer returns clean report
- [ ] Empty audit log returns empty events list

## 3. Architecture Constraints

### 3.1 Thin-LLM / Fat-Deterministic-Core
- [ ] Zero LLM calls in all new code (trace_ingest, fix_planner, remediator)
- [ ] All routing, filtering, state, policy, execution via deterministic code
- [ ] No business logic shifted into prompts

### 3.2 Typed Contracts
- [ ] All Pydantic schemas use explicit types (not dicts)
- [ ] All Go handler types use structs (not interface{})

### 3.3 Auditability
- [ ] Trace ingestion logs stats (total, deduped, failed)
- [ ] Fix execution logs outcome + timestamps
- [ ] All DB operations fail-soft (logged, not raised)

## 4. Test Coverage

### 4.1 Python
- [ ] `test_control_plane.py` — 389 lines, all passing
- [ ] `test_risk.py` — 20 tests, all passing
- [ ] `test_self_guardian.py` — 555 lines, all passing
- [ ] `test_self_guardian_integration.py` — 435 lines, all passing
- [ ] `test_self_guardian_persister.py` — 411 lines, all passing
- [ ] `test_trace_ingest.py` — 19 tests, all passing
- [ ] `test_fix_remediator.py` — 13 tests, all passing
- [ ] Total: **135 tests passing** across all Phase 4 modules

### 4.2 Go
- [ ] `go build ./...` compiles clean
- [ ] 13 command center tests pass (10 existing + 3 risk dashboard)
- [ ] All handlers have nil-DB safety test
- [ ] All handlers have no-HX-request fallback test

## 5. PR Readiness

### PR #28 — Risk Tests + Dashboard
- [ ] `tests/unit/test_risk.py` — 20 tests
- [ ] `handler.go` — `APICommandRiskStatus` + route
- [ ] `command_risk_status.html` — 63-line HTMX partial
- [ ] 3 Go tests for risk dashboard

### PR #29 — Trace Ingestion
- [ ] `trace_ingest.py` — `TraceIngester` + `map_trace_to_observation`
- [ ] `tests/unit/test_trace_ingest.py` — 19 tests
- [ ] Updated `__init__.py` exports

### PR #30 — Fix Planner + Remediator
- [ ] `fix_planner.py` — `FixPlanner` with blast-radius typing
- [ ] `remediator.py` — `Remediator` with approval gating
- [ ] `schemas/self_guardian.py` — `BlastRadius`, `FixProposal`, `FixExecutionResult`
- [ ] `migrations/007_self_guardian_fixes.sql` — fix proposals + results tables
- [ ] `tests/unit/test_fix_remediator.py` — 13 tests

### PR #31 — HITL Surface Expansion
- [ ] `handler.go` — expanded `APICommandApprovals` (queries fix_proposals)
- [ ] `command_approvals.html` — blast radius badges + fix labels
- [ ] Existing tests pass

### PR #32 — Integration + Polish
- [ ] Risk panel wired into `command_center.html` nav + 3-column grid
- [ ] Go build compiles clean
- [ ] 135 Python tests pass
