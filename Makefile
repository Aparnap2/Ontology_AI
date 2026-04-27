# IterateSwarm Makefile
# Quick commands for development and operations

.PHONY: help up down status test build clean proto verify deps logs restart prod prod-up prod-down prod-logs

# Default target
help:
	@echo "IterateSwarm - Go AI ChatOps Platform"
	@echo ""
	@echo "Commands:"
	@echo "  up          Start all services (Docker + apps)"
	@echo "  down        Stop all Docker services"
	@echo "  status      Check service status"
	@echo "  test        Run all tests (Go only)"
	@echo "  build       Build all applications"
	@echo "  build-py    Build Python AI worker"
	@echo "  clean       Clean build artifacts"
	@echo "  proto       Generate protobuf code"
	@echo "  verify      Run E2E verification script"
	@echo "  deps        Install dependencies"
	@echo "  logs        Tail logs from all services"
	@echo "  prod        Build production Docker images"
	@echo "  prod-up     Start production stack"
	@echo "  prod-down   Stop production stack"
	@echo "  v3-up      Start V3 minimal stack"
	@echo "  v3-down    Stop V3 stack"

# Start all infrastructure and applications
up:
	@echo "Starting IterateSwarm..."
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	sleep 10
	@echo "Infrastructure started"

# Check service status
status:
	@echo "Service Status:"
	docker-compose ps

# Run all tests
test:
	@echo "Running tests..."
	cd apps/core && go test ./...

# Build all applications
build:
	@echo "Building applications..."
	cd apps/core && go build -o bin/server ./cmd/server && go build -o bin/worker ./cmd/worker
	@echo "Built: apps/core/bin/server"
	@echo "Built: apps/core/bin/worker"

# Clean build artifacts
clean:
	@echo "Cleaning..."
	cd apps/core && rm -rf bin/

# Generate protobuf code
proto:
	@echo "Generating protobuf code..."
	docker run --rm -v $$(pwd):/workspace -w /workspace bufbuild/buf:latest generate
	@echo "Protobuf code generated"

# Run E2E verification
verify:
	@echo "Running E2E verification..."
	./scripts/verify_system.sh

# Install dependencies
deps:
	@echo "Installing dependencies..."
	cd apps/core && go mod download

# Tail logs from all services
logs:
	@echo "Showing logs (Ctrl+C to exit)..."
	docker-compose logs -f

# Full restart
restart: down up
	@echo "Full restart complete"

# Security Tests
security-test:
	@echo "🔒 Running security test suite..."
	@echo ""
	@echo "[1/5] Go race detector tests..."
	cd apps/core && go test -race -count=3 ./internal/security/... -timeout 3m || true
	@echo ""
	@echo "[2/5] Security unit tests..."
	cd apps/core && go test ./internal/security/... -v -timeout 2m || true
	@echo ""
	@echo "[3/5] Python type safety tests..."
	cd apps/ai && uv run pytest tests/security/ -v || true
	@echo ""
	@echo "✅ Security tests complete"

security-race:
	@echo "🔍 Running Go race detector..."
	cd apps/core && go test -race -count=3 ./... -timeout 5m

security-lint:
	@echo "🔍 Running static analysis..."
	cd apps/core && go vet ./...
	@echo "✅ Linting complete"

# Pre-interview security sweep
security-full: security-race security-test security-lint
	@echo ""
	@echo "╔══════════════════════════════╗"
	@echo "║  SECURITY SWEEP COMPLETE ✅  ║"
	@echo "╚══════════════════════════════╝"

# ===========================================
# Demo Preparation Commands
# ===========================================

.PHONY: demo demo-seed demo-reset demo-feedback demo-health test-all test-e2e

demo:
	@echo "🚀 Starting IterateSwarm OS..."
	docker start iterateswarm-postgres iterateswarm-temporal iterateswarm-qdrant 2>/dev/null || docker compose up -d
	@echo "⏳ Waiting 15s for services..."
	@sleep 15
	$(MAKE) demo-seed
	@echo ""
	@echo "✅ Demo ready!"
	@echo "┌──────────────────────────────────────────┐"
	@echo "│  Admin Panel:  http://localhost:3000/admin│"
	@echo "│  SigNoz:       http://localhost:3301      │"
	@echo "│  Temporal UI:  http://localhost:8088      │"
	@echo "│  Qdrant UI:    http://localhost:6333      │"
	@echo "└──────────────────────────────────────────┘"

demo-seed:
	@echo "🌱 Seeding Qdrant with example issues..."
	cd apps/ai && uv run python scripts/seed_qdrant.py || echo "⚠️  Seed script failed (may need sentence-transformers)"
	@echo "✅ Seeded example issues"

demo-reset:
	@echo "🗑  Resetting all data..."
	docker stop iterateswarm-postgres iterateswarm-temporal iterateswarm-qdrant 2>/dev/null || true
	docker compose down -v
	@echo "✅ Reset complete. Run 'make demo' to restart."

demo-feedback:
	@if [ -z "$(TEXT)" ]; then echo "Usage: make demo-feedback TEXT='your feedback'"; exit 1; fi
	@curl -s -X POST http://localhost:3000/webhooks/discord \
		-H "Content-Type: application/json" \
		-d '{"text":"$(TEXT)","source":"discord","user_id":"demo-user","channel_id":"demo"}' \
		| python3 -m json.tool

