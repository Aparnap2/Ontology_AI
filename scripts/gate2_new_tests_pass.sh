#!/usr/bin/env bash
# OntologyAI — Gate 2: New Agent Tests Must Pass
# Run this AFTER Gate 1 passes, BEFORE any deletion
# Usage: bash scripts/gate2_new_tests_pass.sh

set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     SARTHI — GATE 2: NEW AGENT TESTS PASS               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

cd apps/ai

DATABASE_URL="postgresql://sarthi:sarthi@localhost:5433/sarthi" \
QDRANT_URL="http://localhost:6333" \
OLLAMA_BASE_URL="http://localhost:11434/v1" \
OLLAMA_CHAT_MODEL="qwen3:0.6b" \
OLLAMA_EMBED_MODEL="nomic-embed-text:latest" \
STRIPE_API_KEY="" \
PLAID_ACCESS_TOKEN="" \
SLACK_WEBHOOK_URL="" \
LANGFUSE_ENABLED="false" \
UV_LINK_MODE=hardlink \
uv run pytest \
  tests/unit/test_pulse_agent.py \
  tests/unit/test_anomaly_agent.py \
  tests/unit/test_investor_agent.py \
  tests/unit/test_qa_agent.py \
  tests/unit/test_integrations.py \
  -v --timeout=60 --tb=short -q

NEW_TESTS_STATUS=$?

echo ""
if [ $NEW_TESTS_STATUS -ne 0 ]; then
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     ✗ GATE 2 FAILED                                     ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "New agent tests are failing"
  echo "Do NOT delete old code until new tests pass"
  echo ""
  echo "ACTION REQUIRED:"
  echo "  Fix failing tests in:"
  echo "    - tests/unit/test_pulse_agent.py"
  echo "    - tests/unit/test_anomaly_agent.py"
  echo "    - tests/unit/test_investor_agent.py"
  echo "    - tests/unit/test_qa_agent.py"
  exit 1
else
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     ✅ GATE 2 PASSED — NEW AGENT TESTS PASS             ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "Next: Run Gate 3 (worker must use new agents only)"
  exit 0
fi
