"""Recovery Verification — predicate-based, reject false recovery.

Vendor "fixed" ≠ recovered.  Every recovery claim is checked against
observed system state via predicates.  All must pass; any failure
rejects the recovery.  Empty predicates fail closed (never silent pass).

Pure, deterministic, no I/O, no LLM, no wall clock.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


_OPS = {
    "lt": lambda val, thr: val < thr,
    "lte": lambda val, thr: val <= thr,
    "gt": lambda val, thr: val > thr,
    "gte": lambda val, thr: val >= thr,
    "eq": lambda val, thr: val == thr,
    "neq": lambda val, thr: val != thr,
}


class RecoveryPredicate(BaseModel):
    """One predicate against observed system state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    field: str = Field(min_length=1)
    op: str = Field(min_length=1)
    threshold: float


class RecoveryOutcome(BaseModel):
    """Result of evaluating recovery predicates."""

    model_config = ConfigDict(extra="forbid", strict=True)

    verified: bool
    incident_id: str = ""
    mismatches: list[str] = Field(default_factory=list)
    passed: list[str] = Field(default_factory=list)


def evaluate_predicates(
    predicates: list[RecoveryPredicate],
    observed: dict[str, Any],
) -> RecoveryOutcome:
    """Evaluate all predicates against observed state.  All must pass.

    Empty predicates → fail closed (no_predicates mismatch).
    Unknown operator → fail closed (unknown_op:<op> mismatch).
    Missing field → fail closed (missing:<field> mismatch).
    """
    if not predicates:
        return RecoveryOutcome(verified=False, mismatches=["no_predicates"])

    mismatches: list[str] = []
    passed: list[str] = []

    for pred in predicates:
        fn = _OPS.get(pred.op)
        if fn is None:
            mismatches.append(f"unknown_op:{pred.op}")
            continue
        val = observed.get(pred.field)
        if val is None:
            mismatches.append(f"missing:{pred.field}")
            continue
        try:
            if fn(float(val), pred.threshold):
                passed.append(pred.field)
            else:
                mismatches.append(pred.field)
        except (TypeError, ValueError):
            mismatches.append(pred.field)

    return RecoveryOutcome(verified=not mismatches, mismatches=mismatches, passed=passed)


def verify_recovery(
    incident: dict[str, Any],
    predicates: list[RecoveryPredicate],
    observed: dict[str, Any],
) -> RecoveryOutcome:
    """Top-level recovery verification: predicates against observed state.

    The incident's own status is informational only — vendor claims are
    never trusted.  Only predicates decide.
    """
    outcome = evaluate_predicates(predicates, observed)
    return RecoveryOutcome(
        verified=outcome.verified,
        incident_id=incident.get("id", ""),
        mismatches=outcome.mismatches,
        passed=outcome.passed,
    )
