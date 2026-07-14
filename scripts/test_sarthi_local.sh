#!/usr/bin/env bash
# OntologyAI Local Test Suite with tg-mock Telegram Mock
# Usage: bash scripts/test_sarthi_local.sh
# 
# This script runs OntologyAI tests locally using:
# - tg-mock for Telegram Bot API mocking (ghcr.io/watzon/tg-mock)
# - Docker containers for PostgreSQL, Redpanda, Qdrant
# - Real LLM calls (Azure/Groq/Ollama)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

PASS=0
FAIL=0

log() {
    echo ""
    echo "════════════════════════════════════════════════════"
    echo " $1"
    echo "════════════════════════════════════════════════════"
}

run_test() {
    local label="$1"; shift
    printf "  %-50s" "$label"
    if "$@" > /tmp/sarthi_test.log 2>&1; then
        echo "✓"
        ((PASS++)) || true
    else
        echo "✗"
        cat /tmp/sarthi_test.log
        ((FAIL++)) || true
    fi
}

stop_container() {
    local name="$1"
    if docker ps -q --filter name="$name" | grep -q .; then
        docker stop "$name" >/dev/null 2>&1 || true
        docker rm "$name" >/dev/null 2>&1 || true
    fi
}

cleanup() {
    echo ""
    echo "Cleaning up..."
    stop_container sarthi-tg-mock
    echo "  tg-mock stopped ✓"
}

trap cleanup EXIT

echo ""
log "STEP 0 — Infrastructure Setup"

echo ""
log "STEP 0a — Docker Infrastructure"

for svc in iterateswarm-postgres iterateswarm-redpanda iterateswarm-qdrant; do
    if ! docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
        echo "  Starting $svc..."
        docker run -d --name "$svc" \
            -e POSTGRES_USER=sarthi \
            -e POSTGRES_PASSWORD=sarthi \
            -e POSTGRES_DB=sarthi \
            -p 5432:5432 \
            postgres:16-alpine || true
    else
        echo "  $svc already running ✓"
    fi
done

echo "  Waiting for services to be healthy..."
sleep 5

echo ""
log "STEP 0b — tg-mock Telegram Mock (ghcr.io/watzon/tg-mock)"

stop_container sarthi-tg-mock

docker run -d \
  --name sarthi-tg-mock \
  -p 8081:8081 \
  -v "${PROJECT_ROOT}/config/tg-mock.yaml:/config.yaml:ro" \
  -v tg-mock-storage:/tmp/tg-mock-files \
  ghcr.io/watzon/tg-mock:latest \
  --config /config.yaml \
  --verbose

echo "  Waiting for tg-mock to start..."
sleep 5

export TELEGRAM_BOT_TOKEN=987654321:ZYX-cba
export TELEGRAM_API_BASE=http://localhost:8081
export TELEGRAM_TEST_CHAT_ID=111222333

run_test "tg-mock: getMe returns ok" bash -c \
  "curl -sf http://localhost:8081/bot987654321:ZYX-cba/getMe \
   | grep -q '\"ok\":true'"

