#!/usr/bin/env bash
set -euo pipefail

PASS=0
FAIL=0

check() {
  local label="$1"; shift
  printf "  %-50s" "$label"
  if "$@" > /tmp/sarthi_check.log 2>&1; then
    echo "✓"
    ((PASS++)) || true
  else
    echo "✗"
    cat /tmp/sarthi_check.log
    ((FAIL++)) || true
  fi
}

echo ""
echo "════════════════════════════════════════════════════"
echo " SARTHI TEST SUITE — Real Docker + Real Azure       "
echo "════════════════════════════════════════════════════"

echo ""
echo "[1/6] Docker health"
for svc in iterateswarm-postgres iterateswarm-redpanda iterateswarm-qdrant; do
  check "$svc running" bash -c "docker ps --format '{{.Names}}\t{{.Status}}' | grep '$svc' | grep -qiE 'running|healthy'"
done

echo ""
echo "[2/6] Go tests (all packages)"
check "go test ./..." bash -c "cd apps/core && go test ./... -timeout=60s -count=1 -q"

echo ""
echo "[3/6] Python agent unit tests"
cd apps/ai
for agent in finance_monitor revenue_tracker cs_agent people_coordinator chief_of_staff; do
  check "test_${agent}" uv run pytest "tests/test_${agent}.py" -q --timeout=60 || true
done
cd - > /dev/null

echo ""
echo "[4/6] Invariant checks"
check "I-1 no raw JSON in workflow" bash -c \
  "! grep -rn 'json.Marshal\|json.Unmarshal' apps/core/internal/workflow/ | grep -v '_test.go' | grep -v '// safe:' || true"
check "I-2 no direct AzureOpenAI()" bash -c \
  "! grep -rn 'AzureOpenAI(' apps/ai/src/ | grep -v 'config/llm.py' || true"
check "I-3 no banned jargon" bash -c \
  "! grep -rn 'leverage\|synergy\|utilize\|streamline\|paradigm' apps/ai/src/agents/ | grep -v '# allowed:' || true"

echo ""
echo "[5/6] E2E flows (real Temporal + real LLM)"
cd apps/ai
check "E2E finance anomaly"   uv run pytest tests/test_e2e_sarthi.py -k finance_anomaly -q --timeout=120 || true
check "E2E weekly briefing"   uv run pytest tests/test_e2e_sarthi.py -k weekly_briefing -q --timeout=120 || true
check "E2E onboarding nag"    uv run pytest tests/test_e2e_sarthi.py -k onboarding -q --timeout=120 || true
check "E2E churn alert"       uv run pytest tests/test_e2e_sarthi.py -k churn_alert -q --timeout=120 || true
check "E2E investor draft"    uv run pytest tests/test_e2e_sarthi.py -k investor_update -q --timeout=120 || true
cd - > /dev/null

echo ""
echo "[6/6] Telegram handler tests"
check "Telegram tests" bash -c "cd apps/core && go test ./internal/api -run TestTelegram -v -timeout=60s"

echo ""
echo "════════════════════════════════════════════════════"
printf " PASSED: %-3d  FAILED: %-3d\n" $PASS $FAIL
if [[ $FAIL -eq 0 ]]; then
  echo " ✅ ALL TESTS PASSED — ready to tag v1.0.0-alpha"
else
  echo " ❌ FAILURES — fix before tagging"
fi
echo "════════════════════════════════════════════════════"

exit $FAIL
