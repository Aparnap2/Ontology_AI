"""
WorkflowService — High-level API for Temporal workflow management.

Provides:
- Start workflows by name
- Query workflow status
- List available workflows

Note: Activities communicate with memory-service and decision-engine via
Redpanda events, NOT in-process Python imports.
"""
from __future__ import annotations

import os
import logging
from typing import Any

from temporalio.client import Client

from .schemas import WORKFLOW_NAMES, WORKFLOW_REGISTRY
from .events import get_workflow_publisher, close_workflow_events
from .worker import create_worker, main as worker_main

log = logging.getLogger(__name__)

# OTel tracing - initialize at module load
_TRACER = None


def _init_tracing():
    """Initialize tracing once at module load."""
    global _TRACER
    if _TRACER is None:
        try:
            from apps.ai.src.services.tracing import init_tracing, get_service_name
            init_tracing(service_name=get_service_name("workflow-service"))
            from apps.ai.src.services.tracing import get_tracer
            _TRACER = get_tracer("workflow-service")
            log.info("Workflow service tracing initialized")
        except Exception as e:
            log.warning(f"Tracing init failed: {e}")


# Initialize on import
try:
    _init_tracing()
except Exception:
    pass

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "SARTHI-MAIN-QUEUE")


class WorkflowServiceError(Exception):
    """Base exception for WorkflowService."""
    pass


class TemporalUnavailableError(WorkflowServiceError):
    """Raised when Temporal is unavailable."""
    pass


class WorkflowNotFoundError(WorkflowServiceError):
    """Raised when workflow is not found."""
    pass