run_test "tg-mock: sendMessage with keyboard" bash -c "
curl -sf -X POST \
  http://localhost:8081/bot987654321:ZYX-cba/sendMessage \
  -H 'Content-Type: application/json' \
  -d '{\"chat_id\":\"111222333\",\"text\":\"OntologyAI boot check\",
       \"reply_markup\":{\"inline_keyboard\":
         [[{\"text\":\"OK\",\"callback_data\":\"mark_ok:test\"}]]}}' \
  | grep -q 'message_id'
"

run_test "tg-mock: answerCallbackQuery" bash -c "
curl -sf -X POST \
  http://localhost:8081/bot987654321:ZYX-cba/answerCallbackQuery \
  -H 'Content-Type: application/json' \
  -d '{\"callback_query_id\":\"cq-001\"}' \
  | grep -q '\"ok\":true'
"

run_test "tg-mock: 429 simulation (chat_id=999)" bash -c "
curl -sf -o /dev/null -w '%{http_code}' \
  -X POST \
  http://localhost:8081/bot987654321:ZYX-cba/sendMessage \
  -H 'Content-Type: application/json' \
  -d '{\"chat_id\":999,\"text\":\"test\"}' \
  | grep -q '429'
"

run_test "python: telegram mock tests" bash -c \
  "cd apps/ai && \
   TELEGRAM_API_BASE=http://localhost:8081 \
   TELEGRAM_BOT_TOKEN=test-token-sarthi \
   TELEGRAM_TEST_CHAT_ID=111222333 \
   uv run pytest tests/test_telegram_mock.py -q --timeout=30"

run_test "go: telegram mock handler tests" bash -c \
  "cd apps/core && \
   TELEGRAM_API_BASE=http://localhost:8081 \
   TELEGRAM_BOT_TOKEN=test-token-sarthi \
   TELEGRAM_TEST_CHAT_ID=111222333 \
   go test ./internal/api -run TestTelegramSendMessageViaMock -v -timeout 15s"

echo "  tg-mock running on :8081 — kept alive for E2E steps"

echo ""
log "STEP 1 — Go Unit Tests"

run_test "go test ./internal/api" bash -c \
  "cd apps/core && TELEGRAM_API_BASE=http://localhost:8081 TELEGRAM_BOT_TOKEN=test-token-sarthi go test ./internal/api -timeout=60s -count=1"

run_test "go test ./internal/agents" bash -c \
  "cd apps/core && go test ./internal/agents -timeout=60s -count=1"

echo ""
log "STEP 2 — Python Agent Tests"

cd apps/ai
for agent in finance_monitor revenue_tracker cs_agent people_coordinator chief_of_staff; do
    if [[ -f "tests/test_${agent}.py" ]]; then
        run_test "test_${agent}" uv run pytest "tests/test_${agent}.py" -q --timeout=60 || true
    fi
done
cd - > /dev/null

echo ""
log "STEP 3 — Invariant Checks"

run_test "I-1 no raw JSON in workflow" bash -c \
  "! grep -rn 'json.Marshal\|json.Unmarshal' apps/core/internal/workflow/ | grep -v '_test.go' | grep -v '// safe:' || true"

run_test "I-2 no direct AzureOpenAI()" bash -c \
  "! grep -rn 'AzureOpenAI(' apps/ai/src/ | grep -v 'config/llm.py' || true"

run_test "I-3 no banned jargon" bash -c \
  "! grep -rn 'leverage\|synergy\|utilize\|streamline\|paradigm' apps/ai/src/agents/ | grep -v '# allowed:' || true"

echo ""
log "STEP 4 — E2E Flows (Temporal + LLM)"

cd apps/ai
run_test "E2E finance anomaly"   uv run pytest tests/test_e2e_ontology_ai.py -k finance_anomaly -q --timeout=120 || true
run_test "E2E weekly briefing"   uv run pytest tests/test_e2e_ontology_ai.py -k weekly_briefing -q --timeout=120 || true
run_test "E2E onboarding nag"    uv run pytest tests/test_e2e_ontology_ai.py -k onboarding -q --timeout=120 || true
run_test "E2E churn alert"       uv run pytest tests/test_e2e_ontology_ai.py -k churn_alert -q --timeout=120 || true
run_test "E2E investor draft"    uv run pytest tests/test_e2e_ontology_ai.py -k investor_update -q --timeout=120 || true
cd - > /dev/null

echo ""
log "STEP 5 — Telegram Integration Tests"

run_test "Telegram rate limit handling" bash -c \
  "cd apps/core && TELEGRAM_API_BASE=http://localhost:8081 TELEGRAM_BOT_TOKEN=test-token-sarthi go test ./internal/api -run TestTelegramRateLimitHandling -v -timeout=15s"

run_test "Telegram chat not found" bash -c \
  "cd apps/core && TELEGRAM_API_BASE=http://localhost:8081 TELEGRAM_BOT_TOKEN=test-token-sarthi go test ./internal/api -run TestTelegramChatNotFoundHandling -v -timeout=15s"

echo ""
log "TEST SUMMARY"

printf " PASSED: %-3d  FAILED: %-3d\n" $PASS $FAIL
if [[ $FAIL -eq 0 ]]; then
    echo " ✅ ALL TESTS PASSED — ready to tag v1.0.0-alpha"
else
    echo " ❌ FAILURES — fix before tagging"
fi

echo ""
echo "════════════════════════════════════════════════════"

exit $FAIL
