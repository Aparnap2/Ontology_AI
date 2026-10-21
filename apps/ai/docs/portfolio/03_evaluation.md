# OntologyAI Evaluation Report

## Test Suite Summary

The OntologyAI test suite comprises 618 tests organized by category. All tests
are deterministic (no real LLM calls, no real network) unless explicitly marked
as integration or evaluation tests. Tests run in under 30 seconds.

## Test Categories

```
618 total tests
|
+-- Deterministic correctness (boundary tests, config contracts)
|     Tests verifying Pydantic model strictness, config validation,
|     event envelope contracts, and schema boundaries.
|     Key files: test_event_envelope.py, test_workspace_schema.py,
|     test_mission_config_contracts.py, test_action_intent_contract.py
|
+-- Failure injection (40 tests)
|     |-- Event layer (4 tests): duplicate events, out-of-order events,
|     |     malformed events, unknown event types
|     |-- External vendor capability (6 tests): HTTP 500, HTTP 429,
|     |     timeout, invalid payload, connection refused, partial response
|     |-- Database/state (3 tests): optimistic concurrency conflict,
|     |     stale checkpoint, duplicate write
|     |-- Control plane (3 tests): idempotency under retry, approval
|           timeout, version gate
|     Key files: test_failure_injection.py
|
+-- Idempotency/reconciliation (29 tests)
|     |-- At-most-once (3 tests): retry denied as duplicate, different
|     |     intent objects with same fields, triple retry
|     |-- Unknown execution state (2 tests): reconciliation before blind
|     |     retry, vendor call counter proves at-most-once
|     |-- Key derivation (7 tests): same inputs produce same key,
|     |     different operation/target/scope produce different keys
|     |-- Concurrent submission (2 tests): identical intents race,
|     |     different intents both succeed
|     |-- Crash recovery (2 tests): SeenSet loss allows second execution,
|     |     SeenSet persistence prevents duplicate
|     |-- Version progression (5 tests): N then N+1 succeed, stale
|     |     version rejected, no version bypasses gate, version advances
|     |     only after execution, stale version with unique keys
|     |-- SeenSet unit tests (4 tests): basic mark/is_duplicate
|     |-- VersionStore unit tests (4 tests): seed, current, advance
|     Key files: test_idempotency_reconciliation.py
|
+-- Security (23 tests)
|     |-- Prompt injection (4 tests): direct injection via Slack,
|     |     injection in Evidence flow through checkpoint, indirect
|     |     injection via ticket, forbidden field rejection
|     |-- Tenant isolation (3 tests): cross-tenant evidence rejected,
|     |     mixed evidence rejected, cross-tenant mission denied
|     |-- Capability escalation (5 tests): operation outside allowlist,
|     |     unknown operation in registry, CRITICAL tier blocked,
|     |     CRITICAL intent denied by ingress, op outside role allowlist
|     |-- Approval spoofing (2 tests): no signal_handler denied,
|     |     pre-loaded fake approval denied
|     |-- Replay protection (3 tests): duplicate submission denied,
|     |     SeenSet rejects duplicate, different keys independent
|     |-- Model authority enforcement (3 tests): Action rejects
|     |     approved/bypass_policy fields, Evidence rejects instruction
|     |-- Role allowlist enforcement (3 tests): op outside role raises,
|     |     op inside passes, None role_caps allows all
|     Key files: test_security_adversarial.py
|
+-- LLM evaluation (65 tests)
|     |-- TriggerAgent output quality (5 tests): message length, specific
|     |     amounts, no jargon, single action, specific suppression reason
|     |-- ToneFilter fidelity (4 tests): EBITDA replacement, celebratory
|     |     tone, calm tone, Hindi Devanagari script
|     |-- MemoryAgent pattern detection (3 tests, skipped pending
|     |     implementation): archetype detection, avoidance patterns,
|     |     commitment completion rate
|     |-- LLM-as-Judge evaluations (15 tests in test_llm_eval.py):
|     |     real Azure OpenAI calls, judge prompt with confidence threshold
|     |-- DeepEval evaluations (in test_deepeval_evals.py): faithfulness,
|     |     answer relevancy, context precision/recall
|     |-- DSPy evaluations (in test_dspy_evals.py): prompt optimization
|     |     validation
|     |-- E2E evaluation scenarios (8 scenarios E1-E8): grounding,
|     |     safety, hallucination detection
|     Key files: test_llm_eval.py, test_llm_evals.py, test_llm_evaluation.py,
|     test_deepeval_evals.py, test_dspy_evals.py
|
+-- Observability (31 tests)
|     |-- Trace span ordering (2 tests): append order, single span
|     |-- Parent-child relationships (3 tests): child references parent,
|     |     root has no parent, multiple children
|     |-- LLM call records (3 tests): record captured, multiple records,
|     |     zero tokens
|     |-- Timeline export (4 tests): sorted by time, returns dicts,
|     |     empty trace, preserves all fields
|     |-- Span status (5 tests): default ok, end ok/error/cancelled,
|     |     missing span raises
|     |-- Events within spans (3 tests): event added, multiple events,
|     |     missing span raises
|     |-- Concurrent spans (3 tests): many open spans, interleaved
|     |     start/end, get missing returns None
|     |-- Model strictness (4 tests): TraceSpan/LLMCallRecord reject
|     |     extra fields, strict types
|     |-- No I/O guarantees (4 tests): ISO format times, serializable
|     |     timeline, plain dict attributes/events
|     Key files: test_observability.py
|
+-- Operational readiness (21 tests)
|     |-- Health checks (4 tests): reflects dependencies, check runs
|     |     function, all healthy gives healthy, dependency status recording
|     |-- Degrade behaviors (6 tests): degraded when any dependency
|     |     degraded, unhealthy when critical dependency unhealthy,
|     |     worst-status-wins policy
|     |-- Version tracking (3 tests): version recorded, uptime calculation
|     Key files: test_operational_readiness.py
|
+-- Data governance (41 tests)
|     |-- V7 asset registration (4 tests): count, IDs, loaded into
|     |     registry, names
|     |-- Classification levels (8 tests): evidence/vendor_ticket/incident
|     |     /audit_log/llm_prompt_log classification, unknown asset,
|     |     enum values, str subclass
|     |-- PII detection (3 tests): only llm_prompt_log contains PII,
|     |     flag matches definition, empty registry
|     |-- Retention expiry (7 tests): expired asset, not expired,
|     |     indefinite retention, unknown asset, no audit date, 90-day
|     |     LLM prompt log, naive datetime
|     |-- Tenant isolation (6 tests): same tenant allowed, different
|     |     denied, unknown denied, individual access control, vendor
|     |     ticket isolation, incident isolation
|     |-- PII redaction (5 tests): no redaction for non-PII, no redaction
|     |     for unknown, restricted PII redacts all, confidential non-PII
|     |     no redaction, preserves non-string values
|     |-- Model strictness (3 tests): reject extra fields, valid
|     |     construction, frozen model
|     |-- Registry operations (5 tests): register and get, unknown
|     |     returns None, overwrite existing, encryption when
|     |     confidential/restricted, tenant or individual access
|     Key files: test_data_governance.py
|
+-- Cost/latency (30 tests)
|     |-- LLM cost computation (4 tests): GPT-4o, GPT-4o-mini,
|     |     Claude-3-haiku, zero tokens
|     |-- Mission metrics (tests): aggregation, resolution ratio
|     |-- Multi-mission independence (tests): cost isolation between
|     |     missions, independent tracking
|     Key files: test_cost_latency.py
```

