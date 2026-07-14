#!/usr/bin/env bash
# OntologyAI — Gate 1: Confirm New Agents Exist
# Run this BEFORE any deletion
# Usage: bash scripts/gate1_new_agents_exist.sh

set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     SARTHI — GATE 1: NEW AGENTS EXIST                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

REQUIRED_NEW_FILES=(
  # Pulse Agent
  "apps/ai/src/agents/pulse/__init__.py"
  "apps/ai/src/agents/pulse/state.py"
  "apps/ai/src/agents/pulse/prompts.py"
  "apps/ai/src/agents/pulse/nodes.py"
  "apps/ai/src/agents/pulse/graph.py"
  # Anomaly Agent
  "apps/ai/src/agents/anomaly/__init__.py"
  "apps/ai/src/agents/anomaly/state.py"
  "apps/ai/src/agents/anomaly/prompts.py"
  "apps/ai/src/agents/anomaly/nodes.py"
  "apps/ai/src/agents/anomaly/graph.py"
  # Investor Agent
  "apps/ai/src/agents/investor/__init__.py"
  "apps/ai/src/agents/investor/state.py"
  "apps/ai/src/agents/investor/prompts.py"
  "apps/ai/src/agents/investor/nodes.py"
  "apps/ai/src/agents/investor/graph.py"
  # QA Agent
  "apps/ai/src/agents/qa/__init__.py"
  "apps/ai/src/agents/qa/state.py"
  "apps/ai/src/agents/qa/prompts.py"
  "apps/ai/src/agents/qa/nodes.py"
  "apps/ai/src/agents/qa/graph.py"
  # Workflows
  "apps/ai/src/workflows/pulse_workflow.py"
  "apps/ai/src/workflows/investor_workflow.py"
  "apps/ai/src/workflows/qa_workflow.py"
  # Activities
  "apps/ai/src/activities/run_pulse_agent.py"
  "apps/ai/src/activities/run_anomaly_agent.py"
  "apps/ai/src/activities/run_investor_agent.py"
  "apps/ai/src/activities/run_qa_agent.py"
  "apps/ai/src/activities/send_slack.py"
)

ALL_PRESENT=true
MISSING=()

for f in "${REQUIRED_NEW_FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "  ✓ $f"
  else
    echo "  ✗ MISSING: $f"
    ALL_PRESENT=false
    MISSING+=("$f")
  fi
done

echo ""
if [ "$ALL_PRESENT" = false ]; then
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     ✗ GATE 1 FAILED                                     ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "Missing files (${#MISSING[@]}):"
  for f in "${MISSING[@]}"; do
    echo "  - $f"
  done
  echo ""
  echo "ACTION REQUIRED:"
  echo "  Build new agents first (Day 2-5)"
  echo "  Do NOT proceed with any deletions until all files above exist"
  exit 1
else
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║     ✅ GATE 1 PASSED — ALL NEW AGENTS EXIST             ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "Next: Run Gate 2 (new tests must pass)"
  exit 0
fi
