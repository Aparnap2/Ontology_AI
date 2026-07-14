#!/usr/bin/env python3
"""
Verification tests for IterateSwarm Phase 1-3 implementation.
Run these to confirm the fixes actually work in production.
"""

import sys
import os

# Add the AI src directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_src_path = os.path.join(current_dir, 'apps', 'ai', 'src')
sys.path.insert(0, ai_src_path)

def test_tenant_isolation():
    """Question 1: Does tenant isolation block cross-tenant leakage?"""
    print("🔍 Testing tenant isolation...")

    try:
        from src.memory.qdrant_ops import upsert_memory, search_memory

        # Write a vector for tenant A
        upsert_memory(
            tenant_id="tenant-A",
            content="MRR dropped 20% — critical anomaly",
            memory_type="anomaly",
            agent="AnomalyAgent"
        )

        # Search as tenant B for the same content
        results = search_memory(
            tenant_id="tenant-B",
            query="MRR dropped anomaly critical"
        )

        # This must return zero results
        assert len(results) == 0, f"ISOLATION BREACH: tenant-B sees tenant-A data: {results}"
        print("✅ Tenant isolation verified — cross-tenant leakage blocked")
        return True

    except Exception as e:
        print(f"❌ Tenant isolation test failed: {e}")
        return False


def test_decay_job():
    """Question 2: Does the decay job change relevance_weight in Qdrant?"""
    print("🔍 Testing memory decay...")

    try:
        from src.memory.qdrant_ops import upsert_memory, decay_memory_weights
        from qdrant_client import QdrantClient

        # Write a fresh vector (weight = 1.0)
        point_id = upsert_memory(
            tenant_id="test-tenant",
            content="test decay vector",
            memory_type="anomaly",
            agent="AnomalyAgent"
        )

        # Run one decay cycle
        decayed_count = decay_memory_weights()

        # Read it back — weight must be 0.85, not 1.0
        qd = QdrantClient(host="localhost", port=6333)
        result = qd.retrieve("ontology_ai_memory", ids=[point_id], with_payload=True)

        if result and result[0].payload:
            weight = result[0].payload.get("relevance_weight", 1.0)
            assert abs(weight - 0.85) < 0.001, f"Decay did not run. Weight is still {weight}"
            print(f"✅ Decay verified — weight: 1.0 → {weight}")
            return True
        else:
            print("❌ Could not retrieve vector after decay")
            return False

    except Exception as e:
        print(f"❌ Decay test failed: {e}")
        return False


def test_react_safety():
    """Question 3: Does ReAct loop detection terminate a loop?"""
    print("🔍 Testing ReAct safety guards...")

    try:
        from src.agents.qa.graph import SafeReActAgent

        # Mock a tool that always returns incomplete data
        call_count = 0

        def always_incomplete_tool(query: str, tenant_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return "I need more information"   # agent will keep calling this

        # Create agent with mocked tool
        agent = SafeReActAgent()

        # Mock the tools dict
        agent._execute_tool = lambda tool_call, tid: {
            "result": always_incomplete_tool("", ""),
            "cost": 0.01
        }

        # Mock the tool parsing to always return the same tool
        agent._parse_tool_call = lambda content: {
            "name": "always_incomplete",
            "args": {}
        } if call_count < 10 else None  # Stop after many calls

        result = agent.invoke("What is our churn rate?", "test-tenant")

        # Must terminate — not loop forever
        assert call_count <= 5, f"Loop not detected — tool called {call_count} times"
        assert "error" in result or "fallback" in result.get("answer", "").lower(), \
            f"Agent should return graceful fallback, got: {result}"
        print(f"✅ Loop detection verified — terminated after {call_count} tool calls")
        return True

    except Exception as e:
        print(f"❌ ReAct safety test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_criteria_comprehensive():
    """Question 4: Do criteria catch both good and bad drafts?"""
    print("🔍 Testing investor criteria comprehensively...")

    try:
        from src.agents.investor.criteria import evaluate_draft_quality

        # A draft that SHOULD pass all criteria
        good_draft = """
$12,100 MRR this month, up 8% from last month.
Runway: 14 months at current burn of $16,400/month.

Top 3 Wins:
- Closed 3 new enterprise accounts
- Shipped batch export feature (top requested)
- Reduced AWS costs by 12%

Blockers:
- Activation rate declining (44%, was 68% in October)
- Top customer represents 31% of MRR — concentration risk

Ask: Intro to 2 product-led growth advisors who've scaled
     past $50k MRR with usage-based pricing.
"""

        passes, failures = evaluate_draft_quality(good_draft)
        assert passes, f"Good draft incorrectly failed: {failures}"
        print("✅ Good draft passes all criteria")

        # A draft that SHOULD fail
        bad_draft = "Things are going well. We are leveraging our synergies."
        passes, failures = evaluate_draft_quality(bad_draft)
        assert not passes, "Bad draft incorrectly passed"
        assert "contains_mrr_number" in failures, f"Should fail contains_mrr_number: {failures}"
        assert "no_jargon" in failures, f"Should fail no_jargon for 'leveraging', 'synergies': {failures}"
        print(f"✅ Bad draft correctly failed: {failures}")

        return True

    except Exception as e:
        print(f"❌ Criteria test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_migration_verification():
    """Question 5: Are the migrated vectors actually updated in Qdrant?"""
    print("🔍 Testing migration verification...")

    try:
        from qdrant_client import QdrantClient

        qd = QdrantClient(host="localhost", port=6333)
        vectors, _ = qd.scroll(
            "ontology_ai_memory",
            with_payload=True,
            limit=100
        )

        missing_fields = []
        total_vectors = len(vectors)

        for v in vectors:
            p = v.payload
            if "occurred_at" not in p:
                missing_fields.append((v.id, "occurred_at"))
            if "relevance_weight" not in p:
                missing_fields.append((v.id, "relevance_weight"))
            if "expires_at" not in p:
                missing_fields.append((v.id, "expires_at"))

        if missing_fields:
            print(f"❌ {len(missing_fields)} vectors missing temporal fields:")
            for vid, field in missing_fields[:5]:
                print(f"   Vector {vid} missing: {field}")
            return False
        else:
            print(f"✅ All {total_vectors} vectors have temporal fields")
            return True

    except Exception as e:
        print(f"❌ Migration verification failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("🚀 Running IterateSwarm Phase 1-3 Verification Tests")
    print("=" * 60)

    tests = [
        ("Tenant Isolation", test_tenant_isolation),
        ("Memory Decay", test_decay_job),
        ("ReAct Safety", test_react_safety),
        ("Criteria Comprehensive", test_criteria_comprehensive),
        ("Migration Verification", test_migration_verification),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}")
        print("-" * 40)
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("📊 VERIFICATION RESULTS")

    passed = sum(results)
    total = len(results)

    for i, (test_name, _) in enumerate(tests):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"   {test_name}: {status}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED - Phase 1-3 implementation is production ready!")
        return 0
    else:
        print("⚠️  Some tests failed - implementation needs fixes")
        return 1


if __name__ == "__main__":
    sys.exit(main())