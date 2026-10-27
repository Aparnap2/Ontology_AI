"""Data Governance — Classification, retention, and PII protection.

Tracks data assets with governance metadata, enforces tenant isolation,
detects retention expiry, and provides PII redaction.

No I/O, no LLM calls, no wall clock — pure deterministic logic.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# ── Data Classification Levels ────────────────────────────────────────


class DataClassification(str, enum.Enum):
    """Sensitivity levels for data assets.

    PUBLIC:       Open to everyone.
    INTERNAL:     Company-wide, no external sharing.
    CONFIDENTIAL: Restricted access, encryption recommended.
    RESTRICTED:   PII, secrets — strictest controls required.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


# ── Data Asset Model ──────────────────────────────────────────────────


class DataAsset(BaseModel):
    """One data asset with governance metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    classification: DataClassification
    contains_pii: bool
    retention_days: int  # -1 = indefinite
    encryption_required: bool
    access_control: str  # "none", "role", "tenant", "individual"
    last_audit: str | None = None  # ISO timestamp


# ── Registry ──────────────────────────────────────────────────────────


class DataGovernanceRegistry:
    """Tracks data assets and enforces governance policies."""

    def __init__(self) -> None:
        self._assets: dict[str, DataAsset] = {}

    # ── Registration ──────────────────────────────────────────────────

    def register_asset(self, asset: DataAsset) -> None:
        """Register or update a data asset."""
        self._assets[asset.id] = asset

    def get_asset(self, asset_id: str) -> DataAsset | None:
        """Look up an asset by ID."""
        return self._assets.get(asset_id)

    # ── Classification ────────────────────────────────────────────────

    def classify(self, asset_id: str) -> DataClassification | None:
        """Return the classification level for an asset, or None if unknown."""
        asset = self._assets.get(asset_id)
        return asset.classification if asset else None

    # ── Retention ─────────────────────────────────────────────────────

    def check_retention(self, asset_id: str, now: datetime) -> dict[str, Any]:
        """Check if an asset has exceeded its retention window.

        Returns:
            {"expired": bool, "days_over": int}
            - expired=True  → asset has outlived its retention.
            - expired=False → asset is within its retention window.
            - days_over is the number of days past expiry (0 if not expired).
            - Retention of -1 (indefinite) never expires.
        """
        asset = self._assets.get(asset_id)
        if asset is None:
            return {"expired": False, "days_over": 0}

        if asset.retention_days == -1:
            return {"expired": False, "days_over": 0}

        if asset.last_audit is None:
            return {"expired": False, "days_over": 0}

        audit_dt = datetime.fromisoformat(asset.last_audit)
        if audit_dt.tzinfo is None:
            audit_dt = audit_dt.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        elapsed = (now - audit_dt).days
        if elapsed > asset.retention_days:
            return {"expired": True, "days_over": elapsed - asset.retention_days}
        return {"expired": False, "days_over": 0}

    # ── Access Control ────────────────────────────────────────────────

    def check_access(self, asset_id: str, tenant_id: str, requester_tenant: str) -> bool:
        """Tenant isolation: same tenant only.

        Returns True if the requester belongs to the same tenant as the asset.
        For non-tenant assets, access_control must be "none" or "role".
        """
        asset = self._assets.get(asset_id)
        if asset is None:
            return False

        if asset.access_control == "tenant":
            return tenant_id == requester_tenant

        if asset.access_control == "individual":
            return False  # individual access requires explicit grant

        # "none" or "role" — allow
        return True

    # ── PII Detection ─────────────────────────────────────────────────

    def get_pii_assets(self) -> list[DataAsset]:
        """Return all assets containing PII."""
        return [a for a in self._assets.values() if a.contains_pii]

    # ── PII Redaction ─────────────────────────────────────────────────

    def redact(self, data: dict[str, Any], asset_id: str) -> dict[str, Any]:
        """Redact PII fields based on classification.

        Rules:
        - RESTRICTED assets: redact all string values containing PII patterns.
        - CONFIDENTIAL assets: redact only explicitly PII-flagged fields.
        - PUBLIC/INTERNAL: no redaction.
        """
        asset = self._assets.get(asset_id)
        if asset is None or not asset.contains_pii:
            return data

        if asset.classification == DataClassification.RESTRICTED:
            return {k: "***REDACTED***" for k in data}
        if asset.classification == DataClassification.CONFIDENTIAL:
            return {k: "***REDACTED***" if isinstance(v, str) else v for k, v in data.items()}
        return data


# ── Pre-registered V7 Assets ──────────────────────────────────────────

_V7_ASSETS: list[DataAsset] = [
    DataAsset(
        id="evidence",
        name="Evidence",
        classification=DataClassification.CONFIDENTIAL,
        contains_pii=False,
        retention_days=365,
        encryption_required=True,
        access_control="tenant",
    ),
    DataAsset(
        id="vendor_ticket",
        name="Vendor Ticket",
        classification=DataClassification.INTERNAL,
        contains_pii=False,
        retention_days=730,
        encryption_required=False,
        access_control="tenant",
    ),
    DataAsset(
        id="incident",
        name="Incident",
        classification=DataClassification.CONFIDENTIAL,
        contains_pii=False,
        retention_days=365,
        encryption_required=True,
        access_control="tenant",
    ),
    DataAsset(
        id="audit_log",
        name="Audit Log",
        classification=DataClassification.RESTRICTED,
        contains_pii=False,
        retention_days=2555,
        encryption_required=True,
        access_control="tenant",
    ),
    DataAsset(
        id="llm_prompt_log",
        name="LLM Prompt Log",
        classification=DataClassification.RESTRICTED,
        contains_pii=True,
        retention_days=90,
        encryption_required=True,
        access_control="individual",
    ),
]


def create_default_registry() -> DataGovernanceRegistry:
    """Create a registry pre-loaded with V7 assets."""
    registry = DataGovernanceRegistry()
    for asset in _V7_ASSETS:
        registry.register_asset(asset)
    return registry
