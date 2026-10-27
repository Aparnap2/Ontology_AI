"""Control Plane verification — thin wrapper over read-back verify.

Delegates to ``src/mission/verify.py``: the write is read back through
its read counterpart and compared against expected state. A mismatch
yields ``verified=False`` plus rollback metadata. Emits the
``BUSINESS_OUTCOME_VERIFIED`` outcome for audit. No connector imports.
"""

from __future__ import annotations

from typing import Any

from src.mission import verify as verify_mod
from src.mission.verify import VerifyOutcome


async def verify_execution(
    op_name: str,
    params: dict[str, Any],
    expected: dict[str, Any],
    tenant_id: str,
    capabilities: Any,
    role_caps: list[str] | None = None,
    result: Any = None,
) -> VerifyOutcome:
    """Read-back verify a write (delegated to ``verify.verify_write``).

    When the caller supplies no explicit expectations, predicates are
    derived from the write itself; underivable expectations fail closed
    downstream (INDETERMINATE), never as silent success.
    """
    caller_supplied = bool(expected)
    effective = dict(expected) if expected else verify_mod.derive_expected(
        op_name, params, result
    )
    outcome = await verify_mod.verify_write(
        op_name, params, effective, tenant_id,
        capabilities=capabilities, role_caps=role_caps, result=result,
    )
    labelled = verify_mod.label_expectation_source(outcome, explicit=caller_supplied)
    return labelled if labelled is not None else outcome


def outcome_event(action_id: str, outcome: VerifyOutcome) -> dict[str, Any]:
    """Project a verify outcome onto the auditable outcome event."""
    result = verify_mod.build_action_result(action_id, outcome)
    return {
        "type": "BUSINESS_OUTCOME_VERIFIED",
        "action_id": action_id,
        "verified": outcome.verified,
        "result_id": result.id,
        "summary": result.result_summary,
        # Carried into the audit record so a reader can tell transport
        # fidelity from independent confirmation. Absent expectations mean
        # they were derived from the write, which is the weaker claim.
        "expectation_source": getattr(
            outcome, "expectation_source", "derived_from_write"
        ),
    }
