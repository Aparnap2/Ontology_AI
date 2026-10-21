"""Jira demo binding — real HTTP against local Mockoon (skip-if-unreachable).

Proves request construction, schema parsing, status mapping, and the
op-layer demo path over the wire. Static Mockoon fixtures: assertions
target what static mocks honestly prove (shapes, statuses, echoes are
NOT asserted as statefulness).
"""
from __future__ import annotations

import socket

import pytest

from src.connectors.jira_client import JiraClient, JiraRateLimitedError
from src.mission import capability_ops
from src.mission.capability_binding import reset_binding_cache


def _mockoon_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 3003), timeout=1).close()
        return True
    except OSError:
        return False


needs_mockoon = pytest.mark.skipif(
    not _mockoon_up(), reason="local Mockoon Jira not reachable on :3003"
)


@pytest.fixture
def client():
    cli = JiraClient(base_url="http://localhost:3003", tenant_id="t1", demo=True)
    yield cli
    cli.close()


@needs_mockoon
def test_demo_get_issue_shape(client):
    issue = client.get_issue("PORTAL-1")
    assert issue.key == "PORTAL-1"
    assert issue.summary and issue.status == "In Progress"
    assert issue.project_key == "PORTAL"


@needs_mockoon
def test_demo_search_returns_list(client):
    issues = client.search_issues("project = PORTAL", limit=10)
    assert len(issues) >= 1
    assert all(i.key for i in issues)


@needs_mockoon
def test_demo_create_returns_key(client):
    key = client.create_issue(
        {"project": "PORTAL", "summary": "probe", "description": "", "issue_type": "Task"}
    )
    assert key  # static fixture key; proves construction + 2xx + key parse


@needs_mockoon
def test_demo_update_accepted(client):
    out = client.update_issue("PORTAL-1", {"status": "Done"})
    assert out["id"] == "PORTAL-1"  # 204 accepted; merged view returned


@needs_mockoon
def test_demo_link_acknowledged(client):
    out = client.link_issues("PORTAL-2", "PORTAL-1")
    assert out == {"linked": True, "inward": "PORTAL-2", "outward": "PORTAL-1"}


@needs_mockoon
def test_demo_rate_limit_mapped_retryable(client):
    with pytest.raises(JiraRateLimitedError) as info:
        client.get_issue("RATE-LIMITED-1")
    assert info.value.retryable is True


@needs_mockoon
def test_op_layer_demo_binding_end_to_end(monkeypatch):
    """Ops resolve the demo client and execute real HTTP (create/update/read)."""
    monkeypatch.setenv("ONTOLOGY_CAPABILITY_BINDING", "demo")
    reset_binding_cache()
    try:
        created = capability_ops.CapabilityOpRegistry.execute(
            "jira.create",
            {"project": "PORTAL", "summary": "probe", "description": "", "issue_type": "Task"},
            "t1",
            role_caps=["jira.create", "jira.update", "jira.read"],
        )
        assert created["ok"] is True and created["data"]
        updated = capability_ops.CapabilityOpRegistry.execute(
            "jira.update",
            {"issue_id": "PORTAL-1", "fields": {"status": "Done"}},
            "t1",
            role_caps=["jira.create", "jira.update", "jira.read"],
        )
        assert updated["ok"] is True
        read = capability_ops.CapabilityOpRegistry.execute(
            "jira.read",
            {"jql": "key = PORTAL-1"},
            "t1",
            role_caps=["jira.create", "jira.update", "jira.read"],
        )
        assert read["ok"] is True and read["data"]
    finally:
        reset_binding_cache()


def test_op_layer_denies_without_allowlist():
    """A missing allowlist denies before any connector call (fail-closed)."""
    with pytest.raises(capability_ops.CapabilityNotAllowedError):
        capability_ops.CapabilityOpRegistry.execute(
            "jira.create",
            {"project": "PORTAL", "summary": "probe", "description": "", "issue_type": "Task"},
            "t1",
        )


def test_op_layer_denies_unauthorized_capability():
    """An allowlist that omits the op denies — no over-permission."""
    with pytest.raises(capability_ops.CapabilityNotAllowedError):
        capability_ops.CapabilityOpRegistry.execute(
            "jira.create",
            {"project": "PORTAL", "summary": "probe", "description": "", "issue_type": "Task"},
            "t1",
            role_caps=["jira.read"],
        )
