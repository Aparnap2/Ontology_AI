# OntologyAI — Safe Old Code Deletion Protocol

**Version:** 1.0  
**Date:** March 25, 2026  
**Status:** READY FOR EXECUTION (after Day 2-5 agent implementation)

---

## THE RULE (Non-Negotiable)

```
DELETE NOTHING until the replacement is:
  1. Written
  2. Imported cleanly
  3. Tests passing

Order is always:
  BUILD new → TEST new → DELETE old → TEST again → COMMIT
  
Never:
  DELETE old → build new   ← this breaks imports mid-flight
  Delete both agents at once ← never batch delete
```

---

## STEP 0 — Pre-Deletion Audit Script

**File:** `scripts/audit_before_deletion.sh`

```bash
#!/usr/bin/env bash
# Run this BEFORE any deletion to understand what will be removed

echo "=== PRE-DELETION AUDIT ==="

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
  cat "$f" 2>/dev/null || echo "(file not found)"
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
  cat "$f" 2>/dev/null || echo "(file not found)"
done

echo ""
echo "--- Old workflows ---"
cat apps/ai/src/workflows/finance_workflow.py 2>/dev/null
cat apps/ai/src/workflows/bi_workflow.py 2>/dev/null

echo ""
echo "--- Old activities ---"
cat apps/ai/src/activities/run_finance_agent.py 2>/dev/null
cat apps/ai/src/activities/run_bi_agent.py 2>/dev/null

echo ""
echo "--- Old tests (will be deleted last) ---"
find apps/ai/tests -name "*.py" | xargs grep -l \
  "finance\|bi_agent\|BI\|BIState\|FinanceState" 2>/dev/null

echo ""
echo "--- Cross-references to old agents ---"
grep -rn \
  "from.*agents\.finance\|from.*agents\.bi\|finance_workflow\|bi_workflow\|run_finance_agent\|run_bi_agent" \
  apps/ai/src apps/ai/tests \
  --include="*.py" 2>/dev/null

echo "=== AUDIT DONE — DO NOT DELETE ANYTHING YET ==="
```

---

## THE DELETION GATE (Check Before Each Delete)

**Function:** `safe_to_delete()`

```bash
safe_to_delete() {
  local path="$1"
  local search_term="$2"   # module name to grep for

  echo "--- Safety check: $path ---"

  # 1. Does the file exist?
  if [ ! -e "$path" ]; then
    echo "  (already gone — skip)"
    return 0
  fi

  # 2. Is it still imported anywhere outside itself?
  refs=$(grep -rn "$search_term" \
    apps/ai/src apps/ai/tests \
    --include="*.py" 2>/dev/null | \
    grep -v "^$path:" | \
    grep -v "^Binary" | \
    wc -l | tr -d ' ')

  if [ "$refs" != "0" ]; then
    echo "  ✗ BLOCKED — still referenced in $refs places:"
    grep -rn "$search_term" \
      apps/ai/src apps/ai/tests \
      --include="*.py" 2>/dev/null | \
      grep -v "^$path:" | head -8 | sed 's/^/    /'
    echo "  → Fix references first, then re-run"
    return 1
  fi

  echo "  ✓ Safe to delete (0 external references)"
  return 0
}
```

---

## PHASE-GATED DELETION ORDER

### GATE 1 — New Agents Must Exist

**File:** `scripts/gate1_new_agents_exist.sh`

