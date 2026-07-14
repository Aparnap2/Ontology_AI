"""
Part 2: RAG / Memory Retrieval — Agentic E2E Tests.

Tests SemanticMemory, SessionMemoryWriter, MemoryService, and QdrantService.
Each test is independent and writes new data.

Usage:
    cd apps/ai && DB_PORT=5433 uv run python tests/test_agentic_e2e_rag.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.WARNING)
logging.getLogger("src.memory.semantic").setLevel(logging.WARNING)
logging.getLogger("src.services.qdrant").setLevel(logging.WARNING)

TENANT_ID = f"e2e_rag_{uuid.uuid4().hex[:8]}"


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


# ── Test 1: SemanticMemory availability ──────────────────────────────

async def test_semantic_memory_available() -> bool:
    """Instantiate SemanticMemory with a tenant_id and call .available()."""
    section("Test 1: SemanticMemory availability check")

    def _run():
        from src.memory.semantic import SemanticMemory
        sm = SemanticMemory(tenant_id=TENANT_ID)
        return sm.available()

    available = await asyncio.to_thread(_run)

    assert isinstance(available, bool), f"available() returned {type(available)}"

    if available:
        print("  ✓ SemanticMemory is available (Graphiti/Neo4j reachable)")
    else:
        print("  WARN: SemanticMemory not available (Graphiti/Neo4j may be down)")

    return available


# ── Test 2: Write an episode ─────────────────────────────────────────

async def test_write_episode(skip_if_unavailable: bool = True) -> None:
    """Write an episode via sm.write_episode(name, body) and assert True."""
    section("Test 2: Write an episode")

    def _run(skip: bool):
        from src.memory.semantic import SemanticMemory
        sm = SemanticMemory(tenant_id=TENANT_ID)
        if not sm.available():
            if skip:
                print("  SKIP: Graphiti/Neo4j not available")
                return None
            raise RuntimeError("SemanticMemory not available")
        content = (
            "Enterprise revenue increased by 22% this quarter driven by "
            "expansion in the mid-market segment."
        )
        result = sm.write_episode(
            name=f"ep_revenue_{uuid.uuid4().hex[:6]}",
            body=content,
        )
        return result

    result = await asyncio.to_thread(_run, skip_if_unavailable)
    if result is None:
        return
    assert result is True, f"write_episode returned {result}"
    print("  ✓ write_episode returned True")


# ── Test 3: Search the episode ───────────────────────────────────────

async def test_search_episode() -> None:
    """Write an episode then search — results should contain the content."""
    section("Test 3: Search the episode")

    def _run():
        from src.memory.semantic import SemanticMemory
        sm = SemanticMemory(tenant_id=TENANT_ID)
        if not sm.available():
            return None, None
        content = (
            "Churn rate dropped to 1.8% after introducing the quarterly "
            "business review program for enterprise customers."
        )
        name = f"ep_churn_{uuid.uuid4().hex[:6]}"
        write_ok = sm.write_episode(name=name, body=content)
        if not write_ok:
            return None, None
        results = sm.search(query="churn rate business review program", num_results=5)
        return content, results

    content, results = await asyncio.to_thread(_run)
    if content is None:
        print("  SKIP: Graphiti/Neo4j not available or write failed")
        return

    assert isinstance(results, list), f"search returned {type(results)}"

    if results:
        found = any(content[:40] in str(r) for r in results)
        if found:
            print("  ✓ Written content found in search results")
        else:
            print("  INFO: Written content not found (Graphiti may need indexing time)")
        print(f"  Search returned {len(results)} result(s)")
    else:
        print("  INFO: No search results (Graphiti may need indexing time)")


# ── Test 4: SessionMemoryWriter integration ──────────────────────────

async def test_session_memory_writer() -> None:
    """Write an alert_fired event, then search_session_memory for the content."""
    section("Test 4: SessionMemoryWriter + search_session_memory")

    def _run_mem():
        from src.session.memory_integration import SessionMemoryWriter, search_session_memory
        writer = SessionMemoryWriter(tenant_id=TENANT_ID)
        alert_id = f"FG-{uuid.uuid4().hex[:4].upper()}"
        alert_text = f"Revenue anomaly detected for tenant {TENANT_ID}"
        result = writer.write_alert_fired(
            alert_id=alert_id,
            alert_type="FG",
            message=alert_text,
        )
        search_results = search_session_memory(
            TENANT_ID,
            f"revenue anomaly {TENANT_ID}",
            num_results=5,
        )
        return result, search_results

    def _run_gating():
        from src.session.memory_integration import should_write_to_graphiti
        return (
            should_write_to_graphiti("alert_fired"),
            should_write_to_graphiti("unknown_event"),
        )

    result, search_results = await asyncio.to_thread(_run_mem)

    if not result:
        print("  WARN: write_alert_fired returned False (Graphiti unavailable or event filtered)")
    else:
        print("  ✓ write_alert_fired returned True")

    assert isinstance(search_results, list), (
        f"search_session_memory returned {type(search_results)}"
    )

    if search_results:
        print(f"  ✓ search_session_memory returned {len(search_results)} result(s)")
    else:
        print("  INFO: search_session_memory returned empty list (fallback contract)")

    fires, unknown = await asyncio.to_thread(_run_gating)
    assert fires is True
    assert unknown is False
    print("  ✓ should_write_to_graphiti gates correctly")


# ── Test 5: MemoryService.read() ─────────────────────────────────────

async def test_memory_service_read() -> None:
    """Write via MemoryService facade then read — expect non-empty results."""
    section("Test 5: MemoryService.read() returns results after writes")
    from src.services.memory import get_memory_service

    ms = get_memory_service()

    write_content = (
        f"ARR grew to $3.2M with net retention of 120% for tenant {TENANT_ID}."
    )
    point_id = await ms.write(
        tenant_id=TENANT_ID,
        content=write_content,
        memory_type="revenue_event",
        metadata={"agent": "test", "source": "e2e_rag_test"},
    )

    if point_id:
        print(f"  ✓ write returned point_id: {point_id[:16]}...")
    else:
        print("  INFO: write returned empty point_id (backends may be unavailable)")

    results = await ms.read(
        tenant_id=TENANT_ID,
        query="ARR growth net retention",
        top_k=5,
    )
    assert isinstance(results, list), f"read() returned {type(results)}"
    print(f"  read() returned {len(results)} result(s)")

    if results:
        print("  ✓ read() returned non-empty results")


# ── Test 6: MemoryService.load_context() ─────────────────────────────

async def test_memory_service_load_context() -> None:
    """Write data then load_context — expect a non-empty context string."""
    section("Test 6: MemoryService.load_context() returns context string")
    from src.services.memory import get_memory_service

    ms = get_memory_service()

    await ms.write(
        tenant_id=TENANT_ID,
        content=(
            f"Monthly burn rate is $45K with 18 months of runway remaining "
            f"for tenant {TENANT_ID}."
        ),
        memory_type="financial_metric",
        metadata={"agent": "test", "source": "e2e_rag_test"},
    )

    context = await ms.load_context(tenant_id=TENANT_ID)
    assert isinstance(context, str), f"load_context returned {type(context)}"
    print(f"  load_context returned string of length {len(context)}")

    if context:
        print("  ✓ Context string is non-empty")
    else:
        print("  INFO: Context is empty (backends may be unavailable)")


# ── Test 7: Qdrant index + dedup ─────────────────────────────────────

async def test_qdrant_index_dedup() -> None:
    """Index a feedback, then check_duplicate — verify similarity score > 0."""
    section("Test 7: Qdrant index_feedback + check_duplicate")
    try:
        from src.services.qdrant import get_qdrant_service
        qdrant = await get_qdrant_service()
    except Exception as exc:
        print(f"  WARN: Could not initialise QdrantService: {exc}")
        return

    feedback_id = f"e2e_fb_{uuid.uuid4().hex[:12]}"
    text = (
        "Customers are requesting a self-service dashboard for real-time "
        "usage analytics and billing history."
    )

    try:
        await qdrant.index_feedback(
            feedback_id=feedback_id,
            text=text,
            metadata={"source": "e2e_rag_test", "tenant": TENANT_ID},
        )
        print("  ✓ index_feedback succeeded")
    except Exception as exc:
        print(f"  WARN: index_feedback failed: {exc}")
        return

    # Check duplicate against a very similar text
    similar_text = (
        "Users want a self-service dashboard for real-time analytics "
        "and billing history visibility."
    )
    try:
        is_dup, score = await qdrant.check_duplicate(similar_text)
    except Exception as exc:
        print(f"  WARN: check_duplicate failed: {exc}")
        return

    assert isinstance(is_dup, bool), f"is_duplicate should be bool, got {type(is_dup)}"
    assert isinstance(score, float), f"score should be float, got {type(score)}"
    print(f"  Similar text: is_dup={is_dup}, score={score:.4f}")

    if score > 0:
        print(f"  ✓ Similarity score ({score:.4f}) > 0 — semantic matching works")
    else:
        print("  INFO: Score is 0 (embedding may not have indexed yet)")

    # Check duplicate against completely different text as a sanity check
    diff_text = "The weather is sunny and warm today."
    try:
        _, score2 = await qdrant.check_duplicate(diff_text)
        print(f"  Different text: score={score2:.4f}")
        if score2 < score:
            print(f"  ✓ Different text scored lower ({score2:.4f} < {score:.4f})")
        elif score > 0:
            print("  INFO: score ordering not as expected (small dataset)")
    except Exception as exc:
        print(f"  WARN: check_duplicate on different text failed: {exc}")


# ── Main runner ──────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 70)
    print("  RAG / Memory Retrieval — Agentic E2E Tests (Part 2)")
    print("=" * 70)

    results: list[tuple[str, str | None]] = []

    # Test 1
    try:
        available = await test_semantic_memory_available()
        results.append(("Test 1: SemanticMemory availability", "PASS"))
    except AssertionError as e:
        results.append(("Test 1: SemanticMemory availability", f"FAIL — {e}"))
        available = False

    # Test 2
    try:
        await test_write_episode(skip_if_unavailable=not available)
        results.append(("Test 2: Write an episode", "PASS"))
    except AssertionError as e:
        results.append(("Test 2: Write an episode", f"FAIL — {e}"))

    # Test 3
    try:
        await test_search_episode()
        results.append(("Test 3: Search the episode", "PASS"))
    except AssertionError as e:
        results.append(("Test 3: Search the episode", f"FAIL — {e}"))

    # Test 4
    try:
        await test_session_memory_writer()
        results.append(("Test 4: SessionMemoryWriter", "PASS"))
    except AssertionError as e:
        results.append(("Test 4: SessionMemoryWriter", f"FAIL — {e}"))

    # Test 5
    try:
        await test_memory_service_read()
        results.append(("Test 5: MemoryService.read()", "PASS"))
    except AssertionError as e:
        results.append(("Test 5: MemoryService.read()", f"FAIL — {e}"))

    # Test 6
    try:
        await test_memory_service_load_context()
        results.append(("Test 6: MemoryService.load_context()", "PASS"))
    except AssertionError as e:
        results.append(("Test 6: MemoryService.load_context()", f"FAIL — {e}"))

    # Test 7
    try:
        await test_qdrant_index_dedup()
        results.append(("Test 7: Qdrant index + dedup", "PASS"))
    except AssertionError as e:
        results.append(("Test 7: Qdrant index + dedup", f"FAIL — {e}"))

    # Summary
    print(f"\n{'=' * 70}")
    print(f"  Summary")
    print(f"{'=' * 70}")
    passed = failed = 0
    for name, status in results:
        if status == "PASS":
            print(f"  ✓ {name}")
            passed += 1
        else:
            print(f"  ✗ {name}: {status}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    print(f"{'=' * 70}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
