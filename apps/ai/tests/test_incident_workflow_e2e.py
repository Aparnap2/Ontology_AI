"""IncidentWorkflow E2E Test — real Temporal server, real worker, real execution.

Connects to the Temporal server on localhost:7233, starts a worker with all 9
activities registered, executes the IncidentWorkflow with a real incident payload,
and verifies the result.

Key observations from the codebase:
- Vendor ticket is created with status="open" by InMemoryVendorTicketStore
- verify_recovery checks ticket.status in ("resolved", "closed") -> fails for "open"
- Therefore the workflow takes the "escalated" path (recovery not verified)
- Idempotency key is built from tenant:mission:operation:target:scope
  Using unique vendor_id per test run avoids duplicate detection

Phase: INTEGRATION (real Temporal server, real worker)
"""

from __future__ import annotations

import uuid

import pytest
from temporalio.client import Client
from temporalio.worker import Worker

from src.workflows.incident_workflow import IncidentWorkflow
from src.activities.incident_activities import (
    create_situation,
    assemble_checkpoint,
    run_investigation,
    generate_action_intent,
    submit_to_control_plane,
    execute_capability,
    verify_recovery_activity,
    resolve_situation,
    escalate_situation,
)

TEMPORAL_ADDRESS = "localhost:7233"
TEMPORAL_NAMESPACE = "default"


@pytest.mark.asyncio
async def test_incident_workflow_e2e():
    """Run the full V7 hero path through real Temporal.

    Expected path:
      create_situation -> assemble_checkpoint -> run_investigation ->
      generate_action_intent -> submit_to_control_plane -> execute_capability ->
      sleep(0.1s) -> verify_recovery (fails, ticket is "open") ->
      escalate_situation -> result["status"] == "escalated"
    """
    run_id = uuid.uuid4().hex[:8]
    incident_id = f"INC-{run_id.upper()}"
    vendor_id = f"vendor-e2e-{run_id}"

    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)

    task_queue = f"test-incident-{run_id}"

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[IncidentWorkflow],
        activities=[
            create_situation,
            assemble_checkpoint,
            run_investigation,
            generate_action_intent,
            submit_to_control_plane,
            execute_capability,
            verify_recovery_activity,
            resolve_situation,
            escalate_situation,
        ],
    )

    incident_payload = {
        "incident_id": incident_id,
        "tenant_id": "t-acme",
        "title": "Payment gateway 503 errors",
        "description": "Stripe payment gateway returning 503 since 14:02",
        "vendor_id": vendor_id,
        "severity": "critical",
        "detected_at": "2026-09-14T10:30:00Z",
        "source": "monitoring",
        "reporter": "ops-bot",
        "mission_id": f"m-e2e-{run_id}",
    }

    async with worker:
        handle = await client.start_workflow(
            IncidentWorkflow.run,
            incident_payload,
            id=f"incident-{incident_id}",
            task_queue=task_queue,
        )

        result = await handle.result()

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result["status"] in ("resolved", "escalated"), (
            f"Expected resolved or escalated, got {result['status']}"
        )

        assert "situation" in result, "Result missing 'situation' key"
        situation = result["situation"]
        assert situation["id"] == f"sit-{incident_id}", (
            f"Situation ID mismatch: {situation['id']}"
        )
        assert situation["tenant_id"] == "t-acme"
        assert situation["severity"] == "critical"

        assert "timeline" in result, "Result missing 'timeline' key"
        assert len(result["timeline"]) >= 7, (
            f"Timeline too short: {result['timeline']}"
        )

        assert result["status"] == "escalated", (
            f"Expected escalated (vendor ticket starts open), got {result['status']}"
        )
        assert "INVESTIGATION_COMPLETED" in result["timeline"]
        assert "VENDOR_TICKET_CREATED" in result["timeline"]
        assert "RECOVERY_VERIFIED_FALSE" in result["timeline"]
        assert "ESCALATED" in result["timeline"]

        assert "vendor_ticket" in result
        ticket = result["vendor_ticket"]
        assert ticket["vendor_id"] == vendor_id
        assert ticket["status"] == "open"
