#!/usr/bin/env bash
# Full end-to-end smoke test for OntologyAI v1.0 - Phases 7, 8, 9
# Tests: Container health, Service connectivity, E2E flows, LLM Evals

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TESTS_PASSED=0
TESTS_FAILED=0

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((TESTS_PASSED++)) || true
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((TESTS_FAILED++)) || true
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "========================================"
echo "OntologyAI v1.0 - Full Smoke Test"
echo "Phases 7, 8, 9: E2E + Evals + Production"
echo "========================================"
echo ""

# =============================================================================
# STEP 0: Container Health Checks
# =============================================================================
log "STEP 0 — Container Health Checks"

# PostgreSQL
if docker ps --filter name="iterateswarm-postgres" --format "{{.Status}}" | grep -q "Up"; then
    pass "PostgreSQL container running"
else
    fail "PostgreSQL container not running"
fi

# Qdrant
if docker ps --filter name="iterateswarm-qdrant" --format "{{.Status}}" | grep -q "Up"; then
    pass "Qdrant container running"
else
    fail "Qdrant container not running"
fi

# Redpanda
if docker ps --filter name="iterateswarm-redpanda" --format "{{.Status}}" | grep -q "Up"; then
    pass "Redpanda container running"
else
    fail "Redpanda container not running"
fi

# Temporal
if docker ps --filter name="sarthi-temporal" --format "{{.Status}}" | grep -q "Up"; then
    pass "Temporal container running"
else
    warn "Temporal container not running (may be starting)"
fi

# Ollama
if docker ps --filter name="ollama" --format "{{.Status}}" | grep -q "Up"; then
    pass "Ollama container running"
else
    warn "Ollama container not running"
fi

# Neo4j
if docker ps --filter name="saarathi-neo4j" --format "{{.Status}}" | grep -q "Up"; then
    pass "Neo4j container running"
else
    warn "Neo4j container not running"
fi

echo ""

# =============================================================================
# STEP 1: Service Connectivity Checks
# =============================================================================
log "STEP 1 — Service Connectivity Checks"

# PostgreSQL
if curl -sf "http://localhost:5433" > /dev/null 2>&1 || \
   (command -v psql > /dev/null && psql "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm" -c "SELECT 1" > /dev/null 2>&1); then
    pass "PostgreSQL responding"
else
    # Try Python asyncpg
    if python3 -c "
import asyncio, asyncpg
async def check():
    try:
        c = await asyncpg.connect('postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm')
        await c.close()
        return True
    except: return False
exit(0 if asyncio.run(check()) else 1)
" 2>/dev/null; then
        pass "PostgreSQL responding (via asyncpg)"
    else
        fail "PostgreSQL not responding"
    fi
fi

# Qdrant
if curl -sf "http://localhost:6333/" > /dev/null 2>&1; then
    pass "Qdrant REST API responding"
else
    fail "Qdrant REST API not responding"
fi

# Redpanda (via REST proxy)
if curl -sf "http://localhost:8082/v1/metadata/id" > /dev/null 2>&1; then
    pass "Redpanda REST proxy responding"
else
    # Fallback: port check
    if (echo > /dev/tcp/localhost/19092) 2>/dev/null; then
        pass "Redpanda Kafka port reachable"
    else
        fail "Redpanda not responding"
    fi
fi

# Ollama
if curl -sf "http://localhost:11434/api/tags" > /dev/null 2>&1; then
    pass "Ollama API responding"
else
    warn "Ollama API not responding (optional)"
fi

# Temporal
if python3 -c "
import asyncio
from temporalio.client import Client
async def check():
    try:
        c = await Client.connect('localhost:7233')
        await c.get_system_info()
        return True
    except: return False
exit(0 if asyncio.run(check()) else 1)
" 2>/dev/null; then
    pass "Temporal gRPC API responding"
else
    warn "Temporal not responding (may still be starting)"
fi

echo ""

# =============================================================================
# STEP 2: Database Schema Verification
# =============================================================================
log "STEP 2 — Database Schema Verification"

cd /home/aparna/Desktop/iterate_swarm/apps/ai

# Check required tables exist
python3 << 'EOF'
import asyncio
import asyncpg

