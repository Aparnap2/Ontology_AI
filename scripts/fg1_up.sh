#!/bin/sh
# Bring up the services the deterministic gate needs, and wait until each is
# actually ready. FG-1 (issue #71) cannot complete without these.
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")

# Host-based clients (tests, local tooling) MUST use the EXTERNAL listener,
# which advertises localhost:9094. The 19092 mapping is in-network only: it
# advertises the container hostname "redpanda:9092", which does not resolve
# from the host, so clients bootstrap and then fail metadata resolution.
REDPANDA_HOST_URL=${REDPANDA_HOST_URL:-localhost:9094}
export REDPANDA_URL="$REDPANDA_HOST_URL"

wait_for() {
  _name=$1; _cmd=$2; _tries=${3:-40}
  i=0
  while [ "$i" -lt "$_tries" ]; do
    if eval "$_cmd" >/dev/null 2>&1; then
      echo "OK   $_name"
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  echo "FAIL $_name"
  return 1
}

docker start localgcp-cloudsql iterateswarm-redpanda sarthi-redis \
  ontologiai-temporal ontologiai-postgres >/dev/null 2>&1

# Core mock (mockoon) on :3000 — required by
# apps/ai/tests/integration/test_mockoon_endpoints.py (MOCKOON_BASE_URL default
# http://localhost:3000). Installed via npm, not docker, so it is launched here
# detached and gated on its /health contract (service name asserted by the tests).
if command -v mockoon-cli >/dev/null 2>&1; then
  pkill -f "mockoon-cli.*sarthi-demo" >/dev/null 2>&1 || true
  ( cd "$ROOT" && setsid nohup mockoon-cli start \
      --data mockoon/sarthi-demo.json \
      --port 3000 --hostname 0.0.0.0 --log-transaction \
      > /tmp/mockoon-core.log 2>&1 </dev/null & )
  wait_for "core-mock(3000 /health)" \
    "curl -sf -m 2 http://127.0.0.1:3000/health"
else
  echo "SKIP core-mock(:3000) mockoon-cli not installed"
fi

wait_for "postgres(32768)" \
  "PGPASSWORD=iterateswarm psql -h 127.0.0.1 -p 32768 -U iterateswarm -d iterateswarm -tc 'select 1'"
wait_for "redis(6379)" \
  "python3 -c \"import socket;s=socket.create_connection(('127.0.0.1',6379),3);s.send(b'PING\r\n');import sys;sys.exit(0 if b'PONG' in s.recv(32) else 1)\""
wait_for "redpanda(9644)" \
  "curl -sf -m 3 http://127.0.0.1:9644/v1/status/ready"

# Admin-API readiness only proves the broker process is up. This gate asserts
# the full host path: bootstrap, advertised-address resolution, an acknowledged
# host-originated publish, and consumer readback.
wait_for "redpanda host kafka path (bootstrap+metadata+publish+readback)" \
  "cd apps/ai && REDPANDA_URL=$REDPANDA_HOST_URL uv run --frozen python ../../scripts/redpanda_host_ready.py"
