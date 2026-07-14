"""Backward-compat alias: DataWorkflow -> GrowthAnalyticsWorkflow."""
import warnings
from src.workflows.growth_analytics_workflow import GrowthAnalyticsWorkflow as DataWorkflow

warnings.warn(
    "DataWorkflow is deprecated, use GrowthAnalyticsWorkflow",
    DeprecationWarning,
    stacklevel=2,
)
