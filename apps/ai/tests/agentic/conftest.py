"""
Agentic Test Configuration - Real LLM + Real Docker + Langfuse

Per the TDD strategy: Layer 3 tests prove the real system works.
Provider: Single source of truth from src.config.llm.
"""
import os
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load repo-root .env first, then apps/ai/.env overrides
_repo_root = Path(__file__).resolve().parents[4]
load_dotenv(_repo_root / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Snapshot real credentials at import time.
# test_agentic_ai.py overwrites GROQ_API_KEY with fake values in test methods
# (lines 110, 185) and its _set_env fixture has no teardown to restore them.
# If test_agentic_ai.py runs first (alphabetical), the env var is corrupted
# before the session-scoped ollama_client fixture is created, causing ALL
# real-LLM tests to fail with 401.
_REAL_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
_REAL_GROQ_CHAT_MODEL = os.environ.get(
    "GROQ_CHAT_MODEL", os.environ.get("LLM_MODEL", "qwen/qwen3-32b")
)
_REAL_GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
_REAL_GROQ_REASONING_EFFORT = os.environ.get("GROQ_REASONING_EFFORT", "none")


class _OllamaChatAdapter:
    """Thin adapter wrapping OpenAI client in Ollama-compatible .chat() interface.

    Uses src.config.llm.get_llm_client() as the single source of truth
    instead of creating its own client.
    """

    def __init__(self, client, model: str, reasoning_effort: str) -> None:
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort

    def chat(self, model: str, messages: list[dict], options: dict | None = None):
        options = options or {}
        kwargs = {
            "model": model or self._model,
            "messages": messages,
            "max_tokens": options.get("num_predict", 500),
            "temperature": options.get("temperature", 0.0),
            "reasoning_effort": self._reasoning_effort,
        }
        if options.get("json_mode"):
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**kwargs)
        return {"message": {"content": response.choices[0].message.content}}


@pytest.fixture(scope="session")
def ollama_client():
    """Real LLM client — OpenAI client from src.config.llm.

    Uses the shared client singleton so all LLM calls go through one config.
    """
    from src.config.llm import get_llm_client

    client = get_llm_client()
    return _OllamaChatAdapter(
        client=client,
        model=_REAL_GROQ_CHAT_MODEL,
        reasoning_effort=_REAL_GROQ_REASONING_EFFORT,
    )


@pytest.fixture(scope="session")
def llm_model():
    """Model name — from config module (Groq default)."""
    from src.config.llm import get_chat_model

    return get_chat_model()


@pytest.fixture(scope="session")
def langfuse_client():
    """Real Langfuse client for trace verification."""
    from langfuse import Langfuse

    return Langfuse()


@pytest.fixture
def trace_context(langfuse_client):
    """Create a Langfuse trace context for the test."""
    trace = langfuse_client.start_as_current_observation(
        name=f"test_{datetime.utcnow().isoformat()}",
        metadata={"test": "agentic"},
    )
    yield trace


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "unit: Unit tests - pure Python, no Docker/LLM"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests - real Docker, mocked LLM"
    )
    config.addinivalue_line(
        "markers", "agentic: Agentic tests - real Docker + real LLM + Langfuse"
    )
