"""Finance specialist workflow — handles @finance mentions."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from src.agents.finance.graph import FinanceGraph


@activity.defn
async def run_finance_guardian(payload: dict) -> dict:
    agent = FinanceGraph()
    result = agent.invoke(payload)
    return result


@workflow.defn
class FinanceWorkflow:
    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        question = input_data.get("question", "")
        tenant_id = input_data.get("tenant_id", "default")
        result = await workflow.execute_activity(
            run_finance_guardian,
            args=[{"question": question, "tenant_id": tenant_id}],
            start_to_close_timeout=timedelta(seconds=120),
        )
        return {"ok": True, "qa_result": result, "specialist_type": "finance"}
