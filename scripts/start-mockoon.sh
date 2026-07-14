#!/usr/bin/env bash
# Start Mockoon CLI for OntologyAI v1.0 testing
# Usage: bash scripts/start-mockoon.sh
# Stop:  bash scripts/stop-mockoon.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MOCK_DATA="${PROJECT_ROOT}/config/mockoon-ontology_ai.json"
MOCK_PORT="${MOCK_PORT:-3000}"

stop_existing() {
    if pgrep -f "mockoon-cli.*${MOCK_PORT}" > /dev/null 2>&1; then
        echo "Stopping existing Mockoon process..."
        pkill -f "mockoon-cli.*${MOCK_PORT}" || true
        sleep 2
    fi
}

start_mockoon() {
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║     SARTHI v1.0 — MOCKOON CLI STARTING                   ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
    
    # Check if mockoon-cli is installed
    if ! command -v mockoon-cli &> /dev/null; then
        echo "Installing Mockoon CLI..."
        npm install -g @mockoon/cli --quiet 2>/dev/null || {
            echo "❌ Failed to install @mockoon/cli"
            echo "   Run: npm install -g @mockoon/cli"
            exit 1
        }
    fi
    
    # Verify data file exists
    if [ ! -f "$MOCK_DATA" ]; then
        echo "❌ Mock data file not found: $MOCK_DATA"
        exit 1
    fi
    
    echo "Starting Mockoon CLI..."
    echo "  Data file: $MOCK_DATA"
    echo "  Port:      $MOCK_PORT"
    echo ""
    
    # Start Mockoon in background
    mockoon-cli start \
      --data "$MOCK_DATA" \
      --port "$MOCK_PORT" \
      --hostname "0.0.0.0" \
      --log-transaction \
      &
    
    MOCKOON_PID=$!
    echo $MOCKOON_PID > /tmp/sarthi-mockoon.pid
    
    # Wait for Mockoon to be ready
    echo "Waiting for Mockoon to start..."
    for i in {1..15}; do
        if curl -sf "http://localhost:${MOCK_PORT}/health" > /dev/null 2>&1; then
            echo ""
            echo "✅ Mockoon ready on port ${MOCK_PORT}"
            echo ""
            echo "Available endpoints:"
            echo "  GET  http://localhost:${MOCK_PORT}/health"
            echo "  POST http://localhost:${MOCK_PORT}/internal/hitl/investigate"
            echo "  POST http://localhost:${MOCK_PORT}/internal/hitl/dismiss"
            echo "  POST http://localhost:${MOCK_PORT}/internal/query"
            echo "  POST http://localhost:${MOCK_PORT}/bot:test-token/sendMessage"
            echo "  POST http://localhost:${MOCK_PORT}/bot:test-token/sendPhoto"
            echo ""
            echo "Process ID: ${MOCKOON_PID}"
            echo "Log file:   /tmp/mockoon-ontology_ai.log"
            return 0
        fi
        sleep 1
    done
    
    echo "❌ Mockoon failed to start within 15 seconds"
    cat /tmp/mockoon-ontology_ai.log 2>/dev/null || true
    return 1
}

stop_existing
start_mockoon

# Save log to file
mockoon-cli start \
  --data "$MOCK_DATA" \
  --port "$MOCK_PORT" \
  --hostname "0.0.0.0" \
  --log-transaction \
  > /tmp/mockoon-ontology_ai.log 2>&1 &

echo $! > /tmp/sarthi-mockoon.pid
echo ""
echo "✅ Mockoon started (PID: $(cat /tmp/sarthi-mockoon.pid))"
