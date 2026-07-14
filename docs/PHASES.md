# OntologyAI Phase Execution Plan

**Version:** 4.1  
**Date:** March 2026

---

## Complete Phase Execution Order

### PHASE 0 ✅ — IterateSwarm Base Infra

**Status:** COMPLETE

- Temporal, Redpanda, PostgreSQL, Qdrant running
- Go Fiber API gateway
- Python AI worker skeleton
- gRPC bridge Go ↔ Python

---

### PHASE 1 ✅ — OntologyAI Pivot

**Status:** COMPLETE

- Schemas updated for OntologyAI
- Agents v1 (Memory, Trigger, Supervisor)
- Workflows (SignalConsumer, Onboarding)
- Telegram integration skeleton

---

### PHASE 2 🔨 — NOW: LLM Unification + Graph Memory

**Target:** 125 tests passing

#### Tasks

- [ ] `apps/ai/src/config/llm.py` — universal LLM client factory
- [ ] `apps/ai/src/config/langfuse.py` — observability setup
- [ ] Grep-replace `AzureOpenAI` everywhere → `get_llm_client()`
- [ ] `graph_memory_agent.py` → use `OpenAIClient` (not `AzureOpenAIClient`)
- [ ] `docker-compose.yml`: append neo4j + langfuse + sandbox services
- [ ] `make up` → `make health` → all 12 containers green
- [ ] Migration 007 applied (Neo4j + Graphiti schema)
- [ ] `make test-unit` → 125 green
- [ ] `git tag v2.0.0`

**Exit Criteria:**
- Universal OpenAI SDK enforced everywhere
- Neo4j + Graphiti running and tested
- 125 tests passing

---

### PHASE 3 🔲 — Tier 1 + Core Services

**Target:** 160 tests passing

#### Tasks

- [ ] `tone_filter.py` — DSPy-compiled, jargon validator
- [ ] `dspy_signatures/` — all 4 signatures (CFO, BI, Risk, ToneFilter)
- [ ] `dspy_compiled/` — compiled weights, git-tracked
- [ ] `telegram_notifier.py` — inline keyboard HITL
- [ ] `apps/core/telegram.go` — webhook + sendDM
- [ ] `schemas/findings.py` — all Pydantic contracts v4.1
- [ ] `chief_of_staff_agent.py`
- [ ] `ingestion_agent.py`
- [ ] `bank_statement_parser.py`
- [ ] `apps/sandbox/` — Dockerfile + server.py
- [ ] `make test-unit` → 160 green
- [ ] `git tag v2.3.0`

**Exit Criteria:**
- ToneFilter jargon-free output enforced
- Telegram HITL with inline keyboards working
- Bank parser supports HDFC/ICICI/SBI/Axis/Kotak
- Sandbox isolated execution working

---

### PHASE 4 🔲 — Tier 2 Intelligence

**Target:** 195 tests passing

#### Tasks

- [ ] `cfo_agent.py`
- [ ] `risk_agent.py` + compliance_calendar seeded (India 2026)
- [ ] `bi_agent.py`
- [ ] `market_intel_agent.py` + crawler_agent expanded
- [ ] `jurisdiction_agent.py` [NEW v4.1]
- [ ] `fundraise_readiness_agent.py` [NEW v4.1]
- [ ] `tax_intelligence_agent.py` [NEW v4.1]
- [ ] `grant_credit_agent.py` [NEW v4.1]
- [ ] `make test-unit` → 195 green
- [ ] `git tag v3.0.0`

**Exit Criteria:**
- All Tier 2 intelligence agents operational
- Jurisdiction detection working for India
- Grant detection finding real opportunities

---

### PHASE 5 🔲 — Tier 3 Operations + HITL

**Target:** 20/20 E2E tests green

#### Tasks

