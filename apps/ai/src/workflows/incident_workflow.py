"""V7 IncidentWorkflow — Temporal workflow implementing the hero path.

Flow: Event -> Situation -> ContextCheckpoint -> Investigation ->
      ActionIntent -> Control Plane -> Vendor Ticket -> Temporal Wait ->
      Recovery Verification -> Resolution

This is a real Temporal workflow that orchestrates the full incident-to-
resolution path using existing V7 library code via activities.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

try:
    from temporalio import workflow

    with workflow.unsafe.imports_passed_through():
        pass

    @workflow.defn(name="IncidentWorkflow", sandboxed=False)
    class IncidentWorkflow:
        """V7 Incident-to-Resolution workflow.

        Orchestrates the complete hero path:
          Event -> Situation -> ContextCheckpoint -> Investigation ->
          ActionIntent -> Control Plane -> Vendor Ticket ->
          Temporal Wait -> Recovery Verification -> Resolution

        All heavy lifting happens in activities. This workflow is the
        pure deterministic orchestration skeleton.
        """

        @workflow.run
        async def run(self, incident_data: dict[str, Any]) -> dict[str, Any]:
            """Execute the incident-to-resolution hero path.

            Parameters
            ----------
            incident_data:
                Dict with keys: incident_id, tenant_id, title, description,
                vendor_id, severity, detected_at, source, reporter.

            Returns
            -------
            dict with status (resolved|escalated), situation, and audit info.
            """
            # Step 1: Create Situation from incident
            situation: dict[str, Any] = await workflow.execute_activity(
                "create_situation",
                incident_data,
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 2: Assemble ContextCheckpoint
            checkpoint: dict[str, Any] = await workflow.execute_activity(
                "assemble_checkpoint",
                situation,
                start_to_close_timeout=timedelta(seconds=15),
            )

            # Step 3: Run investigation (deterministic — no LLM)
            investigation_result: dict[str, Any] = await workflow.execute_activity(
                "run_investigation",
                checkpoint,
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Step 4: Generate ActionIntent
            action_intent: dict[str, Any] = await workflow.execute_activity(
                "generate_action_intent",
                investigation_result,
                start_to_close_timeout=timedelta(seconds=10),
            )

            # Step 5: Submit through Control Plane
            authorized: dict[str, Any] = await workflow.execute_activity(
                "submit_to_control_plane",
                action_intent,
                start_to_close_timeout=timedelta(seconds=30),
            )

            # The control plane is authoritative. If it did not accept the
            # intent, no capability may run — a denied submission must stop
            # the workflow here rather than proceeding to a side effect.
            if not authorized.get("accepted", False):
                return {
                    "status": "rejected",
                    "situation": situation,
                    "recovery": {
                        "verified": False,
                        "reason": "control_plane_rejected",
                        "decision": authorized.get("decision", ""),
                    },
                    "vendor_ticket": {},
                    "timeline": [
                        "INCIDENT_INGESTED",
                        "SITUATION_OPENED",
                        "INVESTIGATION_COMPLETED",
                        "ACTION_INTENT_GENERATED",
                        "CONTROL_PLANE_REJECTED",
                    ],
                }

            # Step 6: Execute capability (create vendor ticket)
            # Override investigation-runner's hardcoded vendor_id with the
            # real vendor_id from the original incident payload.
            params = dict(authorized.get("intent", {}).get("requested_parameters", {}))
            if incident_data.get("vendor_id"):
                params["vendor_id"] = incident_data["vendor_id"]
            if incident_data.get("incident_id"):
                params["incident_id"] = incident_data["incident_id"]
            patched_authorized = {
                **authorized,
                "intent": {
                    **authorized.get("intent", {}),
                    "requested_parameters": params,
                },
            }
            vendor_result: dict[str, Any] = await workflow.execute_activity(
                "execute_capability",
                patched_authorized,
                start_to_close_timeout=timedelta(seconds=15),
            )

            # Step 7: Temporal wait for vendor response
            # In production this waits for a vendor callback signal via
            # workflow.wait_condition() or workflow.sleep() for a durable timer.
            # The demo uses a short durable sleep to prove the pattern.
            await workflow.sleep(timedelta(seconds=0.1))

            # Step 8: Verify recovery
            recovery: dict[str, Any] = await workflow.execute_activity(
                "verify_recovery",
                {"situation": situation, "vendor_result": vendor_result},
                start_to_close_timeout=timedelta(seconds=15),
            )

            # Step 9: Resolve or escalate
            if recovery.get("verified"):
                resolved: dict[str, Any] = await workflow.execute_activity(
                    "resolve_situation",
                    situation,
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return {
                    "status": "resolved",
                    "situation": resolved,
                    "recovery": recovery,
                    "vendor_ticket": vendor_result.get("vendor_ticket", {}),
                    "timeline": [
                        "INCIDENT_INGESTED",
                        "SITUATION_OPENED",
                        "INVESTIGATION_COMPLETED",
                        "ACTION_INTENT_GENERATED",
                        "CONTROL_PLANE_SUBMITTED",
                        "VENDOR_TICKET_CREATED",
                        "RECOVERY_VERIFIED",
                        "RESOLVED",
                    ],
                }
            else:
                escalated: dict[str, Any] = await workflow.execute_activity(
                    "escalate_situation",
                    situation,
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return {
                    "status": "escalated",
                    "situation": escalated,
                    "recovery": recovery,
                    "vendor_ticket": vendor_result.get("vendor_ticket", {}),
                    "timeline": [
                        "INCIDENT_INGESTED",
                        "SITUATION_OPENED",
                        "INVESTIGATION_COMPLETED",
                        "ACTION_INTENT_GENERATED",
                        "CONTROL_PLANE_SUBMITTED",
                        "VENDOR_TICKET_CREATED",
                        "RECOVERY_VERIFIED_FALSE",
                        "ESCALATED",
                    ],
                }

except Exception:  # pragma: no cover — Temporal optional at import time
    # Fallback: expose the workflow class under the workflow name when
    # Temporal is not available (keeps imports/tests working).
    from typing import Protocol, runtime_checkable

    @runtime_checkable
    class _WorkflowFallback(Protocol):
        """Protocol for fallback when Temporal is unavailable."""

        def run(self, incident_data: dict[str, Any]) -> dict[str, Any]: ...

    class IncidentWorkflow:  # type: ignore[no-redef]
        """Fallback when Temporal SDK is not importable."""

        def run(self, incident_data: dict[str, Any]) -> dict[str, Any]:
            raise NotImplementedError(
                "IncidentWorkflow requires the Temporal SDK. "
                "Install temporalio to run this workflow."
            )