## Properties Proven

### Safety

| Property | Evidence | Tests |
|----------|----------|-------|
| Prompt injection blocked | External text treated as attributed data, never as instruction. Evidence model rejects `instruction` field. | 4 tests in TestPromptInjection |
| Tenant isolation enforced | Cross-tenant evidence rejected at checkpoint assembly. Cross-tenant missions denied by authorization. | 3 tests in TestTenantIsolation |
| Capability escalation blocked | Operations outside role allowlist rejected. CRITICAL tier blocked before execution. Unknown operations raise error. | 5 tests in TestCapabilityEscalation |
| Approval spoofing blocked | ActionIntent cannot carry `approved` or `bypass_policy` fields. No signal_handler = denied. | 2 tests in TestApprovalSpoofing |
| Replay protection active | Duplicate submissions denied via SeenSet. Concurrent identical intents produce exactly one execution. | 3 tests in TestReplayProtection |

### Reliability

| Property | Evidence | Tests |
|----------|----------|-------|
| Worker failure recoverable | SeenSet loss documented; production uses Temporal durable storage. Reconciliation before blind retry. | 2 tests in TestRecoveryAfterCrash, 2 in TestUnknownExecutionState |
| Network timeout reconcilable | VendorRetryableError for timeouts. Idempotency guard prevents duplicate execution on retry. | 2 tests in TestVendorTimeout, idempotency suite |
| Duplicate event idempotent | SeenSet blocks duplicate events. Different scopes produce distinct keys. | 2 tests in TestDuplicateEvent, 7 in TestIdempotencyKeyDerivation |
| Stale context rejected | Version mismatch detected by VersionStore. Stale version returns deny:stale_version. | 3 tests in TestStaleCheckpoint, 5 in TestVersionProgression |

