"""Temporal Workflows for TrackGuard AI Agents — V4.1 Canonical Names."""

# New canonical workflow imports
from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
from src.workflows.fpa_workflow import FPAWorkflow
from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow
from src.workflows.reliability_workflow import ReliabilityWorkflow
from src.workflows.comms_workflow import CommsWorkflow

# Legacy backward compat aliases (deprecated)
from src.workflows.qa_workflow import QAWorkflow  # compat -> ChiefOfStaffWorkflow
from src.workflows.finance_workflow import FinanceWorkflow  # compat -> FPAWorkflow
from src.workflows.data_workflow import DataWorkflow  # compat -> GrowthAnalyticsWorkflow
from src.workflows.ops_workflow import OpsWorkflow  # compat -> ReliabilityWorkflow

# Other existing workflows
from src.workflows.pulse_workflow import PulseWorkflow
from src.workflows.investor_workflow import InvestorWorkflow
from src.workflows.self_analysis_workflow import SelfAnalysisWorkflow
from src.workflows.eval_loop_workflow import EvalLoopWorkflow
from src.workflows.compression_workflow import CompressionWorkflow
from src.workflows.weight_decay_workflow import WeightDecayWorkflow
from src.workflows.memory_maintenance_workflow import MemoryMaintenanceWorkflow

__all__ = [
    "PulseWorkflow",
    "InvestorWorkflow",
    "ChiefOfStaffWorkflow",
    "FPAWorkflow",
    "GrowthAnalyticsWorkflow",
    "ReliabilityWorkflow",
    "CommsWorkflow",
    "SelfAnalysisWorkflow",
    "EvalLoopWorkflow",
    "CompressionWorkflow",
    "WeightDecayWorkflow",
    "MemoryMaintenanceWorkflow",
    # Legacy backward compat
    "QAWorkflow",
    "FinanceWorkflow",
    "DataWorkflow",
    "OpsWorkflow",
]