- [ ] `finance_ops_agent.py`
- [ ] `accounting_ops_agent.py` [NEW v4.1]
- [ ] `legal_ops_agent.py`
- [ ] `hr_ops_agent.py`
- [ ] `revops_agent.py`
- [ ] `admin_ops_agent.py`
- [ ] `procurement_ops_agent.py` [NEW v4.1]
- [ ] `cap_table_ops_agent.py` [NEW v4.1]
- [ ] `grant_ops_agent.py` [NEW v4.1]
- [ ] `business_os_workflow.go` — full, with Continue-As-New
- [ ] `onboarding_workflow.go`
- [ ] `weekly_checkin_workflow.go`
- [ ] HITL gate tested end-to-end: Telegram → approve → execute
- [ ] `make test-e2e` → 20/20 green
- [ ] `git tag v3.5.0`

**Exit Criteria:**
- All Tier 3 ops agents executing tasks autonomously
- HITL gate working: LOW/MEDIUM/HIGH risk flows
- Go Temporal workflows durable and tested

---

### PHASE 6 🔲 — Production Hardening + Evals

**Target:** ≥13/15 LLM evals green

#### Tasks

- [ ] DSPy eval suite — 15 evals, ≥13/15 must pass
- [ ] Circuit breaker — all external calls
- [ ] Rate limiter — Telegram, Razorpay, Zoho, Crawl4AI
- [ ] `.github/workflows/ci.yml` — unit + lint (no LLM)
- [ ] `.github/workflows/e2e.yml` — manual trigger, full stack
- [ ] All Langfuse traces < 8s p95 latency
- [ ] `make test-llm` → ≥13/15 green
- [ ] `git tag v4.0-alpha`

**Exit Criteria:**
- Production resilience patterns in place
- DSPy eval score ≥ 0.75 maintained
- Langfuse observability complete

---

### PHASE 7 🔲 — v4.0.0: THE REAL MILESTONE

**Target:** One real founder onboarded and reporting value

#### Tasks

- [ ] One real founder signs up via Telegram
- [ ] Completes onboarding (6 questions, < 10 minutes)
- [ ] Uploads a real bank statement (any Indian bank)
- [ ] Receives a real CFO finding (no jargon, ₹ amounts)
- [ ] Approves one action via Telegram inline keyboard
- [ ] Reports: "This saved me time"

**THAT is v4.0.0. Not before.**

**Exit Criteria:**
- Real human value delivered
- Founder testimonial captured
- `git tag -a v4.0.0 -m "OntologyAI v4.0.0 — Production Ready"`

---

### PHASE 8 🔲 — v4.1.0: Global Expansion

**Target:** First non-India founder onboarded

#### Tasks

- [ ] Jurisdiction agent live for US + UK + EU
- [ ] Grant agent: SBIR, Innovate UK, Horizon Europe
- [ ] Tax intelligence: QSBS, R&D credits
- [ ] Fundraise readiness agent live
- [ ] First non-India founder onboarded
- [ ] `git tag -a v4.1.0 -m "OntologyAI v4.1.0 — Global"`

**Exit Criteria:**
- Multi-jurisdiction compliance working
- Global grant detection operational
- First US/UK/EU founder reporting value

---

## Test Count Summary

| Phase | Target | Cumulative |
|-------|--------|------------|
| Phase 2 | 125 tests | 125 |
| Phase 3 | 160 tests | 160 |
| Phase 4 | 195 tests | 195 |
| Phase 5 | 20 E2E | 215 |
| Phase 6 | ≥13/15 LLM evals | 230 |
| Phase 7 | 1 real founder | 1 |
| Phase 8 | 1 global founder | 1 |

---

## Current Status

**Phase:** 2 (IN PROGRESS)

**Completed:**
- ✅ Phase 0: Base infra
- ✅ Phase 1: OntologyAI pivot
- ✅ Test fixes: 117 passing, 10 skipped (GraphMemoryAgent asyncio)

**Next:**
- LLM unification (`get_llm_client()` everywhere)
- Graphiti + Neo4j integration complete
- 125 tests target

---

**Document Version:** 4.1  
**Last Updated:** March 2026
