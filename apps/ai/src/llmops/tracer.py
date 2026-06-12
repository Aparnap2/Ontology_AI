"""Langfuse @observe decorator — zero test impact.
No-op if LANGFUSE_SECRET_KEY or LANGFUSE_ENABLED not set."""
from __future__ import annotations

import os
import functools
from typing import Any, Callable

try:
    from langfuse import observe, get_client

    def _get_langfuse():
        try:
            return get_client()
        except Exception:
            return None

    LANGFUSE_AVAILABLE = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
except ImportError:
    LANGFUSE_AVAILABLE = False
    _get_langfuse = lambda: None
    observe = lambda **kw: lambda fn: fn


def traced(agent: str, signature: str, as_type: str = "generation"):
    """Decorator. Pure pass-through if Langfuse not enabled.

    Args:
        agent: Agent name for tracing (e.g. 'finance_guardian')
        signature: Operation signature (e.g. 'decide_alert')
        as_type: Langfuse observation type ('generation' | 'span' | 'retrieval')
    """
    if not LANGFUSE_AVAILABLE:
        def passthrough(fn: Callable) -> Callable:
            return fn
        return passthrough

    def decorator(fn: Callable) -> Callable:
        langfuse_observe = observe(name=f"{agent}.{signature}", as_type=as_type)

        @functools.wraps(fn)
        @langfuse_observe
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                raise

        return wrapper
    return decorator


def trace_chat_completion(fn: Callable) -> Callable:
    """Decorator for chat_completion to trace every LLM call."""
    if not LANGFUSE_AVAILABLE:
        return fn

    langfuse_observe = observe(name="llm.chat_completion", as_type="generation")

    @functools.wraps(fn)
    @langfuse_observe
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return wrapper


def trace_dspy(fn: Callable) -> Callable:
    """Decorator for DSPy predictor calls."""
    if not LANGFUSE_AVAILABLE:
        return fn

    langfuse_observe = observe(name="dspy.predict", as_type="generation")

    @functools.wraps(fn)
    @langfuse_observe
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return wrapper
