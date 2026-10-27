"""Sprint D contracts — missions are configuration over one shared runtime.

Proves: new analyst/mission = YAML + typed config (no agent class, no new
runtime, no executor path); fail-closed allowlists; anyone changing the
registry Contract breaks these loudly.
"""
from __future__ import annotations

import pytest
import yaml

from src.mission.employee_role_registry import EmployeeRoleRegistry
from src.mission.employee_runtime import EmployeeRuntime
from src.mission.mission_config import (
    MissionNotAllowedError,
    MissionRegistry,
    MissionSpec,
)
from src.mission.skill_contracts import SkillDefinition, SkillInput, SkillOutput
from src.mission.skill_registry import SkillRegistry

ONBOARDING_MISSIONS = [
    "m-handoff-validation-01",
    "m-kickoff-prep-01",
    "m-blocked-work-01",
    "m-milestone-recovery-01",
    "m-process-drift-01",
    "m-readiness-review-01",
]


class _In(SkillInput):
    pass


class _Out(SkillOutput):
    pass


def _stub_skill(name: str, ops: list[str] | None = None) -> SkillDefinition:
    async def run(ctx, inp) -> _Out:
        return _Out()

    return SkillDefinition(
        name=name, description="config-proof stub", input_model=_In,
        output_model=_Out, run=run, uses_llm=False,
        capability_ops=list(ops or []), agentic=False,
    )


@pytest.fixture(autouse=True)
def _clean():
    snapshot = dict(SkillRegistry._skills)
    yield
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)


def _role(role_id: str):
    return EmployeeRoleRegistry.get_role(role_id)


# ── One contract test per canonical onboarding mission ───────────────────


@pytest.mark.parametrize("mission_id", ONBOARDING_MISSIONS)
def test_onboarding_mission_contract(mission_id):
    """Each canonical mission: typed fields present, gates admit it."""
    spec = MissionRegistry.get(mission_id)
    role = _role(spec.employee_role)
    assert spec.goal, f"{mission_id} needs an explicit goal"
    assert spec.trigger_types, f"{mission_id} needs trigger_types"
    assert spec.required_context, f"{mission_id} needs required_context"
    assert spec.success_criteria, f"{mission_id} needs success_criteria"
    assert spec.approval_policy in {"auto", "approval_required", "read_only"}
    assert spec.mission_type in role.mission_types
    assert set(spec.effective_skills()) <= set(role.skills)
    assert not spec.missing_context({k: "x" for k in spec.required_context})


def test_for_trigger_selects_missions():
    """Trigger routing resolves specs without mission-specific code."""
    assert {s.id for s in MissionRegistry.for_trigger("jira.blocked")} == {"m-blocked-work-01"}
    assert {s.id for s in MissionRegistry.for_trigger("salesforce.closed_won")} == {
        "m-handoff-validation-01"
    }
    assert MissionRegistry.for_trigger("no.such.event") == []


# ── Configuration-only addition ──────────────────────────────────────────

async def test_adding_employee_requires_configuration_only():
    """A new analyst is a YAML dict → EmployeeRoleConfig → run_plan. No class."""
    order: list[str] = []

    async def run(ctx, inp) -> _Out:
        order.append("config-probe")
        return _Out()

    SkillRegistry.register(
        SkillDefinition(
            name="config_probe_skill", description="probe", input_model=_In,
            output_model=_Out, run=run, uses_llm=False, agentic=False,
        )
    )
    role_dict = yaml.safe_load(
        """
        role_id: probe-analyst
        role: Probe Analyst
        goals: [prove config-only]
        skills: [config_probe_skill]
        capabilities: []
        permissions: [read]
        policies: []
        authority: {}
        risk_threshold: LOW
        kpis: []
        memory_namespace: probe
        mission_types: [probe_mission]
        """
    )
    from src.mission.employee_role_config import EmployeeRoleConfig

    role = EmployeeRoleConfig(**role_dict)
    runtime = EmployeeRuntime(tenant_id="t1")
    from src.mission.plan import PlanStep, StepPattern

    result = await runtime.run_plan(
        [PlanStep(pattern=StepPattern.SEQUENTIAL, skill="config_probe_skill", id="1")],
        role,
    )
    assert order == ["config-probe"]
    assert result.status == "completed"


async def test_all_missions_use_shared_runtime():
    """All six configs execute through run_mission with stubbed skills.

    Stubs cover every allowlisted role skill (not just the plans) because
    the runtime appends unplanned role skills on replan — the shared
    runtime must execute any allowlisted skill, and the test proves it.
    """
    for role_id in ("revops", "productops", "orgint"):
        for name in _role(role_id).skills:
            SkillRegistry.register(_stub_skill(name))
    runtime = EmployeeRuntime(tenant_id="t1")
    for mission_id in ONBOARDING_MISSIONS:
        result = await runtime.run_mission(MissionRegistry.get(mission_id))
        assert result.status == "completed", mission_id


def test_shared_runtime_has_no_mission_branching():
    """The shared runtime is mission-agnostic: no mission-id literals."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for rel in [
        "src/mission/employee_runtime.py",
        "src/mission/step_runners.py",
        "src/mission/mission_config.py",
    ]:
        src = (root / rel).read_text()
        assert "m-blocked-work-01" not in src
        assert "blocker_investigation" not in src
        assert "src.connectors" not in src


# ── Negative gates ───────────────────────────────────────────────────────


async def test_unauthorized_mission_rejected():
    """A mission type outside the role allowlist is rejected."""
    runtime = EmployeeRuntime(tenant_id="t1")
    bad = MissionSpec(
        id="m-bad", title="Bad", description="", employee_role="productops",
        mission_type="handoff_validation", priority="low", kpi_ids=[],
        skill_plan=["blocked_work_investigation"],
    )
    with pytest.raises(MissionNotAllowedError):
        await runtime.run_mission(bad)


async def test_disallowed_skill_rejected():
    """A plan outside the mission/role skill allowlists is rejected."""
    runtime = EmployeeRuntime(tenant_id="t1")
    bad = MissionSpec(
        id="m-bad", title="Bad", description="", employee_role="productops",
        mission_type="blocked_work_review", priority="low", kpi_ids=[],
        skill_plan=["account_context"],
    )
    with pytest.raises(MissionNotAllowedError):
        await runtime.run_mission(bad)


async def test_disallowed_capability_rejected():
    """A skill whose ops exceed effective capabilities is rejected pre-run."""
    SkillRegistry.register(_stub_skill("blocked_work_investigation", ["salesforce.update"]))
    runtime = EmployeeRuntime(tenant_id="t1")
    spec = MissionRegistry.get("m-blocked-work-01")
    with pytest.raises(MissionNotAllowedError):
        await runtime.run_mission(spec)


async def test_read_only_rejects_write_capable_skill():
    """read_only missions refuse write-capable skills before execution."""
    SkillRegistry.register(_stub_skill("cross_functional_investigation", ["notion.update"]))
    SkillRegistry.register(_stub_skill("ownership_gap_detection"))
    runtime = EmployeeRuntime(tenant_id="t1")
    spec = MissionRegistry.get("m-kickoff-prep-01")
    with pytest.raises(MissionNotAllowedError):
        await runtime.run_mission(spec)


def test_missing_context_is_fail_closed():
    """Absent required context is listed, never hallucinated."""
    spec = MissionRegistry.get("m-handoff-validation-01")
    assert spec.missing_context({}) == ["opportunity", "commitments"]
    assert spec.missing_context({"opportunity": 1, "commitments": 2, "extra": 3}) == []
