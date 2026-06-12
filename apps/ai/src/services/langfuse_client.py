"""
Langfuse client wrapper for Sarthi v1.0.

If LANGFUSE_ENABLED=false or keys are missing — all calls become no-ops.
This ensures zero code changes needed to disable observability.
"""
import os
import logging
from functools import lru_cache
from typing import Optional, Dict, Any

log = logging.getLogger("sarthi.langfuse")

ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"


@lru_cache(maxsize=1)
def _get_langfuse():
    """Returns Langfuse client singleton or None if disabled."""
    if not ENABLED:
        return None
    try:
        from langfuse import Langfuse
        client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        )
        log.info("✓ Langfuse connected: %s", os.getenv("LANGFUSE_HOST"))
        return client
    except Exception as e:
        log.warning("Langfuse init failed (non-fatal): %s", e)
        return None


def start_trace(name: str, tenant_id: str,
                metadata: Optional[Dict[str, Any]] = None) -> str:
    """Start a Langfuse trace. Returns trace_id string."""
    client = _get_langfuse()
    if not client:
        return ""
    try:
        trace = client.trace(
            name=name,
            user_id=tenant_id,
            metadata=metadata or {},
        )
        return trace.id
    except Exception as e:
        log.debug("Langfuse trace start failed: %s", e)
        return ""


def end_trace(trace_id: str, output: Optional[Dict[str, Any]] = None,
              level: str = "DEFAULT") -> None:
    """Update and flush a trace by ID."""
    client = _get_langfuse()
    if not client or not trace_id:
        return
    try:
        client.score(
            trace_id=trace_id,
            name="completed",
            value=1,
        )
        client.flush()
    except Exception as e:
        log.debug("Langfuse trace end failed: %s", e)


def score_trace(trace_id: str, name: str,
                value: float, comment: str = "") -> None:
    """Attach a numeric score to a trace (e.g. anomaly_score)."""
    client = _get_langfuse()
    if not client or not trace_id:
        return
    try:
        client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
    except Exception as e:
        log.debug("Langfuse score failed: %s", e)