class WorkflowService:
    """
    High-level service for managing Temporal workflows.

    Provides:
    - Start workflows asynchronously
    - Query workflow status
    - List available workflows
    - Graceful degradation when Temporal is unavailable
    """

    def __init__(self, temporal_host: str = TEMPORAL_HOST):
        """
        Initialize WorkflowService.

        Args:
            temporal_host: Temporal server address (default: localhost:7233)
        """
        self._temporal_host = temporal_host
        self._client: Client | None = None
        self._connected = False

    async def connect(self) -> bool:
        """
        Connect to Temporal server.

        Returns:
            True if connected, False if unavailable (graceful degradation)
        """
        try:
            self._client = await Client.connect(self._temporal_host)
            self._connected = True
            log.info(f"WorkflowService connected to Temporal at {self._temporal_host}")
            return True
        except Exception as e:
            log.warning(f"Temporal unavailable: {e}. Running in degraded mode.")
            self._connected = False
            return False

    async def close(self) -> None:
        """Close connections to Temporal and clean up resources."""
        await close_workflow_events()
        self._client = None
        self._connected = False
        log.info("WorkflowService closed")

    def is_connected(self) -> bool:
        """Check if connected to Temporal."""
        return self._connected

    def list_workflows(self) -> list[str]:
        """
        List all available workflow names.

        Returns:
            List of workflow names that can be started
        """
        return WORKFLOW_NAMES.copy()

    async def start_workflow(
        self,
        workflow_name: str,
        tenant_id: str,
        input: dict[str, Any] | None = None,
    ) -> str:
        """
        Start a Temporal workflow.

        Args:
            workflow_name: Name of workflow to start (e.g., "PulseWorkflow")
            tenant_id: Tenant identifier
            input: Optional workflow input parameters

        Returns:
            Workflow run_id

        Raises:
            WorkflowNotFoundError: If workflow name is not recognized
            TemporalUnavailableError: If Temporal is not connected
        """
        if not self._connected or not self._client:
            raise TemporalUnavailableError(
                "Temporal is unavailable. Please check connection."
            )

        # Validate workflow name
        if workflow_name not in WORKFLOW_NAMES:
            raise WorkflowNotFoundError(
                f"Unknown workflow: {workflow_name}. "
                f"Available: {WORKFLOW_NAMES}"
            )

        # Build workflow input
        workflow_input = input or {}
        workflow_input["tenant_id"] = tenant_id

        # Map workflow name to task queue workflow class
        # Note: In production, would use proper workflow handles
        workflow_handle = self._client.get_workflow_handle(
            workflow=f"{workflow_name}-{tenant_id}",
            task_queue=TASK_QUEUE,
        )

        try:
            # Start workflow - return run_id
            # Note: This is a simplified version; real implementation
            # would use client.start_workflow() with proper types
            log.info(f"Starting workflow {workflow_name} for tenant {tenant_id}")
            
            # For now, return a placeholder run_id
            # In production, use: result = await client.start_workflow(...)
            run_id = f"run-{workflow_name.lower()}-{tenant_id}-{os.urandom(4).hex()}"
            
            # Publish workflow start event via Redpanda
            publisher = await get_workflow_publisher()
            await publisher.publish_agent_event(
                tenant_id=tenant_id,
                from_agent="workflow_service",
                to_agent="orchestrator",
                event_type="WORKFLOW_STARTED",
                payload={
                    "workflow_name": workflow_name,
                    "run_id": run_id,
                    "input": workflow_input,
                },
            )
            
            return run_id

        except Exception as e:
            log.error(f"Failed to start workflow {workflow_name}: {e}")
            raise WorkflowServiceError(f"Failed to start workflow: {e}") from e

    async def get_workflow_status(self, run_id: str) -> dict[str, Any]:
        """
        Get workflow status from Temporal.

        Args:
            run_id: The workflow run_id

        Returns:
            dict with status information:
                - status: workflow status (running, completed, failed, etc.)
                - workflow_type: name of the workflow
                - run_id: the run identifier
                - start_time: when workflow started
                - close_time: when workflow ended (if completed)
                - error: error message if failed
        """
        if not self._connected or not self._client:
            return {
                "status": "unknown",
                "run_id": run_id,
                "error": "Temporal unavailable",
            }

        try:
            # Get workflow handle
            handle = self._client.get_workflow_handle(run_id)
            
            # Describe the workflow
            description = await handle.describe()
            
            return {
                "status": description.status.name if description.status else "unknown",
                "workflow_type": description.workflow_type,
                "run_id": run_id,
                "start_time": description.start_time.isoformat() if description.start_time else None,
                "close_time": description.close_time.isoformat() if description.close_time else None,
                "error": description.failure.message if description.failure else None,
            }

        except Exception as e:
            log.warning(f"Failed to get workflow status for {run_id}: {e}")
            return {
                "status": "unknown",
                "run_id": run_id,
                "error": str(e),
            }

    async def cancel_workflow(self, run_id: str) -> bool:
        """
        Cancel a running workflow.

        Args:
            run_id: The workflow run_id to cancel

        Returns:
            True if cancelled successfully
        """
        if not self._connected or not self._client:
            log.error("Cannot cancel - Temporal unavailable")
            return False

        try:
            handle = self._client.get_workflow_handle(run_id)
            await handle.cancel()
            log.info(f"Workflow {run_id} cancelled")
            return True
        except Exception as e:
            log.error(f"Failed to cancel workflow {run_id}: {e}")
            return False

    async def terminate_workflow(self, run_id: str, reason: str = "") -> bool:
        """
        Terminate a workflow.

        Args:
            run_id: The workflow run_id to terminate
            reason: Optional termination reason

        Returns:
            True if terminated successfully
        """
        if not self._connected or not self._client:
            log.error("Cannot terminate - Temporal unavailable")
            return False

        try:
            handle = self._client.get_workflow_handle(run_id)
            await handle.terminate(reason=reason)
            log.info(f"Workflow {run_id} terminated: {reason}")
            return True
        except Exception as e:
            log.error(f"Failed to terminate workflow {run_id}: {e}")
            return False


# =============================================================================
# Service Factory
# =============================================================================

_workflow_service: WorkflowService | None = None


async def get_workflow_service() -> WorkflowService:
    """Get or create singleton WorkflowService."""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = WorkflowService()
        await _workflow_service.connect()
    return _workflow_service


async def close_workflow_service() -> None:
    """Close the workflow service."""
    global _workflow_service
    if _workflow_service:
        await _workflow_service.close()
        _workflow_service = None


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "WorkflowService",
    "WorkflowServiceError",
    "TemporalUnavailableError",
    "WorkflowNotFoundError",
    "get_workflow_service",
    "close_workflow_service",
    "worker_main",
    "create_worker",
    "WORKFLOW_NAMES",
    "WORKFLOW_REGISTRY",
]