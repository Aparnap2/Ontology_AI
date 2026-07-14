#!/usr/bin/env bash
# Test OntologyAI v1.0 endpoints against Mockoon mock
# Usage: bash scripts/test-with-mockoon.sh

set -euo pipefail

MOCK_PORT="${MOCK_PORT:-3000}"
MOCK_BASE="http://localhost:${MOCK_PORT}"
PASS=0
FAIL=0

log() { echo "  $*"; }
ok() { log "✅ $*"; PASS=$((PASS + 1)); }
fail() { log "❌ $*"; FAIL=$((FAIL + 1)); }

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     SARTHI v1.0 — MOCKOON INTEGRATION TESTS             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check Mockoon is running
echo "1. Checking Mockoon..."
if curl -sf "${MOCK_BASE}/health" > /dev/null 2>&1; then
    ok "Mockoon running on port ${MOCK_PORT}"
else
    echo "❌ Mockoon not running"
    echo "   Start with: bash scripts/start-mockoon.sh"
    exit 1
fi

# Test HITL Investigate
echo ""
echo "2. Testing HITL Investigate..."

RESPONSE=$(curl -sf -X POST "${MOCK_BASE}/internal/hitl/investigate" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"finance-abc123","tenant_id":"test-tenant","vendor":"AWS"}')

if echo "$RESPONSE" | grep -q '"ok": true'; then
    ok "HITL investigate returns ok=true"
else
    fail "HITL investigate response"
    echo "   Response: $RESPONSE"
fi

if echo "$RESPONSE" | grep -q '"action": "investigate"'; then
    ok "HITL investigate returns correct action"
else
    fail "HITL investigate action field"
fi

# Test HITL Investigate (missing workflow_id)
echo ""
echo "3. Testing HITL Investigate (validation)..."

RESPONSE=$(curl -s -X POST "${MOCK_BASE}/internal/hitl/investigate" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test"}')

if echo "$RESPONSE" | grep -q '"error"'; then
    ok "HITL investigate validates workflow_id"
else
    fail "HITL investigate validation"
fi

# Test HITL Dismiss
echo ""
echo "4. Testing HITL Dismiss..."

RESPONSE=$(curl -sf -X POST "${MOCK_BASE}/internal/hitl/dismiss" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"finance-xyz789","tenant_id":"test-tenant","vendor":"Vercel"}')

if echo "$RESPONSE" | grep -q '"ok": true'; then
    ok "HITL dismiss returns ok=true"
else
    fail "HITL dismiss response"
fi

if echo "$RESPONSE" | grep -q '"action": "dismiss"'; then
    ok "HITL dismiss returns correct action"
else
    fail "HITL dismiss action field"
fi

# Test BI Query
echo ""
echo "5. Testing BI Query..."

RESPONSE=$(curl -sf -X POST "${MOCK_BASE}/internal/query" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test-tenant","query":"What are total expenses by vendor last 30 days?","query_type":"ADHOC"}')

if echo "$RESPONSE" | grep -q '"ok": true'; then
    ok "BI query returns ok=true"
else
    fail "BI query response"
fi

if echo "$RESPONSE" | grep -q '"workflow_id"'; then
    ok "BI query returns workflow_id"
else
    fail "BI query workflow_id field"
fi

if echo "$RESPONSE" | grep -q '"query_id"'; then
    ok "BI query returns query_id"
else
    fail "BI query query_id field"
fi

# Test BI Query (missing query)
echo ""
echo "6. Testing BI Query (validation)..."

RESPONSE=$(curl -s -X POST "${MOCK_BASE}/internal/query" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test"}')

if echo "$RESPONSE" | grep -q '"error"'; then
    ok "BI query validates query field"
else
    fail "BI query validation"
fi

# Test Telegram sendMessage mock
echo ""
echo "7. Testing Telegram sendMessage mock..."

RESPONSE=$(curl -sf -X POST "${MOCK_BASE}/bot:test-token/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"42","text":"🔴 Finance Alert: AWS bill 2.3× usual","parse_mode":"Markdown"}')

if echo "$RESPONSE" | grep -q '"ok": true'; then
    ok "Telegram sendMessage returns ok=true"
else
    fail "Telegram sendMessage response"
fi

if echo "$RESPONSE" | grep -q '"message_id"'; then
    ok "Telegram sendMessage returns message_id"
else
    fail "Telegram sendMessage message_id"
fi

# Test Telegram sendPhoto mock
echo ""
echo "8. Testing Telegram sendPhoto mock..."

RESPONSE=$(curl -sf -X POST "${MOCK_BASE}/bot:test-token/sendPhoto" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"42","caption":"AWS expenses breakdown"}')

if echo "$RESPONSE" | grep -q '"ok": true'; then
    ok "Telegram sendPhoto returns ok=true"
else
    fail "Telegram sendPhoto response"
fi

if echo "$RESPONSE" | grep -q '"photo"'; then
    ok "Telegram sendPhoto returns photo object"
else
    fail "Telegram sendPhoto photo field"
fi

# Summary
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     TEST SUMMARY                                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Passed: ${PASS}"
echo "  Failed: ${FAIL}"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "✅ ALL TESTS PASSED"
    exit 0
else
    echo "❌ SOME TESTS FAILED"
    exit 1
fi
