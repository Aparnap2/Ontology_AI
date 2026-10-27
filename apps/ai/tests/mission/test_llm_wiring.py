"""LLM wiring proofs — requirement #1.

All generation in ``src/mission/`` goes through ``src/config/llm.py``
(``chat_completion_with_metrics``). Grep-able proof: no direct OpenAI
instantiation anywhere in the mission subtree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import llm as llm_module
from src.mission.skill_contracts import SkillContext
from src.mission.skills import llm_ops

MISSION_DIR = Path(__file__).resolve().parents[2] / "src" / "mission"


class TestLLMWiring:
    def test_no_direct_openai_in_mission_subtree(self):
        """Grep-able proof: no openai.OpenAI(...) / OpenAI(...) in src/mission/."""
        banned = ("openai.OpenAI(", "OpenAI(", "from openai import", "import openai")
        hits: list[str] = []
        for py in sorted(MISSION_DIR.rglob("*.py")):
            text = py.read_text(encoding="utf-8")
            for token in banned:
                if token in text:
                    hits.append(f"{py.relative_to(MISSION_DIR)}: {token!r}")
        assert not hits, f"direct OpenAI references found in src/mission/: {hits}"

    def test_llm_ops_never_import_openai_directly(self):
        """llm_ops.py imports the config module, never the openai package."""
        text = Path(llm_ops.__file__).read_text(encoding="utf-8")
        assert "openai" not in text.lower()

    async def test_summarize_uses_chat_completion_with_metrics(self, monkeypatch):
        """The summarize primitive routes through chat_completion_with_metrics."""
        calls: dict = {}

        def fake_chat(messages, model=None, max_tokens=500, temperature=0.0, json_mode=False, **extra):
            calls["messages"] = messages
            calls["model"] = model
            return llm_module.LLMCallResult(content="A crisp summary.", model="test-model")

        monkeypatch.setattr(llm_module, "chat_completion_with_metrics", fake_chat)
        ctx = SkillContext(tenant_id="t1")
        out = await llm_ops.summarize(ctx, "lots of evidence content", max_tokens=250)
        assert calls["messages"], "summarize must build a message list"
        assert "A crisp summary." in out

    async def test_llm_ops_return_structured_results(self, monkeypatch):
        """JSON-requesting primitives parse the model payload into dicts."""
        def fake_chat(messages, model=None, max_tokens=500, temperature=0.0, json_mode=False, **extra):
            return llm_module.LLMCallResult(
                content='{"selected": "option-2", "rationale": "higher roi", "confidence": 0.8, "terminal": true}',
                model="test-model",
            )

        monkeypatch.setattr(llm_module, "chat_completion_with_metrics", fake_chat)
        ctx = SkillContext(tenant_id="t1")
        decision = await llm_ops.compare_options(ctx, [{"id": "option-1"}, {"id": "option-2"}], "roi")
        assert decision["selected"] == "option-2"
        assert decision["terminal"] is True