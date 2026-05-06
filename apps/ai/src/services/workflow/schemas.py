"""
Workflow Schemas — Type contracts for Temporal workflows.

Defines input/output types for all available workflows.
"""
from __future__ import annotations

from typing import Any, Dict, Literal
from pydantic import BaseModel, Field


# =============================================================================
# Common Types
# =============================================================================


class WorkflowInput(BaseModel):
    """Base input for all workflows."""
    tenant_id: str = Field(..., description="Tenant identifier")


class WorkflowResult(BaseModel):
    """Base result for all workflows."""
    ok: bool
    tenant_id: str
    error: str | None = None


# =============================================================================
# Pulse Workflow
# =============================================================================


class PulseWorkflowInput(WorkflowInput):
    """Input for PulseWorkflow."""
    notify_channel: str = "#metrics"


class PulseWorkflowResult(WorkflowResult):
    """Output from PulseWorkflow."""
    pulse_result: dict[str, Any] | None = None
    guardian_result: dict[str, Any] | None = None
    slack_result: dict[str, Any] | None = None


# =============================================================================
# Investor Workflow
# =============================================================================


class InvestorWorkflowInput(WorkflowInput):
    """Input for InvestorWorkflow."""
    notify_channel: str = "#investors"


class InvestorWorkflowResult(WorkflowResult):
    """Output from InvestorWorkflow."""
    investor_result: dict[str, Any] | None = None
    slack_result: dict[str, Any] | None = None


# =============================================================================
# QA Workflow
# =============================================================================


class QAWorkflowInput(WorkflowInput):
    """Input for QAWorkflow."""
    question: str = Field(..., description="Question to answer")
    notify_channel: str = "#qa"


class QAWorkflowResult(WorkflowResult):
    """Output from QAWorkflow."""
    question: str | None = None
    qa_result: dict[str, Any] | None = None
    slack_result: dict[str, Any] | None = None


# =============================================================================
# Memory Maintenance Workflow
# =============================================================================


class MemoryMaintenanceInput(BaseModel):
    """Input for MemoryMaintenanceWorkflow."""
    tenant_id: str | None = Field(default=None, description="Optional tenant filter")
    operations: list[str] = Field(
        default=["decay_weights", "expire_memories", "optimize_performance"],
        description="List of operations to perform"
    )


class MemoryMaintenanceResult(BaseModel):
    """Output from MemoryMaintenanceWorkflow."""
    workflow_id: str
    run_id: str
    start_time: str
    end_time: str | None = None
    operations_completed: list[str]
    errors: list[str]
    summary: dict[str, Any]


# =============================================================================
# Self Analysis Workflow
# =============================================================================


class SelfAnalysisInput(WorkflowInput):
    """Input for SelfAnalysisWorkflow."""


class SelfAnalysisResult(WorkflowResult):
    """Output from SelfAnalysisWorkflow."""
    analysis_data: dict[str, Any] | None = None


# =============================================================================
# Eval Loop Workflow
# =============================================================================


class EvalLoopInput(WorkflowInput):
    """Input for EvalLoopWorkflow."""
    eval_type: str = "llm_quality"


class EvalLoopResult(WorkflowResult):
    """Output from EvalLoopWorkflow."""
    eval_scores: dict[str, Any] | None = None


# =============================================================================
# Compression Workflow
# =============================================================================


class CompressionInput(WorkflowInput):
    """Input for CompressionWorkflow."""
    compression_level: str = "standard"


class CompressionResult(WorkflowResult):
    """Output from CompressionWorkflow."""
    compression_stats: dict[str, Any] | None = None


# =============================================================================
# Weight Decay Workflow
# =============================================================================


class WeightDecayInput(WorkflowInput):
    """Input for WeightDecayWorkflow."""
    decay_rate: float = 0.15


class WeightDecayResult(WorkflowResult):
    """Output from WeightDecayWorkflow."""
    decay_stats: dict[str, Any] | None = None


# =============================================================================
# Workflow Registry
# =============================================================================


WORKFLOW_REGISTRY: dict[str, type] = {
    "pulse": PulseWorkflowInput,
    "investor": InvestorWorkflowInput,
    "qa": QAWorkflowInput,
    "memory_maintenance": MemoryMaintenanceInput,
    "self_analysis": SelfAnalysisInput,
    "eval_loop": EvalLoopInput,
    "compression": CompressionInput,
    "weight_decay": WeightDecayInput,
}

WORKFLOW_NAMES: list[str] = [
    "PulseWorkflow",
    "InvestorWorkflow", 
    "QAWorkflow",
    "MemoryMaintenanceWorkflow",
    "SelfAnalysisWorkflow",
    "EvalLoopWorkflow",
    "CompressionWorkflow",
    "WeightDecayWorkflow",
]