"""Backward-compat alias: OpsWorkflow -> ReliabilityWorkflow."""
import warnings
from src.workflows.reliability_workflow import ReliabilityWorkflow as OpsWorkflow

warnings.warn(
    "OpsWorkflow is deprecated, use ReliabilityWorkflow",
    DeprecationWarning,
    stacklevel=2,
)
