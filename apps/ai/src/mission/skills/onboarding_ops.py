"""Blocker-investigation skill — investigate one onboarding blocker (slice).

Two skill definitions share ONE generic runner core
(:func:`_run_investigation_core`): ``investigate_onboarding_blocker``
(unchanged behavior) and ``investigate_vendor_incident`` (same core,
different prompt framing + allowlist). The LLM is used strictly for
ambiguous evidence interpretation / root-cause reasoning. Every authority
decision (evidence gating, parameter policy, authorization, idempotency,
approval, execution, verification, audit) is deterministic and lives in
the Control Plane.
"""
from __future__ import annotations

import contextvars
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from pydantic import Field

from src.config import llm as llm_module
from src.control_plane.contracts import ActionIntent
from src.control_plane.ingress import submit_intent
from src.entities.models import OntologyBaseModel
from src.mission.skill_contracts import SkillContext, SkillDefinition, SkillInput, SkillOutput

BLOCKER_INVESTIGATION_SKILL_NAME = "investigate_onboarding_blocker"
VENDOR_INVESTIGATION_SKILL_NAME = "investigate_vendor_incident"

# Deterministic blocker-investigation action surface: the ONLY operations this skill may propose.
BLOCKER_INVESTIGATION_ALLOWED_OPS = {"jira.update", "jira.create", "slack.send"}

# Vendor-incident action surface: same runner core, vendor-domain allowlist.
VENDOR_INVESTIGATION_ALLOWED_OPS = {
    "jira.update", "slack.send",
    "vendor_ticket.create", "vendor_ticket.update",
    "incident.get", "incident.search",
    "notification.send_internal", "notification.send_vendor",
}

_JIRA_STATUS_ALLOWED = {"To Do", "In Progress", "Blocked", "Done"}

_VALID_TIERS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

# Tiers that require grounded evidence before any intent may be proposed.
_EVIDENCE_TIERS = {"MEDIUM", "HIGH", "CRITICAL"}

_SYSTEM = (
    "You investigate B2B onboarding blockers. Given evidence texts, reply "
    "with JSON only: {root_cause, action: {capability, operation, target, "
    "parameters}, confidence (0-1), risk_tier (LOW/MEDIUM/HIGH/CRITICAL), "
    "expected_outcome}. You propose; you never authorize or execute."
)

# Same output shape, vendor-incident framing only. No vendor-entity,
# link-type, mission, or framework semantics live in the runner.
_VENDOR_SYSTEM = (
    "You investigate vendor incidents. Given evidence texts, reply "
    "with JSON only: {root_cause, action: {capability, operation, target, "
    "parameters}, confidence (0-1), risk_tier (LOW/MEDIUM/HIGH/CRITICAL), "
    "expected_outcome}. You propose; you never authorize or execute."
)


@dataclass
class BlockerInvestigationWorkItem:
    """Handoff from the blocker-investigation runner to the skill.

    ``_run_skill`` only passes ``tenant_id`` into the skill input, so the
    runner hands the full trusted work item through a ContextVar.
    ``observations`` is the test seam: the skill records its output there.

    ``target_type``/``target_id``/``checkpoint`` are optional generic
    overrides (populated by vendor-path callers); the onboarding path
    leaves them unset and behavior is unchanged.
    """

    mission_id: str
    tenant_id: str
    employee_id: str
    actor_identity: str
    business_scope: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    evidence_texts: list[str] = field(default_factory=list)
    blocker_ref: str = ""
    signal_handler: Any = None
    observations: list[dict[str, Any]] = field(default_factory=list)
    target_type: str | None = None
    target_id: str | None = None
    checkpoint: Any = None