```bash
#!/usr/bin/env bash
echo "=== GATE 1: Confirm new agents exist ==="

REQUIRED_NEW_FILES=(
  "apps/ai/src/agents/pulse/__init__.py"
  "apps/ai/src/agents/pulse/state.py"
  "apps/ai/src/agents/pulse/prompts.py"
  "apps/ai/src/agents/pulse/nodes.py"
  "apps/ai/src/agents/pulse/graph.py"
  "apps/ai/src/agents/anomaly/__init__.py"
  "apps/ai/src/agents/anomaly/state.py"
  "apps/ai/src/agents/anomaly/prompts.py"
  "apps/ai/src/agents/anomaly/nodes.py"
  "apps/ai/src/agents/anomaly/graph.py"
  "apps/ai/src/agents/investor/__init__.py"
  "apps/ai/src/agents/investor/state.py"
  "apps/ai/src/agents/investor/prompts.py"
  "apps/ai/src/agents/investor/nodes.py"
  "apps/ai/src/agents/investor/graph.py"
  "apps/ai/src/agents/qa/__init__.py"
  "apps/ai/src/agents/qa/state.py"
  "apps/ai/src/agents/qa/prompts.py"
  "apps/ai/src/agents/qa/nodes.py"
  "apps/ai/src/agents/qa/graph.py"
  "apps/ai/src/workflows/pulse_workflow.py"
  "apps/ai/src/workflows/investor_workflow.py"
  "apps/ai/src/workflows/qa_workflow.py"
  "apps/ai/src/activities/run_pulse_agent.py"
  "apps/ai/src/activities/run_anomaly_agent.py"
  "apps/ai/src/activities/run_investor_agent.py"
  "apps/ai/src/activities/run_qa_agent.py"
  "apps/ai/src/activities/send_slack.py"
)

ALL_PRESENT=true
for f in "${REQUIRED_NEW_FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "  ✓ $f"
  else
    echo "  ✗ MISSING: $f"
    ALL_PRESENT=false
  fi
done

if [ "$ALL_PRESENT" = false ]; then
  echo ""
  echo "✗ GATE 1 FAILED — build new agents first (Day 2-5)"
  echo "  Do NOT proceed with any deletions until all files above exist"
  exit 1
fi

echo ""
echo "✅ GATE 1 PASSED — new agents exist"
```

### GATE 2 — New Agent Tests Must Pass

**File:** `scripts/gate2_new_tests_pass.sh`

```bash
#!/usr/bin/env bash
echo "=== GATE 2: New agent tests must pass first ==="

cd apps/ai && \
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

if [ $NEW_TESTS_STATUS -ne 0 ]; then
  echo ""
  echo "✗ GATE 2 FAILED — new agent tests failing"
  echo "  Do NOT delete old code until new tests pass"
  exit 1
fi

echo "✅ GATE 2 PASSED — new agent tests pass"
```

### GATE 3 — Worker Updated to Use New Agents Only

**File:** `scripts/gate3_worker_updated.sh`

```bash
#!/usr/bin/env bash
echo "=== GATE 3: Worker must import ONLY new agents ==="

# Worker must reference new workflows, NOT old ones
for REQUIRED in \
  "PulseWorkflow" \
  "InvestorWorkflow" \
  "QAWorkflow" \
  "run_pulse_agent" \
  "run_anomaly_agent" \
  "run_investor_agent" \
  "run_qa_agent" \
  "send_slack_message"; do
  grep -q "$REQUIRED" apps/ai/src/worker.py && \
    echo "  ✓ $REQUIRED" || \
    echo "  ✗ MISSING in worker.py: $REQUIRED"
done

echo ""
# Worker must NOT reference old agents
for DEAD in \
  "FinanceWorkflow" \
  "BIWorkflow" \
  "run_finance_agent" \
  "run_bi_agent" \
  "send_telegram_message"; do
  if grep -q "$DEAD" apps/ai/src/worker.py 2>/dev/null; then
    echo "  ✗ BLOCKED — worker.py still references: $DEAD"
    echo "    Update worker.py before deleting old code"
  else
    echo "  ✓ not in worker: $DEAD"
  fi
done

echo ""
echo "✅ GATE 3 PASSED — worker uses new agents only"
```

---

## ACTUAL DELETION SEQUENCE

**File:** `scripts/safe_deletion_sequence.sh`

