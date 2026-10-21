"""Control Plane contracts — strict intent/authorization models.

Thin data layer only: no I/O, no LLM, no connector imports.
All models are strict (``extra="forbid"``) so unknown prompt
fields are rejected instead of silently carried through.

Authority boundary (ADR-011)
----------------------------
LLM/agent modules may construct :class:`ActionIntent` ONLY. They must
NEVER instantiate :class:`AuthorizedAction` directly — it is created
exclusively by the control plane via :func:`authorize`
(or ``AuthorizedAction.from_intent``) from a validated intent PLUS
trusted server state (tenant/mission/employee/actor/permissions/
policy/risk). An intent is incapable of asserting its own authority:
it carries no approved/authorized/execute_now/bypass_policy fields,
and any such fields are rejected by ``extra="forbid"``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskTier = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PolicyDecision = Literal["approve", "permit", "require_approval", "deny"]


class ActionIntent(BaseModel):
    """Untrusted action proposal from a planner/agent.

    Identity fields (tenant/mission/employee) and authority fields
    (actor/permissions/policy/risk/idempotency) are deliberately absent:
    they are derived from trusted state in :mod:`authorization`, never
    from prompt output. ``requested_by`` is a claim, not an identity.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    capability: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    requested_parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    expected_outcome: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    requested_by: str = Field(min_length=1)


class AuthorizedAction(BaseModel):
    """Trusted action bound to tenant/mission/employee + policy outcome.

    ARCHITECTURE RULE: LLM/agent modules must NEVER instantiate this
    class. Instances are created ONLY by the control plane
    (:func:`authorization.authorize` via ``from_intent``) which binds a
    validated :class:`ActionIntent` to trusted server-side identity,
    permissions, policy decision, risk tier, and a business-scoped
    idempotency key (``tenant:mission:operation:target:scope`` — never
    thread+sequence).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    capability: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    target_reference: str = Field(min_length=1)
    requested_parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    expected_outcome: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    requested_by: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    employee_id: str = Field(min_length=1)
    actor_identity: str = Field(min_length=1)
    permissions: list[str] = Field(default_factory=list)
    policy_decision: PolicyDecision = "require_approval"
    risk_tier: RiskTier = "MEDIUM"
    idempotency_key: str = Field(min_length=1)
    action_id: str = Field(default="")
    expected_version: int | None = Field(default=None)

    @classmethod
    def from_intent(
        cls,
        intent: ActionIntent,
        *,
        tenant_id: str,
        mission_id: str,
        employee_id: str,
        actor_identity: str,
        permissions: list[str] | None = None,
        policy_decision: PolicyDecision = "require_approval",
        risk_tier: RiskTier = "MEDIUM",
        idempotency_key: str,
        action_id: str = "",
        expected_version: int | None = None,
    ) -> AuthorizedAction:
        """Bind a validated intent to trusted control-plane state.

        The ONLY sanctioned construction path — called by
        :func:`authorization.authorize`, never by LLM/agent code.
        ``expected_version`` is trusted-state only (optimistic concurrency);
        an intent cannot assert it (no such field survives ``extra=forbid``).
        """
        data = intent.model_dump()
        data.update(
            tenant_id=tenant_id,
            mission_id=mission_id,
            employee_id=employee_id,
            actor_identity=actor_identity,
            permissions=list(permissions or []),
            policy_decision=policy_decision,
            risk_tier=risk_tier,
            idempotency_key=idempotency_key,
            action_id=action_id,
            expected_version=expected_version,
        )
        return cls.model_validate(data)
