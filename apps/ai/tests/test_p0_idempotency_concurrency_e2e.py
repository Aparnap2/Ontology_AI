"""P0: at-most-once through the real ingress path, not just the guard.

Complements test_p0_idempotency_atomicity.py, which exercises SeenSet
directly. This drives submit_intent, so the claim/commit/release wiring
in ingress.py is covered end to end.

Proven exploit this closes: four concurrent submissions of one key each
performed a side effect, because ingress checked at :84 and only marked
at :136 after execution.
"""
import asyncio
import time

import pytest
from src.control_plane.contracts import ActionIntent
from src.control_plane.idempotency import reset_seen
from src.control_plane.ingress import submit_intent
import src.control_plane.ingress as ing

EXECUTIONS = []

def _intent():
    return ActionIntent(capability="vendor", operation="vendor_ticket.create",
        target_reference="v1", requested_parameters={"vendor_id":"v1","incident_id":"i1"},
        reason="r", evidence_ids=[], expected_outcome="ticket", confidence=0.9,
        requested_by="p")

def _trusted(mid):
    return {"tenant_id":"t1","mission_id":mid,"employee_id":"e1",
            "actor_identity":"sys","permissions":["vendor_ticket.create"]}

@pytest.mark.parametrize("n", [2, 4, 10, 100])
def test_at_most_one_execution_under_concurrency(monkeypatch, n):
    reset_seen()
    EXECUTIONS.clear()
    def slow_execute(authorized, role_caps=None):
        # executor.execute is synchronous (ingress does not await it), so this
        # models the mutation window as a blocking call.
        EXECUTIONS.append(authorized.idempotency_key)
        time.sleep(0.02)
        return {"ok": True}
    monkeypatch.setattr(ing, "_execute", slow_execute)
    async def run():
        return await asyncio.gather(*(submit_intent(_intent(), _trusted("m1")) for _ in range(n)))
    results = asyncio.run(run())
    decisions = [r.get("decision") for r in results]
    print(f"n={n} executions={len(EXECUTIONS)} decisions={set(decisions)}")
    assert len(EXECUTIONS) == 1, f"n={n}: {len(EXECUTIONS)} executions for one key"
    assert decisions.count("permit:executed") == 1
    assert decisions.count("deny:duplicate") == n - 1

def test_different_missions_execute_independently(monkeypatch):
    reset_seen()
    EXECUTIONS.clear()
    def slow_execute(authorized, role_caps=None):
        EXECUTIONS.append(authorized.mission_id)
        time.sleep(0.01)
        return {"ok": True}
    monkeypatch.setattr(ing, "_execute", slow_execute)
    async def run():
        return await asyncio.gather(submit_intent(_intent(), _trusted("mA")),
                                    submit_intent(_intent(), _trusted("mB")))
    asyncio.run(run())
    assert sorted(EXECUTIONS) == ["mA", "mB"], f"expected 2 independent executions, got {EXECUTIONS}"
