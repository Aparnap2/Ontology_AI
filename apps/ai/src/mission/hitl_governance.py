"""HITL Governance — 6-level hierarchy for vendor operation approval.

Maps operation types to governance levels based on blast radius and risk.
Classifies operations, evaluates approval requests, and supports mission
modification/redirect with full audit trails.

No I/O, no LLM calls, no wall clock — pure deterministic logic.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── Governance Levels ─────────────────────────────────────────────────


class GovernanceLevel(str, enum.Enum):
    """6-level governance hierarchy for vendor operations.

    L1_AUTO:     No approval, auto-execute (reads/searches).
    L2_NOTIFY:   Execute + notify stakeholders (low-risk writes).
    L3_PEER:     Requires peer review (medium-risk writes).
    L4_MANAGER:  Requires manager approval (high-risk writes).
    L5_DIRECTOR: Requires director/C-level (financial writes, unknown ops).
    L6_BOARD:    Requires board/external approval.
    """

    L1_AUTO = "L1_AUTO"
    L2_NOTIFY = "L2_NOTIFY"
    L3_PEER = "L3_PEER"
    L4_MANAGER = "L4_MANAGER"
    L5_DIRECTOR = "L5_DIRECTOR"
    L6_BOARD = "L6_BOARD"


# ── Operation Classification Rules ────────────────────────────────────

# Maps operation type prefix → governance level.
# More specific prefixes are checked first (longest prefix match).
_OPERATION_RULES: list[tuple[str, GovernanceLevel]] = [
    # L1: Reads / searches
    ("read", GovernanceLevel.L1_AUTO),
    ("search", GovernanceLevel.L1_AUTO),
    ("get", GovernanceLevel.L1_AUTO),
    ("list", GovernanceLevel.L1_AUTO),
    ("query", GovernanceLevel.L1_AUTO),
    ("fetch", GovernanceLevel.L1_AUTO),
    # L2: Low-risk writes
    ("jira.update", GovernanceLevel.L2_NOTIFY),
    ("vendor_ticket.create", GovernanceLevel.L2_NOTIFY),
    ("vendor_ticket.update", GovernanceLevel.L2_NOTIFY),
    ("note.create", GovernanceLevel.L2_NOTIFY),
    ("note.update", GovernanceLevel.L2_NOTIFY),
    # L3: Medium-risk writes
    ("notification.send_internal", GovernanceLevel.L3_PEER),
    ("notification.send_team", GovernanceLevel.L3_PEER),
    # L4: High-risk writes
    ("notification.send_vendor", GovernanceLevel.L4_MANAGER),
    ("notification.send_external", GovernanceLevel.L4_MANAGER),
    ("vendor.escalate", GovernanceLevel.L4_MANAGER),
    ("vendor.revoke", GovernanceLevel.L4_MANAGER),
    # L5: Financial writes
    ("payment", GovernanceLevel.L5_DIRECTOR),
    ("refund", GovernanceLevel.L5_DIRECTOR),
    ("invoice", GovernanceLevel.L5_DIRECTOR),
    ("transfer", GovernanceLevel.L5_DIRECTOR),
    ("financial", GovernanceLevel.L5_DIRECTOR),
    # L6: Board-level
    ("board", GovernanceLevel.L6_BOARD),
    ("policy.change", GovernanceLevel.L6_BOARD),
    ("contract.sign", GovernanceLevel.L6_BOARD),
]


def classify_governance_level(
    operation: str,
    context: dict[str, Any] | None = None,
) -> GovernanceLevel:
    """Map an operation type to a governance level based on blast radius.

    Uses longest-prefix matching against the operation classification rules.
    Unknown operations default to L5_DIRECTOR (fail conservative).

    Args:
        operation: The operation type string (e.g. "jira.update", "payment.process").
        context: Optional context dict with additional risk signals.

    Returns:
        The governance level for this operation.
    """
    op_lower = operation.lower()

    # Check context overrides first
    if context:
        if context.get("force_level"):
            try:
                return GovernanceLevel(context["force_level"])
            except ValueError:
                logger.warning(
                    "Invalid force_level %r, falling through", context["force_level"]
                )

        if context.get("blast_radius") == "critical":
            return GovernanceLevel.L5_DIRECTOR

    # Longest-prefix match
    best_level: GovernanceLevel | None = None
    best_len = 0
    for prefix, level in _OPERATION_RULES:
        if op_lower.startswith(prefix) and len(prefix) > best_len:
            best_level = level
            best_len = len(prefix)

    if best_level is not None:
        return best_level

    # Unknown → L5 (fail conservative)
    logger.info("Unknown operation %r — defaulting to L5_DIRECTOR", operation)
    return GovernanceLevel.L5_DIRECTOR


# ── Approval Decision Models ──────────────────────────────────────────


class ApprovalDecision(BaseModel):
    """Decision on an approval request.

    For L1: auto-approved immediately.
    For L2–L6: pending with required_approvers list.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    operation: str
    governance_level: GovernanceLevel
    status: str = Field(
        pattern=r"^(auto_approved|pending|approved|rejected)$",
        default="pending",
    )
    required_approvers: list[str] = Field(default_factory=list)
    approved_by: list[str] = Field(default_factory=list)
    rejected_by: list[str] = Field(default_factory=list)
    reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


