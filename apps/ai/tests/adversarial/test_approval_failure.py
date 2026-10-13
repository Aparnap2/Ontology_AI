"""C2 approval failure — reject + timeout semantics (Sprint C).

RED-first: HIGH-risk reject → zero execution, key unmarked (explicit
re-approval can still proceed, never silently); identical resubmit must NOT
auto-execute. Timeout honors ``trusted_context["approval_timeout_seconds"]``
(default: wait indefinitely); on timeout ingress returns audited
``deny:approval_expired`` with no execution, and a later ``resolve()``
cannot resurrect it (replay still denied/duplicate-safe).

Mock conventions: monkeypatched ``capability_ops._resolve_capability`` +
``_ops.clear()``, ``ingress._seen`` + ``AUDIT_LOG`` reset per test,
SkillRegistry snapshot/restore, ``asyncio_mode=auto``.
"""
from __future__ import annotations

import asyncio

import pytest

from src.control_plane import audit as audit_mod
from src.control_plane import ingress as ingress_mod
from src.control_plane.contracts import ActionIntent
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    make_blocker_investigation_role,
    reset_idempotency,
)
from src.mission.signal_handler import InMemorySignalHandler
from src.mission.skill_registry import SkillRegistry


class MockCap:
    def __init__(self) -> None:
        self.store = {"PROJ-1": {"key": "PROJ-1", "status": "Blocked"}}
        self.update_calls: list[tuple[str, dict]] = []

    def update_issue(self, issue_id, fields):
        self.update_calls.append((issue_id, dict(fields)))
        self.store[issue_id] = {**self.store.get(issue_id, {}), **fields}
        return {"id": issue_id, **self.store[issue_id]}

    def get_issues(self, **kwargs):
        jql = str(kwargs.get("jql", ""))
        key = jql.split("=")[-1].strip() if "=" in jql else ""
        rec = self.store.get(key)
        return [dict(rec)] if rec else []


@pytest.fixture(autouse=True)
def _clean():
    reset_idempotency()
    snapshot = dict(SkillRegistry._skills)
    yield
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)
    reset_idempotency()


@pytest.fixture
def mock_cap(monkeypatch):
    cap = MockCap()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    capability_ops.CapabilityOpRegistry._ops.clear()
    return cap


def _high_intent() -> ActionIntent:
    """A HIGH-risk intent.

    The HIGH tier is NOT carried here. Policy reads risk exclusively from
    trusted state (``role_config.risk_threshold``); a tier inside
    ``requested_parameters`` is attacker-influenced and is ignored. These
    tests previously set it in the intent, so the approval gate they were
    written to exercise was never reached.
    """
    return ActionIntent(
        capability="jira",
        operation="jira.update",
        target_reference="PROJ-1",
        requested_parameters={"issue_id": "PROJ-1", "fields": {"status": "In Progress"}},
        reason="high-risk approval probe",
        evidence_ids=["ev-1"],
        expected_outcome="PROJ-1 moves to In Progress",
        confidence=0.91,
        requested_by="onboarding-ops",
    )


def _trusted(**over):
    base = {
        "tenant_id": "t1",
        "mission_id": "m-c2",
        "employee_id": "onboarding-ops",
        "actor_identity": "system",
        "business_scope": "acme",
    }
    base.update(over)
    return base


async def _submit_with_decision(intent, trusted, role, handler, decision):
    task = asyncio.create_task(
        ingress_mod.submit_intent(
            intent, trusted, role_config=role,
            signal_handler=handler,
            capabilities=capability_ops.CapabilityOpRegistry,
        )
    )
    for _ in range(200):
        if handler._futures:
            break
        await asyncio.sleep(0.01)
    assert handler._futures, "approval signal never emitted"
    handler.resolve(decision)
    return await task