### Cognitive Correctness

| Property | Evidence | Tests |
|----------|----------|-------|
| Ambiguous evidence flagged | LLM eval scenarios test grounding against ambiguous inputs. Evidence normalization preserves uncertainty. | Part of LLM evaluation suite (65 tests) |
| Conflicting evidence detected | Checkpoint assembly collects evidence from multiple sources with provenance. Conflict resolution in guardrail tests. | test_evidence_guardrail_contract.py |
| Hallucinated entity rejected | LLM eval tests verify grounding in retrieved context, not hallucinated information. | test_llm_eval.py, test_deepeval_evals.py |
| False recovery rejected | Predicate-based verification: every predicate must pass against observed state. Empty predicates fail closed. | 8 tests in test_recovery_verification.py |
| Insufficient evidence rejected | Recovery verification with insufficient predicates fails closed (INDETERMINATE). | test_recovery_verification.py: test_empty_predicates_fail_closed |

## Test Execution

```bash
# Run all tests
cd apps/ai
uv run pytest tests/ -v

# Run specific category
uv run pytest tests/test_security_adversarial.py -v
uv run pytest tests/test_failure_injection.py -v
uv run pytest tests/test_idempotency_reconciliation.py -v
uv run pytest tests/test_observability.py -v
uv run pytest tests/test_data_governance.py -v
uv run pytest tests/test_cost_latency.py -v
uv run pytest tests/test_operational_readiness.py -v
uv run pytest tests/test_recovery_verification.py -v

# Run with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing
```

## Evaluation Strategy

1. **Deterministic first**: Model contracts, boundary tests, config validation.
   No external dependencies. Runs in seconds.

2. **Failure injection second**: Every layer tested against realistic failures
   (HTTP 500, timeout, stale state, concurrent access). All mocked, no network.

3. **Security adversarial third**: Prompt injection, tenant escape, capability
   escalation, approval spoofing, replay. Deterministic, no real LLM.

4. **LLM evaluation fourth**: Real Azure OpenAI calls against 8 scenarios (E1-E8)
   with judge prompts and confidence thresholds. Separate pipeline, not in dev loop.

5. **Integration fifth**: Docker-gated tests with real containers but mocked
   third-party APIs. Uses VCR cassettes from Phase 2.
