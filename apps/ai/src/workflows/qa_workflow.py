"""Backward-compat alias: QAWorkflow -> ChiefOfStaffWorkflow."""
import warnings
from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow as QAWorkflow

warnings.warn(
    "QAWorkflow is deprecated, use ChiefOfStaffWorkflow",
    DeprecationWarning,
    stacklevel=2,
)
