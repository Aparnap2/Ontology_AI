"""Tests for Data Governance — classification, retention, and PII protection.

Covers:
1. All V7 assets are registered
2. Classification levels are correct
3. PII detection works
4. Retention expiry is detected
5. Tenant isolation enforced
6. PII redaction works
7. All models strict (extra=forbid)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.mission.data_governance import (
    DataAsset,
    DataClassification,
    DataGovernanceRegistry,
    _V7_ASSETS,
    create_default_registry,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _make_asset(
    asset_id: str = "test-asset",
    name: str = "Test Asset",
    classification: DataClassification = DataClassification.INTERNAL,
    contains_pii: bool = False,
    retention_days: int = 365,
    encryption_required: bool = False,
    access_control: str = "tenant",
    last_audit: str | None = None,
) -> DataAsset:
    return DataAsset(
        id=asset_id,
        name=name,
        classification=classification,
        contains_pii=contains_pii,
        retention_days=retention_days,
        encryption_required=encryption_required,
        access_control=access_control,
        last_audit=last_audit,
    )


# ── 1. All V7 assets are registered ───────────────────────────────────


class TestV7AssetsRegistered:
    def test_v7_asset_count(self) -> None:
        assert len(_V7_ASSETS) == 5

    def test_v7_asset_ids(self) -> None:
        ids = {a.id for a in _V7_ASSETS}
        assert ids == {"evidence", "vendor_ticket", "incident", "audit_log", "llm_prompt_log"}

    def test_v7_assets_loaded_into_registry(self) -> None:
        registry = create_default_registry()
        for asset in _V7_ASSETS:
            assert registry.get_asset(asset.id) is not None

    def test_v7_assets_names(self) -> None:
        names = {a.id: a.name for a in _V7_ASSETS}
        assert names["evidence"] == "Evidence"
        assert names["vendor_ticket"] == "Vendor Ticket"
        assert names["incident"] == "Incident"
        assert names["audit_log"] == "Audit Log"
        assert names["llm_prompt_log"] == "LLM Prompt Log"


# ── 2. Classification levels are correct ──────────────────────────────


class TestClassificationLevels:
    def test_evidence_is_confidential(self) -> None:
        registry = create_default_registry()
        assert registry.classify("evidence") == DataClassification.CONFIDENTIAL

    def test_vendor_ticket_is_internal(self) -> None:
        registry = create_default_registry()
        assert registry.classify("vendor_ticket") == DataClassification.INTERNAL

    def test_incident_is_confidential(self) -> None:
        registry = create_default_registry()
        assert registry.classify("incident") == DataClassification.CONFIDENTIAL

    def test_audit_log_is_restricted(self) -> None:
        registry = create_default_registry()
        assert registry.classify("audit_log") == DataClassification.RESTRICTED

    def test_llm_prompt_log_is_restricted(self) -> None:
        registry = create_default_registry()
        assert registry.classify("llm_prompt_log") == DataClassification.RESTRICTED

    def test_unknown_asset_returns_none(self) -> None:
        registry = create_default_registry()
        assert registry.classify("nonexistent") is None

    def test_classification_enum_values(self) -> None:
        assert DataClassification.PUBLIC.value == "public"
        assert DataClassification.INTERNAL.value == "internal"
        assert DataClassification.CONFIDENTIAL.value == "confidential"
        assert DataClassification.RESTRICTED.value == "restricted"

    def test_classification_is_str_subclass(self) -> None:
        assert isinstance(DataClassification.PUBLIC, str)


# ── 3. PII detection works ────────────────────────────────────────────


class TestPIIDetection:
    def test_only_llm_prompt_log_contains_pii(self) -> None:
        registry = create_default_registry()
        pii_assets = registry.get_pii_assets()
        assert len(pii_assets) == 1
        assert pii_assets[0].id == "llm_prompt_log"

    def test_pii_flag_matches_asset_definition(self) -> None:
        for asset in _V7_ASSETS:
            if asset.id == "llm_prompt_log":
                assert asset.contains_pii is True
            else:
                assert asset.contains_pii is False

    def test_get_pii_assets_returns_empty_when_none(self) -> None:
        registry = DataGovernanceRegistry()
        assert registry.get_pii_assets() == []


# ── 4. Retention expiry is detected ───────────────────────────────────


class TestRetentionExpiry:
    def test_expired_asset(self) -> None:
        asset = _make_asset(
            asset_id="old-evidence",
            retention_days=30,
            last_audit="2025-01-01T00:00:00Z",
        )
        registry = DataGovernanceRegistry()
        registry.register_asset(asset)

        now = datetime(2025, 2, 15, tzinfo=timezone.utc)
        result = registry.check_retention("old-evidence", now)
        assert result["expired"] is True
        assert result["days_over"] == 15  # 45 elapsed - 30 retention = 15

    def test_not_expired_asset(self) -> None:
        asset = _make_asset(
            asset_id="fresh-evidence",
            retention_days=365,
            last_audit="2025-06-01T00:00:00Z",
        )
        registry = DataGovernanceRegistry()
        registry.register_asset(asset)

        now = datetime(2025, 7, 1, tzinfo=timezone.utc)
        result = registry.check_retention("fresh-evidence", now)
        assert result["expired"] is False
        assert result["days_over"] == 0

    def test_indefinite_retention_never_expires(self) -> None:
        asset = _make_asset(
            asset_id="eternal",
            retention_days=-1,
            last_audit="2020-01-01T00:00:00Z",
        )
        registry = DataGovernanceRegistry()
        registry.register_asset(asset)

        now = datetime(2099, 12, 31, tzinfo=timezone.utc)
        result = registry.check_retention("eternal", now)
        assert result["expired"] is False
        assert result["days_over"] == 0

    def test_unknown_asset_returns_not_expired(self) -> None:
        registry = DataGovernanceRegistry()
        now = datetime.now(timezone.utc)
        result = registry.check_retention("nonexistent", now)
        assert result["expired"] is False
        assert result["days_over"] == 0

    def test_no_audit_date_returns_not_expired(self) -> None:
        asset = _make_asset(asset_id="no-audit", retention_days=30, last_audit=None)
        registry = DataGovernanceRegistry()
        registry.register_asset(asset)

        now = datetime.now(timezone.utc)
        result = registry.check_retention("no-audit", now)
        assert result["expired"] is False

    def test_v7_llm_prompt_log_expires_at_90_days(self) -> None:
        registry = create_default_registry()
        # Manually set last_audit on the LLM prompt log asset
        asset = DataAsset(
            id="llm_prompt_log",
            name="LLM Prompt Log",
            classification=DataClassification.RESTRICTED,
            contains_pii=True,
            retention_days=90,
            encryption_required=True,
            access_control="individual",
            last_audit="2025-06-01T00:00:00Z",
        )
        registry.register_asset(asset)

        now_expired = datetime(2025, 9, 15, tzinfo=timezone.utc)  # 106 days
        result = registry.check_retention("llm_prompt_log", now_expired)
        assert result["expired"] is True
        assert result["days_over"] == 16

        now_ok = datetime(2025, 8, 15, tzinfo=timezone.utc)  # 75 days
        result_ok = registry.check_retention("llm_prompt_log", now_ok)
        assert result_ok["expired"] is False

    def test_naive_datetime_treated_as_utc(self) -> None:
        asset = _make_asset(
            asset_id="naive",
            retention_days=10,
            last_audit="2025-06-01T00:00:00",
        )
        registry = DataGovernanceRegistry()
        registry.register_asset(asset)

        now = datetime(2025, 6, 15, tzinfo=timezone.utc)
        result = registry.check_retention("naive", now)
        assert result["expired"] is True
        assert result["days_over"] == 4


# ── 5. Tenant isolation enforced ──────────────────────────────────────


class TestTenantIsolation:
    def test_same_tenant_allowed(self) -> None:
        registry = create_default_registry()
        assert registry.check_access("evidence", "tenant-a", "tenant-a") is True

    def test_different_tenant_denied(self) -> None:
        registry = create_default_registry()
        assert registry.check_access("evidence", "tenant-a", "tenant-b") is False

    def test_unknown_asset_denied(self) -> None:
        registry = DataGovernanceRegistry()
        assert registry.check_access("nonexistent", "tenant-a", "tenant-a") is False

    def test_individual_access_control_always_denied(self) -> None:
        registry = create_default_registry()
        # LLM prompt log has access_control="individual"
        assert registry.check_access("llm_prompt_log", "tenant-a", "tenant-a") is False

    def test_vendor_ticket_tenant_isolation(self) -> None:
        registry = create_default_registry()
        assert registry.check_access("vendor_ticket", "x", "x") is True
        assert registry.check_access("vendor_ticket", "x", "y") is False

    def test_incident_tenant_isolation(self) -> None:
        registry = create_default_registry()
        assert registry.check_access("incident", "org-1", "org-1") is True
        assert registry.check_access("incident", "org-1", "org-2") is False


# ── 6. PII redaction works ────────────────────────────────────────────


class TestPIIRedaction:
    def test_no_redaction_for_non_pii_asset(self) -> None:
        registry = create_default_registry()
        data = {"field": "value"}
        result = registry.redact(data, "evidence")
        assert result == data

    def test_no_redaction_for_unknown_asset(self) -> None:
        registry = DataGovernanceRegistry()
        data = {"field": "value"}
        result = registry.redact(data, "nonexistent")
        assert result == data

    def test_restricted_pii_redacts_all_values(self) -> None:
        registry = create_default_registry()
        data = {"name": "Alice", "ssn": "123-45-6789", "count": 42}
        result = registry.redact(data, "llm_prompt_log")
        assert result == {
            "name": "***REDACTED***",
            "ssn": "***REDACTED***",
            "count": "***REDACTED***",
        }

    def test_confidential_non_pii_no_redaction(self) -> None:
        registry = create_default_registry()
        data = {"field": "value", "nested": {"key": "val"}}
        # evidence is CONFIDENTIAL but contains_pii=False
        result = registry.redact(data, "evidence")
        assert result == data

    def test_redaction_preserves_non_string_values(self) -> None:
        asset = DataAsset(
            id="mixed-pii",
            name="Mixed PII",
            classification=DataClassification.CONFIDENTIAL,
            contains_pii=True,
            retention_days=100,
            encryption_required=True,
            access_control="tenant",
        )
        registry = DataGovernanceRegistry()
        registry.register_asset(asset)

        data = {"name": "Alice", "count": 42, "flag": True}
        result = registry.redact(data, "mixed-pii")
        # CONFIDENTIAL + PII: strings redacted, non-strings preserved
        assert result["name"] == "***REDACTED***"
        assert result["count"] == 42
        assert result["flag"] is True


# ── 7. All models strict (extra=forbid) ───────────────────────────────


class TestModelStrictness:
    def test_data_asset_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            DataAsset(
                id="test",
                name="Test",
                classification=DataClassification.PUBLIC,
                contains_pii=False,
                retention_days=100,
                encryption_required=False,
                access_control="none",
                bogus_field="should fail",
            )

    def test_data_asset_valid_construction(self) -> None:
        asset = DataAsset(
            id="ok",
            name="OK",
            classification=DataClassification.PUBLIC,
            contains_pii=False,
            retention_days=-1,
            encryption_required=False,
            access_control="none",
        )
        assert asset.id == "ok"

    def test_data_asset_frozen(self) -> None:
        asset = _make_asset()
        with pytest.raises(Exception):  # ValidationError or AttributeError
            asset.id = "changed"


# ── Registry operations ───────────────────────────────────────────────


class TestRegistryOperations:
    def test_register_and_get(self) -> None:
        registry = DataGovernanceRegistry()
        asset = _make_asset(asset_id="a1")
        registry.register_asset(asset)
        assert registry.get_asset("a1") == asset

    def test_get_unknown_returns_none(self) -> None:
        registry = DataGovernanceRegistry()
        assert registry.get_asset("unknown") is None

    def test_register_overwrites_existing(self) -> None:
        registry = DataGovernanceRegistry()
        a1 = _make_asset(asset_id="a1", name="V1")
        a2 = _make_asset(asset_id="a1", name="V2")
        registry.register_asset(a1)
        registry.register_asset(a2)
        assert registry.get_asset("a1").name == "V2"

    def test_v7_assets_all_have_encryption_when_confidential_or_restricted(self) -> None:
        for asset in _V7_ASSETS:
            if asset.classification in {
                DataClassification.CONFIDENTIAL,
                DataClassification.RESTRICTED,
            }:
                assert asset.encryption_required is True, (
                    f"{asset.id} is {asset.classification.value} but "
                    f"encryption_required={asset.encryption_required}"
                )

    def test_v7_assets_all_use_tenant_or_individual_access(self) -> None:
        for asset in _V7_ASSETS:
            assert asset.access_control in {"tenant", "individual"}, (
                f"{asset.id} has unexpected access_control={asset.access_control}"
            )
