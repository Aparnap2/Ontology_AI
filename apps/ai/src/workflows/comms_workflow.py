"""CommsWorkflow — Communications specialist (new workflow).

Handles @comms mentions. Canonical name: "CommsWorkflow".
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from src.agents.comms.graph import CommsGraph


@activity.defn
async def run_comms_specialist(payload: dict) -> dict:
    """
    Run the Communications specialist agent.

    Args:
        payload: dict with question and tenant_id

    Returns:
        dict with response from comms agent
    """
    agent = CommsGraph()
    result = await agent.invoke(payload)
    return result


@workflow.defn(name="CommsWorkflow")
class CommsWorkflow:
    """Communications specialist workflow — handles @comms mentions."""

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        question = input_data.get("question", "")
        tenant_id = input_data.get("tenant_id", "default")
        result = await workflow.execute_activity(
            run_comms_specialist,
            args=[{"question": question, "tenant_id": tenant_id}],
            start_to_close_timeout=timedelta(seconds=120),
        )
        return {"ok": True, "qa_result": result, "specialist_type": "comms"}
