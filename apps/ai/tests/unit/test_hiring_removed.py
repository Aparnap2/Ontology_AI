"""Tests for Hiring removal from active surfaces — TDD approach.

Run FIRST — they should FAIL, then delete hiring files.
"""
import pytest


class TestHiringRemoved:
    """Hiring must not appear in active surfaces."""

    def test_hiring_not_in_worker_registration(self):
        """HiringWorkflow must NOT be importable."""
        with pytest.raises(ImportError):
            from src.activities.run_hiring_agent import run_hiring_agent_activity  # noqa: F811

    def test_hiring_not_in_authority_manifest(self):
        """Hiring must not appear in authority_manifest.py."""
        from src.agents.authority_manifest import AUTHORITY_MANIFEST
        agent_names = [a.agent_name for a in AUTHORITY_MANIFEST]
        assert "Hiring" not in agent_names
        assert all("hiring" not in n.lower() for n in agent_names)