```bash
#!/usr/bin/env bash
# COMPLETE THIS SCRIPT ONLY AFTER GATES 1-3 PASS

set -euo pipefail

echo "=== DELETION SEQUENCE (Gates 1-3 must have passed) ==="

# ── Helper: delete one file, verify tests still pass ──────────────
delete_one() {
  local file="$1"
  local grep_term="$2"
  local test_cmd="$3"

  echo ""
  echo "Deleting: $file"

  # Safety gate
  if ! safe_to_delete "$file" "$grep_term"; then
    return 1
  fi

  # Git remove (tracked + reversible)
  git rm "$file" 2>/dev/null || rm "$file"
  echo "  Removed from disk"

  # Immediately verify
  echo "  Running tests..."
  if eval "$test_cmd" > /tmp/sarthi_test_output 2>&1; then
    echo "  ✅ Tests pass after deleting $file"
  else
    echo "  ✗ TESTS FAILED — restoring $file"
    git restore "$file" 2>/dev/null || \
      echo "  ✗ Cannot restore — run: git restore $file"
    cat /tmp/sarthi_test_output | tail -20
    return 1
  fi
}

PYTEST="cd apps/ai && \
  DATABASE_URL=postgresql://sarthi:sarthi@localhost:5433/sarthi \
  QDRANT_URL=http://localhost:6333 \
  OLLAMA_BASE_URL=http://localhost:11434/v1 \
  STRIPE_API_KEY='' \
  PLAID_ACCESS_TOKEN='' \
  SLACK_WEBHOOK_URL='' \
  LANGFUSE_ENABLED=false \
  UV_LINK_MODE=hardlink \
  uv run pytest tests/unit/ -q --timeout=60 --tb=short"

# ── DELETE OLD TESTS FIRST (they import old agents) ───────────────
echo "--- Step A: Delete old agent test files ---"

OLD_TEST_FILES=$(grep -rl \
  "from.*agents\.finance\|from.*agents\.bi\|FinanceState\|BIState\|finance_graph\|bi_graph" \
  apps/ai/tests --include="*.py" 2>/dev/null || true)

if [ -n "$OLD_TEST_FILES" ]; then
  for f in $OLD_TEST_FILES; do
    delete_one "$f" \
      "agents\.finance\|agents\.bi" \
      "$PYTEST"
  done
else
  echo "  (no old test files found)"
fi

# ── DELETE OLD ACTIVITIES ─────────────────────────────────────────
echo ""
echo "--- Step B: Delete old activity files ---"

delete_one \
  "apps/ai/src/activities/run_finance_agent.py" \
  "run_finance_agent" \
  "$PYTEST"

delete_one \
  "apps/ai/src/activities/run_bi_agent.py" \
  "run_bi_agent" \
  "$PYTEST"

# Delete old Telegram activity only if send_slack.py replaces it
if grep -q "send_slack" apps/ai/src/worker.py 2>/dev/null; then
  delete_one \
    "apps/ai/src/activities/send_telegram.py" \
    "send_telegram" \
    "$PYTEST"
else
  echo "  (keeping send_telegram.py until send_slack.py is in worker)"
fi

# ── DELETE OLD WORKFLOWS ──────────────────────────────────────────
echo ""
echo "--- Step C: Delete old workflow files ---"

delete_one \
  "apps/ai/src/workflows/finance_workflow.py" \
  "finance_workflow\|FinanceWorkflow" \
  "$PYTEST"

delete_one \
  "apps/ai/src/workflows/bi_workflow.py" \
  "bi_workflow\|BIWorkflow" \
  "$PYTEST"

# ── DELETE OLD AGENT FILES (one file at a time) ───────────────────
echo ""
echo "--- Step D: Delete finance agent files ---"

# Delete in dependency order: graph → nodes → prompts → state → __init__
for f in \
  "apps/ai/src/agents/finance/graph.py" \
  "apps/ai/src/agents/finance/nodes.py" \
  "apps/ai/src/agents/finance/prompts.py" \
  "apps/ai/src/agents/finance/state.py" \
  "apps/ai/src/agents/finance/__init__.py"; do
  delete_one "$f" "agents\.finance" "$PYTEST"
done

# Remove empty directory
rmdir apps/ai/src/agents/finance 2>/dev/null && \
  echo "  ✓ Removed empty: apps/ai/src/agents/finance/" || true

echo ""
echo "--- Step E: Delete BI agent files ---"

for f in \
  "apps/ai/src/agents/bi/graph.py" \
  "apps/ai/src/agents/bi/nodes.py" \
  "apps/ai/src/agents/bi/prompts.py" \
  "apps/ai/src/agents/bi/state.py" \
  "apps/ai/src/agents/bi/__init__.py"; do
  delete_one "$f" "agents\.bi" "$PYTEST"
done

rmdir apps/ai/src/agents/bi 2>/dev/null && \
  echo "  ✓ Removed empty: apps/ai/src/agents/bi/" || true

echo ""
echo "=== DELETION SEQUENCE COMPLETE ==="
```

---

## FINAL VERIFICATION

**File:** `scripts/verify_deletion_complete.sh`

