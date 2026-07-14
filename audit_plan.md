# OntologyAI Microservices Audit Report (Revised)

## Executive Summary

This audit maps the existing codebase to the 5 target microservices defined in the coding-agent prompt. The current codebase contains substantial capabilities but is organized as a **modular distributed application** rather than hardened microservices with explicit boundaries, contracts, and Kubernetes deployment assets.

---

## Current Service Mapping (Revised)

### 1. API Gateway (Go) ✅ Best Candidate

**Current State:** `apps/core/` - Monolithic Go service

| Capability | Status | Location |
|------------|--------|----------|
| Ingress (webhooks) | ✅ | `internal/api/handlers.go`, `internal/webhooks/` |
| Slack/Stripe/Razorpay/Telegram webhooks | ✅ | 11 webhook handlers |
| HTMX admin routes | ✅ | `internal/web/admin_handler.go` |
| Auth (JWT/GitHub OAuth) | ✅ | `internal/api/middleware.go`, `auth.go` |
| Health checks | ✅ | `/health`, `/health/details` |
| Redpanda publisher | ✅ | `internal/redpanda/client.go` |
| Docker image | ✅ | Multi-stage Alpine build |
| k8s manifests | ❌ | **MISSING** |

**Gap Analysis:**
- No rate limiting middleware
- No circuit breaker for external calls
- No IP allowlist for webhooks
- No structured OpenTelemetry tracing
- No k8s deployment manifests

**Readiness: 85%** - Best extraction candidate; edge-complete but needs K8s hardening.

---

### 2. Decision Engine (Python) ⚠️ Needs Extraction

**Current State:** Distributed across `src/guardian/`, `src/hitl/`, `src/activities/`

| Capability | Status | Location |
|------------|--------|----------|
| Guardian watchlist (16 patterns) | ✅ | `src/guardian/watchlist.py` |
| Guardian detector | ✅ | `src/guardian/detector.py` |
| HITL routing (3-tier) | ✅ | `src/hitl/manager.py` |
| Confidence scoring | ✅ | `src/hitl/confidence.py` |
| AlertDecision schema | ✅ | `src/schemas/guardian.py` |
| Redpanda publisher | ✅ | `src/events/redpanda.py` |
| Temporal activity | ✅ | `src/activities/run_guardian_watchlist.py` |

**Gap Analysis:**
- Decision logic woven into agent system - needs extraction to explicit service
- No explicit decision input/output API contracts
- No centralized decision-service module
- Missing unit tests for pattern detection
- Cross-agent collaboration choreography NOT fully implemented

**Readiness: 60%** - Domain logic exists but not yet an explicit service.

---

### 3. Memory Service (Python) 🔒 LOCKED: Neo4j + Graphiti

**Current State:** `src/memory/` - 5-layer architecture

| Capability | Status | Location |
|------------|--------|----------|
| Qdrant vector memory | ✅ | `src/memory/qdrant_ops.py` |
| **Neo4j + Graphiti** | 🔒 **LOCKED** | `src/memory/semantic.py` |
| PostgreSQL session/mission | ✅ | `src/session/context.py`, `mission_state.py` |
| Redis working memory | ✅ | `src/memory/working.py` |
| Redis Streams event bus | ✅ | `src/events/bus.py` |
| Tenant isolation | ✅ | All layers enforce tenant_id |
| Graceful fallback | ✅ | Returns empty on unavailability |

**🔒 Semantic Memory Decision Locked:**

| Mode | Technology | Config |
|------|------------|--------|
| **k3d Production-sim** | Neo4j 5.22+ + Graphiti | `NEO4J_URI=bolt://neo4j:7687` |
| **Lean Local Mode** | Fallback to Qdrant/Redis | When Neo4j unavailable |

**Graphiti + Neo4j Setup (from Context7):**
```python
from graphiti_core import Graphiti

client = Graphiti(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="password",
)
```

**Readiness: 75%** - Strong internals, semantic-store now locked to Neo4j/Graphiti.

---

### 4. Workflow Service (Python) ⚠️ Orchestration Not Microservice-Native

**Current State:** `src/worker.py`, `src/workflows/`

