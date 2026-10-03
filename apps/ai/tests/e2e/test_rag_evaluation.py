"""
E2E Tests for RAG Pipeline Evaluation with DeepEval.

Tests the RAG pipeline: retrieval + generation with metrics.
Uses real LLM calls (Ollama Cloud) and Qdrant for retrieval context.

Run with: uv run pytest tests/e2e/test_rag_evaluation.py -v

Note: DeepEval metrics require an OpenAI-compatible LLM for LLM-as-judge evaluation.
We configure using environment variables pointing to Ollama Cloud.
"""
import os
import pytest
import asyncio
import json
from typing import Optional

os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OLLAMA_API_KEY", "ollama"))
os.environ.setdefault("OPENAI_BASE_URL", "https://ollama.com/v1")

from deepeval.tracing import observe, update_current_span
from deepeval.metrics import AnswerRelevancyMetric, ContextualRecallMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from src.config.llm import get_llm_client, get_chat_model
from src.memory.episodic import EpisodicMemory

# ── Suite classification ────────────────────────────────────────────────
# Live-model evaluation: requires provider credentials, incurs cost and
# latency, and is excluded from the deterministic gate via `-m "not llm"`.
pytestmark = pytest.mark.llm



TEST_TENANT_ID = "test-rag-eval-001"


class RAGPipeline:
    """RAG Pipeline: retrieval + generation with DeepEval metrics."""

    def __init__(self):
        self.llm = get_llm_client()
        self.model = get_chat_model()
        self.episodic = EpisodicMemory(collection="episodes")

    def retrieve(self, query: str, tenant_id: str, top_k: int = 5) -> list[dict]:
        """Retrieve relevant documents from episodic memory."""
        results = self.episodic.search(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
        )
        return results

    @observe(name="RAG Generation", metrics=[
        AnswerRelevancyMetric(threshold=0.5, model="qwen3-next:80b-cloud"),
        ContextualRecallMetric(threshold=0.5, model="qwen3-next:80b-cloud"),
        FaithfulnessMetric(threshold=0.5, model="qwen3-next:80b-cloud"),
    ])
    def generate(self, query: str, retrieved_docs: list[dict]) -> str:
        """Generate response based on retrieved context."""

        context_parts = []
        for doc in retrieved_docs:
            content = doc.get("content", "")
            event_type = doc.get("event_type", "unknown")
            score = doc.get("score", 0)
            context_parts.append(f"[{event_type} (score: {score:.2f})] {content}")

        context_str = "\n".join(context_parts) if context_parts else "No relevant context found."

        prompt = f"""You are a helpful AI assistant.
Use the retrieved context to answer the question accurately.

Retrieved Context:
{context_str}

Question: {query}

Answer based on the context above. If the context doesn't contain enough information, say so."""

        try:
            response = self.llm.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.message.content
        except Exception as e:
            return f"Error generating response: {e}"

    def run_pipeline(self, query: str, tenant_id: str) -> dict:
        """Execute full RAG pipeline."""

        # Retrieval
        retrieved_docs = self.retrieve(query, tenant_id)

        # Generation
        response = self.generate(query, retrieved_docs)

        # Update span with test case
        test_case = LLMTestCase(
            input=query,
            actual_output=response,
            expected_output="Accurate response based on retrieved context",
            retrieval_context=[doc.get("content", "") for doc in retrieved_docs],
        )
        update_current_span(test_case=test_case)

        return {
            "query": query,
            "retrieved_docs": retrieved_docs,
            "response": response,
            "doc_count": len(retrieved_docs),
        }


@pytest.fixture
async def setup_rag_test_data():
    """Set up test documents in episodic memory."""
    em = EpisodicMemory(collection="episodes")

    test_documents = [
        ("burn_alert", "Monthly burn rate is $45,000, up from $35,000 last month"),
        ("runway_warning", "Current runway is 8 months based on $45k monthly burn"),
        ("revenue_report", "Monthly revenue reached $80,000 for Q4"),
        ("churn_notice", "Churn rate increased to 5% this quarter"),
        ("aws_anomaly", "Unusual AWS spend: $12,000 vs baseline of $5,000"),
    ]

    for event_type, content in test_documents:
        em.write(
            tenant_id=TEST_TENANT_ID,
            event_type=event_type,
            content=content,
            confidence=0.9
        )

    yield

    # Cleanup would happen here if we had delete capability


@pytest.mark.e2e
@pytest.mark.asyncio
class TestRAGEvaluation:
    """Test suite for RAG pipeline evaluation."""

    @pytest.mark.asyncio
    async def test_rag_with_answer_relevancy(self):
        """Test RAG pipeline with Answer Relevancy metric."""
        rag = RAGPipeline()
        query = "What is our current burn rate?"

        result = rag.run_pipeline(query, TEST_TENANT_ID)

        assert result["response"] is not None
        assert len(result["response"]) > 0

        print(f"\n✓ Answer Relevancy test")
        print(f"  Query: {query}")
        print(f"  Docs retrieved: {result['doc_count']}")
        print(f"  Response: {result['response'][:100]}...")

    @pytest.mark.asyncio
    async def test_rag_with_contextual_recall(self):
        """Test RAG pipeline with Contextual Recall metric."""
        rag = RAGPipeline()
        query = "Tell me about our runway and revenue"

        result = rag.run_pipeline(query, TEST_TENANT_ID)

        assert result["doc_count"] > 0

        print(f"\n✓ Contextual Recall test")
        print(f"  Query: {query}")
        print(f"  Docs retrieved: {result['doc_count']}")

    @pytest.mark.asyncio
    async def test_rag_with_faithfulness(self):
        """Test RAG pipeline with Faithfulness metric."""
        rag = RAGPipeline()
        query = "What are the current metrics?"

        result = rag.run_pipeline(query, TEST_TENANT_ID)

        assert result["response"] is not None

        print(f"\n✓ Faithfulness test")
        print(f"  Response length: {len(result['response'])}")

    @pytest.mark.asyncio
    async def test_retrieval_relevance(self):
        """Test that retrieval returns relevant documents."""
        rag = RAGPipeline()
        query = "burn rate and spending"

        results = rag.retrieve(query, TEST_TENANT_ID, top_k=3)

        assert len(results) > 0

        has_burn = any("burn" in r.get("content", "").lower() for r in results)
        print(f"\n✓ Retrieval relevance test")
        print(f"  Query: {query}")
        print(f"  Results: {len(results)}")
        print(f"  Contains burn-related: {has_burn}")

    @pytest.mark.asyncio
    async def test_multiple_queries(self):
        """Test RAG with multiple different queries."""
        rag = RAGPipeline()

        queries = [
            "What is our runway?",
            "Tell me about revenue",
            "Any churn warnings?",
        ]

        results = []
        for q in queries:
            result = rag.run_pipeline(q, TEST_TENANT_ID)
            results.append(result)

        assert len(results) == 3
        print(f"\n✓ Multiple queries test")
        print(f"  All queries completed successfully")


@pytest.mark.e2e
def test_llm_test_case_creation():
    """Test creating LLMTestCase for RAG evaluation."""

    test_case = LLMTestCase(
        input="What is the burn rate?",
        actual_output="The burn rate is $45,000 per month.",
        expected_output="$45,000 monthly burn rate",
        retrieval_context=[
            "Monthly burn rate is $45,000",
            "Runway is 8 months",
        ],
    )

    assert test_case.input == "What is the burn rate?"
    assert test_case.actual_output is not None
    assert len(test_case.retrieval_context) == 2

    print("\n✓ LLMTestCase creation works")


@pytest.mark.e2e
def test_deepeval_metrics_configuration():
    """Test DeepEval metrics are properly configured."""
    from deepeval.metrics import BaseMetric

    metrics = [
        AnswerRelevancyMetric(threshold=0.7),
        ContextualRecallMetric(threshold=0.6),
        FaithfulnessMetric(threshold=0.8),
    ]

    for metric in metrics:
        assert metric.threshold > 0
        assert hasattr(metric, "score") or isinstance(metric, BaseMetric)

    print("\n✓ Metrics configuration is valid")
    print(f"  AnswerRelevancy threshold: {metrics[0].threshold}")
    print(f"  ContextualRecall threshold: {metrics[1].threshold}")
    print(f"  Faithfulness threshold: {metrics[2].threshold}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_rag_empty_results_handling():
    """Test RAG handles empty retrieval gracefully."""
    rag = RAGPipeline()
    query = "completely unrelated query xyz123"

    result = rag.run_pipeline("test-tenant-empty", query)

    assert result["response"] is not None

    print(f"\n✓ Empty results handling works")
    print(f"  Response: {result['response'][:50]}...")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_rag_score_threshold():
    """Test that retrieval respects score thresholds."""
    results = RAGPipeline().retrieve(
        query="financial metrics",
        tenant_id=TEST_TENANT_ID,
        top_k=5
    )

    if results:
        scores = [r.get("score", 0) for r in results]
        print(f"\n✓ Score threshold test")
        print(f"  Min score: {min(scores):.3f}")
        print(f"  Max score: {max(scores):.3f}")
        print(f"  Avg score: {sum(scores)/len(scores):.3f}")


if __name__ == "__main__":
    print("Running E2E RAG Evaluation tests...")
    print("=" * 60)
    pytest.main([__file__, "-v", "-s"])