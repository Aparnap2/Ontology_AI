#!/bin/bash
# OntologyAI Portfolio Demo — clean stop
# Usage: bash scripts/demo_stop.sh
set -e

echo "▶ Stopping OntologyAI demo..."

# Stop worker
if [ -f /tmp/sarthi_worker.pid ]; then
  PID=$(cat /tmp/sarthi_worker.pid)
  kill $PID 2>/dev/null && echo "  ✓ Worker stopped (PID $PID)"
  rm /tmp/sarthi_worker.pid
fi

# Stop containers (don't remove — just stop so restart is fast)
docker stop iterateswarm-postgres iterateswarm-qdrant \
           iterateswarm-redpanda sarthi-temporal 2>/dev/null
echo "  ✓ Containers stopped"
echo "  (data preserved — next start will be instant)"
