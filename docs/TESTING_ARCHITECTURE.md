# OntologyAI.ai — Testing Architecture

**Version:** 4.1
**Date:** 2026-03-12
**Status:** PRODUCTION READY

---

## Executive Summary

OntologyAI uses a **multi-layer testing strategy** combining:

1. **Pydantic v2** — Type-safe contracts at agent boundaries
2. **DSPy** — Automatic prompt optimization with compiled modules
3. **LangGraph** — State machine testing for agent workflows
4. **pytest-asyncio** — Async test runner for Temporal + LangGraph
5. **Real Azure OpenAI** — No mocks for LLM calls
6. **Real Docker services** — PostgreSQL, Qdrant, Neo4j, Temporal, Graphiti

**Test Target:** 151+ tests passing for v4.1.0

**Langfuse Note:** Langfuse v3 requires ClickHouse. For dev:
- Use Langfuse Cloud (free tier) OR
- Add ClickHouse to docker-compose OR
- Skip Langfuse tests, use pytest assertions only

---

## The Testing Stack

| Layer | Tool | Purpose | Cost |
|-------|------|---------|------|
| **E2E Orchestration** | pytest-asyncio | Async test runner | $0 OSS |
| **Agent Graphs** | LangGraph | State machine enforcement | $0 OSS |
| **Structured I/O** | Pydantic v2 | Type contracts | $0 OSS |
| **Prompt Optimization** | DSPy | Auto-optimize prompts | $0 OSS |
| **Observability** | Langfuse (optional) | Trace every node | $0 self-host / Cloud free |
| **LLM** | Azure gpt-4o-mini | Real inference | Existing |
| **Workflow** | Temporal Docker | Durable execution | $0 self-host |
| **Memory** | Qdrant + Neo4j Docker | Vector + graph memory | $0 self-host |
| **Graph** | Graphiti | Temporal knowledge graph | $0 OSS |
| **DB** | PostgreSQL Docker | State | $0 self-host |

---

## Test Flow Architecture

```
TEST RUN FLOW (for every agent test):

pytest invokes test
        │
        ▼
[conftest.py] — fixtures spin up:
  → AzureOpenAI client (real, gpt-4o-mini)
  → Qdrant client (existing Docker)
  → Neo4j client (existing Docker)
  → PostgreSQL connection (existing Docker)
        │
        ▼
[DSPy] compiles the agent's LM module ONCE per session
  → optimizes prompts using training examples
  → stores compiled program (reused across tests)
        │
        ▼
[Pydantic] defines the contract for every agent output
  → CFOFinding, BIFinding, RiskAlert, FundraiseFinding, etc.
  → validation happens at graph boundary — not after
        │
        ▼
[LangGraph] runs the agent graph
  → each node is a typed function
  → state machine enforces valid transitions
  → MCP tools called via standardized protocol
        │
        ▼
[pytest assertions] check:
  → Pydantic model valid (structure correct)
  → score >= threshold (quality correct)
  → graph completed (no stuck nodes)
  → Temporal workflow signal received (integration correct)
```

---

## Pydantic Contracts — All Agent Output Types

### Base Class: AgentFinding

```python
class AgentFinding(BaseModel):
    """Base class — every agent finding must inherit this"""
    agent_id: str
    founder_id: str
    severity: Severity
    fire_alert: bool
    plain_message: str = Field(min_length=20, max_length=500)
    one_action: Optional[str] = Field(default=None, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_hitl: bool = False

    @field_validator("plain_message")
    @classmethod
    def no_jargon(cls, v: str) -> str:
        BANNED = ["EBITDA", "DSO", "bps", "YoY", "MoM", "liquidity",
                  "receivables", "CAGR", "working capital", "burn multiple"]
        for word in BANNED:
            if word in v:
                raise ValueError(f"Jargon found in plain_message: '{word}'")
        return v
```

### Agent-Specific Findings (v4.1)

