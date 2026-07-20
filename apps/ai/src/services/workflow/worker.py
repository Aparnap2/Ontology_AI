"""
Temporal Worker for OntologyAI AI Agents.

Registers all workflows and activities with Temporal.

Note: Activities communicate with memory-service and decision-engine via
Redpanda events, NOT in-process Python imports.

Task queue: ONTOLOGYAI-MAIN-QUEUE (env-overridable, legacy fallback)
"""
from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from src.orchestration.queue import resolve_task_queue

log = logging.getLogger("ontology_ai.worker")

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = resolve_task_queue()
MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT_ACTIVITIES", "10"))


async def create_worker() -> Worker:
    """
    Creates and returns configured Temporal worker (not started).

    Registers:
    - Workflows: PulseWorkflow, InvestorWorkflow, QAWorkflow,
                 SelfAnalysisWorkflow, EvalLoopWorkflow,
                 CompressionWorkflow, WeightDecayWorkflow,
                 MemoryMaintenanceWorkflow
    - Activities: run_pulse_agent, run_anomaly_agent,
                 run_investor_agent, run_qa_agent,
                 send_slack_message, run_guardian_watchlist,
                 decay_memory_weights, expire_old_memories,
                 optimize_memory_performance
    """
    client = await Client.connect(TEMPORAL_HOST)

    # Import workflows - use local imports for worker registration
    # Note: These workflows are now in the moved location but we import
    # from original location for backward compatibility during transition
    from src.workflows.pulse_workflow import PulseWorkflow
    from src.workflows.investor_workflow import InvestorWorkflow
    from src.workflows.qa_workflow import QAWorkflow
    from src.workflows.self_analysis_workflow import SelfAnalysisWorkflow
    from src.workflows.eval_loop_workflow import EvalLoopWorkflow
    from src.workflows.compression_workflow import CompressionWorkflow
    from src.workflows.weight_decay_workflow import WeightDecayWorkflow
    from src.workflows.memory_maintenance_workflow import MemoryMaintenanceWorkflow

    # Import activities
    from src.activities.run_pulse_agent import run_pulse_agent
    from src.activities.run_anomaly_agent import run_anomaly_agent
    from src.activities.run_investor_agent import run_investor_agent
    from src.activities.run_qa_agent import run_qa_agent
    from src.activities.send_slack_message import send_slack_message
    from src.activities.run_guardian_watchlist import run_guardian_watchlist
    from src.activities.memory_maintenance import (
        decay_memory_weights,
        expire_old_memories,
        optimize_memory_performance,
    )

    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            PulseWorkflow,
            InvestorWorkflow,
            QAWorkflow,
            SelfAnalysisWorkflow,
            EvalLoopWorkflow,
            CompressionWorkflow,
            WeightDecayWorkflow,
            MemoryMaintenanceWorkflow,
        ],
        activities=[
            run_pulse_agent,
            run_anomaly_agent,
            run_investor_agent,
            run_qa_agent,
            send_slack_message,
            run_guardian_watchlist,
            decay_memory_weights,
            expire_old_memories,
            optimize_memory_performance,
        ],
        max_concurrent_activities=MAX_CONCURRENT,
    )


async def main() -> None:
    """
    Entry point for the Temporal worker.
    
    Run with:
        python -m src.services.workflow.worker
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log.info("Connecting to Temporal at %s", TEMPORAL_HOST)
    log.info("Task queue: %s", TASK_QUEUE)

    worker = await create_worker()

    log.info("Worker started — listening on %s", TASK_QUEUE)
    log.info(
        "Workflows: PulseWorkflow, InvestorWorkflow, QAWorkflow, "
        "SelfAnalysisWorkflow, EvalLoopWorkflow, CompressionWorkflow, "
        "WeightDecayWorkflow, MemoryMaintenanceWorkflow"
    )
    log.info("Activities: 9 registered")

    async with worker:
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())