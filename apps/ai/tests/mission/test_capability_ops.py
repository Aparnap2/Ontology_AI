"""CapabilityOp registry tests — the 10 frozen ops over 4 connectors.

Employees never call connectors directly; they reach external systems ONLY
through ``CapabilityOpRegistry`` ops, which wrap the existing capability
layer (``src/mission/capability.py`` → ``src/connectors``).
"""

from __future__ import annotations

import pytest

from src.mission import capability_ops
from src.mission.capability_ops import (
    CapabilityNotAllowedError,
    CapabilityOp,
    CapabilityOpRegistry,
    UnknownCapabilityOpError,
)

EXPECTED_OPS = [
    "jira.create",
    "jira.read",
    "jira.search",
    "jira.update",
    "notion.read",
    "notion.update",
    "salesforce.read",
    "salesforce.update",
    "slack.search",
    "slack.send",
]

WRITE_OPS = {
    "salesforce.update",
    "slack.send",
    "jira.create",
    "jira.update",
    "notion.update",
}


class RecordingCapability:
    """Test-side double for the capability layer (records method calls)."""

    def __init__(self, data=None):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.data = data or {}

    def _record(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
        return self.data.get(method, [])

    def get_customers(self):
        return self._record("get_customers")

    def get_deals(self):
        return self._record("get_deals")

    def update_deal(self, deal_id, fields):
        return self._record("update_deal", deal_id, fields)

    def get_messages(self, channel, **filters):
        return self._record("get_messages", channel, filters)

    def send_message(self, channel, text):
        return self._record("send_message", channel, text)

    def get_issues(self, **filters):
        return self._record("get_issues", filters)

    def create_issue(self, data):
        return self._record("create_issue", data)

    def update_issue(self, issue_id, fields):
        return self._record("update_issue", issue_id, fields)

    def get_pages(self, **filters):
        return self._record("get_pages", filters)

    def update_page(self, page_id, data):
        return self._record("update_page", page_id, data)


@pytest.fixture
def mock_capability(monkeypatch):
    """Point the real op resolver at a RecordingCapability."""
    cap = RecordingCapability()
    monkeypatch.setattr(capability_ops, "_resolve_capability", lambda name, config: cap)
    return cap


class TestCapabilityOps:
    def test_exactly_ten_ops_registered(self):
        """Frozen 10 intact as a subset; registry grows only via vendor ops.

        Phase 4 added 15 vendor-operations ops (10 read/search + 5 writes)
        on the same builders: 10 + 15 = 25 total. Any other change fails.
        """
        from tests.test_vendor_capabilities import VENDOR_OPS

        names = set(CapabilityOpRegistry.list_ops())
        assert set(EXPECTED_OPS) <= names
        assert set(VENDOR_OPS) <= names
        assert len(names) == len(EXPECTED_OPS) + len(VENDOR_OPS) == 25

    def test_op_signatures(self):
        """Every op exposes name/capability/method/kind and a dict-returning execute."""
        for name in EXPECTED_OPS:
            op = CapabilityOpRegistry.get(name)
            assert isinstance(op, CapabilityOp)
            assert op.name == name
            assert op.capability in {"crm", "project", "messaging", "knowledge"}
            assert op.method
            assert op.kind in {"read", "write", "search", "send"}
            result = op.execute({}, "t1")
            assert isinstance(result, dict)
            assert result["op"] == name

    def test_write_ops_flagged_governed(self):
        """Frozen 5 writes intact; 5 vendor writes join them, all governed."""
        from tests.test_vendor_capabilities import VENDOR_WRITES

        writes = set(CapabilityOpRegistry.write_ops())
        assert WRITE_OPS <= writes
        assert VENDOR_WRITES <= writes
        assert len(writes) == len(WRITE_OPS) + len(VENDOR_WRITES) == 10
        for name in WRITE_OPS | VENDOR_WRITES:
            assert CapabilityOpRegistry.get(name).governed is True

    def test_op_wraps_expected_connector_method(self, mock_capability):
        """Each op calls the expected capability method (mock connector)."""
        CapabilityOpRegistry.get("salesforce.read").execute(
            {"object_type": "opportunity"}, "t1"
        )
        assert mock_capability.calls[-1][0] == "get_deals"

        CapabilityOpRegistry.get("salesforce.read").execute(
            {"object_type": "customer"}, "t1"
        )
        assert mock_capability.calls[-1][0] == "get_customers"

        CapabilityOpRegistry.get("salesforce.update").execute(
            {"record_id": "d-1", "fields": {"stage": "closing"}}, "t1"
        )
        assert mock_capability.calls[-1][0] == "update_deal"

        CapabilityOpRegistry.get("slack.search").execute(
            {"channel": "#revenue", "query": "stalled"}, "t1"
        )
        assert mock_capability.calls[-1][0] == "get_messages"

        CapabilityOpRegistry.get("slack.send").execute(
            {"channel": "#revenue", "text": "hi"}, "t1"
        )
        assert mock_capability.calls[-1][0] == "send_message"

        CapabilityOpRegistry.get("jira.read").execute({"jql": "project = X"}, "t1")
        assert mock_capability.calls[-1][0] == "get_issues"

        CapabilityOpRegistry.get("jira.create").execute(
            {"project": "X", "summary": "s", "description": "d", "issue_type": "Task"},
            "t1",
        )
        assert mock_capability.calls[-1][0] == "create_issue"

        CapabilityOpRegistry.get("jira.update").execute(
            {"issue_id": "X-1", "fields": {"status": "Done"}}, "t1"
        )
        assert mock_capability.calls[-1][0] == "update_issue"

        CapabilityOpRegistry.get("notion.read").execute({"query": "SOP"}, "t1")
        assert mock_capability.calls[-1][0] == "get_pages"

        CapabilityOpRegistry.get("notion.update").execute(
            {"page_id": "p-1", "data": {"title": "new"}}, "t1"
        )
        assert mock_capability.calls[-1][0] == "update_page"

    def test_unknown_op_rejected(self):
        """An unregistered op name is rejected."""
        with pytest.raises(UnknownCapabilityOpError):
            CapabilityOpRegistry.get("salesforce.delete")

    def test_deny_list_enforced_per_role(self):
        """assert_allowed enforces the role capability deny-list."""
        CapabilityOpRegistry.assert_allowed("salesforce.read", ["salesforce.read"])
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.assert_allowed("salesforce.read", ["slack.search"])

    def test_execute_enforces_role_allowlist(self):
        """Registry.execute applies the role allowlist before running the op."""
        with pytest.raises(CapabilityNotAllowedError):
            CapabilityOpRegistry.execute(
                "salesforce.update", {}, "t1", role_caps=["slack.search"]
            )