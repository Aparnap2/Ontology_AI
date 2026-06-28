"""Data specialist workflow — handles @data mentions."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from src.agents.data.graph import DataGraph


@activity.defn
async def run_bi_analyst(payload: dict) -> dict:
    agent = DataGraph()
    result = agent.invoke(payload)
    return result


@workflow.defn
class DataWorkflow:
    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        question = input_data.get("question", "")
        tenant_id = input_data.get("tenant_id", "default")
        result = await workflow.execute_activity(
            run_bi_analyst,
            args=[{"question": question, "tenant_id": tenant_id}],
            start_to_close_timeout=timedelta(seconds=120),
        )
        return {"ok": True, "qa_result": result, "specialist_type": "data"}
