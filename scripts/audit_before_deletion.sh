#!/usr/bin/env bash
# OntologyAI — Pre-Deletion Audit Script
# Run this BEFORE any deletion to understand what will be removed
# Usage: bash scripts/audit_before_deletion.sh

set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     SARTHI — PRE-DELETION AUDIT                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Read EVERY file that will be deleted
echo "--- Finance Agent (5 files to delete) ---"
for f in \
  apps/ai/src/agents/finance/__init__.py \
  apps/ai/src/agents/finance/state.py \
  apps/ai/src/agents/finance/prompts.py \
  apps/ai/src/agents/finance/nodes.py \
  apps/ai/src/agents/finance/graph.py; do
  echo ""
  echo "=== $f ==="
  if [ -f "$f" ]; then
    wc -l "$f" | awk '{print "  Lines:", $1}'
    head -20 "$f" | sed 's/^/  /'
    echo "  ..."
  else
    echo "  (file not found)"
  fi
done

echo ""
echo "--- BI Agent (5 files to delete) ---"
for f in \
  apps/ai/src/agents/bi/__init__.py \
  apps/ai/src/agents/bi/state.py \
  apps/ai/src/agents/bi/prompts.py \
  apps/ai/src/agents/bi/nodes.py \
  apps/ai/src/agents/bi/graph.py; do
  echo ""
  echo "=== $f ==="
  if [ -f "$f" ]; then
    wc -l "$f" | awk '{print "  Lines:", $1}'
    head -20 "$f" | sed 's/^/  /'
    echo "  ..."
  else
    echo "  (file not found)"
  fi
done

echo ""
echo "--- Old workflows ---"
for f in \
  apps/ai/src/workflows/finance_workflow.py \
  apps/ai/src/workflows/bi_workflow.py; do
  echo ""
  echo "=== $f ==="
  if [ -f "$f" ]; then
    wc -l "$f" | awk '{print "  Lines:", $1}'
    head -30 "$f" | sed 's/^/  /'
    echo "  ..."
  else
    echo "  (file not found)"
  fi
done

echo ""
echo "--- Old activities ---"
for f in \
  apps/ai/src/activities/run_finance_agent.py \
  apps/ai/src/activities/run_bi_agent.py \
  apps/ai/src/activities/send_telegram.py; do
  echo ""
  echo "=== $f ==="
  if [ -f "$f" ]; then
    wc -l "$f" | awk '{print "  Lines:", $1}'
    head -30 "$f" | sed 's/^/  /'
    echo "  ..."
  else
    echo "  (file not found)"
  fi
done

echo ""
echo "--- Old tests (will be deleted last) ---"
OLD_TESTS=$(find apps/ai/tests -name "*.py" -type f 2>/dev/null | \
  xargs grep -l "finance\|bi_agent\|BI\|BIState\|FinanceState" 2>/dev/null || true)

if [ -n "$OLD_TESTS" ]; then
  echo "$OLD_TESTS" | while read -r f; do
    echo "  - $f"
  done
else
  echo "  (none found)"
fi

echo ""
echo "--- Cross-references to old agents ---"
REFS=$(grep -rn \
  "from.*agents\.finance\|from.*agents\.bi\|finance_workflow\|bi_workflow\|run_finance_agent\|run_bi_agent" \
  apps/ai/src apps/ai/tests \
  --include="*.py" 2>/dev/null || true)

if [ -n "$REFS" ]; then
  echo "$REFS" | head -20 | sed 's/^/  /'
  COUNT=$(echo "$REFS" | wc -l | tr -d ' ')
  if [ "$COUNT" -gt 20 ]; then
    echo "  ... and $((COUNT - 20)) more"
  fi
else
  echo "  (none found)"
fi

echo ""
echo "=== AUDIT COMPLETE ==="
echo ""
echo "DO NOT DELETE ANYTHING YET"
echo ""
echo "Next steps:"
echo "  1. Complete Day 2-5 (build new agents)"
echo "  2. Run Gate 1-3 checks"
echo "  3. Execute safe_deletion_sequence.sh"
echo "  4. Run final verification"