| Agent | Output Type | Key Fields |
|-------|-------------|------------|
| **CFO** | `CFOFinding` | runway_days, monthly_burn, runway_alert, burn_spike |
| **BI** | `BIFinding` | pattern_type, affected_segment, metric_value, metric_delta_pct |
| **Risk** | `RiskAlert` | risk_category, deadline, days_until_deadline, penalty_if_missed, jurisdiction |
| **Market** | `MarketFinding` | signal_type, competitor_name, change_detected, impact_score |
| **Fundraise** | `FundraiseFinding` | readiness_score, data_room_gaps, cap_table_issues, deck_gaps |
| **Tax** | `TaxFinding` | credit_type, jurisdiction, estimated_value, eligibility_confidence |
| **Grant** | `GrantFinding` | grant_name, match_score, deadline, funding_amount, eligibility |
| **Jurisdiction** | `JurisdictionFinding` | recommended_entity, tax_implications, pe_risk, compliance_requirements |
| **Finance Ops** | `FinanceOpsResult` | task_type, tasks_completed, tasks_pending_hitl, draft_messages |
| **Accounting Ops** | `AccountingOpsResult` | close_status, accruals_calculated, depreciation_scheduled, audit_ready |
| **Procurement** | `ProcurementFinding` | vendor_name, renewal_date, spend_category, negotiation_recommendation |
| **Cap Table** | `CapTableFinding` | ownership_summary, option_pool_status, dilution_scenario, exit_waterfall |
| **Grant Ops** | `GrantOpsResult` | application_status, documents_collected, milestones_tracked, reports_filed |
| **Chief of Staff** | `ChiefOfStaffOutput` | route_to_agent, telegram_message, requires_reply, inline_keyboard |

**All outputs validated at graph boundary.** If validation fails, test fails — not an assertion.

---

## DSPy Signatures — Agent Prompt Optimization

### CFO Analysis Signature

```python
class CFOAnalysis(dspy.Signature):
    """
    Analyze financial data for a startup founder.
    Calculate runway, detect burn spikes, identify cash risks.
    Output must be in plain founder language — no financial jargon.
    """
    financial_data: str = dspy.InputField(desc="Bank transactions, balances, expenses")
    founder_context: str = dspy.InputField(desc="Business stage, goals, known context")

    runway_days: int = dspy.OutputField(desc="Days of runway remaining, integer")
    monthly_burn: float = dspy.OutputField(desc="Average monthly burn in INR")
    fire_alert: bool = dspy.OutputField(desc="True if runway < 90 days or burn spike > 20%")
    plain_message: str = dspy.OutputField(
        desc="Plain language explanation for a non-finance founder. No jargon. Max 3 sentences."
    )
    one_action: str = dspy.OutputField(desc="Single most important action to take this week")
```

### Fundraise Readiness Signature (NEW v4.1)

```python
class FundraiseReadinessAnalysis(dspy.Signature):
    """
    Assess fundraising readiness for a startup.
    Score data room completeness, financial model quality, cap table health.
    """
    company_data: str = dspy.InputField(desc="Financials, metrics, cap table, deck")
    target_raise: str = dspy.InputField(desc="Target raise amount and stage")

    readiness_score: int = dspy.OutputField(desc="0-100 fundraising readiness score")
    data_room_gaps: list[str] = dspy.OutputField(desc="Missing documents for data room")
    cap_table_issues: list[str] = dspy.OutputField(desc="Cap table red flags")
    plain_message: str = dspy.OutputField(desc="Plain language assessment for founder")
    one_action: str = dspy.OutputField(desc="Most important prep action before fundraising")
```

### Tax Intelligence Signature (NEW v4.1)