demo-health:
	@echo "=== Infrastructure Health Check ==="
	@docker exec iterateswarm-postgres pg_isready -U iterateswarm -d iterateswarm > /dev/null && echo "✅ PostgreSQL" || echo "❌ PostgreSQL"
	@curl -sf http://localhost:8088/api/health > /dev/null && echo "✅ Temporal" || echo "❌ Temporal"
	@curl -sf http://localhost:6333/health > /dev/null && echo "✅ Qdrant" || echo "❌ Qdrant"
	@curl -sf http://localhost:3000/api/health > /dev/null && echo "✅ Go API" || echo "❌ Go API"

test-all:
	@echo "=== Running All Tests ==="
	@echo ""
	@echo "🐍 Python tests..."
	cd apps/ai && uv run pytest tests/ -v --tb=short -q || true
	@echo ""
	@echo "🔹 Go tests (with race detection)..."
	cd apps/core && go test -race -count=1 ./... -v || true

test-e2e:
	@echo "=== Running E2E Tests ==="
	@echo ""
	$(MAKE) demo-health
	@echo ""
	@echo "🧪 Running E2E workflow tests (requires all services)..."
	cd apps/ai && uv run pytest tests/test_e2e_workflow.py -v -s -m e2e --timeout=300 || true

# ===========================================
# Health Check
# ===========================================

.PHONY: demo-health
demo-health:
	@echo "════════════════════════════════════════"
	@echo "  IterateSwarm OS — Infrastructure Check"
	@echo "════════════════════════════════════════"
	@echo ""
	@echo "--- Docker Containers ---"
	@docker inspect --format \
	  '  {{slice .Name 1 | printf "%-35s"}} {{.State.Status}}' \
	  iterateswarm-postgres \
	  iterateswarm-redpanda \
	  iterateswarm-qdrant \
	  iterateswarm-temporal \
	  iterateswarm-temporal-ui \
	  iterateswarm-temporal-admin \
	  iterateswarm-worker \
	  iterateswarm-consumer \
	  2>&1
	@echo ""
	@echo "--- Service Endpoints ---"
	@docker exec iterateswarm-postgres \
	  pg_isready -U iterateswarm -q \
	  && printf "  %-35s %s\n" "PostgreSQL :5432" "✅ accepting connections" \
	  || printf "  %-35s %s\n" "PostgreSQL :5432" "❌ not ready"
	@curl -sf http://localhost:6333/healthz > /dev/null \
	  && printf "  %-35s %s\n" "Qdrant :6333" "✅ up" \
	  || printf "  %-35s %s\n" "Qdrant :6333" "❌ down"
	@docker exec iterateswarm-temporal-admin \
	  temporal operator namespace describe default --address iterateswarm-temporal:7233 > /dev/null 2>&1 \
	  && printf "  %-35s %s\n" "Temporal :7233" "✅ namespace:default ready" \
	  || printf "  %-35s %s\n" "Temporal :7233" "❌ not ready"
	@curl -sf http://localhost:8088 > /dev/null \
	  && printf "  %-35s %s\n" "Temporal UI :8088" "✅ up" \
	  || printf "  %-35s %s\n" "Temporal UI :8088" "❌ down"
	@curl -sf http://localhost:3301 > /dev/null \
	  && printf "  %-35s %s\n" "SigNoz :3301" "✅ up" \
	  || printf "  %-35s %s\n" "SigNoz :3301" "⚠️  optional (not installed)"
	@curl -sf http://localhost:3000/health > /dev/null \
	  && printf "  %-35s %s\n" "Go API :3000" "✅ up" \
	  || printf "  %-35s %s\n" "Go API :3000" "⚠️  run: cd apps/core && go run cmd/server/main.go"
	@nc -zv localhost 50051 > /dev/null 2>&1 \
	  && printf "  %-35s %s\n" "Python gRPC :50051" "✅ up" \
	  || printf "  %-35s %s\n" "Python gRPC :50051" "⚠️  run: cd apps/ai && uv run python -m src.grpc_server"
	@echo ""
	@echo "--- Redpanda Topics ---"
	@docker exec iterateswarm-redpanda \
	  rpk topic list 2>/dev/null \
	  && echo "  ✅ Redpanda cluster reachable" \
	  || echo "  ⚠️  Redpanda not responding"
	@echo "════════════════════════════════════════"

# ───────────────────────────────────────────────────────
# Production Build Targets
# ───────────────────────────────────────────────────────

# Build production Docker images
prod:
	@echo "Building production Docker images..."
	@echo "  Building Go Gateway..."
	cd apps/core && CGO_ENABLED=0 GOOS=linux go build -o bin/server ./cmd/server
	@echo "  Building Python AI Worker..."
	cd apps/ai && uv build --wheel
	@echo "Production build complete"

# Start production stack
prod-up:
	@echo "Starting production stack..."
	docker-compose -f docker-compose.prod.yml up -d
	@echo "Production services started"

# Start V3 minimal stack
v3-up:
	@echo "Starting V3 minimal stack..."
	docker-compose -f docker-compose.v3.yml up -d
	@echo "V3 services started"

# Stop V3 stack
v3-down:
	@echo "Stopping V3 stack..."
	docker-compose -f docker-compose.v3.yml down

# Status of V3 stack
v3-status:
	@echo "V3 Stack Status:"
	-docker-compose -f docker-compose.v3.yml ps

# Stop production stack
prod-down:
	@echo "Stopping production stack..."
	docker-compose -f docker-compose.prod.yml down

# Tail production logs
prod-logs:
	@echo "Tailing production logs..."
	docker-compose -f docker-compose.prod.yml logs -f