async def test_high_reject_zero_execution(mock_cap):
    """HIGH reject → deny:approval_rejected, audited, zero writes."""
    role = make_blocker_investigation_role(risk_threshold="HIGH")
    handler = InMemorySignalHandler()
    event = await _submit_with_decision(
        _high_intent(), _trusted(), role, handler, {"approved": False}
    )
    assert event["decision"] == "deny:approval_rejected"
    assert mock_cap.update_calls == []
    assert any(e["decision"] == "deny:approval_rejected" for e in audit_mod.list_events())
    assert not any(e["decision"] == "permit:executed" for e in audit_mod.list_events())


async def test_reject_key_unmarked_explicit_reapproval_proceeds(mock_cap):
    """After reject the key stays unmarked: explicit re-approval executes once."""
    role = make_blocker_investigation_role(risk_threshold="HIGH")
    handler1 = InMemorySignalHandler()
    first = await _submit_with_decision(
        _high_intent(), _trusted(), role, handler1, {"approved": False}
    )
    assert first["decision"] == "deny:approval_rejected"
    # Key must NOT be marked — retry is allowed (never silently, only via approval).
    assert len(ingress_mod._seen._seen) == 0
    handler2 = InMemorySignalHandler()
    second = await _submit_with_decision(
        _high_intent(), _trusted(), role, handler2, {"approved": True}
    )
    assert second["decision"] == "permit:executed"
    assert mock_cap.update_calls == [("PROJ-1", {"status": "In Progress"})]


async def test_identical_resubmit_after_reject_does_not_auto_execute(mock_cap):
    """Identical resubmit without approval must NOT auto-execute."""
    role = make_blocker_investigation_role(risk_threshold="HIGH")
    handler1 = InMemorySignalHandler()
    first = await _submit_with_decision(
        _high_intent(), _trusted(), role, handler1, {"approved": False}
    )
    assert first["decision"] == "deny:approval_rejected"
    # Same intent, no handler → must not permit; idempotency/deny semantics hold.
    event = await ingress_mod.submit_intent(
        _high_intent(), _trusted(), role_config=role,
        signal_handler=None,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] != "permit:executed"
    assert event["decision"] == "require_approval:no_handler"
    assert mock_cap.update_calls == []


async def test_approval_timeout_deny_no_execution(mock_cap):
    """approval_timeout_seconds elapses → audited deny:approval_expired, no write."""
    role = make_blocker_investigation_role(risk_threshold="HIGH")
    handler = InMemorySignalHandler()
    event = await ingress_mod.submit_intent(
        _high_intent(),
        _trusted(approval_timeout_seconds=0.05),
        role_config=role,
        signal_handler=handler,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert event["decision"] == "deny:approval_expired"
    assert mock_cap.update_calls == []
    assert any(e["decision"] == "deny:approval_expired" for e in audit_mod.list_events())


async def test_timeout_cannot_be_resurrected_replay_still_denied(mock_cap):
    """Late resolve() after timeout cannot resurrect; replay stays denied."""
    role = make_blocker_investigation_role(risk_threshold="HIGH")
    handler = InMemorySignalHandler()
    first = await ingress_mod.submit_intent(
        _high_intent(),
        _trusted(approval_timeout_seconds=0.05),
        role_config=role,
        signal_handler=handler,
        capabilities=capability_ops.CapabilityOpRegistry,
    )
    assert first["decision"] == "deny:approval_expired"
    # Late human approval must not resurrect the timed-out intent.
    handler.resolve({"approved": True})
    await asyncio.sleep(0.01)
    assert mock_cap.update_calls == []
    # Replay the same intent → still denied (duplicate-safe), never permitted.
    handler2 = InMemorySignalHandler()
    task = asyncio.create_task(
        ingress_mod.submit_intent(
            _high_intent(), _trusted(approval_timeout_seconds=5),
            role_config=role, signal_handler=handler2,
            capabilities=capability_ops.CapabilityOpRegistry,
        )
    )
    await asyncio.sleep(0.05)
    # Either duplicate-safe deny (preferred) or a fresh approval pause; in
    # neither case may it have executed without a fresh approval.
    if handler2._futures:
        handler2.resolve({"approved": False})
    replay = await task
    assert replay["decision"] in ("deny:duplicate", "deny:approval_rejected")
    assert mock_cap.update_calls == []
