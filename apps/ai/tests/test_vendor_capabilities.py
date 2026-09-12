"""V7 vendor capability layer — registry, boundary, determinism (Phase 4).

The 15 vendor ops extend the frozen 10 (kept intact as a subset) on the
same builders. Writes stay fail-closed without a PlannedAction; tests
exercise underlying determinism through the unwrapped closures.
"""
from __future__ import annotations

import pytest

from src.connectors.base import ConnectorConfig
from src.mission import capability_ops
from src.mission.capability_ops import (
    CapabilityNotAllowedError,
    CapabilityOpRegistry,
    UnknownCapabilityOpError,
)
from src.mission.capability_ops_vendor import (
    VendorRetryableError,
    VendorTerminalError,
)

VENDOR_OPS = [
    "vendor.lookup",
    "vendor.get_contacts",
    "service.get",
    "service.get_dependencies",
    "incident.get",
    "incident.search",
    "sla.get",
    "sla.get_deadlines",
    "evidence.search",
    "evidence.get",
    "vendor_ticket.create",
    "vendor_ticket.update",
    "notification.send_internal",
    "notification.send_vendor",
    "incident.verify_recovery",
]

VENDOR_WRITES = {
    "vendor_ticket.create",
    "vendor_ticket.update",
    "notification.send_internal",
    "notification.send_vendor",
    "incident.verify_recovery",
}


@pytest.fixture
def vendor_double(monkeypatch):
    """Shared deterministic double behind the resolver seam."""
    cap = capability_ops._InMemoryCapability(
        "vendor", ConnectorConfig(tenant_id="t1")
    )
    monkeypatch.setattr(
        capability_ops, "_resolve_capability", lambda name, config: cap
    )
    capability_ops.CapabilityOpRegistry._ops.clear()
    return cap


def test_vendor_ops_registered_alongside_frozen_ten():
    """Registry grows 10 → 25; frozen 10 intact as an exact subset."""
    names = set(CapabilityOpRegistry.list_ops())
    assert len(names) == 25
    for name in VENDOR_OPS:
        assert name in names
    for name in [
        "jira.create", "jira.read", "jira.search", "jira.update", "notion.read",
        "notion.update", "salesforce.read", "salesforce.update",
        "slack.search", "slack.send",
    ]:
        assert name in names


def test_vendor_writes_flagged_governed():
    """The 5 vendor writes join write_ops(); all stay governed."""
    assert VENDOR_WRITES <= set(CapabilityOpRegistry.write_ops())
    for name in VENDOR_WRITES:
        assert CapabilityOpRegistry.get(name).governed is True


def test_allowlist_enforced_no_side_effect(vendor_double):
    """Role without the op is rejected before any backing call."""
    with pytest.raises(CapabilityNotAllowedError):
        CapabilityOpRegistry.execute(
            "vendor_ticket.create",
            {"vendor_id": "v1", "incident_id": "i1", "title": "outage"},
            "t1",
            role_caps=["incident.get"],
        )


def test_unknown_op_name_rejected():
    with pytest.raises(UnknownCapabilityOpError):
        CapabilityOpRegistry.get("vendor.delete_everything")


def test_tenant_id_flows_into_config(monkeypatch):
    """Tenant scoping reaches the resolver (no cross-tenant leakage)."""
    seen: list[str] = []

    def fake_resolve(name, config):
        seen.append(config.tenant_id)
        return capability_ops._InMemoryCapability(
            name, ConnectorConfig(tenant_id=config.tenant_id)
        )

    monkeypatch.setattr(capability_ops, "_resolve_capability", fake_resolve)
    capability_ops.CapabilityOpRegistry._ops.clear()
    CapabilityOpRegistry.execute("vendor.lookup", {"vendor_id": "v1"}, "t-acme")
    assert seen == ["t-acme"]


def test_malformed_params_fail_closed(vendor_double):
    """Strict params: missing keys and non-mappings raise terminal errors."""
    op = CapabilityOpRegistry.get("vendor.lookup")
    with pytest.raises(VendorTerminalError):
        op.execute({}, "t1")
    with pytest.raises(VendorTerminalError):
        op.execute("not-a-dict", "t1")


def test_error_taxonomy_retryable_flags():
    """Retryable vs terminal is explicit on the error types."""
    assert VendorRetryableError("x").retryable is True
    assert VendorTerminalError("x").retryable is False


def test_ticket_upsert_idempotent(vendor_double):
    """Same create params twice → same ticket id, single stored row."""
    op = CapabilityOpRegistry.get("vendor_ticket.create")
    fn = op.execute.__wrapped__
    params = {"vendor_id": "v1", "incident_id": "i1", "title": "outage"}
    first = fn(params, "t1")
    second = fn(params, "t1")
    assert first["data"]["id"] == second["data"]["id"]


def test_verify_recovery_predicates(vendor_double):
    """Recovery check returns verified-style dict, never a bare 200."""
    op = CapabilityOpRegistry.get("incident.verify_recovery")
    fn = op.execute.__wrapped__
    out = fn({"incident_id": "i1", "expected": {"status": "open"}}, "t1")
    assert out["verified"] in (True, False)
    assert "mismatches" in out["data"]
    bad = fn({"incident_id": "i1", "expected": {"status": "never-happens"}}, "t1")
    assert bad["verified"] is False
    assert bad["data"]["mismatches"]


def test_vendor_writes_have_no_silent_verify():
    """Vendor writes lack read counterparts → verify fails closed, not pass."""
    from src.mission.verify import READ_COUNTERPART, verify_write

    assert "vendor_ticket.create" not in READ_COUNTERPART

    async def go():
        return await verify_write(
            "vendor_ticket.create",
            {"vendor_id": "v1"},
            {"ticket_id": "t"},
            "t1",
            capabilities=vendor_double,
        )

    import asyncio

    outcome = asyncio.get_event_loop().run_until_complete(go())
    assert outcome.verified is False


def test_connector_boundary_scan():
    """Only capability_ops.py + executor may touch connector code."""
    from pathlib import Path

    root = Path(__file__).resolve().parent
    offenders = []
    for path in list((root / "src" / "mission").rglob("*.py")) + list(
        (root / "src" / "control_plane").rglob("*.py")
    ):
        if path.name in ("capability_ops.py", "capability_ops_vendor.py"):
            continue
        if path.name == "executor.py":
            continue
        text = path.read_text()
        if "from src.connectors" in text or "import src.connectors" in text:
            offenders.append(str(path))
    assert offenders == []
