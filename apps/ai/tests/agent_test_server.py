"""
Agent Test Server — FastAPI app for testing agentic AI capabilities.

Uses groq LLM via src/config/llm.py, not blocking the Temporal worker.
Provides endpoints for testing each agent's Phase 2/3 individually.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException

from src.config.llm import chat_completion, get_chat_model, get_llm_client

log = structlog.get_logger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="TrackGuard Agent Test Server",
    description="Test endpoints for agentic AI capabilities",
    version="1.0.0",
)


# ── Health check ──────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Return status of all containers and LLM connectivity."""
    statuses: dict[str, Any] = {"status": "ok", "services": {}}

    # PostgreSQL
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                os.environ.get("DATABASE_URL", "http://localhost:5432").replace(
                    "postgresql://", "http://"
                )
            )
            statuses["services"]["postgresql"] = "ok" if r.status_code < 500 else "error"
    except Exception:
        statuses["services"]["postgresql"] = "unreachable"

    # Redis
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(os.environ.get("REDIS_URL", "http://localhost:6379"))
            statuses["services"]["redis"] = "ok" if r.status_code < 500 else "error"
    except Exception:
        statuses["services"]["redis"] = "unreachable"

    # Qdrant
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{os.environ.get('QDRANT_URL', 'http://localhost:6333')}/healthz"
            )
            statuses["services"]["qdrant"] = "ok" if r.status_code < 500 else "error"
    except Exception:
        statuses["services"]["qdrant"] = "unreachable"

    # Neo4j
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            neo4j_url = os.environ.get("NEO4J_URI", "bolt://localhost:7687").replace(
                "bolt://", "http://"
            )
            r = await client.get(f"{neo4j_url}/")
            statuses["services"]["neo4j"] = "ok" if r.status_code < 500 else "error"
    except Exception:
        statuses["services"]["neo4j"] = "unreachable"

    # LLM connectivity
    try:
        test_response = chat_completion(
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=10,
            temperature=0.0,
        )
        statuses["services"]["llm"] = "ok" if test_response else "error"
    except Exception as e:
        statuses["services"]["llm"] = f"error: {e}"

    statuses["model"] = get_chat_model()
    return statuses


# ── Agent endpoints: Finance Guardian ─────────────────────────────

async def _run_finance_phase1_2(tenant_id: str) -> dict:
    """Run Finance Guardian Phase 1 + 2, return AlertDecision."""
    from src.agents.finance.graph import FinanceGuardianGraph

    graph = FinanceGuardianGraph()
    await graph._assemble_data(tenant_id, mission_context={})
    if graph.state.triggered_patterns:
        await graph._decide_alert(mission_context={})
    return {
        "tenant_id": tenant_id,
        "triggered_patterns": graph.state.triggered_patterns,
        "alert_decision": graph.state.alert_decision.model_dump() if graph.state.alert_decision else None,
        "financial_snapshot": graph.state.financial_snapshot,
    }