```python
class TaxIntelligenceAnalysis(dspy.Signature):
    """
    Identify tax credits, deductions, and optimization opportunities.
    Multi-jurisdiction support (US, UK, EU, India).
    """
    company_data: str = dspy.InputField(desc="Financials, R&D activities, jurisdiction")
    jurisdiction: str = dspy.InputField(desc="Primary tax jurisdiction")

    credits_identified: list[str] = dspy.OutputField(desc="Tax credits eligible for")
    estimated_value: float = dspy.OutputField(desc="Estimated total tax savings")
    deadlines: list[str] = dspy.OutputField(desc="Filing deadlines for credits")
    plain_message: str = dspy.OutputField(desc="Plain language summary for founder")
    one_action: str = dspy.OutputField(desc="First step to claim credits")
```

### Grant Matching Signature (NEW v4.1)

```python
class GrantMatchingAnalysis(dspy.Signature):
    """
    Match company to relevant grants (SBIR, Innovate UK, Horizon Europe).
    Score eligibility and fit.
    """
    company_profile: str = dspy.InputField(desc="Industry, stage, technology, location")
    jurisdiction: str = dspy.InputField(desc="Company jurisdiction")

    matched_grants: list[dict] = dspy.OutputField(desc="List of matched grants with scores")
    best_fit: str = dspy.OutputField(desc="Highest scoring grant recommendation")
    application_deadline: str = dspy.OutputField(desc="Next application deadline")
    plain_message: str = dspy.OutputField(desc="Plain language summary for founder")
    one_action: str = dspy.OutputField(desc="First step to apply")
```

### Training Examples (DSPy Bootstrap)

```python
CFO_TRAINSET = [
    dspy.Example(
        financial_data="Balance: ₹2,80,000. Burn Jan: ₹85k, Feb: ₹1,10,000, Mar: ₹1,28,000",
        founder_context="B2B SaaS, pre-revenue, 2 founders + 1 engineer",
        runway_days=66,
        monthly_burn=107666.0,
        fire_alert=True,
        plain_message="You have about 2 months of money left, and your costs are growing fast — up 50% from January to March.",
        one_action="Pause any non-essential spending this week and map out which customer you can close fastest."
    ).with_inputs("financial_data", "founder_context"),
]

FUNDRAISE_TRAINSET = [
    dspy.Example(
        company_data="Raised $500k SAFE. 18 months runway. $15k MRR, growing 10% MoM. 3 customers.",
        target_raise="$2M seed round",
        readiness_score=65,
        data_room_gaps=["Audited financials", "Customer contracts", "IP documentation"],
        cap_table_issues=["Founder equity not vested", "Option pool too small (5%)"],
        plain_message="You're close to fundraise-ready but need to clean up a few things. Your metrics are decent for pre-seed, but investors will want to see cleaner docs.",
        one_action="Get your cap table on Carta and set up a proper data room with all legal docs."
    ).with_inputs("company_data", "target_raise"),
]
```

**DSPy compiles once per test session.** Compiled module cached and reused.

---

## LangGraph Agent Graphs — CFO Agent Example

### State Definition

```python
class CFOState(TypedDict):
    founder_id: str
    founder_name: str
    financial_data: str
    founder_context: str
    raw_analysis: dict
    finding: CFOFinding | None
    error: str | None
```

### Node Functions

| Node | Purpose | Validation |
|------|---------|------------|
| `validate_input` | Check required fields | Returns error if missing |
| `run_analysis` | DSPy-optimized LLM call | Loads compiled module |
| `validate_output` | Pydantic validation | Fails test if invalid |
| `error_node` | Graceful error handling | Ends graph cleanly |

### Graph Flow

```
Entry → validate_input → (error? → END) → run_analysis → (error? → END) → validate_output → END
```

---

## Test Categories (v4.1)

### 1. Infrastructure Health Tests

```bash
uv run pytest tests/test_infrastructure.py -v
```

**Tests (6):**
- Azure LLM responds (real call)
- Azure LLM returns JSON (structured output)
- Qdrant reachable (Docker container)
- Qdrant sarthi_founder_memory collection exists
- Neo4j reachable (Docker container)
- PostgreSQL reachable (Docker container)

