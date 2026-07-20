"""OntologyAI V6 — GovernanceGate (PRD §18.3 extension).

Thin, testable adapter that checks whether a ChangeStrategy or PlannedAction
is approved before execution may proceed. Complements the existing
@governed_write decorator and GovernanceWorkflow.
"""
from __future__ import annotations

from typing import Optional

from src.schemas.ba_artifact import ArtifactLifecycleStatus
from src.schemas.strategy_artifacts import ChangeStrategy
from src.ontology.action_types import PlannedAction


# Blast-radius rank lookup (higher = more impact).
_BLAST_RADIUS_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


class GovernanceGateError(Exception):
    """Raised when a governance gate blocks execution."""


class GovernanceGate:
    """Thin policy gate: blocks execution unless strategy/action is approved.

    Composable static checks:
    1. ``check_strategy`` — ChangeStrategy must be approved.
    2. ``check_planned_action`` — PlannedAction must be approved.
    3. ``check_blast_radius`` — action blast radius must not exceed max.
    4. ``check_actor_authorized`` — actor must be in authorized set.
    """

    @staticmethod
    def check_strategy(strategy: ChangeStrategy) -> None:
        """Raise GovernanceGateError if strategy is not approved."""
        if strategy.status != ArtifactLifecycleStatus.APPROVED:
            raise GovernanceGateError(
                f"ChangeStrategy {strategy.artifact_id} has status "
                f"'{strategy.status.value}'; must be 'approved' for execution"
            )

    @staticmethod
    def check_planned_action(action: PlannedAction) -> None:
        """Raise GovernanceGateError if PlannedAction is not approved."""
        if action.status != "approved":
            raise GovernanceGateError(
                f"PlannedAction {action.id} has status '{action.status}'; "
                f"must be 'approved' for execution"
            )

    @staticmethod
    def check_blast_radius(
        action: PlannedAction, max_allowed: str = "medium"
    ) -> None:
        """Raise GovernanceGateError if action blast radius exceeds max_allowed.

        Blast radius ranking: low=1, medium=2, high=3.
        """
        action_rank = _BLAST_RADIUS_RANK.get(action.blast_radius, 3)
        max_rank = _BLAST_RADIUS_RANK.get(max_allowed, 2)
        if action_rank > max_rank:
            raise GovernanceGateError(
                f"PlannedAction {action.id} has blast radius "
                f"'{action.blast_radius}' (rank {action_rank}) which exceeds "
                f"maximum allowed '{max_allowed}' (rank {max_rank})"
            )

    @staticmethod
    def check_actor_authorized(
        actor: str, action: PlannedAction, authorized_actors: set[str]
    ) -> None:
        """Raise GovernanceGateError if actor is not in authorized set."""
        if actor not in authorized_actors:
            raise GovernanceGateError(
                f"Actor '{actor}' is not authorized to execute "
                f"PlannedAction {action.id}. "
                f"Authorized actors: {sorted(authorized_actors)}"
            )

    @staticmethod
    def is_execution_allowed(
        strategy: ChangeStrategy,
        action: PlannedAction,
        *,
        actor: Optional[str] = None,
        max_blast_radius: Optional[str] = None,
        authorized_actors: Optional[set[str]] = None,
    ) -> bool:
        """Return True only if all applicable gates pass.

        Args:
            strategy: The ChangeStrategy to check.
            action: The PlannedAction to check.
            actor: Optional actor name for authorization check.
            max_blast_radius: Optional max allowed blast radius.
            authorized_actors: Optional set of authorized actors.

        Returns:
            True if all checks pass; False if any gate blocks.
        """
        try:
            GovernanceGate.check_strategy(strategy)
            GovernanceGate.check_planned_action(action)
            if max_blast_radius is not None:
                GovernanceGate.check_blast_radius(action, max_allowed=max_blast_radius)
            if actor is not None and authorized_actors is not None:
                GovernanceGate.check_actor_authorized(actor, action, authorized_actors)
            return True
        except GovernanceGateError:
            return False
