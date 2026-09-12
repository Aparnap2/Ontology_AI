"""Evidence-checkpoint pipeline (issue #63, Sprint 1): pure, deterministic, no LLM/I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from src.context.checkpoint import ContextCheckpoint, RelevantEvidence
from src.ontology.object_types import Evidence, Onboarding


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def freshness_of(captured: str, now: datetime, stale_after: int) -> Literal["fresh", "stale"]:
    return "stale" if (now - _parse(captured)).total_seconds() > stale_after else "fresh"


def resolve_entities(evidence: list[Evidence], index: dict[str, list[str]]) -> list[str]:
    return sorted({e for ev in evidence for e in index.get(ev.id, [])})


def resolve_mission(mid: str, ob: Optional[Onboarding]) -> tuple[str, list[str]]:
    if ob is not None and mid in ob.missions:
        return ob.lifecycle_state, []
    return "unknown", [f"mission scope unresolved for {mid}"]


def select_policies(mid: str, pol: dict, sops: dict, procs: dict) -> tuple[list, Optional[str], Optional[str], list[str]]:
    q = []
    if sops.get(mid) is None:
        q.append(f"SOP unresolved for {mid}")
    if procs.get(mid) is None:
        q.append(f"process unresolved for {mid}")
    return list(pol.get(mid, [])), procs.get(mid), sops.get(mid), q


def lookup_recent(mid: str, states: dict, recents: dict) -> tuple[str | None, dict, list]:
    e = states.get(mid, {})
    return e.get("current_state"), {k: v for k, v in e.items() if k != "current_state"}, list(recents.get(mid, []))


def snapshot_kpis(mid: str, kpis: dict) -> tuple[dict, list[str]]:
    snap = dict(kpis.get(mid, {}))
    return (snap, []) if snap else ({}, [f"KPI snapshot unresolved for {mid}"])


def _truncate(ev: list, kpis: dict, acts: list, n: int, chars: int) -> tuple[list, dict, list]:
    ev = list(ev)[:n]
    while ev and sum(len(e.excerpt) for e in ev) > chars:
        ev = ev[:-1]
    return ev, {k: kpis[k] for k in sorted(kpis)[:n]}, list(acts)[:n]


def assemble_checkpoint(
    *,
    checkpoint_id: str, tenant_id: str, mission_id: str, trigger_event_id: str,
    evidence: list[Evidence], now: datetime, onboarding: Optional[Onboarding] = None,
    target_type: Optional[str] = None, target_id: Optional[str] = None,
    entity_index: Optional[dict] = None, policy_registry: Optional[dict] = None,
    sop_registry: Optional[dict] = None, process_registry: Optional[dict] = None,
    state_store: Optional[dict] = None, kpi_store: Optional[dict] = None,
    recent_store: Optional[dict] = None, confidence_by_id: Optional[dict] = None,
    allowed_capabilities: Optional[list[str]] = None, authority_constraints: Optional[list[str]] = None,
    max_items: int = 10, max_chars: int = 2000, stale_after_seconds: int = 86400, version: int = 1,
) -> ContextCheckpoint:
    """Assemble a checkpoint from injected state only; stale marked, gaps questioned.

    ``onboarding`` is a deprecated alias: when passed without explicit
    ``target_type``/``target_id``, the target derives as
    ``("onboarding", onboarding.id)`` (dual-write, zero behavior change).
    """
    for ev in evidence:
        if ev.tenant_id != tenant_id:
            raise ValueError(f"cross-tenant evidence rejected: {ev.id}")
    if target_type is not None and not target_type.strip():
        raise ValueError("target_type must be a non-empty string when provided")
    if target_id is not None and not target_id.strip():
        raise ValueError("target_id must be a non-empty string when provided")
    if onboarding is not None and target_type is None and target_id is None:
        target_type, target_id = "onboarding", onboarding.id
    conf = confidence_by_id or {}
    scoped, q_scope = resolve_mission(mission_id, onboarding)
    policies, proc, sop, q_pol = select_policies(mission_id, policy_registry or {}, sop_registry or {}, process_registry or {})
    override, delta, recents = lookup_recent(mission_id, state_store or {}, recent_store or {})
    kpis, q_kpi = snapshot_kpis(mission_id, kpi_store or {})
    q_state = [] if override is not None else [f"recent state unresolved for {mission_id}"]
    cited = [RelevantEvidence(
        evidence_id=ev.id, source=ev.source,
        freshness=freshness_of(ev.captured_at, now, stale_after_seconds),
        confidence=float(conf.get(ev.id, 1.0)), provenance=ev.provenance,
        excerpt=ev.normalized_text[:max_chars]) for ev in evidence]
    cited, kpis, recents = _truncate(cited, kpis, recents, max_items, max_chars)
    open_q = q_scope + q_pol + q_state + q_kpi
    if not (entity_index or {}):
        open_q = [f"entity resolution unresolved for {mission_id}"] + open_q
    at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return ContextCheckpoint(
        checkpoint_id=checkpoint_id, tenant_id=tenant_id, mission_id=mission_id,
        trigger_event_id=trigger_event_id, version=version,
        affected_entities=resolve_entities(evidence, entity_index or {}),
        current_state=override if override is not None else scoped, state_delta=delta,
        relevant_evidence=cited, relevant_process=proc, relevant_sop=sop,
        applicable_policies=policies, kpi_snapshot=kpis, recent_actions=recents,
        unresolved_questions=open_q, allowed_capabilities=list(allowed_capabilities or []),
        authority_constraints=list(authority_constraints or []),
        target_type=target_type, target_id=target_id,
        provenance=f"checkpoint:{checkpoint_id}|trigger:{trigger_event_id}|mission:{mission_id}|at:{at}",
    )
