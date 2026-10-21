"""Skill contract tests — 20 skills with typed I/O, allowlist discipline.

Skills are bounded, reusable units with predictable I/O. Exactly 4 are
agentic (bounded internal loop, no goals/memory/authority). A skill can
never schedule its own mission.
"""

from __future__ import annotations

from src.mission.employee_role_registry import EmployeeRoleRegistry
from src.mission.skill_contracts import SkillDefinition, SkillInput, SkillOutput
from src.mission.skill_registry import SkillRegistry

AGENTIC_SKILLS = {
    "stalled_opportunity_investigation",
    "blocked_work_investigation",
    "cross_functional_investigation",
    "decision_capture",
}

EXPECTED_SKILLS = {
    # RevOps (6)
    "pipeline_health",
    "stalled_opportunity_investigation",
    "crm_hygiene",
    "followup_analysis",
    "account_context",
    "revenue_kpi_analysis",
    # ProductOps (6)
    "blocked_work_investigation",
    "roadmap_health",
    "sprint_health",
    "process_adherence",
    "documentation_sync",
    "delivery_risk_analysis",
    # OrgIntelligence (6)
    "decision_capture",
    "knowledge_gap_detection",
    "sop_freshness",
    "ownership_gap_detection",
    "cross_functional_investigation",
    "organizational_brief",
    # RAG / memory (2)
    "retrieve_memory",
    "retrieve_evidence",
}


class TestSkillContracts:
    def test_twenty_skills_registered(self):
        """Exactly 20 skills are registered (18 frozen + 2 RAG)."""
        SkillRegistry.load_all()
        assert len(SkillRegistry.list_skills()) == 20
        assert set(SkillRegistry.list_skills()) == EXPECTED_SKILLS

    def test_each_skill_has_typed_in_out(self):
        """Every skill declares Pydantic input/output models."""
        for name in EXPECTED_SKILLS:
            skill = SkillRegistry.get_skill(name)
            assert isinstance(skill, SkillDefinition)
            assert issubclass(skill.input_model, SkillInput)
            assert issubclass(skill.output_model, SkillOutput)
            assert skill.description

    def test_agentic_flags_exactly_four(self):
        """Exactly 4 skills are agentic with a bounded max_iterations."""
        agentic = {s for s in SkillRegistry.list_skills() if SkillRegistry.get_skill(s).agentic}
        assert agentic == AGENTIC_SKILLS
        for name in agentic:
            assert SkillRegistry.get_skill(name).max_iterations >= 1

    def test_skill_capability_ops_subset_of_role_caps(self):
        """Every skill's capability ops are within the allowlist of each role that owns it."""
        roles = EmployeeRoleRegistry.load()
        for role in roles.values():
            for skill_name in role.skills:
                skill = SkillRegistry.get_skill(skill_name)
                assert set(skill.capability_ops) <= set(role.capabilities), (
                    f"{role.role_id}/{skill_name} uses {skill.capability_ops} "
                    f"outside {role.capabilities}"
                )

    def test_skill_cannot_schedule_mission(self):
        """A skill has no mission-writing surface — no goals, no authority."""
        for name in EXPECTED_SKILLS:
            skill = SkillRegistry.get_skill(name)
            assert "mission" not in skill.model_fields
            assert not hasattr(skill, "schedule_mission")
            assert not hasattr(skill, "assign_mission")
            assert not hasattr(skill, "create_mission")

    def test_llm_skills_declare_llm_calls(self):
        """Skills that use the LLM declare which llm_ops primitives they call."""
        for name in EXPECTED_SKILLS:
            skill = SkillRegistry.get_skill(name)
            if skill.uses_llm:
                assert skill.llm_calls, f"{name} uses_llm but declares no llm_calls"
            else:
                assert skill.llm_calls == []