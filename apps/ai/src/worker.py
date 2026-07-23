"""
OntologyAI Temporal Worker — V5.1 Canonical Names.

Default active roster is EXACTLY 6 V5.1 workflows:
    ChiefOfStaffWorkflow, DiscoveryWorkflow, OntologyMappingWorkflow,
    TruthAnalysisWorkflow, WorkflowBuilderWorkflow, GovernanceWorkflow

V6 StrategyWorkflow is gated behind ``ENABLE_V6_WORKFLOWS=on``.
Legacy V4.1 workflows are gated behind ``LEGACY_FDE_MODULES=on``.

Task queue: ONTOLOGYAI-MAIN-QUEUE (env-overridable, legacy fallback)
"""
from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from src.orchestration.queue import ONTOLOGYAI_MAIN_QUEUE, resolve_task_queue

# ── V5.1 canonical workflow imports (always importable) ─────────────────
from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
from src.workflows.discovery_workflow import DiscoveryWorkflow
from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
from src.workflows.governance_workflow import GovernanceWorkflow

# ── Activities ──────────────────────────────────────────────────────────
from src.activities.run_pulse_agent import run_pulse_agent
from src.activities.run_anomaly_agent import run_anomaly_agent
from src.activities.run_investor_agent import run_investor_agent
from src.activities.run_qa_agent import run_qa_agent
from src.activities.send_slack_message import send_slack_message
from src.activities.run_guardian_watchlist import run_guardian_watchlist
from src.activities.compile_n8n_workflow import compile_n8n_workflow
from src.activities.memory_maintenance import decay_memory_weights, expire_old_memories, optimize_memory_performance

log = logging.getLogger("ontology_ai.worker")

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = resolve_task_queue()
MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT_ACTIVITIES", "10"))


def _build_workflow_list() -> list[type]:
    """Build the registered workflow list based on env flags.

    Default: exactly 6 V5.1 canonical workflows.
    V6 (+StrategyWorkflow) added when ``ENABLE_V6_WORKFLOWS=on``.
    Legacy V4.1 workflows added when ``LEGACY_FDE_MODULES=on``.
    """
    workflows: list[type] = [
        ChiefOfStaffWorkflow,
        DiscoveryWorkflow,
        OntologyMappingWorkflow,
        TruthAnalysisWorkflow,
        WorkflowBuilderWorkflow,
        GovernanceWorkflow,
    ]

    if os.getenv("ENABLE_V6_WORKFLOWS") == "on":
        from src.workflows.strategy_workflow import StrategyWorkflow
        workflows.append(StrategyWorkflow)

    if os.getenv("LEGACY_FDE_MODULES") == "on":
        from src.workflows.pulse_workflow import PulseWorkflow
        from src.workflows.investor_workflow import InvestorWorkflow
        from src.workflows.self_analysis_workflow import SelfAnalysisWorkflow
        from src.workflows.eval_loop_workflow import EvalLoopWorkflow
        from src.workflows.compression_workflow import CompressionWorkflow
        from src.workflows.weight_decay_workflow import WeightDecayWorkflow
        from src.workflows.memory_maintenance_workflow import MemoryMaintenanceWorkflow
        from src.workflows.fpa_workflow import FPAWorkflow
        from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow
        from src.workflows.reliability_workflow import ReliabilityWorkflow
        from src.workflows.comms_workflow import CommsWorkflow
        workflows.extend([
            PulseWorkflow,
            InvestorWorkflow,
            SelfAnalysisWorkflow,
            EvalLoopWorkflow,
            CompressionWorkflow,
            WeightDecayWorkflow,
            MemoryMaintenanceWorkflow,
            FPAWorkflow,
            GrowthAnalyticsWorkflow,
            ReliabilityWorkflow,
            CommsWorkflow,
        ])

    return workflows


async def create_worker() -> Worker:
    """Creates and returns configured Temporal worker (not started)."""
    client = await Client.connect(TEMPORAL_HOST)
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=_build_workflow_list(),
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
            compile_n8n_workflow,
        ],
        max_concurrent_activities=MAX_CONCURRENT,
    )


async def main() -> None:
    """Entry point for the Temporal worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log.info("Connecting to Temporal at %s", TEMPORAL_HOST)
    log.info("Task queue: %s", TASK_QUEUE)

    worker = await create_worker()

    wf_count = len(worker._workflows) if hasattr(worker, "_workflows") else "?"
    log.info("Worker started — listening on %s", TASK_QUEUE)
    log.info("Workflows registered: %s — V5.1 canonical (6) | V6=%s | Legacy=%s",
             wf_count,
             os.getenv("ENABLE_V6_WORKFLOWS", "off"),
             os.getenv("LEGACY_FDE_MODULES", "off"))
    log.info("Activities: 10 registered (n8n compile) | V5.1 specialists: chief_of_staff, discovery, ontology_mapping, truth_analysis, workflow_builder, governance")

    async with worker:
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
