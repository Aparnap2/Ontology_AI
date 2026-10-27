"""EmployeeRoleConfig model + YAML registry tests.

Asserts the frozen verbatim skill/capability inventories for the exactly
three employees (RevOps, ProductOps, OrgIntelligence), the ``extra="forbid"``
policy, the risk-threshold literal, and the skill→tool map binding.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mission.capability_ops import CapabilityOpRegistry
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.employee_role_registry import EmployeeRoleRegistry

# ── Frozen inventories (verbatim from the build blueprint) ────────────────

FROZEN_SKILLS = {
    "revops": [
        "pipeline_health",
        "stalled_opportunity_investigation",
        "crm_hygiene",
        "followup_analysis",
        "account_context",
        "revenue_kpi_analysis",
    ],
    "productops": [
        "blocked_work_investigation",
        "roadmap_health",
        "sprint_health",
        "process_adherence",
        "documentation_sync",
        "delivery_risk_analysis",
    ],
    "orgint": [
        "decision_capture",
        "knowledge_gap_detection",
        "sop_freshness",
        "ownership_gap_detection",
        "cross_functional_investigation",
        "organizational_brief",
    ],
}

FROZEN_CAPS = {
    "revops": [
        "salesforce.read",
        "salesforce.update",
        "slack.search",
        "slack.send",
        "jira.search",
        "jira.create",
    ],
    "productops": [
        "jira.read",
        "jira.create",
        "jira.update",
        "notion.read",
        "notion.update",
        "slack.search",
        "slack.send",
    ],
    "orgint": ["slack.search", "notion.read", "notion.update", "jira.read"],
}


class TestEmployeeRoleConfigModel:
    def test_minimal_config_constructs(self):
        """A minimal EmployeeRoleConfig constructs with defaults."""
        cfg = EmployeeRoleConfig(
            role_id="revops",
            role="Revenue Operations Analyst",
            goals=["Own the revenue pipeline"],
            skills=["pipeline_health"],
            capabilities=["salesforce.read"],
            permissions=["read"],
            policies=["policy.revenue"],
            authority={"escalate": ["founder"]},
            kpis=["pipeline_coverage"],
            memory_namespace="revops",
            mission_types=["pipeline_health_monitor"],
            persona="You are the RevOps analyst.",
        )
        assert cfg.risk_threshold == "MEDIUM"
        assert cfg.prompt_templates == {}
        assert cfg.skill_tool_map == {}

    def test_extra_field_forbidden(self):
        """extra='forbid' rejects unknown fields on EmployeeRoleConfig."""
        with pytest.raises(ValidationError):
            EmployeeRoleConfig(
                role_id="revops",
                role="RevOps",
                goals=[],
                skills=[],
                capabilities=[],
                permissions=[],
                policies=[],
                authority={},
                kpis=[],
                memory_namespace="revops",
                mission_types=[],
                persona="x",
                not_a_field=True,
            )

    def test_risk_threshold_literal(self):
        """risk_threshold must be one of LOW/MEDIUM/HIGH/CRITICAL."""
        with pytest.raises(ValidationError):
            EmployeeRoleConfig(
                role_id="revops",
                role="RevOps",
                goals=[],
                skills=[],
                capabilities=[],
                permissions=[],
                policies=[],
                authority={},
                risk_threshold="EXTREME",
                kpis=[],
                memory_namespace="revops",
                mission_types=[],
                persona="x",
            )

    def test_skill_allowlist_matches_frozen(self):
        """Each role's skills allowlist matches the frozen inventory verbatim."""
        roles = EmployeeRoleRegistry.load()
        for role_id, frozen in FROZEN_SKILLS.items():
            assert roles[role_id].skills == frozen

    def test_capability_allowlist_matches_frozen(self):
        """Each role's capabilities allowlist matches the frozen inventory verbatim."""
        roles = EmployeeRoleRegistry.load()
        for role_id, frozen in FROZEN_CAPS.items():
            assert roles[role_id].capabilities == frozen

    def test_skill_tool_map_values_are_registered_ops(self):
        """Every skill→tool binding resolves to a registered capability op."""
        roles = EmployeeRoleRegistry.load()
        known_ops = set(CapabilityOpRegistry.list_ops())
        for role in roles.values():
            for skill, op in role.skill_tool_map.items():
                assert skill in role.skills
                assert op in known_ops
                assert op in role.capabilities


class TestEmployeeRoleRegistry:
    def test_yaml_loads_exactly_three_role_configs(self):
        """config/employees.yaml loads exactly 3 role configs, field-by-field."""
        roles = EmployeeRoleRegistry.load()
        assert len(roles) == 3
        assert set(roles) == {"revops", "productops", "orgint"}

        revops = roles["revops"]
        assert revops.role_id == "revops"
        assert revops.role == "Revenue Operations Analyst"
        assert revops.skills == FROZEN_SKILLS["revops"]
        assert revops.capabilities == FROZEN_CAPS["revops"]
        assert "read" in revops.permissions
        assert revops.risk_threshold == "MEDIUM"
        assert revops.memory_namespace == "revops"
        assert "pipeline_health_monitor" in revops.mission_types
        assert revops.persona

        productops = roles["productops"]
        assert productops.role_id == "productops"
        assert productops.skills == FROZEN_SKILLS["productops"]
        assert productops.capabilities == FROZEN_CAPS["productops"]

        orgint = roles["orgint"]
        assert orgint.role_id == "orgint"
        assert orgint.skills == FROZEN_SKILLS["orgint"]
        assert orgint.capabilities == FROZEN_CAPS["orgint"]

    def test_get_role_known(self):
        """get_role returns the config for a known role_id."""
        role = EmployeeRoleRegistry.get_role("productops")
        assert isinstance(role, EmployeeRoleConfig)
        assert role.role_id == "productops"

    def test_get_role_unknown_raises(self):
        """get_role raises for an unknown role_id."""
        with pytest.raises(KeyError):
            EmployeeRoleRegistry.get_role("nope")