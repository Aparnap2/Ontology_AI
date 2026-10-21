"""EmployeeRuntime control-loop tests — the 7 frozen patterns.

Sequential · Parallel · Branch · Loop · Wait/Human-signal · Replan · Verify.
The loop is a single shared interpreter over the 7 patterns — never a
generic workflow engine and never a LangGraph clone.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.mission import capability_ops
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.employee_runtime import (
    EmployeeRuntime,
    InMemorySignalHandler,
    PlanStep,
    StepPattern,
)
from src.mission.skill_contracts import SkillDefinition, SkillInput, SkillOutput
from src.mission.skill_registry import SkillRegistry


class _In(SkillInput):
    """Minimal stub input model."""


class _Out(SkillOutput):
    """Minimal stub output model."""


def make_stub_skill(
    name,
    *,
    record=None,
    sleep=0.0,
    output=None,
    terminal=False,
    confidence=None,
    run_extra=None,
) -> SkillDefinition:
    """Build a deterministic stub skill (registered for the duration of the test)."""

    async def run(ctx, inp) -> _Out:
        if run_extra is not None:
            await run_extra(ctx, inp)
        if sleep:
            await asyncio.sleep(sleep)
        if record is not None:
            record.append(name)
        out = dict(output) if output else {"value": name}
        if terminal:
            out["terminal"] = True
        if confidence is not None:
            out["confidence"] = confidence
        return _Out(**out)

    return SkillDefinition(
        name=name,
        description=name,
        input_model=_In,
        output_model=_Out,
        run=run,
        uses_llm=False,
        capability_ops=[],
        agentic=False,
    )


def test_role(*skills, caps=None) -> EmployeeRoleConfig:
    """A config-driven role allowing exactly the given stub skills."""
    return EmployeeRoleConfig(
        role_id="testrole",
        role="Test Role",
        goals=["test"],
        skills=list(skills),
        capabilities=caps or [],
        permissions=["read"],
        policies=[],
        authority={},
        risk_threshold="MEDIUM",
        kpis=[],
        memory_namespace="testrole",
        mission_types=["test_mission"],
        persona="test",
    )


@pytest.fixture
def skills_registry():
    """Snapshot + restore the real SkillRegistry around each test."""
    snapshot = dict(SkillRegistry._skills)
    yield SkillRegistry
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)


class TestSequential:
    async def test_sequential_order_preserved(self, skills_registry):
        """Sequential steps run in declared order, each awaiting the previous."""
        order: list[str] = []
        for name in ("stub-a", "stub-b", "stub-c"):
            skills_registry.register(make_stub_skill(name, record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        role = test_role("stub-a", "stub-b", "stub-c")
        plan = [
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-a", id="1"),
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-b", id="2"),
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-c", id="3"),
        ]
        result = await runtime.run_plan(plan, role)
        assert order == ["stub-a", "stub-b", "stub-c"]
        assert result.status != "failed"


class TestParallel:
    async def test_parallel_fanout_executes_concurrently(self, skills_registry):
        """Parallel steps fan out to concurrent skill runs and join before the next phase."""
        results: list[str] = []
        for name in ("stub-p1", "stub-p2", "stub-p3"):
            skills_registry.register(make_stub_skill(name, record=results, sleep=0.05))
        runtime = EmployeeRuntime(tenant_id="t1")
        role = test_role("stub-p1", "stub-p2", "stub-p3")
        plan = [
            PlanStep(
                pattern=StepPattern.PARALLEL,
                skills=["stub-p1", "stub-p2", "stub-p3"],
                id="p",
            ),
        ]
        t0 = time.monotonic()
        result = await runtime.run_plan(plan, role)
        elapsed = time.monotonic() - t0
        # Serial execution would take >= 0.15s (3 x 0.05). Concurrent joins under that.
        assert set(results) == {"stub-p1", "stub-p2", "stub-p3"}
        assert elapsed < 0.13, f"fan-out was not concurrent: {elapsed:.3f}s"
        assert result.status != "failed"


class TestBranch:
    async def test_branch_selects_next_skill(self, skills_registry):
        """A branch step selects the next skill from the prior step's output value."""
        order: list[str] = []
        skills_registry.register(
            make_stub_skill("stub-decide", output={"risk": "high"}, record=order)
        )
        skills_registry.register(make_stub_skill("stub-escalate", record=order))
        skills_registry.register(make_stub_skill("stub-continue", record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        role = test_role("stub-decide", "stub-escalate", "stub-continue")
        plan = [
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-decide", id="1"),
            PlanStep(
                pattern=StepPattern.BRANCH,
                condition="risk",
                branches={"high": "stub-escalate", "low": "stub-continue"},
                id="2",
            ),
        ]
        result = await runtime.run_plan(plan, role)
        assert "stub-escalate" in order
        assert "stub-continue" not in order
        assert result.status != "failed"


class TestLoop:
    async def test_bounded_loop_terminates_at_max_iterations(self, skills_registry):
        """A loop step repeats the skill at most max_iterations times (bounded)."""
        count = {"n": 0}

        async def run(ctx, inp) -> _Out:
            count["n"] += 1
            return _Out(value="never-terminal")

        skills_registry.register(
            SkillDefinition(
                name="stub-loop",
                description="loop stub",
                input_model=_In,
                output_model=_Out,
                run=run,
                uses_llm=False,
                capability_ops=[],
                agentic=True,
                max_iterations=5,
            )
        )
        runtime = EmployeeRuntime(tenant_id="t1")
        role = test_role("stub-loop")
        plan = [
            PlanStep(pattern=StepPattern.LOOP, skill="stub-loop", max_iterations=5, id="L"),
        ]
        await runtime.run_plan(plan, role)
        assert count["n"] == 5


class TestReplan:
    async def test_replan_on_low_confidence(self, skills_registry):
        """A replan step re-evaluates on low confidence and emits a replanned event."""
        order: list[str] = []
        skills_registry.register(make_stub_skill("stub-orig", record=order, confidence=0.2))
        skills_registry.register(make_stub_skill("stub-replan-a", record=order))
        skills_registry.register(make_stub_skill("stub-replan-b", record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        role = test_role("stub-orig", "stub-replan-a", "stub-replan-b")
        plan = [
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-orig", id="1"),
            PlanStep(
                pattern=StepPattern.REPLAN,
                id="2",
                params={"confidence_threshold": 0.5},
            ),
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-replan-a", id="3"),
        ]
        result = await runtime.run_plan(plan, role)
        assert "stub-replan-a" in order
        assert "stub-replan-b" in order
        assert any(e.get("type") == "mission_replanned" for e in result.events)


class TestVerify:
    @pytest.fixture
    def mock_store(self, monkeypatch):
        """Point the real capability resolver at an in-memory CRM store."""
        store: dict[str, dict] = {"d-1": {"stage": "discovery", "amount": 1000}}

        class MockCap:
            def get_deals(self):
                return [store["d-1"]]

            def get_customers(self):
                return []

            def update_deal(self, deal_id, fields):
                store[deal_id] = {**store.get(deal_id, {}), **fields}
                return store[deal_id]

            def get_messages(self, channel, **filters):
                return []

            def send_message(self, channel, text):
                return {"ok": True, "channel": channel}

            def get_issues(self, **filters):
                return []

            def create_issue(self, data):
                return "X-1"

            def update_issue(self, issue_id, fields):
                return {"ok": True}

            def get_pages(self, **filters):
                return []

            def update_page(self, page_id, data):
                return {"ok": True}

        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: MockCap())
        capability_ops.CapabilityOpRegistry._ops.clear()
        return store

    @pytest.fixture
    def mock_failing_store(self, monkeypatch):
        """A store whose write op is a no-op — read-back will mismatch."""

        class FailingCap:
            def get_deals(self):
                return [{"id": "d-1", "stage": "discovery"}]

            def get_customers(self):
                return []

            def update_deal(self, deal_id, fields):
                return {"id": deal_id, "stage": "discovery"}  # write silently lost

            def get_messages(self, channel, **filters):
                return []

            def send_message(self, channel, text):
                return {"ok": True}

            def get_issues(self, **filters):
                return []

            def create_issue(self, data):
                return "X-1"

            def update_issue(self, issue_id, fields):
                return {"ok": True}

            def get_pages(self, **filters):
                return []

            def update_page(self, page_id, data):
                return {"ok": True}

        monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: FailingCap())
        capability_ops.CapabilityOpRegistry._ops.clear()
        return None

    def _writer_skill(self, name="stub-writer"):
        """Skill whose run performs a governed write via the capability layer."""

        async def run(ctx, inp) -> _Out:
            await ctx.run_capability(
                "salesforce.update",
                {"record_id": "d-1", "fields": {"stage": "closing"}},
            )
            return _Out(written=True)

        return SkillDefinition(
            name=name,
            description="writer stub",
            input_model=_In,
            output_model=_Out,
            run=run,
            uses_llm=False,
            capability_ops=["salesforce.update"],
            agentic=False,
        )

    def _verify_plan(self):
        return [
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-writer", id="1"),
            PlanStep(
                pattern=StepPattern.VERIFY,
                id="2",
                action={
                    "capability": "salesforce.update",
                    "params": {"record_id": "d-1", "fields": {"stage": "closing"}},
                    "expected": {"stage": "closing"},
                },
            ),
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-downstream", id="3"),
        ]

    async def test_verify_pass(self, skills_registry, mock_store):
        """Read-back matching the write sets verified=True and downstream runs."""
        order: list[str] = []
        skills_registry.register(self._writer_skill())
        skills_registry.register(make_stub_skill("stub-downstream", record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        # A role that can write must also be able to READ, otherwise it
        # cannot verify its own write: verify.py performs read-back through
        # READ_COUNTERPART (salesforce.update -> salesforce.read) and the
        # capability registry correctly denies an absent allowlist. Shipped
        # configs pair them (config/employees.yaml). Previously this passed
        # only because assert_allowed treated a missing allowlist as
        # "unrestricted" — the read-back ran under no authority at all.
        # See tests/test_p0_verify_readback_authority.py.
        role = test_role(
            "stub-writer",
            "stub-downstream",
            caps=["salesforce.update", "salesforce.read"],
        )
        result = await runtime.run_plan(self._verify_plan(), role)
        assert "stub-downstream" in order
        assert any(ar.get("verified") is True for ar in result.action_results)

    async def test_verify_rejection_blocks_downstream_write(self, skills_registry, mock_failing_store):
        """Read-back mismatch halts execution: verified=False + rollback metadata, no downstream."""
        order: list[str] = []
        skills_registry.register(self._writer_skill())
        skills_registry.register(make_stub_skill("stub-downstream", record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        # A role that can write must also be able to READ, otherwise it
        # cannot verify its own write: verify.py performs read-back through
        # READ_COUNTERPART (salesforce.update -> salesforce.read) and the
        # capability registry correctly denies an absent allowlist. Shipped
        # configs pair them (config/employees.yaml). Previously this passed
        # only because assert_allowed treated a missing allowlist as
        # "unrestricted" — the read-back ran under no authority at all.
        # See tests/test_p0_verify_readback_authority.py.
        role = test_role(
            "stub-writer",
            "stub-downstream",
            caps=["salesforce.update", "salesforce.read"],
        )
        result = await runtime.run_plan(self._verify_plan(), role)
        assert "stub-downstream" not in order
        rejected = [ar for ar in result.action_results if ar.get("verified") is False]
        assert rejected, "expected at least one rejected action result"
        assert rejected[0]["rollback_metadata"], "rollback metadata must be populated"


class TestWaitHumanSignal:
    async def test_wait_human_signal_emits_and_resumes(self, skills_registry):
        """A WAIT step emits hitl-approval and resumes after the human decision."""
        order: list[str] = []
        skills_registry.register(make_stub_skill("stub-pre", record=order))
        skills_registry.register(make_stub_skill("stub-post", record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        handler = runtime.signal_handler
        role = test_role("stub-pre", "stub-post")
        plan = [
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-pre", id="1"),
            PlanStep(
                pattern=StepPattern.WAIT,
                id="2",
                params={"reason": "founder review", "signal": "hitl-approval"},
            ),
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-post", id="3"),
        ]
        task = asyncio.create_task(runtime.run_plan(plan, role))
        for _ in range(200):
            if handler.emitted:
                break
            await asyncio.sleep(0.01)
        assert handler.emitted, "runtime never emitted the hitl-approval signal"
        assert handler.emitted[0][0] == "hitl-approval"
        handler.resolve({"approved": True, "decision": "approved"})
        result = await task
        assert order == ["stub-pre", "stub-post"]
        assert result.status != "failed"

    async def test_wait_signal_rejection_stops_plan(self, skills_registry):
        """A rejected human decision halts the plan before the gated step."""
        order: list[str] = []
        skills_registry.register(make_stub_skill("stub-pre", record=order))
        skills_registry.register(make_stub_skill("stub-blocked", record=order))
        runtime = EmployeeRuntime(tenant_id="t1")
        handler = runtime.signal_handler
        role = test_role("stub-pre", "stub-blocked")
        plan = [
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-pre", id="1"),
            PlanStep(
                pattern=StepPattern.WAIT,
                id="2",
                params={"signal": "hitl-approval", "on_reject": "stop"},
            ),
            PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-blocked", id="3"),
        ]
        task = asyncio.create_task(runtime.run_plan(plan, role))
        for _ in range(200):
            if handler.emitted:
                break
            await asyncio.sleep(0.01)
        handler.resolve({"approved": False, "decision": "rejected"})
        result = await task
        assert "stub-blocked" not in order
        assert any(e.get("type") == "mission_interrupted" for e in result.events)


class TestRuntimeConstruction:
    def test_default_signal_handler_is_in_memory(self):
        """The runtime ships an in-memory signal handler (Temporal binds later)."""
        runtime = EmployeeRuntime(tenant_id="t1")
        assert isinstance(runtime.signal_handler, InMemorySignalHandler)

    def test_runtime_rejects_unknown_skill_in_plan(self, skills_registry):
        """A plan step referencing a skill outside the role allowlist is rejected."""
        skills_registry.register(make_stub_skill("stub-ok"))
        runtime = EmployeeRuntime(tenant_id="t1")
        role = test_role("stub-ok")
        plan = [PlanStep(pattern=StepPattern.SEQUENTIAL, skill="stub-unknown", id="1")]
        with pytest.raises(Exception):
            asyncio.get_event_loop().run_until_complete(runtime.run_plan(plan, role))