# ── Approval Evaluation ───────────────────────────────────────────────

_REQUIRED_APPROVERS: dict[GovernanceLevel, list[str]] = {
    GovernanceLevel.L1_AUTO: [],
    GovernanceLevel.L2_NOTIFY: ["stakeholder"],
    GovernanceLevel.L3_PEER: ["peer_reviewer"],
    GovernanceLevel.L4_MANAGER: ["manager"],
    GovernanceLevel.L5_DIRECTOR: ["director", "c_level"],
    GovernanceLevel.L6_BOARD: ["board_member", "legal"],
}


def evaluate_approval_request(
    operation: str,
    governance_level: GovernanceLevel,
    context: dict[str, Any] | None = None,
) -> ApprovalDecision:
    """Evaluate an approval request for a given operation and governance level.

    For L1: returns an auto-approved decision immediately.
    For L2–L6: returns a pending decision with the required approvers list.
    If context already contains approvals, they are recorded.

    Args:
        operation: The operation type string.
        governance_level: The classified governance level.
        context: Optional context with existing approvals.

    Returns:
        An ApprovalDecision reflecting the current approval state.
    """
    required = list(_REQUIRED_APPROVERS.get(governance_level, []))
    existing_approvals: list[str] = list((context or {}).get("approvals", []))
    existing_rejections: list[str] = list((context or {}).get("rejections", []))

    if governance_level == GovernanceLevel.L1_AUTO:
        decision = ApprovalDecision(
            operation=operation,
            governance_level=governance_level,
            status="auto_approved",
            required_approvers=[],
            approved_by=["system"],
        )
        logger.info("Operation %r auto-approved at L1", operation)
        return decision

    # Check for rejections first
    if existing_rejections:
        decision = ApprovalDecision(
            operation=operation,
            governance_level=governance_level,
            status="rejected",
            required_approvers=required,
            rejected_by=existing_rejections,
            reason=f"Rejected by: {', '.join(existing_rejections)}",
        )
        logger.info("Operation %r rejected at %s", operation, governance_level.value)
        return decision

    # Check if all required approvers have approved
    missing = [a for a in required if a not in existing_approvals]
    if not missing and required:
        decision = ApprovalDecision(
            operation=operation,
            governance_level=governance_level,
            status="approved",
            required_approvers=required,
            approved_by=existing_approvals,
        )
        logger.info(
            "Operation %r fully approved at %s", operation, governance_level.value
        )
        return decision

    # Still pending
    decision = ApprovalDecision(
        operation=operation,
        governance_level=governance_level,
        status="pending",
        required_approvers=required,
        approved_by=existing_approvals,
        reason=f"Missing approvers: {', '.join(missing)}"
        if missing
        else "Awaiting approvals",
    )
    logger.info(
        "Operation %r pending at %s — need: %s",
        operation,
        governance_level.value,
        missing,
    )
    return decision


# ── Mission Modification Models ───────────────────────────────────────


class AuditEntry(BaseModel):
    """Single audit trail entry for mission modifications."""

    model_config = ConfigDict(extra="forbid", strict=True)

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    actor: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    previous_value: Any = None
    new_value: Any = None
    reason: str = ""


class MissionSnapshot(BaseModel):
    """Immutable snapshot of a mission at a point in time."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mission_id: str
    target: str
    priority: str = "medium"
    scope: str = ""
    escalation_policy: str = ""
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Modification(BaseModel):
    """A human-initiated modification to a mission."""

    model_config = ConfigDict(extra="forbid", strict=True)

    target: str | None = None
    priority: str | None = None
    scope: str | None = None
    escalation_policy: str | None = None
    status: str | None = None
    reason: str = ""
    actor: str = "human"


class ModifiedMission(BaseModel):
    """Result of applying a modification to a mission, with full audit trail."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mission: MissionSnapshot
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    modification_applied: bool = False


