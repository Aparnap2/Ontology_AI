"""Remediator — executes approved fixes and logs outcomes.

Applies FixProposals based on approval state. Supports auto-apply
for low-blast-radius reversible fixes. All outcomes are logged
to the audit trail.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.schemas.self_guardian import FixExecutionResult, FixProposal

log = logging.getLogger(__name__)


class Remediator:
    """Executes FixProposals and logs outcomes.

    Stateless by design — all state is in the proposals and results.
    """

    def execute(
        self, proposal: FixProposal, approved: bool = False
    ) -> FixExecutionResult:
        """Execute a fix proposal.

        Args:
            proposal: The FixProposal to execute.
            approved: Whether the proposal has been approved for execution.
                For proposals that require approval, this must be True.

        Returns:
            A FixExecutionResult with the outcome.
        """
        started_at = datetime.now(timezone.utc)

        if proposal.requires_approval and not approved:
            log.info(
                "Fix %s/%s requires approval — rejected",
                proposal.agent_name,
                proposal.action,
            )
            return FixExecutionResult(
                proposal_id=proposal.alert_id,
                success=False,
                outcome="rejected",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error_message="Approval required but not granted",
            )

        log.info(
            "Executing fix for %s: %s (blast_radius=%s, reversible=%s)",
            proposal.agent_name,
            proposal.action,
            proposal.blast_radius.value,
            proposal.reversible,
        )

        try:
            result = self._apply_action(proposal)
            return result
        except Exception as exc:
            log.error("Fix execution failed for %s: %s", proposal.alert_id, exc)
            return FixExecutionResult(
                proposal_id=proposal.alert_id,
                success=False,
                outcome="failed",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error_message=str(exc),
            )

    def _apply_action(
        self, proposal: FixProposal
    ) -> FixExecutionResult:
        """Apply the specific fix action.

        This is a stub that logs the intended action. Real implementations
        would perform the actual remediation (e.g., switch model config,
        pause schedule, disable feature flag).
        """
        started_at = datetime.now(timezone.utc)

        if proposal.action == "rollback_prompt":
            log.info("Would rollback prompt for %s", proposal.agent_name)
        elif proposal.action == "switch_model":
            log.info("Would switch model for %s", proposal.agent_name)
        elif proposal.action == "rerun_workflow":
            log.info("Would rerun workflow for %s", proposal.agent_name)
        elif proposal.action == "pause_schedule":
            log.info("Would pause schedule for %s", proposal.agent_name)
        elif proposal.action == "disable_tool":
            log.info("Would disable tool for %s", proposal.agent_name)
        elif proposal.action == "notify_operator":
            log.info("Would notify operator about %s", proposal.agent_name)
        else:
            log.warning("Unknown fix action: %s", proposal.action)

        return FixExecutionResult(
            proposal_id=proposal.alert_id,
            success=True,
            outcome="applied",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )
