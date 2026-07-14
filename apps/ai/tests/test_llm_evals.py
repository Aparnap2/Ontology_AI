"""
LLM Evaluation Suite for OntologyAI Agents.

Tests agent reasoning quality, tone, jargon detection, and memory citation.
Uses Ollama (qwen3:0.6b) for all LLM calls.

Requirements:
    - Ollama running on localhost:11434
    - qwen3:0.6b model available
    - nomic-embed-text:latest model available
    - Qdrant running on localhost:6333
"""
import pytest
import os
import httpx

# CRITICAL: Clear Azure env vars to force Ollama usage
# Azure credentials in .env take priority, so we must remove them
for key in list(os.environ.keys()):
    if key.startswith("AZURE_"):
        del os.environ[key]

# Set Ollama config for all tests - MUST be set before importing agents
# Using LFM2:2.6b for cleaner output (qwen3 outputs chain-of-thought)
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434/v1"
os.environ["OLLAMA_CHAT_MODEL"] = "sam860/LFM2:2.6b"
os.environ["OLLAMA_EMBED_MODEL"] = "nomic-embed-text:latest"
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "6333"


def _llm_reachable() -> bool:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").replace("/v1", "")
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


LLM_REACHABLE = _llm_reachable()

# Reset LLM client to pick up new config
from src.config.llm import reset_client
reset_client()

TENANT = "test-tenant-llm-eval"


class TestLLMConnectivity:
    """Verify Ollama is reachable and models are available."""

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_ollama_reachable(self):
        """Ollama API should respond on port 11434."""
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        assert resp.status_code == 200
        assert "models" in resp.json()

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_chat_model_available(self):
        """sam860/LFM2:2.6b model should be available."""
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json()["models"]]
        assert any("LFM2" in m or "lfm" in m.lower() for m in models)

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_nomic_embed_available(self):
        """nomic-embed-text model should be available."""
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in resp.json()["models"]]
        assert any("nomic" in m for m in models)

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_chat_completions_smoke(self):
        """Chat completions should work via OpenAI-compatible API."""
        from openai import OpenAI
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )
        resp = client.chat.completions.create(
            model="sam860/LFM2:2.6b",
            messages=[{"role": "user", "content": "Say: ok"}],
            max_tokens=20
        )
        assert resp.choices[0].message.content
        assert len(resp.choices[0].message.content.strip()) > 0

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_embeddings_smoke(self):
        """Embeddings should work via OpenAI-compatible API."""
        from openai import OpenAI
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )
        resp = client.embeddings.create(
            model="nomic-embed-text:latest",
            input="ontology_ai memory test"
        )
        assert len(resp.data[0].embedding) > 0
        # nomic-embed-text produces 768-dim vectors
        assert len(resp.data[0].embedding) == 768


class TestRevenueTrackerLLM:
    """Evaluate Revenue Tracker agent reasoning with real LLM."""

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def setup_method(self):
        from src.agents.revenue_tracker import RevenueTrackerAgent
        self.agent = RevenueTrackerAgent()

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_mrr_milestone_detection(self):
        """Revenue Tracker should detect MRR milestone crossing."""
        state = {"tenant_id": TENANT, "last_30d_mrr": 98000}
        event = {
            "event_type": "PAYMENT_SUCCESS",
            "amount": 3500, "customer_name": "Acme"
        }
        result = self.agent.run(state, event)
        
        assert result["fire_telegram"] is True
        assert result["is_good_news"] is True
        assert "1L" in result["headline"] or "1,00,000" in result["headline"] or "100" in result["headline"]

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_stale_deal_detection(self):
        """Revenue Tracker should detect stale deals (>7 days)."""
        state = {
            "tenant_id": TENANT,
            "pipeline_deals": [{
                "name": "Acme Corp", "amount": 50000,
                "stage": "NEGOTIATION",
                "last_contact_at": "2026-03-01T00:00:00Z"  # 17 days ago
            }],
        }
        event = {"event_type": "TIME_TICK_WEEKLY"}
        result = self.agent.run(state, event)
        
        assert result["fire_telegram"] is True
        assert "Acme" in result["headline"]
        assert "idle" in result["headline"].lower() or "days" in result["headline"].lower()

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_concentration_risk_detection(self):
        """Revenue Tracker should flag >30% concentration."""
        state = {"tenant_id": TENANT, "top_customer_pct": 0.38}
        event = {
            "event_type": "PAYMENT_SUCCESS",
            "amount": 5000, "customer_name": "Acme"
        }
        result = self.agent.run(state, event)
        
        assert result["fire_telegram"] is True
        assert "38%" in result["headline"] or "35%" in result["headline"] or "concentration" in result["headline"].lower()


class TestCSAgentLLM:
    """Evaluate CS Agent reasoning with real LLM."""

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def setup_method(self):
        from src.agents.cs_agent import CSAgent
        self.agent = CSAgent()

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_churn_risk_detection(self):
        """CS Agent should detect high churn risk (>7 days no login)."""
        state = {
            "tenant_id": TENANT,
            "days_since_last_login": 10,  # 10/14 = 0.71 > 0.7 threshold
            "onboarding_stage": "WELCOME",
            "customer_name": "Arjun",
        }
        event = {"event_type": "TIME_TICK_D7"}
        result = self.agent.run(state, event)
        
        assert result["fire_telegram"] is True
        assert result["urgency"] == "high"
        assert "10 days" in result["headline"] or "days" in result["headline"]

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_ticket_escalation(self):
        """CS Agent should escalate ≥3 tickets in 48h."""
        state = {
            "tenant_id": TENANT,
            "tickets_last_48h": 3,
            "customer_name": "Arjun",
        }
        event = {"event_type": "SUPPORT_TICKET_CREATED"}
        result = self.agent.run(state, event)
        
        assert result["fire_telegram"] is True
        assert "3 tickets" in result["headline"] or "tickets" in result["headline"]


class TestPeopleCoordinatorLLM:
    """Evaluate People Coordinator agent reasoning with real LLM."""

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def setup_method(self):
        from src.agents.people_coordinator import PeopleCoordinatorAgent
        self.agent = PeopleCoordinatorAgent()

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_eng_checklist_has_github(self):
        """Eng checklist should include GitHub."""
        state = {"tenant_id": TENANT}
        event = {
            "event_type": "EMPLOYEE_CREATED",
            "name": "Priya", "role_function": "eng"
        }
        result = self.agent.run(state, event)
        
        checklist = result["output_json"].get("checklist", {})
        if isinstance(checklist, dict):
            assert "github" in checklist
        else:
            # If checklist is a list
            assert "github" in checklist

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_sales_checklist_no_github(self):
        """Sales checklist should NOT include GitHub."""
        state = {"tenant_id": TENANT}
        event = {
            "event_type": "EMPLOYEE_CREATED",
            "name": "Rahul", "role_function": "sales"
        }
        result = self.agent.run(state, event)
        
        checklist = result["output_json"].get("checklist", {})
        if isinstance(checklist, dict):
            assert "github" not in checklist
        else:
            # If checklist is a list
            assert "github" not in checklist

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_offboarding_revoke_list(self):
        """Offboarding should generate revoke list."""
        state = {"tenant_id": TENANT}
        event = {
            "event_type": "EMPLOYEE_TERMINATED",
            "name": "Rahul", "role_function": "eng"
        }
        result = self.agent.run(state, event)
        
        assert result["fire_telegram"] is True
        revoke_list = result["output_json"].get("revoke_list", [])
        if isinstance(revoke_list, list):
            assert "github" in revoke_list
        else:
            # If revoke_list is a string
            assert "github" in revoke_list.lower()


class TestChiefOfStaffLLM:
    """Evaluate Chief of Staff agent reasoning with real LLM."""

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def setup_method(self):
        from src.agents.chief_of_staff import ChiefOfStaffAgent
        self.agent = ChiefOfStaffAgent()

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_briefing_max_5_items(self):
        """Briefing should have max 5 items."""
        state = {
            "tenant_id": TENANT,
            "agent_outputs": [
                {"headline": f"Issue {i}", "urgency": "low", "is_good_news": False}
                for i in range(10)
            ],
        }
        event = {"event_type": "TIME_TICK_WEEKLY"}
        result = self.agent.run(state, event)
        
        assert result["output_json"]["item_count"] <= 5

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_briefing_no_jargon(self):
        """Briefing headlines must be jargon-free."""
        from src.agents.base import BANNED_JARGON
        
        state = {
            "tenant_id": TENANT,
            "agent_outputs": [
                {"headline": "AWS spike detected", "urgency": "high", "is_good_news": False}
            ],
        }
        event = {"event_type": "TIME_TICK_WEEKLY"}
        result = self.agent.run(state, event)
        
        for term in BANNED_JARGON:
            assert term.lower() not in result.get("headline", "").lower(), \
                f"Banned jargon '{term}' found in: {result['headline']}"

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_investor_draft_has_metrics(self):
        """Investor draft should contain revenue, burn, runway."""
        state = {
            "tenant_id": TENANT,
            "monthly_revenue": 500000,
            "burn_rate": 180000,
            "runway_months": 14.2,
            "last_30d_mrr": 480000,
        }
        event = {"event_type": "TIME_TICK_MONTHLY"}
        result = self.agent.run(state, event)
        
        draft = result["output_json"].get("draft", "")
        assert "Revenue" in draft
        assert "Burn" in draft
        assert "Runway" in draft


class TestMemoryRetrievalLLM:
    """Evaluate Qdrant memory retrieval quality with Ollama embeddings."""

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_memory_write_and_retrieve(self):
        """Memory should be writable and retrievable via semantic search."""
        from src.memory.qdrant_ops import upsert_memory, query_memory, clear_tenant_memory
        
        # Clear any existing memory
        clear_tenant_memory(TENANT)
        
        # Write memory
        point_id = upsert_memory(
            tenant_id=TENANT,
            content="AWS spend spike on March 15 — training run for new ML model. Not recurring.",
            memory_type="anomaly",
            agent="anomaly_agent",
        )
        assert point_id is not None

        # Retrieve with semantic query
        results = query_memory(
            tenant_id=TENANT,
            query_text="AWS bill anomaly vendor spike",
            memory_types=["anomaly"],
            top_k=3,
            min_score=0.5,
        )
        
        assert len(results) >= 1
        assert "AWS" in results[0]["content"]
        assert results[0]["score"] >= 0.5

    @pytest.mark.skipif(not LLM_REACHABLE, reason="No LLM reachable")
    def test_memory_distinct_by_tenant(self):
        """Memory should be isolated by tenant_id."""
        from src.memory.qdrant_ops import upsert_memory, query_memory, clear_tenant_memory
        
        tenant_a = f"{TENANT}-A"
        tenant_b = f"{TENANT}-B"
        
        # Clear any existing memory
        clear_tenant_memory(tenant_a)
        clear_tenant_memory(tenant_b)
        
        # Write to two different tenants
        upsert_memory(
            tenant_id=tenant_a,
            content="Tenant A: AWS spike March 2026",
            memory_type="anomaly",
            agent="anomaly_agent",
        )
        upsert_memory(
            tenant_id=tenant_b,
            content="Tenant B: Azure spike February 2026",
            memory_type="anomaly",
            agent="anomaly_agent",
        )

        # Query each tenant
        results_a = query_memory(
            tenant_id=tenant_a,
            query_text="AWS spike",
            memory_types=["anomaly"],
            top_k=3,
        )
        results_b = query_memory(
            tenant_id=tenant_b,
            query_text="Azure spike",
            memory_types=["anomaly"],
            top_k=3,
        )
        
        assert len(results_a) >= 1
        assert len(results_b) >= 1
        assert "AWS" in results_a[0]["content"]
        assert "Azure" in results_b[0]["content"]
