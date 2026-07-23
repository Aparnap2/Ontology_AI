"""OntologyAI V5.1 — Workflow registry (PRD §7 / §25).

Default roster is EXACTLY 6 V5.1 canonical workflows:
    ChiefOfStaffWorkflow, DiscoveryWorkflow, OntologyMappingWorkflow,
    TruthAnalysisWorkflow, WorkflowBuilderWorkflow, GovernanceWorkflow

V6 StrategyWorkflow is gated behind ``ENABLE_V6_WORKFLOWS=on`` and is
lazily imported (not loaded at module level) to keep the V5.1 contract clean.

Legacy FDE modules (Pulse/Investor/FPA/GrowthAnalytics/Reliability/Comms/etc.)
are gated behind ``LEGACY_FDE_MODULES=on``.
"""
from __future__ import annotations

import os

# ── Workflow imports (always importable at module level) ─────────────────
from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
from src.workflows.discovery_workflow import DiscoveryWorkflow
from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
from src.workflows.governance_workflow import GovernanceWorkflow


def _build_active_workflows() -> dict[str, type]:
    """Build the active workflow roster based on env flags.

    Default: exactly 6 V5.1 canonical workflows.
    V6 (StrategyWorkflow) added when ``ENABLE_V6_WORKFLOWS=on``.
    """
    base: dict[str, type] = {
        "ChiefOfStaffWorkflow": ChiefOfStaffWorkflow,
        "DiscoveryWorkflow": DiscoveryWorkflow,
        "OntologyMappingWorkflow": OntologyMappingWorkflow,
        "TruthAnalysisWorkflow": TruthAnalysisWorkflow,
        "WorkflowBuilderWorkflow": WorkflowBuilderWorkflow,
        "GovernanceWorkflow": GovernanceWorkflow,
    }
    if os.getenv("ENABLE_V6_WORKFLOWS") == "on":
        from src.workflows.strategy_workflow import StrategyWorkflow  # noqa: PLC0415

        base["StrategyWorkflow"] = StrategyWorkflow
    return base


# Active roster: dynamically built. Default = 6 entries.
ACTIVE_WORKFLOWS: dict[str, type] = _build_active_workflows()

# Alias used by some call sites / tests.
WORKFLOW_REGISTRY: dict[str, type] = dict(ACTIVE_WORKFLOWS)

# Agent registry: maps agent display names to their workflow classes.
# Used by AgentBus for peer-to-peer dispatch in ChiefOfStaff inbox drain.
AGENT_REGISTRY: dict[str, type] = {
    "ChiefOfStaff": ChiefOfStaffWorkflow,
    "Discovery": DiscoveryWorkflow,
    "OntologyMapper": OntologyMappingWorkflow,
    "TruthAnalyst": TruthAnalysisWorkflow,
    "WorkflowBuilder": WorkflowBuilderWorkflow,
    "Governance": GovernanceWorkflow,
}


def _build_route_map() -> dict[str, type]:
    """Build route map. V6 aliases included only when ENABLE_V6_WORKFLOWS=on."""
    base: dict[str, type] = {
        "@ontologyai": ChiefOfStaffWorkflow,
        "@agent": ChiefOfStaffWorkflow,
        "@ask": ChiefOfStaffWorkflow,
        "@chief": ChiefOfStaffWorkflow,
        "@discover": DiscoveryWorkflow,
        "@map": OntologyMappingWorkflow,
        "@truth": TruthAnalysisWorkflow,
        "@build": WorkflowBuilderWorkflow,
        "@govern": GovernanceWorkflow,
        "@sarthi": ChiefOfStaffWorkflow,
    }
    if os.getenv("ENABLE_V6_WORKFLOWS") == "on":
        from src.workflows.strategy_workflow import StrategyWorkflow  # noqa: PLC0415

        base["@strategy"] = StrategyWorkflow
    return base


ROUTE_MAP: dict[str, type] = _build_route_map()

__all__ = [
    "ChiefOfStaffWorkflow",
    "DiscoveryWorkflow",
    "OntologyMappingWorkflow",
    "TruthAnalysisWorkflow",
    "WorkflowBuilderWorkflow",
    "GovernanceWorkflow",
    "ACTIVE_WORKFLOWS",
    "WORKFLOW_REGISTRY",
    "AGENT_REGISTRY",
    "ROUTE_MAP",
]


# ── Legacy FDE modules (gated, not in active roster) ─────────────────────
# These are preserved (not deleted) but only imported when the operator
# explicitly enables them via LEGACY_FDE_MODULES=on. This keeps the repo's
# other modules importable without polluting the active V5.1 roster.
_LEGACY_MODULES = [
    "pulse_workflow",
    "investor_workflow",
    "fpa_workflow",
    "growth_analytics_workflow",
    "reliability_workflow",
    "comms_workflow",
    "qa_workflow",
    "finance_workflow",
    "data_workflow",
    "ops_workflow",
    "self_analysis_workflow",
    "eval_loop_workflow",
    "compression_workflow",
    "weight_decay_workflow",
    "memory_maintenance_workflow",
]


def _load_legacy() -> dict[str, type]:
    """Lazily import legacy workflow modules when enabled.

    Returns a name->class dict. Raises nothing; missing modules are skipped.
    """
    if os.getenv("LEGACY_FDE_MODULES") != "on":
        return {}
    legacy: dict[str, type] = {}
    import importlib

    for mod in _LEGACY_MODULES:
        try:
            m = importlib.import_module(f"src.workflows.{mod}")
            for attr in dir(m):
                obj = getattr(m, attr)
                if isinstance(obj, type) and attr.endswith("Workflow"):
                    legacy[attr] = obj
        except Exception:
            continue
    return legacy


# Expose legacy workflows only when the flag is set (lazy, non-breaking).
LEGACY_WORKFLOWS: dict[str, type] = _load_legacy()
