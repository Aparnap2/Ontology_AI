#!/usr/bin/env bash
# Stop Mockoon CLI for OntologyAI (core mock on :3000 + connectors on :3001-3004).
# Usage:  bash scripts/stop-mockoon.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PIDS_DIR="/tmp/ontologyai-mockoon-pids"

echo "Stopping Mockoon CLI..."

stopped=0
if [ -d "$PIDS_DIR" ] && ls "$PIDS_DIR"/*.pid >/dev/null 2>&1; then
    for pidfile in "$PIDS_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        local_pid=$(cat "$pidfile" 2>/dev/null || true)
        if [ -n "$local_pid" ] && kill -0 "$local_pid" 2>/dev/null; then
            kill "$local_pid" 2>/dev/null || true
            echo "  ✅ stopped pid $local_pid ($(basename "$pidfile" .pid))"
            stopped=$((stopped + 1))
        fi
        rm -f "$pidfile"
    done
fi

# Fallback: kill any lingering mockoon-cli on the OntologyAI ports.
pkill -f "mockoon-cli.*--port 300[0-4]" 2>/dev/null && stopped=$((stopped + 1)) || true
sleep 1

if [ "$stopped" -gt 0 ]; then
    echo ""
    echo "✅ Mockoon stopped ($stopped process(es))."
else
    echo "ℹ️  No Mockoon process found."
fi
rm -rf "$PIDS_DIR"
