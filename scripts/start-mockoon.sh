#!/usr/bin/env bash
# Start Mockoon CLI for OntologyAI — one process per config.
# Directive: mockoon-cli (NOT docker). Core mock on :3000, connectors on :3001-:3004.
# Usage:  bash scripts/start-mockoon.sh
# Stop:   bash scripts/stop-mockoon.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MOCK_DIR="${PROJECT_ROOT}/mockoon"

# Config + port mapping. :3000 is the core mock asserted by
# apps/ai/tests/integration/test_mockoon_endpoints.py; :3001-:3004 match the V6
# connector base URLs.
declare -a CONFIGS=(
  "ontology-ai:3000:${MOCK_DIR}/ontology-ai-demo.json"
  "notion:3001:${MOCK_DIR}/notion.json"
  "slack:3002:${MOCK_DIR}/slack.json"
  "jira:3003:${MOCK_DIR}/jira.json"
  "salesforce:3004:${MOCK_DIR}/salesforce.json"
)

PIDS_DIR="/tmp/ontologyai-mockoon-pids"
mkdir -p "$PIDS_DIR"

stop_existing() {
    if [ -d "$PIDS_DIR" ] && ls "$PIDS_DIR"/*.pid >/dev/null 2>&1; then
        echo "Stopping existing Mockoon CLI processes..."
        for pidfile in "$PIDS_DIR"/*.pid; do
            [ -f "$pidfile" ] || continue
            local pid; pid=$(cat "$pidfile" 2>/dev/null || true)
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
            fi
            rm -f "$pidfile"
        done
        sleep 1
        pkill -f "mockoon-cli.*--port 300[0-4]" 2>/dev/null || true
        sleep 1
    fi
}

check_mockoon_installed() {
    if ! command -v mockoon-cli &> /dev/null; then
        echo "mockoon-cli not found; installing @mockoon/cli..."
        npm install -g @mockoon/cli --quiet || {
            echo "FAIL: npm install -g @mockoon/cli"; exit 1
        }
    fi
}

start_one() {
    local name="$1" port="$2" datafile="$3"
    if [ ! -f "$datafile" ]; then
        echo "FAIL: $datafile missing"; return 1
    fi

    # mockoon-cli: start --data <file> --port <port> --hostname <host> [--cors] [--log-transaction]
    mockoon-cli start \
        --data "$datafile" \
        --port "$port" \
        --hostname "0.0.0.0" \
        --log-transaction \
        > "/tmp/mockoon-${name}.log" 2>&1 &
    local pid=$!
    echo "$pid" > "${PIDS_DIR}/${name}.pid"
    echo "  $name -> :$port (pid $pid)"
}

healthcheck() {
    local port="$1"
    # Core mock (:3000) exposes /health and the tests assert its service name;
    # connector configs may not define /health, so any HTTP response (incl. 404)
    # proves the server is listening.
    local path="/"
    [ "$port" = "3000" ] && path="/health"
    for i in $(seq 1 15); do
        local code
        code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}${path}" 2>/dev/null || echo "000")
        if [ "$port" = "3000" ]; then
            [ "$code" = "200" ] && return 0
        elif [ "$code" != "000" ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

stop_existing
check_mockoon_installed

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   OntologyAI — MOCKOON CLI (core :3000 + 4 connectors)   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

for entry in "${CONFIGS[@]}"; do
    IFS=':' read -r name port datafile <<< "$entry"
    start_one "$name" "$port" "$datafile"
done

echo ""
echo "Waiting for Mockoon APIs to be ready..."
FAIL=0
for entry in "${CONFIGS[@]}"; do
    IFS=':' read -r name port datafile <<< "$entry"
    if healthcheck "$port"; then
        echo "  ✅ $name healthy on :$port"
    else
        echo "  ❌ $name NOT healthy on :$port"
        FAIL=1
    fi
done

if [ "$FAIL" -ne 0 ]; then
    echo ""
    echo "One or more Mockoon APIs failed to start. Logs:"
    for f in /tmp/mockoon-*.log; do echo "--- $f"; tail -5 "$f" 2>/dev/null; done
    exit 1
fi

echo ""
echo "✅ All 5 Mockoon APIs healthy on :3000-:3004"
echo ""
echo "  ontology-ai -> http://localhost:3000  (/health, /internal/hitl/*, /internal/query)"
echo "  notion    -> http://localhost:3001  (/pages)"
echo "  slack     -> http://localhost:3002  (/conversations.list)"
echo "  jira      -> http://localhost:3003  (/rest/api/3/search)"
echo "  salesforce-> http://localhost:3004  (/services/data/v58.0/query)"
