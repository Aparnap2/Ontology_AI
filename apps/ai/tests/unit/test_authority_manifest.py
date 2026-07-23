"""Tests for Authority Manifest — OntologyAI V5.1."""
import pytest


class TestAuthorityManifest:
    """Authority manifest V5.1 canonical agent tests."""

    CANONICAL_AGENTS = [
        "ChiefOfStaff",
        "Discovery",
        "OntologyMapper",
        "TruthAnalyst",
        "WorkflowBuilder",
        "Governance",
    ]

    def test_authority_manifest_has_six_canonical_agents(self):
        """Authority manifest must have exactly 6 V5.1 canonical agents."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert len(agent_names) == 6, (
            f"Expected 6 canonical agents, found {len(agent_names)}: {agent_names}"
        )

    def test_authority_manifest_contains_all_canonical(self):
        """All 6 V5.1 canonical agents must be present."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        for agent in self.CANONICAL_AGENTS:
            assert agent in agent_names, (
                f"Canonical agent '{agent}' not found in manifest: {agent_names}"
            )

    def test_authority_manifest_no_legacy_agents(self):
        """Legacy agent names must not appear in V5.1 manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        legacy_names = ["FP&A", "Growth Analytics", "Reliability & Delivery", "Communications", "Correlation Agent"]
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        for legacy in legacy_names:
            assert legacy not in agent_names, (
                f"Legacy agent '{legacy}' still present in manifest: {agent_names}"
            )

    def test_authority_manifest_no_hiring(self):
        """Hiring must not appear in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Hiring" not in agent_names, f"Hiring still present: {agent_names}"

    def test_authority_manifest_no_ontologyai_prefix(self):
        """Agent names must not use 'OntologyAI' prefix — use canonical names."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        for agent in AUTHORITY_MANIFEST:
            name = agent.agent_name
            assert "OntologyAI" not in name, (
                f"Agent name still uses 'OntologyAI' prefix: '{name}'. "
                f"Must use canonical display name."
            )

    def test_authority_manifest_governance_external_facing(self):
        """Governance must be external_facing with highest escalation tier."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST, AUTHORITY_MAP
        gov = AUTHORITY_MAP.get("Governance")
        assert gov is not None, "Governance not found in AUTHORITY_MAP"
        assert gov.external_facing is True, "Governance should be external_facing"
        assert gov.escalation_tier == "blocked", (
            f"Governance escalation_tier should be 'blocked', got '{gov.escalation_tier}'"
        )

    def test_get_authority_o1_dict_lookup(self):
        """get_authority should use O(1) dict lookup (AUTHORITY_MAP)."""
        from src.agents.authority_manifest import AUTHORITY_MAP
        from src.agents.authority_manifest import get_authority
        assert isinstance(AUTHORITY_MAP, dict), "AUTHORITY_MAP must be a dict"
        for name in self.CANONICAL_AGENTS:
            assert get_authority(name) is not None, (
                f"get_authority('{name}') returned None"
            )
        assert get_authority("nonexistent") is None

    def test_get_authority_all_domains_valid(self):
        """Each canonical agent must have a domain in the V5.1 set."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        valid_domains = {"control_plane", "discovery", "ontology_mapping", "truth_analysis", "workflow_building", "governance"}
        for agent in AUTHORITY_MANIFEST:
            assert agent.domain in valid_domains, (
                f"Agent '{agent.agent_name}' has invalid domain '{agent.domain}'"
            )
