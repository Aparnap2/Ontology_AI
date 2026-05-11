"""QA state - stub for V3.0."""
from typing import TypedDict


class QAState(TypedDict, total=False):
    tenant_id: str
    metrics: dict
    memory_context: str
    draft: str
    narrative: str
    slack_message: str
    slack_blocks: list
    error: str
    retry_count: int
    langfuse_trace_id: str