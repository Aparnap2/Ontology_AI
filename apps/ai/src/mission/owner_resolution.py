"""Deterministic owner resolution — reusable domain service (Phase E).

Connector-independent: this module never imports connectors, the LLM, or
mission runners. Connector-specific identity mapping stays at the adapter
boundary — callers translate external identities (Slack/Jira/Salesforce
handles) into directory ``user_id`` values before querying.

Frozen precedence (deterministic, stable, testable)::

    L1 explicit owner on the affected object  → OBJECT_OWNER
    L2 process / SOP owner                   → PROCESS_OWNER
    L3 team / role mapping                   → ROLE_MAPPING
    L4 project owner, then account owner     → PROJECT_OWNER / ACCOUNT_OWNER
    L5 configured escalation owner           → ESCALATION_OWNER
    L6 agent-recommended candidate, ONLY after L1–L5 fail/ambiguate
                                             → AGENT_RECOMMENDATION
    L7 HITL when nothing safe                → ESCALATION_REQUIRED (source HITL)

Rules (all enforced, all traced in ``resolution_path``):

* Tenant isolation: candidates whose directory tenant differs from the
  requesting tenant are rejected (recorded, never selected).
* Inactive users are never selected (skipped, precedence continues).
* No cross-team selection unless permitted: when the query carries a
  ``home_team`` and a candidate's team differs, the candidate is skipped
  unless ``allow_cross_team`` is set (policy explicitly permits).
* Conflicting valid owners at the same level → AMBIGUOUS (never an
  arbitrary pick). Lower levels are not consulted once a level populates.
* Missing ownership → UNRESOLVED (no references anywhere) or
  INVALID_OWNER (references existed but every one failed validation) —
  never an invented owner.
* An agent recommendation conflicting with a deterministic owner loses to
  the deterministic owner, unless ``hitl_on_agent_conflict`` policy demands
  HITL (then ESCALATION_REQUIRED).
* Every resolution retains evidence (``evidence_refs``) and source.
* The LLM is never the authority — it may only supply a candidate at L6.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from src.entities.models import OntologyBaseModel

logger = logging.getLogger(__name__)

OwnerStatus = Literal[
    "RESOLVED", "AMBIGUOUS", "UNRESOLVED", "INVALID_OWNER", "ESCALATION_REQUIRED"
]
OwnerSource = Literal[
    "OBJECT_OWNER",
    "PROCESS_OWNER",
    "ROLE_MAPPING",
    "PROJECT_OWNER",
    "ACCOUNT_OWNER",
    "ESCALATION_OWNER",
    "AGENT_RECOMMENDATION",
    "HITL",
]

# Resolution confidence per deterministic level (L6 agent candidates are
# inherently weaker; terminals carry no confidence).
_LEVEL_CONFIDENCE: dict[str, float] = {
    "OBJECT_OWNER": 0.95,
    "PROCESS_OWNER": 0.90,
    "ROLE_MAPPING": 0.85,
    "PROJECT_OWNER": 0.85,
    "ACCOUNT_OWNER": 0.85,
    "ESCALATION_OWNER": 0.80,
    "AGENT_RECOMMENDATION": 0.55,
}


class OrganizationUser(OntologyBaseModel):
    """One selectable owner in the org directory (reference ACME data)."""

    user_id: str
    tenant_id: str
    team: str = ""
    roles: list[str] = Field(default_factory=list)
    active: bool = True


class OrganizationConfig(OntologyBaseModel):
    """Minimum org ownership data: teams, roles, process/project/account
    owners, escalation owner, active/inactive status."""

    tenant_id: str
    users: list[OrganizationUser] = Field(default_factory=list)
    roles: dict[str, list[str]] = Field(default_factory=dict)
    processes: dict[str, str] = Field(default_factory=dict)
    projects: dict[str, str] = Field(default_factory=dict)
    accounts: dict[str, str] = Field(default_factory=dict)
    escalation_owner: str | None = None
    allow_cross_team: bool = False

    def user_index(self) -> dict[str, OrganizationUser]:
        """Index users by ``user_id`` (first entry wins, deterministic)."""
        index: dict[str, OrganizationUser] = {}
        for user in self.users:
            index.setdefault(user.user_id, user)
        return index


class OwnerQuery(OntologyBaseModel):
    """Ownership evidence for one resolution request.

    All owner references are directory ``user_id`` values (adapter boundary
    already applied). ``*_id`` lookups (process/project/account/role) resolve
    against the org config and merge with explicit ``*_owner_ids`` at the
    same precedence level.
    """

    tenant_id: str
    home_team: str = ""
    object_owner_ids: list[str] = Field(default_factory=list)
    process_id: str = ""
    process_owner_ids: list[str] = Field(default_factory=list)
    role: str = ""
    project_id: str = ""
    project_owner_ids: list[str] = Field(default_factory=list)
    account_id: str = ""
    account_owner_ids: list[str] = Field(default_factory=list)
    agent_recommended_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    allow_cross_team: bool = False
    hitl_on_agent_conflict: bool = False


class OwnerResolution(OntologyBaseModel):
    """Deterministic resolution outcome — explicit status, never null."""

    status: OwnerStatus
    owner_id: str | None = None
    owner_type: str | None = None
    source: OwnerSource
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    resolution_path: list[str] = Field(default_factory=list)
    escalation_required: bool = False


def _find_config(path: str | None = None) -> Path:
    """Locate config/organization.yaml (explicit path or search path)."""
    if path:
        candidate = Path(path)
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"organization config not found: {path}")
    candidates = [
        Path.cwd() / "config" / "organization.yaml",
        Path(__file__).resolve().parents[2] / "config" / "organization.yaml",
        Path(__file__).resolve().parents[1] / "config" / "organization.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/organization.yaml not found on any search path")


def _load_text(path: Path) -> str:
    """Read the file and expand ${VAR} environment placeholders."""
    return os.path.expandvars(path.read_text(encoding="utf-8"))


def load_organization_config(path: str | None = None) -> OrganizationConfig:
    """Load and validate the reference org config (additive, env-expanded)."""
    config_path = _find_config(path)
    data = yaml.safe_load(_load_text(config_path)) or {}
    config = OrganizationConfig(**data)
    logger.info(
        "Loaded organization config for tenant %s from %s",
        config.tenant_id,
        config_path,
    )
    return config


class OrganizationRegistry:
    """Thin cached accessor over :func:`load_organization_config`."""

    _config: OrganizationConfig | None = None

    @classmethod
    def load(cls, path: str | None = None) -> OrganizationConfig:
        """Load (once) and return the validated org config."""
        if cls._config is not None and path is None:
            return cls._config
        cls._config = load_organization_config(path)
        return cls._config

    @classmethod
    def reset(cls) -> None:
        """Clear the cached config (test seam only)."""
        cls._config = None


def _disposition(
    user_id: str,
    query: OwnerQuery,
    index: dict[str, OrganizationUser],
    cross_team_allowed: bool,
) -> tuple[bool, str]:
    """Validate one candidate: (selectable, rejection reason or '')."""
    user = index.get(user_id)
    if user is None:
        return False, "unknown"
    if user.tenant_id != query.tenant_id:
        return False, f"foreign-tenant:{user.tenant_id}"
    if not user.active:
        return False, "inactive"
    if (
        query.home_team
        and user.team
        and user.team != query.home_team
        and not cross_team_allowed
    ):
        return False, f"cross-team:{user.team}"
    return True, ""


def resolve_owner(query: OwnerQuery, org: OrganizationConfig) -> OwnerResolution:
    """Resolve the owning user for *query* against *org* (pure, no I/O).

    Walks the frozen L1–L6 precedence; the first populated level decides.
    Deterministic: same inputs always yield the same resolution, and the
    ordered ``resolution_path`` traces every evaluated step ("why Priya?").
    """
    index = org.user_index()
    cross_team_allowed = bool(query.allow_cross_team or org.allow_cross_team)
    path: list[str] = []
    invalid_seen: list[str] = []
    saw_refs = False

    def _level_ids(
        explicit: list[str], lookup: str | None = None
    ) -> list[str]:
        """Merge explicit ids with one config lookup id (dedupe, stable)."""
        merged = list(explicit)
        if lookup:
            merged.append(lookup)
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in merged:
            if candidate and candidate not in seen:
                seen.add(candidate)
                ordered.append(candidate)
        return ordered

    # Level plan: (label, source, candidate ids). Role lookup miss yields []
    # but a named role still counts as "referenced" for terminal accounting.
    role_members = list(org.roles.get(query.role, [])) if query.role else []
    levels: list[tuple[str, OwnerSource, list[str]]] = [
        ("L1", "OBJECT_OWNER", _level_ids(query.object_owner_ids)),
        (
            "L2",
            "PROCESS_OWNER",
            _level_ids(
                query.process_owner_ids,
                org.processes.get(query.process_id) if query.process_id else None,
            ),
        ),
        ("L3", "ROLE_MAPPING", _level_ids(role_members)),
        (
            "L4a",
            "PROJECT_OWNER",
            _level_ids(
                query.project_owner_ids,
                org.projects.get(query.project_id) if query.project_id else None,
            ),
        ),
        (
            "L4b",
            "ACCOUNT_OWNER",
            _level_ids(
                query.account_owner_ids,
                org.accounts.get(query.account_id) if query.account_id else None,
            ),
        ),
        (
            "L5",
            "ESCALATION_OWNER",
            _level_ids([org.escalation_owner] if org.escalation_owner else []),
        ),
    ]

    for label, source, raw in levels:
        if not raw:
            path.append(f"{label}:{source} skipped (no references)")
            continue
        saw_refs = True
        valid: list[str] = []
        rejected: list[str] = []
        for candidate in raw:
            ok, why = _disposition(candidate, query, index, cross_team_allowed)
            if ok:
                valid.append(candidate)
            else:
                rejected.append(f"{candidate}({why})")
                if candidate not in invalid_seen:
                    invalid_seen.append(candidate)
        if len(valid) >= 2:
            path.append(
                f"{label}:{source} refs={raw} valid={valid} "
                f"rejected={rejected} => AMBIGUOUS"
            )
            return OwnerResolution(
                status="AMBIGUOUS",
                owner_id=None,
                owner_type=None,
                source=source,
                confidence=0.5,
                reason=(
                    f"conflicting owners {valid} at {label}:{source}; "
                    "refusing arbitrary pick, escalation required"
                ),
                candidate_ids=list(valid),
                evidence_refs=list(query.evidence_refs),
                resolution_path=list(path),
                escalation_required=True,
            )
        if len(valid) == 1:
            winner = valid[0]
            path.append(
                f"{label}:{source} refs={raw} valid={valid} "
                f"rejected={rejected} => SELECT {winner}"
            )
            return _finish_deterministic(
                query, index, path, label, source, winner, cross_team_allowed
            )
        path.append(
            f"{label}:{source} refs={raw} valid=[] "
            f"rejected={rejected} => continue"
        )

    # L6: agent-recommended candidate, ONLY after L1–L5 fail/ambiguate.
    if query.agent_recommended_id:
        saw_refs = True
        candidate = query.agent_recommended_id
        ok, why = _disposition(candidate, query, index, cross_team_allowed)
        if ok:
            path.append(
                f"L6:AGENT_RECOMMENDATION refs=['{candidate}'] "
                f"deterministic levels exhausted => SELECT {candidate}"
            )
            return OwnerResolution(
                status="RESOLVED",
                owner_id=candidate,
                owner_type="user",
                source="AGENT_RECOMMENDATION",
                confidence=_LEVEL_CONFIDENCE["AGENT_RECOMMENDATION"],
                reason=(
                    f"agent-recommended {candidate} selected after "
                    "deterministic levels exhausted (advisory only)"
                ),
                candidate_ids=[candidate],
                evidence_refs=list(query.evidence_refs),
                resolution_path=list(path),
                escalation_required=False,
            )
        path.append(
            f"L6:AGENT_RECOMMENDATION refs=['{candidate}'] "
            f"rejected={candidate}({why}) => continue"
        )
        if candidate not in invalid_seen:
            invalid_seen.append(candidate)
    else:
        path.append("L6:AGENT_RECOMMENDATION skipped (no recommendation)")

    # L7: HITL when nothing safe.
    if saw_refs or query.role or query.process_id or query.project_id or query.account_id:
        path.append("L7:HITL nothing selectable => INVALID_OWNER")
        return OwnerResolution(
            status="INVALID_OWNER",
            owner_id=None,
            owner_type=None,
            source="HITL",
            confidence=0.0,
            reason=(
                f"ownership references existed but none validated "
                f"(rejected: {invalid_seen}); escalation required"
            ),
            candidate_ids=list(invalid_seen),
            evidence_refs=list(query.evidence_refs),
            resolution_path=list(path),
            escalation_required=True,
        )
    path.append("L7:HITL no ownership anywhere => UNRESOLVED")
    return OwnerResolution(
        status="UNRESOLVED",
        owner_id=None,
        owner_type=None,
        source="HITL",
        confidence=0.0,
        reason="no ownership references at any level; escalation required",
        candidate_ids=[],
        evidence_refs=list(query.evidence_refs),
        resolution_path=list(path),
        escalation_required=True,
    )


def _finish_deterministic(
    query: OwnerQuery,
    index: dict[str, OrganizationUser],
    path: list[str],
    label: str,
    source: OwnerSource,
    winner: str,
    cross_team_allowed: bool,
) -> OwnerResolution:
    """Build a deterministic RESOLVED outcome, applying the agent rule.

    A conflicting agent recommendation loses to the deterministic owner
    unless ``hitl_on_agent_conflict`` policy demands HITL (then
    ESCALATION_REQUIRED, never a silent override).
    """
    agent = query.agent_recommended_id
    if agent and agent != winner:
        ok, _ = _disposition(agent, query, index, cross_team_allowed)
        if ok and query.hitl_on_agent_conflict:
            path.append(
                f"{label}:{source} agent recommendation '{agent}' conflicts "
                f"with deterministic '{winner}' under HITL policy "
                "=> ESCALATION_REQUIRED"
            )
            return OwnerResolution(
                status="ESCALATION_REQUIRED",
                owner_id=None,
                owner_type=None,
                source="HITL",
                confidence=0.0,
                reason=(
                    f"agent recommendation '{agent}' conflicts with "
                    f"deterministic owner '{winner}'; policy demands HITL"
                ),
                candidate_ids=[winner, agent],
                evidence_refs=list(query.evidence_refs),
                resolution_path=list(path),
                escalation_required=True,
            )
        path.append(
            f"{label}:{source} agent recommendation '{agent}' overridden "
            f"by deterministic '{winner}'"
        )
        reason = (
            f"deterministic owner {winner} selected at {label}:{source}; "
            f"conflicting agent recommendation '{agent}' rejected"
        )
    else:
        reason = f"deterministic owner {winner} selected at {label}:{source}"
    return OwnerResolution(
        status="RESOLVED",
        owner_id=winner,
        owner_type="user",
        source=source,
        confidence=_LEVEL_CONFIDENCE[source],
        reason=reason,
        candidate_ids=[winner],
        evidence_refs=list(query.evidence_refs),
        resolution_path=list(path),
        escalation_required=False,
    )