| Capability | Status | Location |
|------------|--------|----------|
| Temporal worker | ✅ | `src/worker.py` (8 workflows, 9 activities) |
| PulseWorkflow | ✅ | `src/workflows/pulse_workflow.py` |
| InvestorWorkflow | ✅ | `src/workflows/investor_workflow.py` |
| Retry policies | ✅ | All workflows have exponential backoff |
| APScheduler fallback | ✅ | `src/scheduler/sarthi_scheduler.py` (dev only) |

**Gap Analysis:**
- Workflows are in same module as agents - needs package separation
- Event-based cross-agent collaboration NOT fully documented/implemented
- Service boundary + inter-service choreography NOT production-like
- k8s manifests for Temporal deployment needed

**Audit-and-plan says:** "cross-agent collaboration was undocumented or unimplemented"

**Readiness: 70%** - Temporal assets exist, but orchestration not yet fully microservice-native.

---

### 5. Delivery Service (Python) ⚠️ Needs Boundary Extraction

**Current State:** `src/integrations/slack.py`, `src/orchestration/`

| Capability | Status | Location |
|------------|--------|----------|
| Slack webhook delivery | ✅ | `src/integrations/slack.py` |
| Block Kit formatting | ✅ | `format_slack_blocks()` |
| Temporal activity | ✅ | `src/activities/send_slack_message.py` |
| Telegram fallback | ✅ | `src/integrations/slack.py` |
| Modal handling | ✅ | `src/integrations/slack_client.py` |

**Gap Analysis:**
- Delivery logic embedded in orchestration modules - needs explicit package
- No review queue abstraction
- No explicit delivery-service boundary

**Readiness: 70%** - Capability exists, but boundary and review-queue abstraction need extraction.

---

## Semantic Memory Decision 🔒 LOCKED

**Decision:** Neo4j + Graphiti for k3d production-sim path.

| Mode | Technology | Rationale |
|------|------------|-----------|
| **k3d Production-sim** | Neo4j 5.22+ + Graphiti | Temporal graph, episodic edges, better interview story |
| **Lean Local Mode** | Fallback to Qdrant + Redis | For daily development on 16GB machine |

This aligns with Context7 documentation and coding prompt: "Keep and/or restore these architectural choices: ... Neo4j for vector memory."

**Graphiti Configuration:**
```yaml
# docker-compose.v3.yml addition
graphiti:
  image: zepai/graphiti:latest
  environment:
    - NEO4J_URI=bolt://neo4j:7687
    - NEO4J_USER=neo4j
    - NEO4J_PASSWORD=sarthi
```

---

## Gap Summary: What's Missing

### Architecture
- [ ] 5 services with explicit ownership boundaries
- [ ] Per-service Docker images (only Go has Dockerfile)
- [ ] Per-service k8s manifests
- [ ] Service contracts documented and tested

### Data Separation
- [ ] One Postgres cluster with logical separation per service
- [ ] Cross-service reads through API/events only
- [ ] Tenant isolation tests for all services

### Eventing
- [ ] Redpanda topics for all inter-service communication
- [ ] Event schema contracts documented

### Observability
- [ ] OpenTelemetry traces across services
- [ ] Grafana dashboards per service
- [ ] Structured logs with correlation IDs

### Testing
- [ ] Unit tests for decision engine patterns
- [ ] Contract tests for service APIs
- [ ] k3d smoke tests
- [ ] E2E: webhook → event → workflow → decision → delivery

---

## Recommended Extraction Order

1. **Create k8s manifests for Go API Gateway** (simplest start)
2. **Lock semantic memory decision:** Neo4j/Graphiti for k3d, fallback for local
3. **Create Dockerfiles for each Python service**
4. **Define event contracts first**
5. **Extract decision-engine** (centralize guardian/hitl logic)
6. **Extract memory-service** (wrap Qdrant/Postgres behind service)
7. **Extract workflow-service** (separate Temporal worker)
8. **Extract delivery-service** (move Slack integration)
9. **Add observability**
10. **Create Helm charts** for k3d deployment

---

## Quick Wins

1. Add k8s manifests to `apps/core/k8s/`
2. Add rate limiting middleware to Go webhooks
3. Add unit tests for guardian pattern detection
4. Create separate Dockerfiles for Python services
5. Add OpenTelemetry tracing to Go handlers