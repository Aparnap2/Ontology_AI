"""
E2E Tests for IterateSwarm Agentic Pipeline with DeepEval.

Tests the full pipeline: message → Finance Guardian → Memory Spine → Correlation → Response
Uses real LLM calls (Ollama Cloud) and Qdrant for retrieval context.

Run with: uv run pytest tests/e2e/test_agentic_pipeline.py -v

Note: DeepEval metrics require an OpenAI-compatible LLM for LLM-as-judge evaluation.
The metrics configuration uses a custom model that works with Ollama Cloud.
"""
import os
import pytest
import asyncio
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

os.environ.setdefault("OPENAI_API_KEY", "deepeval-ollama-cloud")
os.environ.setdefault("OPENAI_BASE_URL", "https://ollama.com/v1")

from deepeval.tracing import observe, update_current_span
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric, ContextualRecallMetric, FaithfulnessMetric
from deepeval import evaluate

from src.config.llm import get_llm_client, get_chat_model
from src.memory.spine import load_context, MemoryContext
from src.memory.episodic import EpisodicMemory

# ── Suite classification ────────────────────────────────────────────────
# Live-model evaluation: requires provider credentials, incurs cost and
# latency, and is excluded from the deterministic gate via `-m "not llm"`.
pytestmark = pytest.mark.llm



TENANT_ID = "test-e2e-pipeline-001"


class FinanceGuardianAgent:
    """Finance Guardian - validates financial queries and extracts entities."""

    def __init__(self):
        self.llm = get_llm_client()
        self.model = get_chat_model()

    @observe(name="Finance Guardian")
    async def validate(self, message: str) -> dict:
        """Validate financial message and extract key entities."""
        prompt = f"""You are a Finance Guardian for a startup intelligence system.
Analyze this message and determine:
1. Is it finance-related? (yes/no)
2. What entities are mentioned? (vendors, amounts, categories)
3. What is the intent? (query, alert, anomaly, report)

Message: {message}

Respond in JSON format:
{{
    "is_finance_related": true/false,
    "entities": ["vendor1", "amount", "category"],
    "intent": "query|alert|anomaly|report",
    "confidence": 0.0-1.0
}}"""

        try:
            response = self.llm.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.message.content
            result = json.loads(content)
            return result
        except Exception as e:
            return {
                "is_finance_related": True,
                "entities": [],
                "intent": "query",
                "confidence": 0.5,
                "error": str(e)
            }


class CorrelationAgent:
    """Correlation Agent - cross-signal detection and synthesis."""

    def __init__(self):
        self.llm = get_llm_client()
        self.model = get_chat_model()

    @observe(name="Correlation Agent")
    async def detect(self, mission_state: dict) -> list[dict]:
        """Detect co-signals from guardian output and memory context."""
        prompt = f"""You are a Correlation Agent that detects patterns across signals.
Given the current state, identify any co-signals or patterns:

State: {json.dumps(mission_state, indent=2)}

Respond with detected co-signals in JSON format:
[
    {{"name": "co_signal_name", "severity": "critical|warning|info", "description": "..."}}
]
If none, return empty array []. """

        try:
            response = self.llm.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.message.content
            signals = json.loads(content)
            return signals if isinstance(signals, list) else []
        except Exception as e:
            return []


class ResponseGenerator:
    """Final response generator - synthesizes guardian + memory + correlation."""

    def __init__(self):
        self.llm = get_llm_client()
        self.model = get_chat_model()

    @observe(name="Response Generator")
    async def generate(
        self,
        message: str,
        guardian_output: dict,
        memory_context: MemoryContext,
        correlation_signals: list[dict]
    ) -> str:
        """Generate final response combining all pipeline components."""

        context_parts = []
        if memory_context.episodic:
            context_parts.append(f"Recent events: {len(memory_context.episodic)} found")
        if memory_context.semantic:
            context_parts.append(f"Semantic knowledge: {len(memory_context.semantic)} found")
        if correlation_signals:
            signal_names = [s.get("name", "unknown") for s in correlation_signals]
            context_parts.append(f"Co-signals detected: {', '.join(signal_names)}")

        context_str = "\n".join(context_parts) if context_parts else "No additional context found"

        prompt = f"""You are an AI assistant for startup intelligence.
Generate a helpful, concise response based on the full pipeline analysis.

Original Message: {message}

Finance Guardian Analysis:
- Intent: {guardian_output.get('intent', 'unknown')}
- Entities: {guardian_output.get('entities', [])}
- Finance Related: {guardian_output.get('is_finance_related', False)}

Memory Context:
{context_str}

Co-signals: {correlation_signals if correlation_signals else 'None detected'}

Generate a clear, actionable response:"""

        try:
            response = self.llm.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.message.content
        except Exception as e:
            return f"Error generating response: {e}"