@dataclass
class InvestigationContext:
    """Generic investigation target + authority view (Phase 2a).

    Exactly ONE such context exists — there is intentionally no
    ``VendorInvestigationContext``. The skill resolves target/authority
    from this instead of onboarding-shaped fields: ``target_type`` /
    ``target_id`` identify the investigated entity, ``checkpoint`` is the
    deterministic context snapshot (opaque to the runner), ``mission_id``
    is the mission ref used for trusted intent binding, and
    ``allowed_capabilities`` carries the checkpoint-advertised capability
    surface (informational; enforcement stays in the Control Plane).
    """

    target_type: str | None = None
    target_id: str | None = None
    checkpoint: Any = None
    mission_id: str = ""
    allowed_capabilities: list[str] = field(default_factory=list)

    @classmethod
    def from_work_item(
        cls,
        item: BlockerInvestigationWorkItem,
        checkpoint: Any = None,
    ) -> InvestigationContext:
        """Derive the generic context from the trusted work item."""
        resolved_checkpoint = checkpoint if checkpoint is not None else item.checkpoint
        allowed: list[str] = []
        if isinstance(resolved_checkpoint, dict):
            raw = resolved_checkpoint.get("allowed_capabilities", [])
            if isinstance(raw, list):
                allowed = [str(c) for c in raw]
        else:
            raw_caps = getattr(resolved_checkpoint, "allowed_capabilities", None)
            if isinstance(raw_caps, list):
                allowed = [str(c) for c in raw_caps]
        return cls(
            target_type=item.target_type,
            target_id=item.target_id,
            checkpoint=resolved_checkpoint,
            mission_id=item.mission_id,
            allowed_capabilities=allowed,
        )


class InvestigationFinding(OntologyBaseModel):
    """One cited finding: a FACT only when it cites trusted evidence."""

    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class InvestigationResult(OntologyBaseModel):
    """Strict LLM-output shape, validated BEFORE ActionIntent construction.

    Superset of the legacy proposal shape (``root_cause``/``action``/
    ``risk_tier``/``confidence``/``expected_outcome``) so the onboarding
    path validates unchanged; the ``findings``/``evidence_refs``/
    ``unresolved_questions``/``recommended_action`` fields carry the
    generic evidence-grounded shape. ``agentic_loop`` has no equivalent
    contract (only loop-control ``AgenticDecision`` and envelope
    ``SkillResult``), so this model is added here and reused by both
    skills. Extra fields are rejected (fail closed → INVALID_PROPOSAL).
    """

    findings: list[InvestigationFinding] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    recommended_action: dict[str, Any] | None = Field(default=None)
    root_cause: str = ""
    action: dict[str, Any] | None = Field(default=None)
    risk_tier: str = ""
    expected_outcome: str = ""


def grounding_violation(
    findings: list[InvestigationFinding],
    trusted_evidence_ids: list[str],
) -> str | None:
    """Return an error string when a finding asserts without citation.

    Every finding is a FACT only if each of its ``evidence_ids`` is a
    trusted evidence id from the work item. Uncited (or unknown-id)
    findings are never asserted as fact — the caller fails the proposal
    honestly (no intent) and routes the statements to unresolved.
    """
    trusted = set(trusted_evidence_ids)
    for finding in findings:
        if not finding.evidence_ids:
            return f"finding without evidence citation: {finding.statement!r}"
        unknown = [e for e in finding.evidence_ids if e not in trusted]
        if unknown:
            return f"finding cites unknown evidence {unknown!r}: {finding.statement!r}"
    return None


_current: contextvars.ContextVar[BlockerInvestigationWorkItem | None] = contextvars.ContextVar(
    "blocker_investigation_work_item", default=None
)


@contextmanager
def set_investigation_work_item(
    item: BlockerInvestigationWorkItem,
) -> Iterator[BlockerInvestigationWorkItem]:
    """Bind a work item for the duration of one skill run."""
    token = _current.set(item)
    try:
        yield item
    finally:
        _current.reset(token)


class _BlockerInvestigationIn(SkillInput):
    """Tenant scope only — the work item arrives via ContextVar."""


class _BlockerInvestigationOut(SkillOutput):
    """Extra fields allowed (SkillOutput is extra=allow)."""


def _observe(item: BlockerInvestigationWorkItem, **fields: Any) -> SkillOutput:
    out = _BlockerInvestigationOut(**fields)
    item.observations.append(out.model_dump())
    return out