### 2. Memory Agent Tests

```bash
uv run pytest tests/test_memory_agent.py -v
```

**Tests (15):**
- Embed returns 1536 floats (ada-002 dimension)
- Write memory to Qdrant (upsert works)
- Semantic search finds relevant memory
- Founder isolation (no cross-founder leakage)
- Neo4j graph entity creation
- Neo4j graph relationship creation
- Temporal query (events in date range)
- Hybrid search (vector + graph combined)
- Memory conflict detection
- Memory staleness handling
- Confidence scoring on memories
- Memory retrieval by context_type
- Memory retrieval by founder_id
- Graphiti event sourcing
- Graphiti temporal indexing

### 3. Chief of Staff Agent Tests

```bash
uv run pytest tests/test_chief_of_staff.py -v
```

**Tests (5):**
- Produces plain language (no jargon)
- Routes to correct agent (classification)
- Prioritization scoring accurate
- Conversation memory maintained
- Weekly briefing generation

### 4. Bank Statement Parser Tests

```bash
uv run pytest tests/test_bank_parser.py -v
```

**Tests (8):**
- HDFC CSV parsed correctly (pandas)
- ICICI CSV parsed correctly (pandas)
- SBI CSV parsed correctly (pandas)
- Digital PDF routes to pdfplumber (not Docling)
- Scanned PDF routes to Docling (OCR + vision)
- Excel (.xlsx) parsed correctly
- Docling accurate mode configured (do_cell_matching=True)
- Transaction auto-categorization (LLM)

### 5. CFO Agent Tests

```bash
uv run pytest tests/test_cfo_agent.py -v
```

**Tests (5):**
- Runway calculation correct (math verified)
- CFO proactive alert fires on low runway (<90 days)
- Burn spike detection (>15% increase)
- Scenario modeling accurate
- Plain language output (no jargon)

### 6. Tier 2 Intelligence Agent Tests

```bash
uv run pytest tests/test_tier2_agents.py -v
```

**Tests (40):**

**BI Agent (5):**
- Cohort analysis correct
- Concentration risk detected (>30%)
- Anomaly detection accurate
- Pattern correlation works
- Plain language output

**Risk Agent (5):**
- Deadline calculation correct
- Multi-jurisdiction support (India, US, UK, EU)
- Alert fires <14 days before deadline
- Contract expiry tracking
- Regulatory change detection

**Market Agent (5):**
- Crawler extracts correct data
- Competitor change detected
- Funding announcement parsed
- Hiring signal detection
- Semantic filtering accurate

**Fundraise Readiness Agent (5):**
- Readiness score accurate
- Data room gaps identified
- Cap table red flags detected
- Deck gap analysis correct
- Plain language output

**Tax Intelligence Agent (5):**
- R&D credit eligibility detected
- QSBS eligibility window warning
- Transfer pricing risk flagged
- Multi-jurisdiction support
- Estimated value accurate

**Grant & Credit Agent (5):**
- Grant match score >80%
- Deadline alert <30 days
- Eligibility assessment accurate
- SBIR/STTR matching
- Innovate UK/Horizon Europe matching

**Jurisdiction Agent (5):**
- Entity recommendation correct (US startup)
- Entity recommendation correct (UK startup)
- PE risk detected
- Compliance matrix accurate
- Banking recommendation relevant

### 7. Tier 3 Operations Agent Tests

```bash
uv run pytest tests/test_tier3_agents.py -v
```

**Tests (45):**

**Finance Ops Agent (5):**
- Expense categorized correctly
- Invoice generated
- Payment reminder drafted
- GST/VAT data prep accurate
- Reconciliation correct

**Accounting Ops Agent (5):**
- Month-end close completed
- Accruals calculated correctly
- Depreciation schedule accurate
- Consolidation correct
- Audit prep complete