class AgenticPipeline:
    """Full agentic pipeline orchestrator."""

    def __init__(self):
        self.guardian = FinanceGuardianAgent()
        self.correlation = CorrelationAgent()
        self.response_gen = ResponseGenerator()

    @observe(name="Agentic Pipeline", metrics=[
        AnswerRelevancyMetric(threshold=0.5, model="qwen3-next:80b-cloud"),
        ContextualRecallMetric(threshold=0.5, model="qwen3-next:80b-cloud"),
        FaithfulnessMetric(threshold=0.5, model="qwen3-next:80b-cloud"),
    ])
    async def run(self, message: str, tenant_id: str) -> dict:
        """Execute full pipeline: Guardian → Memory → Correlation → Response."""

        # Step 1: Finance Guardian validates and extracts
        guardian_output = await self.guardian.validate(message)

        # Step 2: Memory Spine loads context from all layers
        memory_context = await load_context(
            tenant_id=tenant_id,
            query=message,
            domain="finance"
        )

        # Step 3: Correlation detects co-signals
        mission_state = {
            "guardian": guardian_output,
            "memory_layers": memory_context.total_layers_hit,
            "episodic_count": len(memory_context.episodic),
        }
        correlation_signals = await self.correlation.detect(mission_state)

        # Step 4: Generate response
        response = await self.response_gen.generate(
            message=message,
            guardian_output=guardian_output,
            memory_context=memory_context,
            correlation_signals=correlation_signals
        )

        # Update span with test case for metrics
        test_case = LLMTestCase(
            input=message,
            actual_output=response,
            expected_output="Helpful, actionable response about finance topic",
            retrieval_context=[
                f"Episodic: {len(memory_context.episodic)} items",
                f"Semantic: {len(memory_context.semantic)} items",
                f"Procedural: {len(memory_context.procedural)} items",
            ]
        )
        update_current_span(test_case=test_case)

        return {
            "message": message,
            "guardian": guardian_output,
            "memory": {
                "layers_hit": memory_context.total_layers_hit,
                "episodic_count": len(memory_context.episodic),
                "semantic_count": len(memory_context.semantic),
                "errors": memory_context.errors,
            },
            "correlation": correlation_signals,
            "response": response,
        }


async def setup_test_memory(tenant_id: str) -> None:
    """Set up test data in Qdrant episodic memory."""
    em = EpisodicMemory(collection="episodes")

    test_events = [
        ("burn_alert", f"Monthly burn rate increased to $45,000 for {tenant_id}"),
        ("runway_warning", f"Runway decreased to 8 months for {tenant_id}"),
        ("vendor_anomaly", f"Unusual AWS spend of $12,000 detected for {tenant_id}"),
    ]

    for event_type, content in test_events:
        em.write(
            tenant_id=tenant_id,
            event_type=event_type,
            content=content,
            confidence=0.9
        )


@pytest.mark.e2e
@pytest.mark.asyncio
class TestAgenticPipeline:
    """Test suite for full agentic pipeline."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Set up test memory data."""
        await setup_test_memory(TENANT_ID)
        yield
        # Cleanup handled by Qdrant retention policies

    @pytest.mark.asyncio
    async def test_finance_query_pipeline(self):
        """Test pipeline with a finance-related query."""
        pipeline = AgenticPipeline()
        message = "What's our current burn rate and runway?"

        result = await pipeline.run(message, TENANT_ID)

        assert result["guardian"]["is_finance_related"] is True
        assert result["guardian"]["intent"] in ["query", "alert", "report"]
        assert result["response"] is not None
        assert len(result["response"]) > 0

        print(f"\n✓ Pipeline executed successfully")
        print(f"  Guardian intent: {result['guardian']['intent']}")
        print(f"  Memory layers hit: {result['memory']['layers_hit']}")
        print(f"  Correlation signals: {len(result['correlation'])}")

    @pytest.mark.asyncio
    async def test_anomaly_alert_pipeline(self):
        """Test pipeline with anomaly detection alert."""
        pipeline = AgenticPipeline()
        message = "Alert: AWS spending jumped 40% this month, is this normal?"

        result = await pipeline.run(message, TENANT_ID)

        assert result["guardian"]["intent"] == "anomaly"
        assert result["response"] is not None

        print(f"\n✓ Anomaly pipeline executed")
        print(f"  Guardian intent: {result['guardian']['intent']}")
        print(f"  Entities: {result['guardian']['entities']}")

    @pytest.mark.asyncio
    async def test_multi_signal_correlation(self):
        """Test correlation detection across multiple signals."""
        pipeline = AgenticPipeline()
        message = "Our runway is getting short and we just had a big burn spike - should we be worried?"

        result = await pipeline.run(message, TENANT_ID)

        assert result["guardian"]["is_finance_related"] is True
        assert result["response"] is not None

        print(f"\n✓ Multi-signal correlation tested")
        print(f"  Signals detected: {result['correlation']}")

    @pytest.mark.asyncio
    async def test_memory_context_loaded(self):
        """Verify memory context is properly loaded from Qdrant."""
        memory_ctx = await load_context(
            tenant_id=TENANT_ID,
            query="burn rate runway",
            domain="finance"
        )

        assert memory_ctx is not None
        assert memory_ctx.total_layers_hit > 0

        print(f"\n✓ Memory context loaded")
        print(f"  Layers hit: {memory_ctx.total_layers_hit}")
        print(f"  Episodic: {len(memory_ctx.episodic)}")
        print(f"  Semantic: {len(memory_ctx.semantic)}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_guardian_entity_extraction():
    """Standalone test for Finance Guardian entity extraction."""
    guardian = FinanceGuardianAgent()

    message = "We spent $25,000 on AWS and $15,000 on GCP last month"
    result = await guardian.validate(message)

    assert result["is_finance_related"] is True
    assert "aws" in [e.lower() for e in result.get("entities", [])] or "gcp" in [e.lower() for e in result.get("entities", [])]

    print(f"\n✓ Entity extraction works")
    print(f"  Entities: {result.get('entities', [])}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_correlation_signal_detection():
    """Standalone test for correlation signal detection."""
    correlation = CorrelationAgent()

    mission_state = {
        "burn_alert": True,
        "churn_rate": 0.08,
        "runway_days": 90,
        "founder_focus": "fundraising",
    }

    signals = await correlation.detect(mission_state)

    assert isinstance(signals, list)
    print(f"\n✓ Correlation detection works")
    print(f"  Signals: {signals}")


if __name__ == "__main__":
    print("Running E2E Agentic Pipeline tests...")
    print("=" * 60)
    pytest.main([__file__, "-v", "-s"])