class RedirectedMission(BaseModel):
    """Result of redirecting a mission to a new target, preserving history."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mission: MissionSnapshot
    original_target: str
    redirect_history: list[dict[str, Any]] = Field(default_factory=list)
    audit_trail: list[AuditEntry] = Field(default_factory=list)


# ── Mission Modification ──────────────────────────────────────────────

_MODIFIABLE_FIELDS = ("target", "priority", "scope", "escalation_policy", "status")
_VALID_PRIORITIES = ("low", "medium", "high", "urgent")
_VALID_STATUSES = ("active", "paused", "completed", "failed", "redirected")


def modify_mission(
    mission: MissionSnapshot,
    modification: Modification,
    context: dict[str, Any] | None = None,
) -> ModifiedMission:
    """Apply a human-initiated modification to a mission.

    Validates the modification fields, applies changes, and builds an
    audit trail entry for each field changed.

    Args:
        mission: The current mission snapshot.
        modification: The requested modification.
        context: Optional context (unused, reserved for future use).

    Returns:
        A ModifiedMission with the updated mission and audit trail.

    Raises:
        ValueError: If modification contains invalid field values.
    """
    audit_trail: list[AuditEntry] = list(
        (context or {}).get("existing_audit_trail", [])
    )
    updated = mission.model_copy(deep=True)

    # Validate priority
    if (
        modification.priority is not None
        and modification.priority not in _VALID_PRIORITIES
    ):
        raise ValueError(
            f"Invalid priority {modification.priority!r}; "
            f"must be one of {_VALID_PRIORITIES}"
        )

    # Validate status
    if modification.status is not None and modification.status not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status {modification.status!r}; must be one of {_VALID_STATUSES}"
        )

    changes_made = False
    for field_name in _MODIFIABLE_FIELDS:
        new_value = getattr(modification, field_name)
        if new_value is not None:
            old_value = getattr(updated, field_name)
            if old_value != new_value:
                entry = AuditEntry(
                    action=f"modify_{field_name}",
                    actor=modification.actor,
                    previous_value=old_value,
                    new_value=new_value,
                    reason=modification.reason,
                )
                audit_trail.append(entry)
                setattr(updated, field_name, new_value)
                changes_made = True
                logger.info(
                    "Mission %s: %s changed from %r to %r by %s",
                    mission.mission_id,
                    field_name,
                    old_value,
                    new_value,
                    modification.actor,
                )

    return ModifiedMission(
        mission=updated,
        audit_trail=audit_trail,
        modification_applied=changes_made,
    )


# ── Mission Redirect ──────────────────────────────────────────────────


def redirect_mission(
    mission: MissionSnapshot,
    new_target: str,
    context: dict[str, Any] | None = None,
) -> RedirectedMission:
    """Redirect a mission to a new target, preserving original history.

    Creates a redirect entry in the history and updates the mission target
    while recording the full audit trail.

    Args:
        mission: The current mission snapshot.
        new_target: The new target for the mission.
        context: Optional context with actor info and existing history.

    Returns:
        A RedirectedMission with updated target and preserved history.
    """
    actor = (context or {}).get("actor", "system")
    reason = (context or {}).get("reason", "Mission redirected")
    existing_history: list[dict[str, Any]] = list(
        (context or {}).get("redirect_history", [])
    )
    existing_audit: list[AuditEntry] = list(
        (context or {}).get("existing_audit_trail", [])
    )

    original_target = mission.target

    # Build redirect history entry
    redirect_entry: dict[str, Any] = {
        "from_target": original_target,
        "to_target": new_target,
        "actor": actor,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    redirect_history = existing_history + [redirect_entry]

    # Audit trail
    audit_entry = AuditEntry(
        action="redirect_target",
        actor=actor,
        previous_value=original_target,
        new_value=new_target,
        reason=reason,
    )
    audit_trail = existing_audit + [audit_entry]

    # Update mission
    updated = mission.model_copy(deep=True)
    updated.target = new_target
    updated.status = "redirected"

    logger.info(
        "Mission %s redirected from %r to %r by %s",
        mission.mission_id,
        original_target,
        new_target,
        actor,
    )

    return RedirectedMission(
        mission=updated,
        original_target=original_target,
        redirect_history=redirect_history,
        audit_trail=audit_trail,
    )