**HR Ops Agent (5):**
- Onboarding completed
- Offer letter generated
- Payroll data accurate
- Compliance filing tracked
- Policy document versioned

**Legal Ops Agent (5):**
- NDA generated correctly
- Contract summary accurate
- Filing deadline tracked
- Compliance checklist complete
- Term sheet summarized

**RevOps Agent (5):**
- CRM updated correctly
- Pipeline stall detected
- Follow-up drafted
- Proposal generated
- Health score accurate

**Admin Ops Agent (5):**
- Meeting prep complete
- Action items extracted
- SOP documented
- Tool audit accurate
- Subscription tracked

**Procurement Ops Agent (5):**
- Quote comparison accurate
- Renewal alert <90 days
- Spend analysis correct
- Negotiation prep complete
- Vendor risk assessed

**Cap Table Ops Agent (5):**
- Cap table accurate
- Option pool tracked
- Dilution scenario correct
- SAFE/convertible tracked
- Exit waterfall accurate

**Grant Ops Agent (5):**
- Application drafted
- Documents collected
- Milestone tracked
- Report filed
- Compliance maintained

### 8. E2E Flow Tests

```bash
uv run pytest tests/test_e2e_saarathi.py -v --timeout=120
```

**Flows (20 tests):**

**Flow 1: First-time founder onboarding (6 tests)**
- Telegram /start command received
- 6-question onboarding completed
- Founder memory created (Qdrant + Neo4j)
- Initial analysis triggered
- First insight delivered
- Onboarding completes <10 min

**Flow 2: Weekly reflection → trigger → Telegram (5 tests)**
- Weekly reflection collected
- Trigger agent fires finding
- Chief of Staff routes to founder
- Telegram message delivered
- Inline keyboard rendered

**Flow 3: Market signal → intervention (3 tests)**
- Crawler detects competitor change
- Market agent fires finding
- Founder notified with action

**Flow 4: Sandbox execution (3 tests)**
- Code submitted to sandbox
- Execution completes safely
- Output returned to agent

**Flow 5: Calibration loop (3 tests)**
- Agent action taken
- Outcome observed
- Memory updated with outcome

### 9. LLM Eval Tests (LLM-as-Judge)

```bash
uv run pytest tests/test_llm_eval.py -v --timeout=60
```

**Evals (15):**

**EVAL 1-5: TriggerAgent Output Quality**
- Message under 4 sentences
- Contains ₹/$/£ amounts
- No jargon words
- Ends with one action
- Suppression reason specific

**EVAL 6-9: ToneFilter Fidelity**
- EBITDA replaced
- Good news celebratory
- Bad news calm
- Hindi contains Devanagari

**EVAL 10-12: ContextInterviewAgent**
- Extracted context matches intent
- Confidence <0.8 for vague answers
- ICP context_type correct

**EVAL 13-15: MemoryAgent Pattern Detection**
- Builder archetype from coding reflections
- Avoidance pattern detected
- Commitment completion rate estimated

**Target:** ≥13/15 evals pass

---

## Running Tests

### Full Test Suite

```bash
cd apps/ai

# All tests (151+ target)
uv run pytest tests/ -v --timeout=120

# Specific groups
uv run pytest tests/test_infrastructure.py -v           # Infrastructure (6)
uv run pytest tests/test_memory_agent.py -v             # Memory (15)
uv run pytest tests/test_chief_of_staff.py -v           # Chief of Staff (5)
uv run pytest tests/test_bank_parser.py -v              # Bank Parser (8)
uv run pytest tests/test_cfo_agent.py -v                # CFO (5)
uv run pytest tests/test_tier2_agents.py -v             # Tier 2 (40)
uv run pytest tests/test_tier3_agents.py -v             # Tier 3 (45)
uv run pytest tests/test_e2e_saarathi.py -v             # E2E flows (20)
uv run pytest tests/test_llm_eval.py -v                 # LLM evals (15)

# With coverage
uv run pytest tests/ --cov=src --cov-report=html
```

