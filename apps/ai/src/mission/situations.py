"""Situation open helper — pure constructor (E2).

Evidence + checkpoint + owner-resolution output in, validated
``Situation`` out. No I/O, no globals, no registries.
"""
from __future__ import annotations

from src.mission.owner_resolution import OwnerResolution
from src.ontology.object_types import Evidence, Situation


def open_situation(
    *,
    situation_id: str,
    tenant_id: str,
    evidence: list[Evidence],
    checkpoint_id: str,
    resolution: OwnerResolution | None = None,
    situation_type: str = "DELIVERY_BLOCKER",
    detected_condition: str,
    business_impact: str,
    affected_entities: list[str] | None = None,
    severity: str = "medium",
) -> Situation:
    """Open a validated ``Situation`` from evidence and resolution output."""
    return Situation(
        id=situation_id,
        tenant_id=tenant_id,
        type=situation_type,  # type: ignore[arg-type]
        affected_entities=list(affected_entities or []),
        detected_condition=detected_condition,
        severity=severity,  # type: ignore[arg-type]
        owner_id=resolution.owner_id if resolution is not None else None,
        evidence_ids=[item.id for item in evidence],
        checkpoint_id=checkpoint_id,
        business_impact=business_impact,
    )