@app.post("/api/agents/finance/decide")
async def finance_decide(payload: dict | None = None):
    """Run Phase 1 + 2 of Finance Guardian, returns AlertDecision."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        result = await _run_finance_phase1_2(tenant_id)
        log.info("finance.decide", tenant_id=tenant_id, result=result.get("alert_decision"))
        return result
    except Exception as e:
        log.error("finance.decide.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/finance/narrate")
async def finance_narrate(payload: dict | None = None):
    """Run Finance Guardian Phase 3, returns narrative."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.agents.finance.graph import FinanceGuardianGraph

        graph = FinanceGuardianGraph()
        await graph._assemble_data(tenant_id, mission_context={})
        if graph.state.triggered_patterns:
            await graph._decide_alert(mission_context={})
        if graph.state.alert_decision and graph.state.alert_decision.should_alert:
            await graph._generate_narrative()

        log.info("finance.narrate", tenant_id=tenant_id, narrative_len=len(graph.state.narrative))
        return {
            "tenant_id": tenant_id,
            "narrative": graph.state.narrative,
            "alert_decision": graph.state.alert_decision.model_dump() if graph.state.alert_decision else None,
        }
    except Exception as e:
        log.error("finance.narrate.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Agent endpoints: BI Analyst ───────────────────────────────────

@app.post("/api/agents/bi/decide")
async def bi_decide(payload: dict | None = None):
    """Run BI Analyst Phase 1 + 2, returns AlertDecision."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.agents.bi.graph import BIAnalystGraph

        graph = BIAnalystGraph()
        await graph._assemble_data(tenant_id, mission_context={})
        if graph.state.triggered_patterns:
            await graph._decide_alert(mission_context={})
        log.info("bi.decide", tenant_id=tenant_id, result=graph.state.alert_decision)
        return {
            "tenant_id": tenant_id,
            "triggered_patterns": graph.state.triggered_patterns,
            "alert_decision": graph.state.alert_decision.model_dump() if graph.state.alert_decision else None,
            "metrics_snapshot": graph.state.metrics_snapshot,
        }
    except Exception as e:
        log.error("bi.decide.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/bi/narrate")
async def bi_narrate(payload: dict | None = None):
    """Run BI Analyst Phase 3, returns narrative."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.agents.bi.graph import BIAnalystGraph

        graph = BIAnalystGraph()
        await graph._assemble_data(tenant_id, mission_context={})
        if graph.state.triggered_patterns:
            await graph._decide_alert(mission_context={})
        if graph.state.alert_decision and graph.state.alert_decision.should_alert:
            await graph._generate_narrative()
        log.info("bi.narrate", tenant_id=tenant_id, narrative_len=len(graph.state.narrative))
        return {
            "tenant_id": tenant_id,
            "narrative": graph.state.narrative,
            "alert_decision": graph.state.alert_decision.model_dump() if graph.state.alert_decision else None,
        }
    except Exception as e:
        log.error("bi.narrate.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Agent endpoints: Ops Watch ────────────────────────────────────

@app.post("/api/agents/ops/decide")
async def ops_decide(payload: dict | None = None):
    """Run Ops Watch Phase 1 + 2, returns AlertDecision."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.agents.ops.graph import OpsWatchGraph

        graph = OpsWatchGraph()
        await graph._assemble_data(tenant_id, mission_context={})
        if graph.state.triggered_patterns:
            await graph._decide_alert(mission_context={})
        log.info("ops.decide", tenant_id=tenant_id, result=graph.state.alert_decision)
        return {
            "tenant_id": tenant_id,
            "triggered_patterns": graph.state.triggered_patterns,
            "alert_decision": graph.state.alert_decision.model_dump() if graph.state.alert_decision else None,
            "ops_snapshot": graph.state.ops_snapshot,
        }
    except Exception as e:
        log.error("ops.decide.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/ops/narrate")
async def ops_narrate(payload: dict | None = None):
    """Run Ops Watch Phase 3, returns narrative."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.agents.ops.graph import OpsWatchGraph

        graph = OpsWatchGraph()
        await graph._assemble_data(tenant_id, mission_context={})
        if graph.state.triggered_patterns:
            await graph._decide_alert(mission_context={})
        if graph.state.alert_decision and graph.state.alert_decision.should_alert:
            await graph._generate_narrative()
        log.info("ops.narrate", tenant_id=tenant_id, narrative_len=len(graph.state.narrative))
        return {
            "tenant_id": tenant_id,
            "narrative": graph.state.narrative,
            "alert_decision": graph.state.alert_decision.model_dump() if graph.state.alert_decision else None,
        }
    except Exception as e:
        log.error("ops.narrate.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Business pipeline ─────────────────────────────────────────────

@app.post("/api/business/pipeline")
async def business_pipeline(payload: dict | None = None):
    """Run the full business pipeline (finance -> guardrails -> predictive)."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        results: dict[str, Any] = {"tenant_id": tenant_id}

        # Phase 1: Finance Guardian
        from src.agents.finance.graph import FinanceGuardianGraph

        fg = FinanceGuardianGraph()
        await fg.run(tenant_id, {})
        results["finance_guardian"] = {
            "triggered_patterns": fg.state.triggered_patterns,
            "alert_decision": fg.state.alert_decision.model_dump() if fg.state.alert_decision else None,
            "narrative": fg.state.narrative,
        }

        # Phase 2: Guardrails
        from src.guardian.detector import GuardianDetector

        detector = GuardianDetector()
        signals = fg.state.financial_snapshot or {}
        guardrail_matches = detector.run(signals)
        results["guardrails"] = [
            {"id": m.id, "name": m.name, "severity": m.severity}
            for m in guardrail_matches
        ]

        # Phase 3: Predictive
        from src.agents.anomaly.graph import AnomalyDetector

        ch = AnomalyDetector()
        results["predictive"] = {"status": "simulated", "detector": "AnomalyDetector"}

        log.info("business.pipeline", tenant_id=tenant_id, patterns=fg.state.triggered_patterns)
        return results
    except Exception as e:
        log.error("business.pipeline.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Memory & RAG endpoints ────────────────────────────────────────

@app.post("/api/memory/rag-context")
async def rag_context(payload: dict | None = None):
    """Test RAG context loading from spine."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        task = (payload or {}).get("task", "finance_guardian")

        from src.memory.spine import load_context

        ctx = await load_context(tenant_id=tenant_id, query=task, domain="finance")
        return {
            "tenant_id": tenant_id,
            "layers_hit": ctx.total_layers_hit,
            "errors": ctx.errors,
            "working": bool(ctx.working),
            "episodic_count": len(ctx.episodic),
            "semantic_count": len(ctx.semantic),
            "compressed_count": len(ctx.compressed),
            "procedural_count": len(ctx.procedural),
        }
    except Exception as e:
        log.error("memory.rag_context.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/memory/search")
async def memory_search(payload: dict):
    """Test Qdrant semantic search."""
    try:
        tenant_id = payload.get("tenant_id", "test-tenant-001")
        query = payload.get("query", "financial metrics")
        collection = payload.get("collection", "pulse_memory")
        limit = payload.get("limit", 5)

        from src.memory.qdrant_ops import search_memory

        results = search_memory(
            tenant_id=tenant_id,
            query=query,
            memory_type=collection,
            limit=limit,
        )

        return {
            "tenant_id": tenant_id,
            "query": query,
            "collection": collection,
            "result_count": len(results),
            "results": results[:limit],
        }
    except Exception as e:
        log.error("memory.search.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Trust & Guardrails ────────────────────────────────────────────

@app.post("/api/trust/evaluate")
async def trust_evaluate(payload: dict | None = None):
    """Test trust battery evaluation."""
    try:
        agent_name = (payload or {}).get("agent_name", "finance_guardian")
        from src.agents.cofounder.trust_battery import TrustBattery

        battery = TrustBattery()
        profile = battery.load_profile(agent_name)
        return {
            "agent": agent_name,
            "profile": profile,
            "evaluated": True,
        }
    except Exception as e:
        log.error("trust.evaluate.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/guardrails/evaluate")
async def guardrails_evaluate(payload: dict | None = None):
    """Test guardrails engine."""
    try:
        signals = (payload or {}).get("signals", {})
        from src.guardian.detector import GuardianDetector

        detector = GuardianDetector()
        matches = detector.run(signals)
        return {
            "signals_checked": list(signals.keys()),
            "matches": [
                {"id": m.id, "name": m.name, "domain": m.domain, "severity": m.severity}
                for m in matches
            ],
            "match_count": len(matches),
        }
    except Exception as e:
        log.error("guardrails.evaluate.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Predictive ────────────────────────────────────────────────────

@app.post("/api/predictive/forecast")
async def predictive_forecast(payload: dict | None = None):
    """Test predictive guardian."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.agents.anomaly.graph import AnomalyDetector

        detector = AnomalyDetector()
        return {
            "tenant_id": tenant_id,
            "detector": "AnomalyDetector",
            "forecast": {"status": "simulated", "confidence": 0.85},
        }
    except Exception as e:
        log.error("predictive.forecast.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Tool calling ──────────────────────────────────────────────────

@app.post("/api/tool-call")
async def tool_call(payload: dict):
    """Test LLM tool calling via the factory."""
    try:
        prompt = payload.get("prompt", "Say hello in JSON format.")
        model = payload.get("model") or get_chat_model()

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that outputs valid JSON.",
            },
            {"role": "user", "content": prompt},
        ]

        response = chat_completion(
            messages=messages,
            model=model,
            max_tokens=400,
            temperature=0.0,
            json_mode=True,
        )

        parsed = json.loads(response)
        return {"response": parsed}
    except Exception as e:
        log.error("tool_call.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Format validation ─────────────────────────────────────────────

@app.post("/api/format-validate")
async def format_validate(payload: dict):
    """Test Pydantic schema validation."""
    try:
        from src.schemas.guardian import AlertDecision

        decision = AlertDecision(**payload)
        return {
            "valid": True,
            "data": decision.model_dump(),
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }


# ── Memory status ─────────────────────────────────────────────────

@app.get("/api/memory/status/{tenant_id}")
async def memory_status(tenant_id: str):
    """Test memory layer status."""
    try:
        from src.memory.spine import load_context

        ctx = await load_context(tenant_id=tenant_id, query="status", domain="general")
        return {
            "tenant_id": tenant_id,
            "layers_hit": ctx.total_layers_hit,
            "working": bool(ctx.working),
            "episodic_count": len(ctx.episodic),
            "semantic_count": len(ctx.semantic),
            "procedural_count": len(ctx.procedural),
            "compressed_count": len(ctx.compressed),
            "errors": ctx.errors,
        }
    except Exception as e:
        log.error("memory.status.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Compaction ────────────────────────────────────────────────────

@app.post("/api/compaction/trigger")
async def compaction_trigger(payload: dict | None = None):
    """Test L5 compaction."""
    try:
        tenant_id = (payload or {}).get("tenant_id", "test-tenant-001")
        from src.memory.compressed import CompressedMemory

        cm = CompressedMemory()
        cm.track_write(tenant_id)
        return {
            "tenant_id": tenant_id,
            "compacted": cm.write_count == 0,
            "write_count": cm.write_count,
        }
    except Exception as e:
        log.error("compaction.trigger.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── State persistence ─────────────────────────────────────────────

@app.post("/api/state/snapshot")
async def state_snapshot(payload: dict):
    """Test state persistence (simulated)."""
    try:
        tenant_id = payload.get("tenant_id", "test-tenant-001")
        data = payload.get("data", {})
        # Store in a simple dict to simulate MissionState
        app.state._state_store = getattr(app.state, "_state_store", {})
        app.state._state_store[tenant_id] = {
            **(app.state._state_store.get(tenant_id, {})),
            **data,
        }
        return {"tenant_id": tenant_id, "persisted": True}
    except Exception as e:
        log.error("state.snapshot.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/state/{tenant_id}")
async def state_read(tenant_id: str):
    """Test state retrieval (simulated)."""
    try:
        store = getattr(app.state, "_state_store", {})
        data = store.get(tenant_id, {})
        return {"tenant_id": tenant_id, "data": data}
    except Exception as e:
        log.error("state.read.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Checkpoints ───────────────────────────────────────────────────

@app.get("/api/checkpoints/{workflow_id}")
async def checkpoints_read(workflow_id: str):
    """Test Temporal checkpoint retrieval (stub)."""
    try:
        # Stub: return a placeholder checkpoint
        return {
            "workflow_id": workflow_id,
            "checkpoint": {
                "status": "simulated",
                "activities_completed": [],
                "pending_activities": [],
                "timestamp": "2026-01-01T00:00:00Z",
            },
        }
    except Exception as e:
        log.error("checkpoints.read.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Main entrypoint ───────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tests.agent_test_server:app", host="0.0.0.0", port=8001, reload=True)
