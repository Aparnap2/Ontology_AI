"""Verify — read-back verification of governed writes.

After a write op executes, the runtime reads the record back through the op's
read counterpart and compares it against the expected state. A mismatch yields
``verified=False`` plus rollback metadata; the runtime then blocks downstream
steps. Every verification produces a frozen :class:`ActionResult` for audit.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from pydantic import model_validator

from src.entities.models import ActionResult, OntologyBaseModel

logger = logging.getLogger(__name__)

VerifyState = Literal[
    "VERIFIED", "NOT_VERIFIED", "PARTIALLY_VERIFIED", "INDETERMINATE", "RETRYABLE_FAILURE",
]

# Write op → read-back counterpart.
# Vendor writes intentionally have NO read counterpart — they use the
# vendor-specific ``incident.verify_recovery`` path instead (fail-closed,
# never silent pass).  See test_vendor_writes_have_no_silent_verify.
READ_COUNTERPART: dict[str, str] = {
    "salesforce.update": "salesforce.read",
    "jira.update": "jira.read",
    "jira.create": "jira.read",
    "notion.update": "notion.read",
    "slack.send": "slack.search",
}


class VerifyOutcome(OntologyBaseModel):
    """The outcome of a read-back verification.

    ``state`` carries the precise outcome; ``verified`` stays True only for
    full VERIFIED (existing readers keep working). When ``state`` is omitted
    it is derived from ``verified`` so every historical constructor keeps
    its meaning.
    """

    verified: bool = False
    verified_by: str = "EmployeeRuntime.verify"
    rollback_metadata: dict[str, Any] = {}
    mismatch: str | None = None
    state: VerifyState | None = None

    @model_validator(mode="after")
    def _sync_state(self) -> "VerifyOutcome":
        if self.state is None:
            object.__setattr__(self, "state", "VERIFIED" if self.verified else "NOT_VERIFIED")
        else:
            object.__setattr__(self, "verified", self.state == "VERIFIED")
        return self


def _read_params_for(
    op_name: str, params: dict[str, Any], result: Any = None
) -> dict[str, Any]:
    """Derive the read-back params from the write params (plus write result)."""
    if op_name == "salesforce.update":
        return {"object_type": "opportunity", "record_id": params.get("record_id")}
    if op_name == "jira.update":
        return {"jql": f"key = {params.get('issue_id', '')}"}
    if op_name == "jira.create":
        key = result if isinstance(result, str) else params.get("issue_id", "")
        return {"jql": f"key = {key}"}
    if op_name == "notion.update":
        return {"page_id": params.get("page_id")}
    if op_name == "slack.send":
        return {"channel": params.get("channel", ""), "query": str(params.get("text", ""))[:80]}
    return dict(params)


def derive_expected(
    op_name: str, params: dict[str, Any], result: Any = None
) -> dict[str, Any]:
    """Derive expected read-back predicates from a write (no LLM, no I/O).

    Used when the caller supplies no explicit expectations. Returns {}
    when nothing derivable exists — the caller must then fail closed
    (INDETERMINATE), never silently pass.
    """
    fields = params.get("fields")
    if op_name in ("jira.update", "salesforce.update") and isinstance(fields, dict):
        return dict(fields)
    if op_name == "notion.update" and isinstance(params.get("data"), dict):
        return dict(params["data"])
    if op_name == "jira.create" and isinstance(result, str) and result:
        return {"key": result}
    return {}


def _first_record(data: Any) -> dict[str, Any] | None:
    """Extract the first record from an op result payload."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else None
    return None


async def verify_write(
    op_name: str,
    params: dict[str, Any],
    expected: dict[str, Any],
    tenant_id: str,
    *,
    capabilities: Any,
    role_caps: list[str] | None = None,
    result: Any = None,
) -> VerifyOutcome:
    """Verify a write by reading it back through the op's read counterpart.

    An empty ``expected`` fails closed as INDETERMINATE — the absence of
    expectations is never evidence of success. ``result`` (the write's
    returned data) keys read-backs for ops like ``jira.create`` whose
    record id is minted at write time.
    """
    read_op = READ_COUNTERPART.get(op_name)
    if read_op is None:
        return VerifyOutcome(
            verified=False,
            rollback_metadata={
                "op": op_name,
                "reason": f"no read counterpart for {op_name}",
            },
        )
    if not expected:
        return VerifyOutcome(
            state="INDETERMINATE",
            rollback_metadata={
                "capability": op_name,
                "reason": "empty expected predicates: refusing to verify",
            },
        )
    try:
        read_back = capabilities.execute(
            read_op, _read_params_for(op_name, params, result),
            tenant_id, role_caps=role_caps,
        )
        payload = read_back.get("data", read_back) if isinstance(read_back, dict) else read_back
        record = _first_record(payload)
        if record is None:
            return VerifyOutcome(
                state="NOT_VERIFIED",
                mismatch="record",
                rollback_metadata={
                    "capability": op_name,
                    "read_op": read_op,
                    "expected": expected,
                    "read_back": None,
                    "reason": "read-back returned no record",
                },
            )
        bad = [key for key, value in expected.items() if record.get(key) != value]
        if not bad:
            return VerifyOutcome(state="VERIFIED")
        good = [key for key in expected if key not in bad]
        state: VerifyState = "PARTIALLY_VERIFIED" if good else "NOT_VERIFIED"
        return VerifyOutcome(
            state=state,
            mismatch=bad[0],
            rollback_metadata={
                "capability": op_name,
                "read_op": read_op,
                "record_id": params.get("record_id") or params.get("issue_id")
                or params.get("page_id") or params.get("channel"),
                "expected": expected,
                "read_back": record,
                "reason": f"read-back mismatch on {bad[0]}",
            },
        )
    except Exception as exc:  # noqa: BLE001 — verification must not raise
        logger.warning("verify_write failed for %s: %s", op_name, exc)
        retryable = bool(getattr(exc, "retryable", False))
        return VerifyOutcome(
            state="RETRYABLE_FAILURE" if retryable else "NOT_VERIFIED",
            rollback_metadata={"capability": op_name, "error": str(exc)},
        )


def build_action_result(action_id: str, outcome: VerifyOutcome) -> ActionResult:
    """Project a VerifyOutcome onto the frozen ActionResult entity."""
    return ActionResult(
        id=f"ar-{uuid.uuid4().hex[:12]}",
        action_id=action_id,
        result_summary=(
            "verified" if outcome.verified else f"rejected: {outcome.mismatch or 'error'}"
        ),
        output_snapshot={"verified": outcome.verified, "mismatch": outcome.mismatch},
        rollback_metadata=outcome.rollback_metadata,
        verified=outcome.verified,
        verified_by=outcome.verified_by,
    )