#!/bin/bash
# OntologyAI Portfolio Demo — 3-minute recruiter walkthrough
# Run AFTER demo_start.sh
set -e

TENANT="demo-founder-$(date +%s)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   SARTHI — AI Business Intelligence for Founders   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Tenant: $TENANT"
echo ""

cd /home/aparna/Desktop/iterate_swarm/apps/ai

BASE_ENV="DATABASE_URL=postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm \
QDRANT_URL=http://localhost:6333 \
OLLAMA_BASE_URL=http://localhost:11434/v1 \
OLLAMA_CHAT_MODEL=qwen3:0.6b \
OLLAMA_EMBED_MODEL=nomic-embed-text:latest \
STRIPE_API_KEY='' \
PLAID_ACCESS_TOKEN='' \
SLACK_WEBHOOK_URL='' \
LANGFUSE_ENABLED=false"

# ── DEMO 1: Daily Pulse ───────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DEMO 1 — Daily Business Pulse"
echo "  'What's happening with my business today?'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "▶ Running PulseAgent..."
echo ""

eval "env $BASE_ENV uv run python -c \"
import asyncio
from src.agents.pulse.graph import build_pulse_graph

async def run():
    graph = build_pulse_graph()
    state = await graph.ainvoke({'tenant_id': '$TENANT'})

    print('  MRR:          ₹{:,.0f}'.format(state.get('mrr_cents',0)/100))
    print('  ARR:          ₹{:,.0f}'.format(state.get('arr_cents',0)/100))
    print('  Runway:       {:.1f} months'.format(state.get('runway_months',0)))
    print('  Burn/month:   ₹{:,.0f}'.format(state.get('burn_30d_cents',0)/100))
    print('  Customers:    {} active (+{} new, -{} churned)'.format(
        state.get('active_customers',0),
        state.get('new_customers',0),
        state.get('churned_customers',0)
    ))
    print()
    print('  NARRATIVE:')
    print('  ' + state.get('narrative','').replace('\n', '\n  '))
    print()
    print('  ACTION:  ' + state.get('action_item',''))
    print()
    anomalies = state.get('anomalies_detected', [])
    if anomalies:
        print('  ⚠️  ANOMALIES DETECTED:')
        for a in anomalies:
            print('    -', a)
    else:
        print('  ✅ No anomalies detected')
    print()
    print('  Slack delivery: {}'.format(
        '✓ sent' if state.get('slack_result',{}).get('ok') else '○ mock mode'
    ))
    print('  Snapshot saved:', state.get('snapshot_id','')[:8] + '...')

asyncio.run(run())
\""

echo ""
sleep 2

# ── DEMO 2: Founder Q&A ───────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DEMO 2 — Founder Q&A"
echo "  'What is my current runway?'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "▶ Running QAAgent..."
echo ""

eval "env $BASE_ENV uv run python -c \"
import asyncio
from src.agents.qa.graph import build_qa_graph

async def run():
    graph = build_qa_graph()
    state = await graph.ainvoke({
        'tenant_id': '$TENANT',
        'question':  'What is my current runway and should I be worried?'
    })
    print('  QUESTION: What is my current runway and should I be worried?')
    print()
    print('  ANSWER:')
    print('  ' + state.get('answer','').replace('\n','\n  '))
    print()
    print('  Latency: {}ms'.format(state.get('latency_ms', 0)))

asyncio.run(run())
\""

echo ""
sleep 2

# ── DEMO 3: Memory (run pulse again — shows Qdrant working) ───────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DEMO 3 — Memory Engine"
echo "  'Run pulse twice — second run uses historical context'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "▶ Running PulseAgent again (retrieves memory from run 1)..."
echo ""

eval "env $BASE_ENV uv run python -c \"
import asyncio
from src.agents.pulse.graph import build_pulse_graph

async def run():
    graph = build_pulse_graph()
    state = await graph.ainvoke({'tenant_id': '$TENANT'})
    hist  = state.get('historical_context', '')
    if hist and 'No previous' not in hist:
        print('  ✅ MEMORY WORKING — historical context retrieved:')
        print('  ' + hist[:200])
    else:
        print('  ○ First run — no prior history yet (expected)')
    print()
    print('  MRR growth vs last snapshot: {:+.1f}%'.format(
        state.get('mrr_growth_pct', 0)
    ))

asyncio.run(run())
\""

echo ""

# ── DEMO 4: Test suite ───────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DEMO 4 — Test Coverage (show recruiter)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

eval "env $BASE_ENV TEMPORAL_HOST=localhost:7233 UV_LINK_MODE=hardlink \
  uv run pytest tests/unit/ \
    --timeout=60 --asyncio-mode=auto -q --tb=no 2>&1 | tail -3"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              ✅ DEMO COMPLETE                       ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Stack:  Python · Go · Temporal · Qdrant · Ollama  ║"
echo "║  Agents: Pulse · Anomaly · Investor · QA            ║"
echo "║  LLM:    qwen3:0.6b (100% local, zero API cost)     ║"
echo "║  DB:     PostgreSQL + Qdrant vector memory          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
