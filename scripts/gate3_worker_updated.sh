#!/usr/bin/env bash
# OntologyAI — Gate 3: Worker Must Import ONLY New Agents
# Run this AFTER Gate 2 passes, BEFORE any deletion
# Usage: bash scripts/gate3_worker_updated.sh

set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     SARTHI — GATE 3: WORKER USES NEW AGENTS ONLY        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

WORKER_FILE="apps/ai/src/worker.py"

if [ ! -f "$WORKER_FILE" ]; then
  echo "  ✗ Worker file not found: $WORKER_FILE"
  echo ""
  echo "ACTION REQUIRED:"
  echo "  Create/update worker.py before proceeding"
  exit 1
fi

echo "--- Checking for REQUIRED new agent imports ---"
REQUIRED_NEW=(
  "PulseWorkflow"
  "InvestorWorkflow"
  "QAWorkflow"
  "run_pulse_agent"
  "run_anomaly_agent"
  "run_investor_agent"
  "run_qa_agent"
  "send_slack_message"
)

ALL_PRESENT=true
for req in "${REQUIRED_NEW[@]}"; do
  if grep -q "$req" "$WORKER_FILE" 2>/dev/null; then
    echo "  ✓ $req"
  else
    echo "  ✗ MISSING: $req"
    ALL_PRESENT=false
  fi
done

echo ""
echo "--- Checking for FORBIDDEN old agent imports ---"
FORBIDDEN_OLD=(
  "FinanceWorkflow"
  "BIWorkflow"
  "run_finance_agent"
  "run_bi_agent"
  "send_telegram_message"
)

ANY_BLOCKED=false
for dead in "${FORBIDDEN_OLD[@]}"; do
  if grep -q "$dead" "$WORKER_FILE" 2>/dev/null; then
    echo "  ✗ BLOCKED — worker.py still references: $dead"
    ANY_BLOCKED=true
  else
    echo "  ✓ not in worker: $dead"
  fi
done

echo ""
if [ "$ALL_PRESENT" = false ] || [ "$ANY_BLOCKED" = true ]; then
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     ✗ GATE 3 FAILED                                     ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "ACTION REQUIRED:"
  if [ "$ALL_PRESENT" = false ]; then
    echo "  Update worker.py to import new agents:"
    for req in "${REQUIRED_NEW[@]}"; do
      if ! grep -q "$req" "$WORKER_FILE" 2>/dev/null; then
        echo "    - Add: $req"
      fi
    done
  fi
  if [ "$ANY_BLOCKED" = true ]; then
    echo "  Remove old agent imports from worker.py:"
    for dead in "${FORBIDDEN_OLD[@]}"; do
      if grep -q "$dead" "$WORKER_FILE" 2>/dev/null; then
        echo "    - Remove: $dead"
      fi
    done
  fi
  exit 1
else
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     ✅ GATE 3 PASSED — WORKER USES NEW AGENTS ONLY      ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "All gates passed!"
  echo "Next: Execute safe_deletion_sequence.sh"
  exit 0
fi