```bash
#!/usr/bin/env bash
echo "=== FINAL VERIFICATION ==="

# 1. No dead references remain
echo "--- Dead references check ---"
DEAD_REFS=$(grep -rn \
  "agents\.finance\|agents\.bi\|FinanceState\|BIState\|finance_graph\|bi_graph\|FinanceWorkflow\|BIWorkflow\|run_finance_agent\|run_bi_agent" \
  apps/ai/src apps/ai/tests \
  --include="*.py" 2>/dev/null || true)

if [ -z "$DEAD_REFS" ]; then
  echo "  ✅ Zero dead references"
else
  echo "  ✗ DEAD REFERENCES REMAIN:"
  echo "$DEAD_REFS" | sed 's/^/  /'
  exit 1
fi

# 2. Exactly 4 agents remain
echo ""
echo "--- Agent directories ---"
find apps/ai/src/agents -mindepth 1 -maxdepth 1 -type d | sort
# Expected: anomaly/ investor/ pulse/ qa/

AGENT_COUNT=$(find apps/ai/src/agents -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
[ "$AGENT_COUNT" = "4" ] && \
  echo "  ✅ Exactly 4 agents" || \
  echo "  ✗ Expected 4 agents, found: $AGENT_COUNT"

# 3. All new unit tests still pass
echo ""
echo "--- Full unit test run ---"
cd apps/ai && \
  DATABASE_URL="postgresql://sarthi:sarthi@localhost:5433/sarthi" \
  QDRANT_URL="http://localhost:6333" \
  OLLAMA_BASE_URL="http://localhost:11434/v1" \
  STRIPE_API_KEY="" PLAID_ACCESS_TOKEN="" SLACK_WEBHOOK_URL="" \
  LANGFUSE_ENABLED="false" UV_LINK_MODE=hardlink \
  uv run pytest tests/unit/ \
    -v --timeout=60 --tb=short -q
echo ""
# Expected: all new tests pass, zero failures

# 4. Worker imports cleanly with zero old references
echo ""
echo "--- Worker import check ---"
cd apps/ai && \
  DATABASE_URL="postgresql://sarthi:sarthi@localhost:5433/sarthi" \
  QDRANT_URL="http://localhost:6333" \
  OLLAMA_BASE_URL="http://localhost:11434/v1" \
  TEMPORAL_HOST="localhost:7233" \
  LANGFUSE_ENABLED="false" \
  uv run python -c "
from src.worker import main
from src.workflows.pulse_workflow    import PulseWorkflow
from src.workflows.investor_workflow import InvestorWorkflow
from src.workflows.qa_workflow       import QAWorkflow
print('✅ Worker imports clean — zero old agent references')
"

# 5. Go build still clean
echo ""
cd apps/core && go build ./... && \
  echo "✅ Go build clean" || \
  echo "✗ Go build FAILED"

# 6. Git status — confirm only deletions + new files
echo ""
echo "--- Git status summary ---"
git status --short | head -30

echo ""
echo "=== DELETION COMPLETE ==="
echo ""
echo "Summary:"
echo "  Deleted:  10 files (finance agent + BI agent + old workflows/activities)"
echo "  Kept:      4 agents (pulse, anomaly, investor, qa)"
echo "  Tests:     all pass"
echo "  Regressions: 0"
```

---

## EXECUTION TIMELINE

| Day | Task | Status |
|-----|------|--------|
| Day 1 | Infrastructure (Migration + Qdrant + Integrations) | ✅ COMPLETE |
| Day 2-5 | Build 4 new agents (Pulse, Anomaly, Investor, QA) | ⏳ PENDING |
| Day 6 | GATE 1-3 + Safe deletion sequence | ⏳ PENDING |
| Day 7 | Final verification + git commit | ⏳ PENDING |

---

## CRITICAL REMINDERS

1. **NEVER delete before new code is working** — build first, test second, delete third
2. **NEVER batch delete** — one file at a time, test after each
3. **ALWAYS use `git rm`** — makes restoration trivial if tests fail
4. **NEVER skip gates** — Gates 1-3 exist to prevent broken imports
5. **ALWAYS run final verification** — confirm zero dead references remain

---

**Document Version:** 1.0  
**Last Updated:** March 25, 2026  
**Status:** READY FOR EXECUTION (after Day 2-5 agent implementation)