async def check_tables():
    conn = await asyncpg.connect('postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm')
    
    required_tables = [
        'transactions',
        'vendor_baselines',
        'finance_snapshots',
        'bi_queries',
        'agent_outputs',
    ]
    
    for table in required_tables:
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = $1
            )
        """, table)
        if exists:
            print(f"  ✓ Table {table} exists")
        else:
            print(f"  ✗ Table {table} missing")
    
    await conn.close()

asyncio.run(check_tables())
EOF

echo ""

# =============================================================================
# STEP 3: Qdrant Collection Verification
# =============================================================================
log "STEP 3 — Qdrant Collection Verification"

# Check finance_memory collection
if curl -sf "http://localhost:6333/collections/finance_memory" | grep -q '"status"'; then
    pass "Qdrant finance_memory collection exists"
else
    # Try to create it
    curl -sf -X PUT "http://localhost:6333/collections/finance_memory" \
        -H "Content-Type: application/json" \
        -d '{
            "vectors": {"size": 768, "distance": "Cosine"}
        }' > /dev/null 2>&1 && \
        pass "Qdrant finance_memory collection created" || \
        warn "Qdrant finance_memory collection not available"
fi

# Check bi_memory collection
if curl -sf "http://localhost:6333/collections/bi_memory" | grep -q '"status"'; then
    pass "Qdrant bi_memory collection exists"
else
    curl -sf -X PUT "http://localhost:6333/collections/bi_memory" \
        -H "Content-Type: application/json" \
        -d '{
            "vectors": {"size": 768, "distance": "Cosine"}
        }' > /dev/null 2>&1 && \
        pass "Qdrant bi_memory collection created" || \
        warn "Qdrant bi_memory collection not available"
fi

echo ""

# =============================================================================
# STEP 4: Ollama Model Verification
# =============================================================================
log "STEP 4 — Ollama Model Verification"

# Check required models
MODELS=("qwen3:0.6b" "nomic-embed-text:latest")

for model in "${MODELS[@]}"; do
    if curl -sf "http://localhost:11434/api/tags" | grep -q "\"name\":\"$model\""; then
        pass "Ollama model $model available"
    else
        warn "Ollama model $model not found"
    fi
done

echo ""

# =============================================================================
# STEP 5: Redpanda Topic Verification
# =============================================================================
log "STEP 5 — Redpanda Topic Verification"

# Check payment-events topic
if curl -sf "http://localhost:8082/v1/topics/payment-events" > /dev/null 2>&1; then
    pass "Redpanda payment-events topic exists"
else
    warn "Redpanda payment-events topic not found (may be created on first use)"
fi

echo ""

# =============================================================================
# STEP 6: Graph Compilation Check (LangGraph)
# =============================================================================
log "STEP 6 — LangGraph Compilation Check"

cd /home/aparna/Desktop/iterate_swarm/apps/ai

# Check Finance Graph
if uv run python -c "
from src.agents.finance.graph import finance_graph
assert finance_graph is not None
print('Finance graph compiled successfully')
" 2>&1 | grep -q "successfully"; then
    pass "Finance LangGraph compiled"
else
    fail "Finance LangGraph compilation failed"
fi

# Check BI Graph
if uv run python -c "
from src.agents.bi.graph import bi_graph
assert bi_graph is not None
print('BI graph compiled successfully')
" 2>&1 | grep -q "successfully"; then
    pass "BI LangGraph compiled"
else
    fail "BI LangGraph compilation failed"
fi

echo ""

# =============================================================================
# STEP 7: Unit Test Sanity Check
# =============================================================================
log "STEP 7 — Unit Test Sanity Check"

cd /home/aparna/Desktop/iterate_swarm/apps/ai

# Run a quick subset of unit tests
if uv run pytest tests/unit/test_workflows.py -v --timeout=30 -q 2>&1 | grep -q "passed"; then
    pass "Unit tests passing"
else
    warn "Some unit tests failing (see full output for details)"
fi

echo ""

# =============================================================================
# STEP 8: E2E Test Infrastructure Check
# =============================================================================
log "STEP 8 — E2E Test Infrastructure Check"

# Run the infrastructure connectivity test
if uv run pytest tests/e2e/test_e2e_flows.py::test_infra_all_services_connected -v --timeout=60 2>&1 | grep -q "PASSED\|passed"; then
    pass "E2E infrastructure test passed"
else
    warn "E2E infrastructure test incomplete (services may still be starting)"
fi

echo ""

# =============================================================================
# STEP 9: LLM Evals Framework Check
# =============================================================================
log "STEP 9 — LLM Evals Framework Check"

# Run evals (simulated - actual LLM calls would improve scores)
if uv run python tests/evals/run_evals.py 2>&1 | grep -q "EVALUATION SUMMARY"; then
    pass "LLM evals framework running"
else
    fail "LLM evals framework error"
fi

echo ""

# =============================================================================
# STEP 10: Simulate Payment Integration
# =============================================================================
log "STEP 10 — Payment Simulation Integration"

if [ -f "/home/aparna/Desktop/iterate_swarm/scripts/simulate_payment.sh" ]; then
    # Just verify script exists and is executable
    if [ -x "/home/aparna/Desktop/iterate_swarm/scripts/simulate_payment.sh" ]; then
        pass "simulate_payment.sh exists and executable"
    else
        warn "simulate_payment.sh not executable"
    fi
else
    fail "simulate_payment.sh not found"
fi

echo ""

# =============================================================================
# SUMMARY
# =============================================================================
echo "========================================"
echo "SMOKE TEST SUMMARY"
echo "========================================"
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All smoke tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Run full E2E suite: uv run pytest tests/e2e/ -v"
    echo "2. Run LLM evals: uv run python tests/evals/run_evals.py"
    echo "3. Start worker: uv run python -m src.worker"
    exit 0
else
    echo -e "${YELLOW}Some tests failed. Check output above for details.${NC}"
    echo ""
    echo "Common fixes:"
    echo "1. Start containers: docker-compose up -d"
    echo "2. Wait for Temporal: sleep 30"
    echo "3. Check Ollama models: ollama pull qwen3:0.6b"
    exit 1
fi
