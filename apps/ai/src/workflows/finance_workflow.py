"""Backward-compat alias: FinanceWorkflow -> FPAWorkflow."""
import warnings
from src.workflows.fpa_workflow import FPAWorkflow as FinanceWorkflow

warnings.warn(
    "FinanceWorkflow is deprecated, use FPAWorkflow",
    DeprecationWarning,
    stacklevel=2,
)