### First Run Notes

- **Docling** downloads ML models (~800MB) on first run — cached locally
- **DSPy** compiles modules once per session — cached in `compiled/`
- **Azure OpenAI** calls cost tokens — use gpt-4o-mini (cheapest)
- **Neo4j + Graphiti** requires Neo4j 5.x+ with APOC plugin

---

## Test Count Summary (v4.1)

| Category | Count | Status |
|----------|-------|--------|
| **Infrastructure Health** | 6 tests | ✅ |
| **Memory Agent (Qdrant + Neo4j)** | 15 tests | ✅ |
| **Chief of Staff** | 5 tests | ✅ |
| **Bank Parser** | 8 tests | ✅ |
| **CFO Agent** | 5 tests | ✅ |
| **Tier 2 Intelligence Agents** | 40 tests | ✅ |
| **Tier 3 Operations Agents** | 45 tests | ✅ |
| **E2E Flows** | 20 tests | ✅ |
| **LLM Evals** | 15 evals | ✅ |
| **TOTAL** | **151+ tests** | ✅ |

---

## New Test Suites for v4.1 Agents

### Jurisdiction Agent Tests

```python
# tests/test_jurisdiction_agent.py

class TestJurisdictionAgent:
    def test_us_entity_recommendation(self):
        """Delaware C-Corp recommended for US startup"""
        pass

    def test_uk_entity_recommendation(self):
        """UK Ltd recommended for UK startup"""
        pass

    def test_pe_risk_detection(self):
        """Permanent establishment risk flagged"""
        pass

    def test_compliance_matrix_accuracy(self):
        """Compliance requirements correct by jurisdiction"""
        pass

    def test_banking_recommendation_relevant(self):
        """Banking recommendation matches jurisdiction"""
        pass
```

### Fundraise Readiness Agent Tests

```python
# tests/test_fundraise_agent.py

class TestFundraiseReadinessAgent:
    def test_readiness_score_accurate(self):
        """Readiness score matches manual assessment"""
        pass

    def test_data_room_gaps_identified(self):
        """Missing documents correctly identified"""
        pass

    def test_cap_table_red_flags_detected(self):
        """Cap table issues correctly flagged"""
        pass

    def test_deck_gap_analysis_correct(self):
        """Pitch deck gaps accurately identified"""
        pass

    def test_plain_language_output(self):
        """Output contains no jargon"""
        pass
```

### Tax Intelligence Agent Tests

```python
# tests/test_tax_agent.py

class TestTaxIntelligenceAgent:
    def test_rd_credit_eligibility_detected(self):
        """R&D credit eligibility correctly identified"""
        pass

    def test_qsbs_eligibility_window_warning(self):
        """QSBS 6-month warning triggered"""
        pass

    def test_transfer_pricing_risk_flagged(self):
        """Transfer pricing risk correctly assessed"""
        pass

    def test_multi_jurisdiction_support(self):
        """Tax credits identified for US, UK, EU, India"""
        pass

    def test_estimated_value_accurate(self):
        """Tax savings estimate within 20% of actual"""
        pass
```

### Grant & Credit Agent Tests

```python
# tests/test_grant_agent.py

class TestGrantCreditAgent:
    def test_grant_match_score_above_80(self):
        """High-quality grant matches scored >80%"""
        pass

    def test_deadline_alert_30_days(self):
        """Alert fires 30 days before deadline"""
        pass

    def test_eligibility_assessment_accurate(self):
        """Eligibility assessment matches criteria"""
        pass

    def test_sbir_sttr_matching(self):
        """SBIR/STTR grants correctly matched"""
        pass

    def test_innovate_uk_horizon_europe_matching(self):
        """UK/EU grants correctly matched"""
        pass
```

### Accounting Ops Agent Tests

