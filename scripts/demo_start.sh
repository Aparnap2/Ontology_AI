#!/bin/bash
# OntologyAI Portfolio Demo — single command startup
# Usage: bash scripts/demo_start.sh
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         SARTHI — Starting Demo          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Start all containers ───────────────────────────────────────
echo "▶ Starting infrastructure..."
docker start iterateswarm-postgres  2>/dev/null || true
docker start iterateswarm-qdrant    2>/dev/null || true
docker start iterateswarm-redpanda  2>/dev/null || true
docker start sarthi-temporal        2>/dev/null || true

# ── 2. Wait for services with timeout ────────────────────────────
echo "▶ Waiting for services..."

wait_for() {
  local name="$1"; local cmd="$2"; local max=30; local n=0
  while ! eval "$cmd" > /dev/null 2>&1; do
    n=$((n+1))
    if [ $n -ge $max ]; then echo "  ✗ $name timed out"; exit 1; fi
    sleep 1
  done
  echo "  ✓ $name"
}

wait_for "PostgreSQL" \
  "docker exec iterateswarm-postgres pg_isready -U iterateswarm -q"
wait_for "Qdrant" \
  "curl -sf http://localhost:6333/healthz"
wait_for "Temporal" \
  "nc -z localhost 7233"
wait_for "Ollama" \
  "curl -sf http://localhost:11434/api/tags"

# ── 3. Verify Qdrant collections exist ───────────────────────────
echo ""
echo "▶ Verifying Qdrant collections..."
cd /home/aparna/Desktop/iterate_swarm/apps/ai && \
  QDRANT_URL="http://localhost:6333" \
  OLLAMA_BASE_URL="http://localhost:11434/v1" \
  uv run python src/setup/init_qdrant_collections.py --quiet 2>/dev/null || \
  uv run python src/setup/init_qdrant_collections.py
cd ../..

# ── 4. Run DB migration (idempotent) ─────────────────────────────
echo ""
echo "▶ Ensuring database schema..."
psql "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm" \
  -f migrations/009_pulse_pivot.sql -q 2>/dev/null && \
  echo "  ✓ Schema ready"

# ── 5. Start Temporal worker in background ────────────────────────
echo ""
echo "▶ Starting Temporal worker..."
cd /home/aparna/Desktop/iterate_swarm/apps/ai

DATABASE_URL="postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm" \
QDRANT_URL="http://localhost:6333" \
OLLAMA_BASE_URL="http://localhost:11434/v1" \
OLLAMA_CHAT_MODEL="qwen3:0.6b" \
OLLAMA_EMBED_MODEL="nomic-embed-text:latest" \
TEMPORAL_HOST="localhost:7233" \
TEMPORAL_TASK_QUEUE="SARTHI-MAIN-QUEUE" \
STRIPE_API_KEY="" \
PLAID_ACCESS_TOKEN="" \
SLACK_WEBHOOK_URL="" \
LANGFUSE_ENABLED="false" \
UV_LINK_MODE=hardlink \
uv run python -m src.worker > /tmp/sarthi_worker.log 2>&1 &

WORKER_PID=$!
echo $WORKER_PID > /tmp/sarthi_worker.pid
cd ../..

# Wait for worker to connect
sleep 4
if kill -0 $WORKER_PID 2>/dev/null; then
  echo "  ✓ Worker running (PID $WORKER_PID)"
else
  echo "  ✗ Worker failed to start — check /tmp/sarthi_worker.log"
  cat /tmp/sarthi_worker.log | tail -20
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         ✅ SARTHI READY TO DEMO         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  PostgreSQL  → localhost:5433            ║"
echo "║  Qdrant      → localhost:6333            ║"
echo "║  Temporal    → localhost:7233            ║"
echo "║  Ollama      → localhost:11434           ║"
echo "║  Worker      → PID $WORKER_PID           ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Run demo:  bash scripts/demo_run.sh     ║"
echo "║  Stop all:  bash scripts/demo_stop.sh    ║"
echo "╚══════════════════════════════════════════╝"
echo ""
