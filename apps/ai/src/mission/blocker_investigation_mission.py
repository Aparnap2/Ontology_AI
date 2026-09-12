"""Blocker-investigation mission wiring — Slack event to governed remediation.

Owns the investigation-specific adapters only: Slack→Evidence ingestion
(ADR-012), the onboarding context checkpoint, the in-memory timeline
validated against frozen ``MissionEventType``, and working-memory
checkpoints. Execution flows through ``EmployeeRuntime`` → the
blocker-investigation skill → Control Plane.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.control_plane import audit as audit_mod
from src.control_plane import ingress as ingress_mod
from src.mission.employee_role_config import EmployeeRoleConfig
from src.mission.employee_runtime import EmployeeRuntime
from src.mission.plan import PlanStep, StepPattern
from src.mission.skill_registry import SkillRegistry
from src.mission.skills.onboarding_ops import (
    BLOCKER_INVESTIGATION_SKILL_NAME,
    BlockerInvestigationWorkItem,
    register as register_blocker_investigation_skill,
    set_investigation_work_item,
)
from src.mission.timeline import MissionEventType
from src.ontology.object_types import Evidence, Onboarding

BLOCKER_INVESTIGATION_MISSION_TYPE = "blocker-investigate"

DEFAULT_BLOCKER_INVESTIGATION_CAPS = [
    "jira.update", "jira.read", "slack.send", "salesforce.read",
]


def ingest_slack_event(payload: dict[str, Any], tenant_id: str) -> Evidence:
    """Normalize a raw Slack payload into attributed Evidence (ADR-012).

    The message text is preserved as *data* attributed to its reporter —
    never as an instruction. Injection strings (e.g. "ignore previous
    instructions") survive verbatim in ``raw_text`` but cannot become
    authority: the normalized form quotes them as a third-party report.
    """
    channel = str(payload.get("channel", "unknown"))
    user = str(payload.get("user", "unknown"))
    text = str(payload.get("text", ""))
    ts = str(payload.get("ts", datetime.now(timezone.utc).isoformat()))
    return Evidence(
        id=f"ev-slack-{channel}-{ts}",
        tenant_id=tenant_id,
        source="slack",
        provenance=f"slack:{channel}:{user}",
        captured_at=ts,
        raw_text=text,
        normalized_text=f"[slack report by {user} in #{channel}]: {text}",
    )


def resolve_checkpoint_target(
    onboarding: Onboarding | None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve the generic checkpoint target with onboarding dual-write fallback.

    Explicit ``target_*`` wins; ``onboarding``-only derives
    ``("onboarding", onboarding.id)``; an explicit onboarding target claiming
    a different identity raises; all-blank stays allowed (callers enforce
    presence).
    """
    if target_type is None and target_id is None:
        if onboarding is not None:
            return "onboarding", onboarding.id
        return None, None
    if (
        target_type == "onboarding"
        and target_id is not None
        and onboarding is not None
        and target_id != onboarding.id
    ):
        raise ValueError(
            "contradictory checkpoint target: explicit target_* "
            f"({target_type!r}, {target_id!r}) disagrees with "
            f"onboarding.id={onboarding.id!r}"
        )
    return target_type, target_id


def build_context_checkpoint(
    onboarding: Onboarding,
    mission_id: str,
    evidence: list[Evidence],
    *,
    target_type: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the deterministic onboarding context checkpoint for blocker investigation."""
    resolved_type, resolved_id = resolve_checkpoint_target(
        onboarding, target_type, target_id
    )
    return {
        "onboarding_id": onboarding.id,
        "target_type": resolved_type,
        "target_id": resolved_id,
        "customer": onboarding.customer,
        "lifecycle_state": onboarding.lifecycle_state,
        "mission_id": mission_id,
        "evidence_refs": [e.id for e in evidence],
        "open_tasks": list(onboarding.tasks),
        "issues": list(onboarding.issues),
        "freshness": max((e.captured_at for e in evidence), default=""),
    }


class BlockerInvestigationTimeline:
    """Append-only timeline; every row must be a frozen MissionEventType."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event_type: MissionEventType, payload: dict[str, Any]) -> None:
        """Append a validated timeline row (rejects ad-hoc strings)."""
        if not isinstance(event_type, MissionEventType):
            raise ValueError(f"timeline event must be MissionEventType, got {event_type!r}")
        self.events.append({"type": event_type.value, "payload": dict(payload)})

    def list(self) -> list[dict[str, Any]]:
        """Return a defensive copy of the timeline rows."""
        return [dict(e) for e in self.events]


class WorkingMemory:
    """Minimal mission-scoped checkpoint store (slice seam)."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def save(self, mission_id: str, checkpoint: dict[str, Any]) -> None:
        """Persist a checkpoint snapshot for a mission."""
        self._store[mission_id] = dict(checkpoint)

    def get(self, mission_id: str) -> dict[str, Any]:
        """Return the stored checkpoint (empty when absent)."""
        return dict(self._store.get(mission_id, {}))


def reset_idempotency() -> None:
    """Clear Control Plane replay + audit state (test seam only)."""
    ingress_mod._seen._seen.clear()
    audit_mod.AUDIT_LOG.clear()


def make_blocker_investigation_role(
    role_caps: list[str] | None = None,
) -> EmployeeRoleConfig:
    """Build the config-driven blocker-investigation analyst role for one run."""
    return EmployeeRoleConfig(
        role_id="onboarding-ops",
        role="Onboarding Operations Analyst",
        goals=["keep implementation moving toward first value"],
        skills=[BLOCKER_INVESTIGATION_SKILL_NAME],
        capabilities=list(role_caps or DEFAULT_BLOCKER_INVESTIGATION_CAPS),
        permissions=["read"],
        policies=[],
        authority={},
        risk_threshold="MEDIUM",
        kpis=[],
    )


async def run_blocker_investigation_mission(
    onboarding: Onboarding,
    slack_payload: dict[str, Any],
    *,
    tenant_id: str = "t1",
    mission_id: str = "blocker-investigation-1",
    employee_id: str = "onboarding-ops",
    actor_identity: str = "system",
    business_scope: str = "acme",
    role_caps: list[str] | None = None,
    signal_handler: Any = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Run one investigate-blocker mission end to end (slice).

    Returns timeline rows, skill observations, audit events, the memory
    checkpoint, and the runtime result. Registers the investigation skill
    explicitly and restores the registry afterwards (canonical 20 untouched).
    """
    evidence = ingest_slack_event(slack_payload, tenant_id)
    resolved_type, resolved_id = resolve_checkpoint_target(
        onboarding, target_type, target_id
    )
    checkpoint = build_context_checkpoint(
        onboarding,
        mission_id,
        [evidence],
        target_type=resolved_type,
        target_id=resolved_id,
    )
    role = make_blocker_investigation_role(role_caps)

    # Typed deterministic context checkpoint (#63): the bounded context the
    # analyst reasons from. The slice evidence timestamp is wall-clock text
    # ("10:23"), so freshness is computed from an ISO-coerced COPY — the
    # original Evidence (and its stable ID) is untouched.
    from datetime import datetime, timezone

    from src.context.assemble import assemble_checkpoint

    now = datetime.now(timezone.utc)
    typed_checkpoint = assemble_checkpoint(
        checkpoint_id=f"cp-{mission_id}",
        tenant_id=tenant_id,
        mission_id=mission_id,
        trigger_event_id=evidence.id,
        evidence=[evidence.model_copy(update={"captured_at": now.isoformat()})],
        now=now,
        onboarding=onboarding,
        target_type=resolved_type,
        target_id=resolved_id,
        allowed_capabilities=list(role.capabilities),
    )
    checkpoint_dict = typed_checkpoint.model_dump()
    timeline = BlockerInvestigationTimeline()
    timeline.append(MissionEventType.CREATED, {"mission_id": mission_id})
    timeline.append(MissionEventType.EVIDENCE_ADDED, {"evidence_id": evidence.id})
    timeline.append(MissionEventType.STARTED, {"mission_id": mission_id})

    memory = WorkingMemory()
    memory.save(mission_id, checkpoint)

    item = BlockerInvestigationWorkItem(
        mission_id=mission_id,
        tenant_id=tenant_id,
        employee_id=employee_id,
        actor_identity=actor_identity,
        business_scope=business_scope,
        evidence_ids=[evidence.id],
        evidence_texts=[evidence.normalized_text],
        blocker_ref=",".join(onboarding.issues),
        signal_handler=signal_handler,
    )
    runtime = EmployeeRuntime(tenant_id=tenant_id)
    plan = [
        PlanStep(
            pattern=StepPattern.SEQUENTIAL,
            skill=BLOCKER_INVESTIGATION_SKILL_NAME,
            id="blocker-investigation-1",
        )
    ]

    previous = SkillRegistry._skills.get(BLOCKER_INVESTIGATION_SKILL_NAME)
    register_blocker_investigation_skill()
    try:
        with set_investigation_work_item(item):
            result = await runtime.run_plan(plan, role)
    finally:
        if previous is None:
            SkillRegistry._skills.pop(BLOCKER_INVESTIGATION_SKILL_NAME, None)
        else:
            SkillRegistry._skills[BLOCKER_INVESTIGATION_SKILL_NAME] = previous

    obs = item.observations[-1] if item.observations else {}
    if obs.get("verified"):
        timeline.append(MissionEventType.EXECUTED, {"action_id": obs.get("action_id", "")})
        timeline.append(MissionEventType.COMPLETED, {"mission_id": mission_id})
    else:
        timeline.append(MissionEventType.REVIEWED, {"outcome": obs.get("outcome", "")})

    # Workspace-facing event payload the Go SSE hub consumes: the smallest
    # seam between the headless slice and the live workspace.
    permit = next(
        (
            e
            for e in audit_mod.list_events()
            if e.get("decision") == "permit:executed"
            and e.get("mission_id") == mission_id
        ),
        {},
    )
    permit_intent = permit.get("intent", {}) if isinstance(permit, dict) else {}
    workspace_event = {
        "mission_id": mission_id,
        "action_id": permit.get("action_id", obs.get("action_id", "")),
        "status": "completed" if obs.get("verified") else "needs_review",
        "verified": bool(obs.get("verified", False)),
        "decision": obs.get("decision", obs.get("outcome", "")),
        "target_reference": permit_intent.get("target_reference", ""),
        "checkpoint_id": f"cp-{mission_id}",
    }
    return {
        "result": result,
        "timeline": timeline.list(),
        "observations": item.observations,
        "audit_events": audit_mod.list_events(),
        "memory": memory.get(mission_id),
        "handler": signal_handler,
        "context_checkpoint": checkpoint_dict,
        "workspace_event": workspace_event,
    }
