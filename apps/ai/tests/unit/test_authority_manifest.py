"""Tests for Authority Manifest updates — TrackGuard V4.1.

Run FIRST — they should FAIL, then implement code to pass them.
"""
import pytest


class TestAuthorityManifest:
    """Authority manifest update tests."""

    CANONICAL_AGENTS = [
        "Chief of Staff",
        "FP&A",
        "Growth Analytics",
        "Reliability & Delivery",
        "Communications",
    ]

    def test_authority_manifest_has_core_specialist_agents(self):
        """Authority manifest must have at least 3 core specialist agents."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        found = [n for n in self.CANONICAL_AGENTS if n in agent_names]
        assert len(found) >= 3, (
            f"Expected at least 3 canonical agents, found {len(found)}: {found}"
        )

    def test_authority_manifest_no_hiring(self):
        """Hiring must not appear in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Hiring" not in agent_names, f"Hiring still present: {agent_names}"

    def test_authority_manifest_no_sarthi_prefix(self):
        """Agent names must not use 'Sarthi' prefix — use canonical names."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        for agent in AUTHORITY_MANIFEST:
            name = agent.agent_name
            assert "Sarthi" not in name, (
                f"Agent name still uses 'Sarthi' prefix: '{name}'. "
                f"Must use canonical display name."
            )

    def test_authority_manifest_comms_agent_exists(self):
        """Communications agent must exist in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Communications" in agent_names, (
            f"Communications agent not found in manifest: {agent_names}"
        )

    def test_authority_manifest_chief_of_staff_exists(self):
        """Chief of Staff must exist in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Chief of Staff" in agent_names, (
            f"Chief of Staff not found in manifest: {agent_names}"
        )

    def test_authority_manifest_fp_and_a_exists(self):
        """FP&A must exist in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "FP&A" in agent_names, (
            f"FP&A not found in manifest: {agent_names}"
        )

    def test_authority_manifest_growth_analytics_exists(self):
        """Growth Analytics must exist in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Growth Analytics" in agent_names, (
            f"Growth Analytics not found in manifest: {agent_names}"
        )

    def test_authority_manifest_reliability_and_delivery_exists(self):
        """Reliability & Delivery must exist in authority manifest."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Reliability & Delivery" in agent_names, (
            f"Reliability & Delivery not found in manifest: {agent_names}"
        )
