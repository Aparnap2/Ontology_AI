"""
Agentic Test Configuration - Real LLM + Real Docker + Langfuse

Per the TDD strategy: Layer 3 tests prove the real system works.
Provider priority: Groq (GROQ_API_KEY) → Ollama Cloud/local.
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


class _GroqChatAdapter:
    """Ollama-compatible .chat() interface backed by Groq OpenAI API."""

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=os.environ["GROQ_API_KEY"],
        )
        self._reasoning_effort = os.environ.get("GROQ_REASONING_EFFORT", "none")

    def chat(self, model: str, messages: list[dict], options: dict | None = None):
        options = options or {}
        kwargs = {
            "model": model,
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
    """Real LLM client — Groq when GROQ_API_KEY is set, else Ollama."""
    if os.environ.get("GROQ_API_KEY"):
        return _GroqChatAdapter()

    from ollama import Client as OllamaClient

    base_url = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com")
    api_key = os.environ.get("OLLAMA_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return OllamaClient(host=base_url, headers=headers)


@pytest.fixture(scope="session")
def llm_model():
    """Model name — Groq, LLM_MODEL, or Ollama fallback."""
    if os.environ.get("GROQ_API_KEY"):
        return os.environ.get(
            "GROQ_CHAT_MODEL",
            os.environ.get("LLM_MODEL", "qwen/qwen3-32b"),
        )
    return os.environ.get("OLLAMA_CHAT_MODEL", "qwen3-next:80b-cloud")


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