def _policy_check(
    operation: str,
    target: str,
    params: Any,
    allowed_ops: set[str] | frozenset[str] = BLOCKER_INVESTIGATION_ALLOWED_OPS,
) -> str | None:
    """Return an error string when the proposal violates investigation policy, else None."""
    if operation not in allowed_ops:
        return f"operation {operation!r} outside investigation allowlist"
    if not target:
        return "empty target_reference"
    if not isinstance(params, dict):
        return "parameters must be an object"
    if operation == "jira.update":
        if not params.get("issue_id"):
            return "jira.update requires issue_id"
        fields = params.get("fields", {})
        if not isinstance(fields, dict):
            return "jira.update fields must be an object"
        status = fields.get("status")
        if status is not None and status not in _JIRA_STATUS_ALLOWED:
            return f"jira status {status!r} not permitted"
    return None


async def _run_investigation_core(
    ctx: SkillContext,
    *,
    system_prompt: str,
    allowed_ops: set[str] | frozenset[str],
) -> SkillOutput:
    """Generic investigation runner shared by both skill definitions.

    Behavior is identical regardless of caller; only ``system_prompt``
    (LLM framing) and ``allowed_ops`` (deterministic policy surface)
    vary. No vendor/onboarding semantics are hardcoded here.
    """
    item = _current.get()
    if item is None:
        return _BlockerInvestigationOut(ok=False, action_taken=False, outcome="NO_WORK_ITEM")

    # Generic target/authority view: mission ref + target come from the
    # InvestigationContext, not from onboarding-shaped fields.
    ictx = InvestigationContext.from_work_item(item)

    # 1. LLM reasons about ambiguous evidence ONLY (mocked in tests).
    try:
        reply = llm_module.chat_completion_with_metrics(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"blocker": item.blocker_ref, "evidence": item.evidence_texts}
                    ),
                },
            ],
            json_mode=True,
        )
        raw = json.loads(reply.content)
        if not isinstance(raw, dict):
            raise ValueError("proposal must be a JSON object")
        result = InvestigationResult.model_validate(raw)
        action = result.recommended_action if result.recommended_action is not None else result.action
        if action is None:
            raise ValueError("proposal failed validation")
        tier = str(result.risk_tier or "").upper()
        confidence = float(result.confidence)
        root_cause = str(result.root_cause or "")
        if tier not in _VALID_TIERS or not (0.0 <= confidence <= 1.0) or not root_cause:
            raise ValueError("proposal failed validation")
        findings = list(result.findings)
        unresolved = list(result.unresolved_questions)
    except Exception as exc:  # noqa: BLE001 — LLM output is untrusted by design
        return _observe(
            item, ok=False, action_taken=False, outcome="INVALID_PROPOSAL",
            error=f"unusable LLM proposal: {exc}",
        )

    # 1b. Deterministic evidence-grounding gate: cited findings only.
    # Untrusted external text stays data — a finding without a trusted
    # citation is never asserted as fact.
    violation = grounding_violation(findings, list(item.evidence_ids))
    if violation is not None:
        uncited = [f.statement for f in findings if not f.evidence_ids]
        return _observe(
            item, ok=False, action_taken=False, outcome="UNGROUNDED_FINDING",
            error=violation,
            root_cause=root_cause, confidence=confidence,
            unresolved_questions=list(unresolved) + uncited,
        )

    # 2. Deterministic evidence gate (ADR-012).
    if tier in _EVIDENCE_TIERS and not item.evidence_ids:
        return _observe(
            item, ok=False, action_taken=False, outcome="MISSING_EVIDENCE",
            error=f"{tier}-risk intent requires grounded evidence",
            root_cause=root_cause, confidence=confidence,
        )

    # 3. Deterministic business-parameter gate.
    op = str(action.get("operation", ""))
    target = str(action.get("target", ""))
    params = action.get("parameters", {})
    policy_violation = _policy_check(op, target, params, allowed_ops)
    if policy_violation is not None:
        return _observe(
            item, ok=False, action_taken=False, outcome="POLICY_BLOCKED",
            error=policy_violation, root_cause=root_cause, confidence=confidence,
        )

    # 4. Propose the untrusted intent; the Control Plane decides.
    try:
        intent = ActionIntent(
            capability=str(action.get("capability", "")),
            operation=op,
            target_reference=target,
            requested_parameters={**params, "risk_tier": tier},
            reason=f"{root_cause} (evidence: {len(item.evidence_ids)} refs)",
            evidence_ids=list(item.evidence_ids),
            expected_outcome=str(
                result.expected_outcome or f"{op} on {target} verified by read-back"
            ),
            confidence=confidence,
            requested_by=item.employee_id,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on malformed intent
        return _observe(
            item, ok=False, action_taken=False, outcome="INVALID_PROPOSAL",
            error=f"intent construction failed: {exc}",
        )

    trusted = {
        "tenant_id": item.tenant_id,
        "mission_id": ictx.mission_id,
        "employee_id": item.employee_id,
        "actor_identity": item.actor_identity,
        "business_scope": item.business_scope,
    }
    try:
        event = await submit_intent(
            intent,
            trusted,
            role_config=ctx.role_config,
            signal_handler=item.signal_handler,
            capabilities=ctx.capabilities,
        )
    except Exception as exc:  # noqa: BLE001 — honest failure, never false success
        return _observe(
            item, ok=False, action_taken=False, outcome="EXECUTION_FAILED",
            verified=False, error=str(exc),
            root_cause=root_cause, confidence=confidence,
        )

    decision = event.get("decision", "")
    verified = bool(event.get("verified", False))
    if decision == "permit:executed":
        outcome = "BUSINESS_OUTCOME_VERIFIED" if verified else "EXECUTED_UNVERIFIED"
    else:
        outcome = decision
    return _observe(
        item,
        ok=decision == "permit:executed" and verified,
        action_taken=decision == "permit:executed",
        outcome=outcome,
        decision=decision,
        verified=verified,
        action_id=event.get("action_id", ""),
        root_cause=root_cause,
        confidence=confidence,
        target_type=ictx.target_type,
        target_id=ictx.target_id,
    )


async def _run(ctx: SkillContext, inp: SkillInput) -> SkillOutput:
    """Onboarding blocker skill — thin wrapper over the generic core."""
    return await _run_investigation_core(
        ctx,
        system_prompt=_SYSTEM,
        allowed_ops=BLOCKER_INVESTIGATION_ALLOWED_OPS,
    )


async def _run_vendor(ctx: SkillContext, inp: SkillInput) -> SkillOutput:
    """Vendor-incident skill — same core, vendor framing + allowlist only."""
    return await _run_investigation_core(
        ctx,
        system_prompt=_VENDOR_SYSTEM,
        allowed_ops=VENDOR_INVESTIGATION_ALLOWED_OPS,
    )


BLOCKER_INVESTIGATION_SKILL = SkillDefinition(
    name=BLOCKER_INVESTIGATION_SKILL_NAME,
    description="Investigate an onboarding blocker and propose one governed remediation.",
    input_model=_BlockerInvestigationIn,
    output_model=_BlockerInvestigationOut,
    run=_run,
    uses_llm=True,
    llm_calls=["root_cause_analysis"],
    capability_ops=["jira.update", "jira.read", "slack.send", "salesforce.read"],
    agentic=False,
    max_iterations=1,
)

VENDOR_INVESTIGATION_SKILL = SkillDefinition(
    name=VENDOR_INVESTIGATION_SKILL_NAME,
    description="Investigate a vendor incident and propose one governed remediation.",
    input_model=_BlockerInvestigationIn,
    output_model=_BlockerInvestigationOut,
    run=_run_vendor,
    uses_llm=True,
    llm_calls=["root_cause_analysis"],
    capability_ops=[
        "vendor_ticket.create", "vendor_ticket.update",
        "incident.get", "incident.search",
        "jira.update", "slack.send",
        "notification.send_internal", "notification.send_vendor",
    ],
    agentic=False,
    max_iterations=1,
)


def register() -> None:
    """Register the investigation skills explicitly (never via canonical register_all)."""
    from src.mission.skill_registry import SkillRegistry

    SkillRegistry.register(BLOCKER_INVESTIGATION_SKILL)
    SkillRegistry.register(VENDOR_INVESTIGATION_SKILL)
