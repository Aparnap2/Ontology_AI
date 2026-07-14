#!/usr/bin/env bash
set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║     SARTHI v1.0 — PRODUCTION START                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")/.."

# 1. Validate .env exists
if [ ! -f .env ]; then
  echo "✗ .env not found — copy from .env.example and fill in values"
  echo "  cp .env.example .env"
  exit 1
fi

# 2. Load env
set -a; source .env; set +a

# 3. Validate compose file
echo "Validating docker-compose.prod.yml..."
docker compose -f docker-compose.prod.yml config > /dev/null && \
  echo "✓ docker-compose.prod.yml valid"

# 4. Start only NEW services (don't restart existing infra)
echo ""
echo "Starting Temporal + Langfuse services..."
docker compose -f docker-compose.prod.yml up -d \
  temporal temporal-ui-prod langfuse

echo "Waiting for services to be ready..."
sleep 8

# 5. Health checks
echo ""
echo "Checking services..."

check() {
  local name="$1"; local port="$2"
  if nc -z localhost "$port" 2>/dev/null; then
    echo "  ✓ $name :$port"
  else
    echo "  ✗ $name :$port NOT READY"
  fi
}

check "temporal-prod"    7234
check "temporal-ui-prod" 8089
check "langfuse"         3001

echo ""
echo "══════════════════════════════════════════════════════════"
echo "Temporal UI:  http://localhost:8089"
echo "Langfuse UI:  http://localhost:3001"
echo "  Login:      admin@ontology_ai.local / sarthi-admin-pass"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "To start API + Worker:"
echo "  docker compose -f docker-compose.prod.yml up -d sarthi-api sarthi-worker"
echo ""
echo "══════════════════════════════════════════════════════════"
echo "✓ START COMPLETE"
echo "══════════════════════════════════════════════════════════"
