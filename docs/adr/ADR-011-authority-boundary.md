# ADR-011: Authority Boundary — Propose, Authorize, Execute Separation

## Status
Accepted

## Context
AI employees investigate ambiguous evidence and recommend next steps,
but onboarding actions mutate Jira, Slack, CRM and customer-facing
state. If the LLM directly authorizes, dedupes, executes, or audits,
a hallucination becomes a side effect with no recourse. Deterministic
controls (auth, policy, idempotency, verification, audit) must survive
even when the LLM is wrong, retried, or prompt-influenced.

## Decision
Enforce a three-role authority boundary with a fixed pipeline:
AI components may only emit `ActionIntent` (untrusted proposal).
Only `Control Plane` may produce `AuthorizedAction` (validated,
policy-checked, approved). Only `Capability Runtime` may execute
side effects. Pipeline:
PROPOSE → VALIDATE → AUTHORIZE → POLICY → DEDUPE → APPROVE/ESCALATE
→ EXECUTE → VERIFY → RECONCILE → RECORD.
LLM owns PROPOSE only; it may assist VERIFY interpretation,
root-cause analysis, and REPLAN. It never owns auth, policy,
idempotency, execution, audit, or state truth (PostgreSQL).

## Consequences
- Positive: hallucinations are rejected at VALIDATE/POLICY, never executed.
- Positive: every action has evidence, policy decision, approval, verification.
- Positive: autonomy rate and success rate measurable separately.
- Negative: more hops per action; low-risk actions still pay DEDUPE/RECORD cost.
- Negative: Capability Runtime must be the sole executor — no direct tool calls.

## Alternatives Rejected
- LLM calls tools directly: rejected — no auth/policy/audit; injection = RCE.
- Pydantic validation is enough: rejected — schema ≠ permission, risk tier,
  dedupe, approval, or verification.
- Human approves everything: rejected — destroys autonomy; humans approve
  only by risk tier, rest auto-executes under policy.

## References
- `OntologyAI_PRD_28_08.md`: Agentic reasoning purpose (LLM decides only
  ambiguous investigation); Where-NOT-to-use-AI list; Safety model
  (Structured output → Pydantic → Policy → RBAC → Risk → Execution →
  Verification); Operational reliability metrics.
