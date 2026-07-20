"""OntologyAI V5.1 — Workflow registry (PRD §7 / §25).

Exposes EXACTLY 7 active workflows:
    ChiefOfStaffWorkflow, DiscoveryWorkflow, OntologyMappingWorkflow,
    TruthAnalysisWorkflow, WorkflowBuilderWorkflow, GovernanceWorkflow,
    StrategyWorkflow

Legacy FDE modules (Pulse/Investor/FPA/GrowthAnalytics/Reliability/Comms/etc.)
are NOT in the active roster. They are gated behind the ``LEGACY_FDE_MODULES``
env flag and are not imported unless explicitly enabled, so existing imports
elsewhere in the repo are not broken at module-load time.
"""
from __future__ import annotations

import os

# ── Active V5.1 workflow roster (exactly 7) ──────────────────────────────
from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
from src.workflows.discovery_workflow import DiscoveryWorkflow
from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
from src.workflows.governance_workflow import GovernanceWorkflow
from src.workflows.strategy_workflow import StrategyWorkflow

# Active roster: name -> class. Exactly 7 entries.
ACTIVE_WORKFLOWS: dict[str, type] = {
    "ChiefOfStaffWorkflow": ChiefOfStaffWorkflow,
    "DiscoveryWorkflow": DiscoveryWorkflow,
    "OntologyMappingWorkflow": OntologyMappingWorkflow,
    "TruthAnalysisWorkflow": TruthAnalysisWorkflow,
    "WorkflowBuilderWorkflow": WorkflowBuilderWorkflow,
    "GovernanceWorkflow": GovernanceWorkflow,
    "StrategyWorkflow": StrategyWorkflow,
}

# Alias used by some call sites / tests.
WORKFLOW_REGISTRY: dict[str, type] = dict(ACTIVE_WORKFLOWS)

# ── Route map (PRD §25) ─────────────────────────────────────────────────
ROUTE_MAP: dict[str, type] = {
    # Default routes -> ChiefOfStaff
    "@ontologyai": ChiefOfStaffWorkflow,
    "@agent": ChiefOfStaffWorkflow,
    "@ask": ChiefOfStaffWorkflow,
    "@chief": ChiefOfStaffWorkflow,
    # Specialist aliases
    "@discover": DiscoveryWorkflow,
    "@map": OntologyMappingWorkflow,
    "@truth": TruthAnalysisWorkflow,
    "@build": WorkflowBuilderWorkflow,
    "@govern": GovernanceWorkflow,
    "@strategy": StrategyWorkflow,
    # Backward compatibility
    "@sarthi": ChiefOfStaffWorkflow,
}

__all__ = [
    "ChiefOfStaffWorkflow",
    "DiscoveryWorkflow",
    "OntologyMappingWorkflow",
    "TruthAnalysisWorkflow",
    "WorkflowBuilderWorkflow",
    "GovernanceWorkflow",
    "StrategyWorkflow",
    "ACTIVE_WORKFLOWS",
    "WORKFLOW_REGISTRY",
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