```python
# tests/test_accounting_ops_agent.py

class TestAccountingOpsAgent:
    def test_month_end_close_completed(self):
        """Close checklist fully executed"""
        pass

    def test_accruals_calculated_correctly(self):
        """Accrual calculations accurate"""
        pass

    def test_depreciation_schedule_accurate(self):
        """Depreciation schedule correct"""
        pass

    def test_consolidation_correct(self):
        """Multi-entity consolidation accurate"""
        pass

    def test_audit_prep_complete(self):
        """Audit workpapers complete"""
        pass
```

### Procurement Ops Agent Tests

```python
# tests/test_procurement_ops_agent.py

class TestProcurementOpsAgent:
    def test_quote_comparison_accurate(self):
        """Vendor quotes compared apples-to-apples"""
        pass

    def test_renewal_alert_90_days(self):
        """Renewal alert fires 90 days before expiry"""
        pass

    def test_spend_analysis_correct(self):
        """Spend by category accurately analyzed"""
        pass

    def test_negotiation_prep_complete(self):
        """Negotiation benchmarks provided"""
        pass

    def test_vendor_risk_assessed(self):
        """Vendor risk correctly assessed"""
        pass
```

### Cap Table Ops Agent Tests

```python
# tests/test_cap_table_ops_agent.py

class TestCapTableOpsAgent:
    def test_cap_table_accurate(self):
        """Ownership percentages correct"""
        pass

    def test_option_pool_tracked(self):
        """Option pool grants/vesting tracked"""
        pass

    def test_dilution_scenario_correct(self):
        """Dilution modeling accurate"""
        pass

    def test_safe_convertible_tracked(self):
        """SAFE/convertible notes tracked"""
        pass

    def test_exit_waterfall_accurate(self):
        """Exit waterfall analysis correct"""
        pass
```

### Grant Ops Agent Tests

```python
# tests/test_grant_ops_agent.py

class TestGrantOpsAgent:
    def test_application_drafted(self):
        """Grant application drafted from context"""
        pass

    def test_documents_collected(self):
        """Supporting documents collected"""
        pass

    def test_milestone_tracked(self):
        """Post-award milestones tracked"""
        pass

    def test_report_filed(self):
        """Compliance reports filed"""
        pass

    def test_compliance_maintained(self):
        """Grant compliance maintained"""
        pass
```

---

## Langfuse Integration (Optional)

**Langfuse v3 requires:**
- PostgreSQL (existing)
- ClickHouse (new — heavy)

### Option 1: Langfuse Cloud (Recommended for Dev)

```bash
# Sign up free tier: langfuse.com
# Add to .env:
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Option 2: Self-Host with ClickHouse

```yaml
# Add to docker-compose.yml:
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "9000:9000"
    environment:
      - CLICKHOUSE_USER=clickhouse
      - CLICKHOUSE_PASSWORD=clickhouse
    volumes:
      - clickhouse_data:/var/lib/clickhouse

  langfuse:
    image: langfuse/langfuse:3
    ports:
      - "3001:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langfuse
      - CLICKHOUSE_HOST=clickhouse
      - CLICKHOUSE_PORT=9000
    depends_on:
      - postgres
      - clickhouse
```

### Option 3: Skip Langfuse Tests

Tests work without Langfuse — use pytest assertions only.

---

## Definition of Done

**A test passes when:**
1. ✅ Pydantic model validates (type-safe)
2. ✅ Graph completes (no stuck nodes)
3. ✅ Score >= threshold (quality)
4. ✅ No jargon in output (tone)
5. ✅ One action at end (actionable)

**A feature ships when:**
1. ✅ All tests pass (100%)
2. ✅ DSPy module compiled (optimized prompts)
3. ✅ E2E flow verified (real LLM, real Docker)
4. ✅ LLM eval score >= 0.8 (quality gate)

---

**Document Version:** 4.1
**Last Updated:** 2026-03-12
**Status:** ✅ PRODUCTION READY
