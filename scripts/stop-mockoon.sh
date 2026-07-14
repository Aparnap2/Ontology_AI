#!/usr/bin/env bash
# Stop Mockoon CLI for OntologyAI v1.0
# Usage: bash scripts/stop-mockoon.sh

set -euo pipefail

echo "Stopping Mockoon CLI..."

if [ -f /tmp/sarthi-mockoon.pid ]; then
    PID=$(cat /tmp/sarthi-mockoon.pid)
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "✅ Mockoon stopped (PID: ${PID})"
        rm /tmp/sarthi-mockoon.pid
    else
        echo "⚠️  Mockoon process not running (stale PID file)"
        rm /tmp/sarthi-mockoon.pid
    fi
else
    # Fallback: kill by process name
    if pkill -f "mockoon-cli.*3000" > /dev/null 2>&1; then
        echo "✅ Mockoon stopped"
    else
        echo "ℹ️  No Mockoon process found"
    fi
fi
