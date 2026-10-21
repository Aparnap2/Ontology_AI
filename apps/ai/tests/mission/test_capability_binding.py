"""Capability binding selection — Phase E P0 step 1 (offline unit).

Covers binding precedence (env > runtime.yaml > default test), fail-closed
invalid values, preserved in-memory behavior under test, and NotConfigured
(instead of silent fallback) under demo/prod.
"""

from __future__ import annotations

import pytest

from src.connectors.base import ConnectorConfig
from src.mission import capability_ops
from src.mission.capability_binding import (
    CapabilityBindingError,
    NotConfigured,
    get_capability_binding,
    reset_binding_cache,
)


@pytest.fixture(autouse=True)
def _isolated_binding(monkeypatch):
    monkeypatch.delenv("ONTOLOGY_CAPABILITY_BINDING", raising=False)
    reset_binding_cache()
    yield
    reset_binding_cache()


class TestBindingSelection:
    def test_default_binding_is_test(self):
        """No env, yaml says test → test (current behavior preserved)."""
        assert get_capability_binding() == "test"

    def test_env_override_wins_over_yaml(self, monkeypatch):
        """ONTOLOGY_CAPABILITY_BINDING=demo beats the yaml default."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
        assert get_capability_binding() == "demo"

    def test_binding_is_cached_until_refresh(self, monkeypatch):
        """Repeat reads are cached; refresh re-reads the environment."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
        assert get_capability_binding() == "demo"
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "prod")
        assert get_capability_binding() == "demo"
        assert get_capability_binding(refresh=True) == "prod"

    def test_invalid_binding_fails_closed(self, monkeypatch):
        """An explicit-but-unknown binding raises instead of downgrading."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "staging")
        with pytest.raises(CapabilityBindingError, match="staging"):
            get_capability_binding(refresh=True)


class TestTestBindingPreserved:
    def test_config_for_keeps_mock_mode(self):
        """_config_for still builds mock_mode=True under test binding."""
        assert capability_ops._config_for("t1").mock_mode is True

    def test_resolve_falls_back_to_in_memory(self):
        """Unregistered 'project' still resolves to the deterministic double."""
        cap = capability_ops._resolve_capability(
            "project", ConnectorConfig(tenant_id="t1", mock_mode=True)
        )
        assert isinstance(cap, capability_ops._InMemoryCapability)
        assert cap.create_issue({"project": "X"}) == "X-1"
        assert cap.get_issues() == []


class TestNonTestBindingsFailClosed:
    def test_demo_binding_resolves_jira_client(self, monkeypatch):
        """Demo project resolves a real client (no network on construct)."""
        from src.connectors.jira_client import JiraClient

        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
        cap = capability_ops._resolve_capability(
            "project", ConnectorConfig(tenant_id="t1")
        )
        assert isinstance(cap, JiraClient)

    def test_demo_binding_refuses_non_localhost(self, monkeypatch):
        """Demo binding never points at a non-local host."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
        monkeypatch.setenv("JIRA_MOCK_URL", "https://jira.evil.example")
        with pytest.raises(ValueError, match="localhost"):
            capability_ops._resolve_capability(
                "project", ConnectorConfig(tenant_id="t1")
            )

    def test_demo_binding_unbridged_capability_raises(self, monkeypatch):
        """Demo for unbridged capabilities fails closed, never in-memory."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
        with pytest.raises(NotConfigured, match="demo binding"):
            capability_ops._resolve_capability(
                "crm", ConnectorConfig(tenant_id="t1")
            )

    def test_prod_binding_raises_not_configured_without_creds(self, monkeypatch):
        """Prod without credentials raises naming the missing creds."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "prod")
        for var in ("JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(NotConfigured, match="credential"):
            capability_ops._resolve_capability(
                "project", ConnectorConfig(tenant_id="t1")
            )

    def test_prod_never_returns_in_memory(self, monkeypatch):
        """Prod must raise, never silently hand back the double."""
        monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "prod")
        try:
            result = capability_ops._resolve_capability(
                "project", ConnectorConfig(tenant_id="t1")
            )
        except NotConfigured:
            return
        raise AssertionError(f"prod silently resolved: {result!r}")
