# OntologyAI.ai — Canonical PRD v4.1

**Version:** 4.1  
**Date:** March 2026  
**Status:** Product Vision — Current Implementation Status Below

---

## ⚠️ CURRENT IMPLEMENTATION STATUS

**This document is the aspirational product vision (v4.1).** The parts marked `[BUILT]` below have been implemented in the current codebase (as of June 2026). Sections marked `[PLANNED]` are future scope.

### What Is Actually Built (V4.0 as of June 2026)

| Component | Status | Implementation |
|-----------|--------|----------------|
| **Command Center Dashboard** | ✅ [BUILT] | 13+ HTMX panels (Chat, Approvals, MissionState, KPIs, etc.) |
| **SSE Chat with @mentions** | ✅ [BUILT] | `hx-ext="sse"` + goroutine Temporal dispatch |
| **Specialist Agents** | ✅ [BUILT] | Finance, Data, Ops, Comms, Hiring, QA (LangGraph + Temporal) |
| **HITL Temporal Signals** | ✅ [BUILT] | `SignalWorkflow("hitl-approval")` unblocks workflows |
| **MissionState Write Path** | ✅ [BUILT] | Python AI → POST → PostgreSQL → GET → Dashboard |
| **Map-based @mention Routing** | ✅ [BUILT] | `map[string]specialistRoute`, 9 aliases → 6 workflows |
| **Server-rendered Chat Bubbles** | ✅ [BUILT] | `renderChatBubble()` with `html.EscapeString()` |
| **Go Core (Fiber + Temporal)** | ✅ [BUILT] | HTTP server, Temporal dispatch, SSE streaming |
| **Python AI Worker** | ✅ [BUILT] | Temporal worker, LangGraph agents, Pydantic outputs |
| **LLM Integration** | ✅ [BUILT] | Azure AI Foundry / Groq / Ollama via OpenAI SDK |
| **319 Python + 52 Go Tests** | ✅ [BUILT] | Suite passing, Go build clean |

### What Is Not Yet Built (Aspirational per v4.1 Vision)

| Component | Status | Notes |
|-----------|--------|-------|
| **Telegram Bot** | ❌ [PLANNED] | Current UI is HTMX web (not Telegram) |
| **Neo4j/Graphiti** | ❌ [PLANNED] | Not deployed; PostgreSQL + Qdrant used for memory |
| **Crawl4AI / Market Intel** | ❌ [PLANNED] | Not built; external web crawling not implemented |
| **Bank Statement Parser** | ❌ [PLANNED] | Not built; data ingestion pipeline not implemented |
| **Finance Ops / Accounting Ops** | ❌ [PLANNED] | Not built; only Finance analysis agent exists |
| **Legal Ops / HR Ops / Admin Ops** | ❌ [PLANNED] | Not built |
| **Jurisdiction / Tax / Grant Agents** | ❌ [PLANNED] | Not built |
| **Cap Table / Procurement Agents** | ❌ [PLANNED] | Not built |
| **Real Docker + Real LLM Testing** | ❌ [PLANNED] | Tests use mocked APIs (respx/polyfactory) |
| **BizOS Workflow (Continue-As-New)** | ❌ [PLANNED] | Not implemented |
| **First Real Founder Onboarding** | ❌ [PLANNED] | Pre-seed / alpha stage |

> **For current implementation status, see:**
> - [README.md](./README.md) — Project overview, architecture, test counts
> - [PRD.md](./PRD.md) — Detailed V4.0 implementation status
> - [ADR-001](../.opencode/context/adr/001-sarthi-v4-architecture-evolution.md) — Architecture decisions
> - [AGENTS.md](./AGENTS.md) — Development guidelines and project structure

---

---

## 1. The One-Line Definition

```
OntologyAI is the autonomous back-office for any company that has
outgrown spreadsheets but cannot yet afford a team of specialists.

It does not advise. It works.
It does not build dashboards. It acts on what it sees.
It does not wait to be asked. It tells you what matters.

Finance. Accounting. Bookkeeping. Legal. Compliance.
Business Intelligence. Market Intelligence.
All of it. Running continuously. In the background.
Delivered as a message — not a login.
```

---

## 2. The Problem

| What a Startup Needs | What They Actually Have |
|---------------------|------------------------|
| CFO | Founder checking a spreadsheet at 11pm |
| Head of HR | Founder copying an offer letter template |
| Legal counsel | Founder ignoring the contract renewal email |
| BI analyst | Founder not knowing what they don't know |
| COO | Founder doing everything manually |

**The result:** 15–20 hours/week of founder time eaten by back-office work that doesn't require their unique judgment. That is ~3 months/year of product and growth time permanently lost.

---

## 3. The ICP

### Who OntologyAI Is For

| Attribute | Value |
|-----------|-------|
| **Stage** | Pre-seed → Series A |
| **Team size** | 1–25 people |
| **Type** | Product/tech startup (B2B SaaS, D2C, marketplace, fintech, edtech) |
| **Geography** | India (beachhead) → US → UK → EU → SEA |

### Jurisdiction Awareness

OntologyAI detects which laws apply based on company incorporation profile at onboarding:

- **India:** GST, TDS, PF, ESIC, PT, MCA, DPDP
- **US:** Sales tax, SBIR/STTR grants, QSBS, 409A, SOC2
- **UK:** VAT, Innovate UK grants, Companies House
- **EU:** VAT OSS, GDPR, Horizon Europe grants
- **SEA:** SST (Malaysia), GST (Singapore), BOI (Thailand)

### What Defines Them

- Tech-literate — they know what an API is
- Already using tools (Notion, Linear, Razorpay, Google Workspace, Zoho Books/QuickBooks)
- Do NOT have dedicated ops/finance/HR/legal hires
- The founder IS the back-office right now

### What They Feel

- "I'm spending all my time on admin, not product"
- "I don't know if my numbers are okay"
- "I almost missed a GST deadline last month"
- "I have to write the same follow-up emails every single week"

### What They Need

- Not the best financial firm
- Not another dashboard
- Someone (something) to hold their hand, handle the grunt work, and tell them the one thing that matters right now

---

## 4. Global TAM

| Market | Current | 2030 | CAGR |
|--------|---------|------|------|
| AI Agents | $7.8B | $52.6B | 46.3% |
| AI Policy & Governance | $1.3B | $39.5B | 40.0% |
| Accounting services startups | $8.2B | $14.1B | 14.5% |

**OntologyAI SAM:** ~135M companies globally with 1–100 employees, outgrown Excel, cannot afford specialists. At $50/month = **$81B/year addressable**.

---

## 5. The Interface

### Primary: Telegram Bot [PLANNED — Current UI is HTMX web]

Free, no per-message cost, async, file-capable, inline keyboards for HITL approvals. Works globally.

### What Founders Send OntologyAI

- **Text questions:** "What's my runway?"
- **CSV/Excel files:** Bank statement export from net banking
- **PDF files:** Contracts, notices, invoices
- **Photos:** Tax notices, receipts, whiteboards
- **/commands:** `/status` `/runway` `/pipeline` `/decisions` `/weekly`

### What OntologyAI Sends Founders

- **Proactive alerts** (unprompted, when score > threshold)
- **Task reports:** "Done: sent 3 payment reminders"
- **HITL requests:** "Send this to Raju? [Yes / Edit / No]"
- **Weekly briefing:** Every Monday 9am local time
- **Deadline alerts:** 14-day advance warning on all compliance

---

## 6. The BI Replacement Layer

| Excel / Power BI | OntologyAI |
|-----------------|--------|
| Founder opens tool | OntologyAI watches 24/7 |
| Refresh to see data | OntologyAI pushes when it matters |
| Founder spots anomaly | OntologyAI spots it first |
| Export for investor | OntologyAI generates narrative |
| Manual scenario math | "What if I hire in April?" answered against live data |
| Rear-view snapshot | Rolling 13-week forward forecast |
| Static chart | "At current trajectory: zero June 14" |

**Every agent in OntologyAI is a living BI query. Not a chart. A decision.**

---

## 7. The Agent Architecture

### Tier Map

```
TIER 0  ── KERNEL (Go + Temporal)
           BusinessOSWorkflow: orchestrates all agents,
           enforces HITL gates, maintains audit trail,
           never crashes, never loses state.

TIER 1  ── CHIEF OF STAFF (1 agent — Python/LangGraph)
           The ONLY agent that talks to the founder.
           Routes, translates, decides what to surface.
           Holds the full company knowledge graph.

TIER 2  ── INTELLIGENCE (observe + advise, NEVER talk to founder)
           These agents produce typed findings → CoS decides.

TIER 3  ── OPERATIONS (execute, not just advise)
           Owner approves → agent executes autonomously.

TIER 4  ── DATA LAYER (invisible — founder never interacts)
           Normalizes inputs, manages memory,
           crawls external intelligence.
```

### Tier 1: Chief of Staff [PLANNED]

- **LangGraph graph:** `chief_of_staff_agent.py`
- **DSPy signatures:** ToneFilter, RouteClassifier
- **Pydantic output:** `ChiefOfStaffOutput`
- **Single entrypoint** for all founder communication
- **Routes** inbound messages to Tier 2/3 agents
- **Scores** all findings: fire now / queue / suppress
- **Applies ToneFilter:** jargon → plain language
- **Manages conversation memory** (Qdrant + Neo4j)
- **Monday 9am weekly briefing** (Temporal cron)
- **Enforces:** one message = one action only

**HITL Gate:**
- **LOW RISK** → auto-execute + notify after
- **MEDIUM RISK** → 1-tap Telegram inline keyboard
- **HIGH RISK** → explicit confirm with context

### Tier 2: Intelligence Agents

#### CFO Agent [PLANNED — Finance specialist (FinanceGraph) exists but is simpler]
- 13-week rolling cash flow forecast
- Burn rate + runway (alert < 90 days)
- Burn spike detection (> 20% MoM)
- Margin analysis per revenue line
- Unit economics: CAC, LTV, payback
- Scenario modeling ("what if I hire?")
- **Integrations:** Zoho Books, QuickBooks, Razorpay, Bank parser

#### BI Agent [PLANNED — Data specialist (DataGraph) is the closest analog]
- Customer cohort analysis (retention/churn)
- Revenue concentration risk (single customer > 30%)
- Product usage vs revenue contribution
- Operational efficiency anomalies
- Growth lever identification
- Cross-source pattern correlation

#### Risk & Compliance Agent [PLANNED]
- GST, TDS, Advance Tax deadlines
- PF, ESIC, PT compliance calendar
- Contract expiry tracking
- DPDP Act compliance status
- MCA annual filing deadlines
- IP protection deadlines
- Regulatory changes in sector
- **Rule:** ANY deadline within 14 days fires. Hard.

#### Market Intelligence Agent [PLANNED]
- **Tools:** Crawl4AI (Docker, $0) + Firecrawl (free tier)
- **Watches:**
  - **REGULATORY:** SEC/SEBI/FCA/MCA/GDPR/DPDP filings per jurisdiction
  - **GRANTS:** SBIR, Innovate UK, DPIIT, Horizon Europe — detects money founder doesn't know exists
  - **COMPETITORS:** Pricing page changes, feature launches, job postings, funding announcements, G2/Capterra pain points
  - **NEW TOOLS:** "A free API launched that replaces your ₹12k/mo tool"
  - **POLICY:** Tax law changes that affect THIS company specifically
- **Output contract:** NOT a newsletter. NOT a summary. One signal. One opportunity or risk. One action. Fires ONLY when something is actionable.

#### Fundraise Readiness Agent [NEW — v4.1] [PLANNED]
- Data room scoring and gap detection
- Investor-ready P&L narrative generation
- Diligence question anticipation
- Cap table cleanliness check

#### Tax Intelligence Agent [NEW — v4.1] [PLANNED]
- R&D credit eligibility detection (global)
- QSBS status monitoring (US)
- DPIIT Startup India recognition (India)
- Jurisdiction-specific tax opportunity detection

#### Grant & Credit Agent [NEW — v4.1] [PLANNED]
- SBIR/STTR eligibility (US)
- Innovate UK eligibility
- DPIIT Startup India recognition
- Horizon Europe eligibility (EU)
- Application drafting from company context

### Tier 3: Operations Agents [ALL PLANNED — No execution agents implemented yet]

#### Finance Ops Agent
- Auto-categorizes every bank transaction
- Reconciles bank vs accounting books
- Drafts and sends payment reminders (founder approval via Telegram)
- Generates GST return summary data
- Produces monthly P&L narrative
- Optimizes vendor payment timing
- Tracks accounts receivable aging

#### Accounting Ops Agent [NEW — v4.1]
- Revenue recognition (GAAP / Ind AS)
- Deferred revenue tracking
- Investor-ready P&L formatting
- Month-end close checklist execution
- Audit trail generation

#### HR Ops Agent
- Generates offer letters and contracts
- Runs onboarding checklist per new hire
- Tracks leave balances
- Prepares payroll data (Razorpay Payroll)
- PF/ESIC filing reminders + data prep
- Performance review scheduling
- Exit process checklist

#### Legal Ops Agent
- Generates NDAs and service agreements
- Summarizes any contract in plain language
- Tracks all contract deadlines
- Prepares MCA filing data
- Manages eSign workflows (Leegality/Digio)
- DPDP Act compliance checklist

#### RevOps Agent
- CRM hygiene (updates stale deals in HubSpot)
- Pipeline stall detection + follow-up drafts
- Proposal/quote generation
- Subscription renewal reminders
- Win/loss pattern analysis
- Customer health scoring

#### Admin Ops Agent
- Meeting prep (pulls context, agenda)
- Action item extraction from meeting notes
- SOP documentation from observed workflows
- Tool stack + subscription audit
- Internal announcement drafts

#### Procurement Ops Agent [NEW — v4.1]
- Vendor onboarding checklist
- Invoice validation against PO
- Payment timing optimization
- Duplicate invoice detection
- Vendor contract renewal tracking

#### Cap Table Ops Agent [NEW — v4.1]
- Option grant drafting
- 409A valuation reminder (US)
- ESOP trust compliance (India)
- Shareholder update draft generation
- Cap table cleanliness audit

#### Grant Ops Agent [NEW — v4.1]
- Grant application drafting
- Submission deadline tracking
- Eligibility evidence compilation
- Status tracking and follow-up

### Tier 4: Data Layer [ALL PLANNED — Ingestion pipeline not built]

#### Ingestion Agent
- **CSV/Excel:** pandas + openpyxl (Bank detection: HDFC/ICICI/SBI/Axis/Kotak)
- **PDF (digital):** pdfplumber
- **PDF (scanned):** Docling accurate mode
- **PDF (fallback):** Azure Document Intelligence (500 pages/mo free tier)
- **Photos:** Docling vision mode
- All normalised → standard transaction schema
- PostgreSQL write + Qdrant embed + Neo4j episode

#### Memory Agent (Qdrant — semantic) [BUILT — src/memory/ exists with Qdrant integration]
- Manages Qdrant collection: `sarthi-founder-memory`
- Embeddings: text-embedding-3-small (1536d)
- Founder isolation enforced at filter level
- Conflict detection on contradicting writes
- Stale memory compression after 90 days
- Pattern detection: archetype classification

#### Graph Memory Agent (Neo4j + Graphiti — relational) [PLANNED — Not deployed; using simpler memory patterns]
- Temporal knowledge graph via Graphiti (Zep)
- Every reflection, commitment, signal, decision is an episode
- Answers questions Qdrant cannot:
  - "Has this founder broken this commitment 3 weeks running?"
  - "What happened to revenue AFTER missed customer calls?"
  - "Which interventions did this founder respond to?"
- Hybrid search: semantic + graph traversal (RRF)
- **Qdrant** = "what is this similar to?"
- **Neo4j** = "what does this mean in context?"

#### Crawler Agent [expanded v4.1]
- **Crawl4AI** (Docker, $0) primary
- **Firecrawl API** (free tier) fallback
- **Scheduled crawls:**
  - Competitor pricing pages (weekly)
  - Competitor job postings (daily — roadmap signal)
  - G2/Capterra reviews for competitors (weekly)
  - Government grant databases per jurisdiction (daily)
  - Policy tracker feeds per jurisdiction (daily)
  - Competitor changelogs / product updates (weekly)
- On-demand deep crawl when Market Intel fires

#### Jurisdiction Agent [NEW — v4.1]
- Detects applicable laws at onboarding based on company incorporation profile
- Produces `JurisdictionProfile` → stored in PostgreSQL
- Updates automatically when laws change (Crawler Agent feeds policy changes here)
- All other agents query this at runtime: "Which compliance deadlines apply to THIS company?"

#### Connector Agent
- Manages OAuth token health for all integrations
- Token refresh, sync schedule
- Falls back to polling if webhook fails
- Alerts CoS if integration goes dark

---

## 8. The Self-Correcting Loop

```
1. Agent acts      (e.g. sends payment reminder to Client X)
2. Outcome seen    (Client X pays in 24 hours)
3. MemoryAgent writes to Qdrant:
   "Client X: high responsiveness, 24hr payment"
4. GraphMemoryAgent writes episode to Neo4j:
   Entity: Client X → RELATION: responds_within → 24h
5. Future: warmer tone, earlier follow-up,
   CoS knows not to escalate this client
6. Context drift:  CoS detects macro pattern across
   all memory and surfaces unprompted:
   "You've raised prices twice but win rate is unchanged
    — your pricing has headroom."

The system gets smarter about THIS company specifically.
Not generic AI. Company-specific intelligence that compounds.
```

---

## 9. The Technology Stack

### Infrastructure ($0 — Docker, self-hosted)

| Component | Technology | Port | Purpose |
|-----------|------------|------|---------|
| Workflow engine | Temporal | 7233/8088 | Durable execution |
| Message queue | Redpanda | 19092 | Event bus |
| Primary DB | PostgreSQL | 5432 | State, founders |
| Vector DB | Qdrant | 6333 | Semantic memory |
| Graph DB | Neo4j | 7687 | Relational memory |
| LLM observability | Langfuse | 3001 | Tracing + evals |
| Web crawler | Crawl4AI | 11235 | Market intel |
| Isolated exec | Sandbox (alpine) | 5001 | CFO charts/math |

### Go Core (`apps/core`)

| Technology | Purpose |
|------------|---------|
| Go 1.24 + Fiber | API gateway, webhook hub |
| Temporal Go SDK | BusinessOSWorkflow definition |
| franz-go | Redpanda producer/consumer |
| sqlc | Type-safe PostgreSQL queries |
| htmx + Go tmpl | Ops dashboard (internal) |
| go-telegram-bot | Telegram webhook + send DM |

### Python AI Worker (`apps/ai`)

| Technology | Purpose |
|------------|---------|
| Python 3.11 + uv | Package management |
| LangGraph | Agent state machines (all tiers) |
| DSPy | Prompt optimization per agent node |
| Pydantic v2 | Output contracts + jargon validator |
| Langfuse SDK | Auto-trace every LangGraph node |
| Temporal Python | Activity worker |
| Qdrant Client | Semantic memory read/write |
| Graphiti (Zep) | Neo4j temporal knowledge graph |
| graphiti-core | Graphiti Python library |
| neo4j | Neo4j Python driver |

### THE ONE SDK RULE — ABSOLUTE

```python
# apps/ai/src/config/llm.py
# THE ONLY FILE WHERE THE LLM CLIENT IS CREATED.
# Every agent imports from here. No exceptions. Ever.

from openai import OpenAI   # ← ALWAYS. Never AzureOpenAI.

def get_llm_client() -> OpenAI:
    return OpenAI(
        base_url = os.environ["LLM_BASE_URL"],
        api_key  = os.environ["LLM_API_KEY"],
    )

# Provider      LLM_BASE_URL
# ──────────────────────────────────────────────────────
# OpenRouter    https://openrouter.ai/api/v1   ← default
# Azure OpenAI  https://{res}.openai.azure.com/openai/v1
# OpenAI        https://api.openai.com/v1
# Groq          https://api.groq.com/openai/v1
# Ollama        http://localhost:11434/v1
```

### Graphiti uses the same factory

```python
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.embedder.openai_embedder import OpenAIEmbedder
from src.config.llm import get_llm_client, get_model

graphiti = Graphiti(
    neo4j_uri      = os.environ["NEO4J_URI"],
    neo4j_user     = os.environ["NEO4J_USER"],
    neo4j_password = os.environ["NEO4J_PASSWORD"],
    llm_client     = OpenAIClient(
        client = get_llm_client(),
        model  = get_model(),
    ),
    embedder = OpenAIEmbedder(
        client          = get_llm_client(),
        embedding_model = os.environ.get(
            "EMBEDDING_MODEL", "text-embedding-3-small"),
    ),
)
```

### Document Processing ($0 OSS)

| Tool | When Used |
|------|-----------|
| pandas + openpyxl | CSV/Excel bank statements |
| pdfplumber | Digital PDFs (text-selectable) |
| Docling (IBM OSS, accurate) | Scanned PDFs (image-based OCR) |
| Azure Document Intelligence | Fallback only (500 pages/mo free) |

### External Integrations (all free for dev)

| Service | API | Cost |
|---------|-----|------|
| Telegram Bot | python-telegram-bot | $0 forever |
| Zoho Books | REST API | $0 free tier |
| QuickBooks Online | Sandbox API | $0 dev |
| Razorpay | Webhooks + API | $0 setup |
| HubSpot CRM | API | $0 free tier |
| Firecrawl | Crawl API | $0 (500/mo) |
| Leegality / Digio | eSign API | $0 sandbox |

---

## 10. The Tone Contract

### BANNED IN ALL OUTPUT (every agent, every message)

```
EBITDA, DSO, bps, YoY, MoM, liquidity,
working capital, CAGR, accounts receivable,
burn multiple, runway compression, NWC,
cash conversion cycle, churn cohort delta,
basis points, net margin, gross margin,
accounts payable, amortization, depreciation,
optimize, leverage, synergy, streamline,
actionable insights, KPIs, metrics, data-driven
```

### REQUIRED IN ALL OUTPUT

- Lead with human reality, not the metric
- Max 3 sentences of explanation
- End with exactly ONE action
- Warm, direct — trusted friend, not consultant
- If bad news: acknowledge before data
- If good news: celebrate explicitly first

### Example

**BAD:** "Your EBITDA margin compressed 340bps MoM due to elevated SG&A spend."

**GOOD:** "You kept less money from every rupee you earned this month — costs grew faster than revenue. The main culprit is [specific line]. This week: cut or pause [specific item]."

**Enforced via:**
1. Pydantic validator on every output model
2. DSPy-compiled ToneFilter (compiled weights in git)
3. Langfuse scores every output — <0.7 is flagged

---

## 11. The HITL Gate Model

| Risk Level | Examples | Approval Flow |
|------------|----------|--------------|
| **LOW RISK** (auto-execute + notify after) | Categorize a transaction, Update a CRM record, Log a compliance deadline, Generate a draft document (not yet sent) | Auto |
| **MEDIUM RISK** (1-tap Telegram inline keyboard) | Send a message to a client, Send a payment reminder, Book a meeting, Share a document externally | 1-tap |
| **HIGH RISK** (explicit confirm + reason shown) | File a GST return, Send a legal document, Make a payment, Delete or archive data, Submit a grant application | Explicit confirm |

**PRINCIPLE:** Powerful but never autonomous where it matters. The founder always controls the wheel. They just don't have to steer on empty roads.

---

## 12. The Data Flow

```
EVENT: Founder sends HDFC CSV to Telegram bot
         │
         ▼
[Go Fiber] TelegramWebhookHandler
  → Validates, authenticates founder
  → Produces to Redpanda: "ontology_ai.business.events"
         │
         ▼
[Temporal] BusinessOSWorkflow (long-running, never stops)
  → Classifies event: "bank_statement_upload"
  → Spawns: IngestionAgent
         │
         ├──▶ IngestionAgent: detects HDFC format
         │    → pandas normalize → standard schema
         │    → PostgreSQL write (transactions table)
         │    → Qdrant upsert (memory + embedding)
         │    → Neo4j episode via Graphiti
         │    → Signals: "ingestion_complete"
         │
         ├──▶ Parallel Tier 2 agents (all fire):
         │    CFOAgent.analyze(new_data)
         │    RiskAgent.check_deadlines()
         │    BIAgent.detect_patterns()
         │    MarketIntelAgent.check_relevant_signals()
         │
         ├──▶ Each agent → typed Pydantic finding
         │    (validated at output boundary)
         │    (Langfuse traces every node)
         │
         └──▶ ChiefOfStaffAgent receives ALL findings
              → Queries Qdrant: semantic context
              → Queries Neo4j: relational patterns
              → Scores: what to surface right now?
              → ToneFilter: jargon → plain language
              → Drafts ONE Telegram message
              → HITL gate: medium/high risk queued
              → Go activity: send via Telegram Bot API
                         │
                         ▼
              Founder's Telegram:
              "Got your HDFC statement (March 1–15).
               Money in: ₹2,34,000 | Out: ₹1,87,000
               One thing I noticed: AWS costs up ₹23k
               vs last month. Anything new deployed?
               [It's fine] [Let me check]"
```

---

## 13. Pydantic Output Contracts

```python
# apps/ai/src/schemas/findings.py

BANNED_JARGON = {
    "EBITDA","DSO","bps","YoY","MoM","liquidity",
    "working capital","CAGR","accounts receivable",
    "burn multiple","runway compression","NWC",
    "cash conversion cycle","churn cohort delta",
    "basis points","net margin","gross margin",
    "accounts payable","amortization","depreciation",
}

def validate_no_jargon(text: str) -> str:
    for term in BANNED_JARGON:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            raise ValueError(f"Jargon violation: '{term}'")
    return text

class HitlRisk(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"

class CFOFinding(BaseModel):
    headline:     str    # max 10 words, plain language
    what_is_true: str    # 2-3 sentences, ₹ amounts, no jargon
    do_this:      str    # exactly ONE action
    urgency:      str    # "today" | "this week" | "this month"
    rupee_impact: Optional[int]
    hitl_risk:    HitlRisk
    trigger_type: str
    is_good_news: bool = False

    @validator("headline", "what_is_true", "do_this")
    def no_jargon(cls, v): return validate_no_jargon(v)

    @validator("do_this")
    def single_action(cls, v):
        if any(c in v for c in ["\n-", "\n•", "\n1.", "\n2."]):
            raise ValueError("do_this must be a single action")
        return v

class BIFinding(BaseModel):
    headline:     str
    pattern:      str
    evidence:     str
    do_this:      str
    hitl_risk:    HitlRisk
    is_good_news: bool = False

class RiskAlert(BaseModel):
    title:       str
    deadline:    str    # "March 28 — 16 days away"
    consequence: str    # plain language: "₹X penalty if missed"
    do_this:     str
    days_until:  int
    hitl_risk:   HitlRisk = HitlRisk.HIGH

class AgentFinding(BaseModel):  # Market Intel
    source:      str
    headline:    str
    relevance:   float  # 0.0–1.0
    summary:     str
    do_this:     Optional[str]
    hitl_risk:   HitlRisk = HitlRisk.LOW

class FundraiseFinding(BaseModel):  # NEW v4.1
    data_room_score:     float  # 0.0–1.0
    gaps:                list[str]
    narrative:           str    # investor-ready P&L narrative
    do_this:             str
    hitl_risk:           HitlRisk

class TaxFinding(BaseModel):  # NEW v4.1
    opportunity:         str
    jurisdiction:        str
    estimated_saving:    Optional[int]  # ₹ or $
    do_this:             str
    hitl_risk:           HitlRisk

class GrantFinding(BaseModel):  # NEW v4.1
    grant_name:          str
    jurisdiction:        str
    eligibility_score:   float
    deadline:            Optional[str]
    estimated_amount:    Optional[str]
    do_this:             str
    hitl_risk:           HitlRisk = HitlRisk.MEDIUM
```

---

## 14. Testing Architecture [PLANNED — Current tests use mocked APIs]

**PRINCIPLE:** Real Docker. Real LLM. No mocks. Always.  
**CURRENT REALITY:** Tests use `respx` (httpx mocking), `polyfactory` (fixtures), and `unittest.mock.patch`. Real Docker/LLM testing is planned for future phases.

| Layer | Tool | What Is Tested |
|-------|------|---------------|
| **Infra** | conftest.py poison pill | All 12 Docker containers reachable before any test. LLM confirmed live. Mock patches on LLM BLOCKED |
| **Agent graphs** | LangGraph + pytest-asyncio | Graph completes all nodes. State transitions valid. Error nodes reachable |
| **Output contracts** | Pydantic v2 | Every finding typed. Jargon validator fires. Structure enforced at boundary |
| **Prompt quality** | DSPy + BootstrapFewShot + compiled JSON | Score ≥ 0.7 on holdout examples. CFO runway within ±15 days. ToneFilter jargon-free |
| **Observability** | Langfuse self-hosted | Every LangGraph node traced. Scores logged per run. Trace visible in UI |
| **E2E flows** | Full stack | Telegram → Go → Redpanda → Temporal → Python agent → Pydantic output → Langfuse trace → Telegram delivery |

### Test Count Targets

| Suite | Tests | Type |
|-------|-------|------|
| Infrastructure health | 6 | Docker + LLM connectivity |
| Memory agent (Qdrant) | 10 | write/read/isolation |
| Graph memory agent (Neo4j) | 12 | episodes/search/patterns |
| Chief of Staff | 8 | routing + tone |
| Bank parser | 8 | HDFC/ICICI/SBI/scanned PDF |
| CFO agent | 10 | LangGraph E2E + Pydantic |
| BI agent | 8 | pattern detection |
| Risk agent | 10 | deadline engine |
| Finance ops agent | 10 | HITL gates + execution |
| Ingestion agent | 10 | CSV/PDF/photo normalization |
| Tone filter | 14 | jargon + DSPy + Hindi |
| Sandbox client | 10 | isolated exec + charts |
| E2E flows | 20 | full stack Telegram → output |
| LLM evals (DSPy) | 15 | scoring + LLM-as-judge |
| **Total** | **151+** | **Real LLM, real Docker** |

---

## 15. Infrastructure — All Containers

```yaml
# docker-compose additions (append to existing — never touch base)

  saarathi-neo4j:
    image: neo4j:5.18-community
    container_name: saarathi-neo4j
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD:-sarthi}
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_memory_heap_initial__size=512m
      - NEO4J_dbms_memory_heap_max__size=1G
    volumes:
      - neo4j_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD","cypher-shell","-u","neo4j",
             "-p","${NEO4J_PASSWORD:-sarthi}","RETURN 1"]
      interval: 30s
      retries: 5

  saarathi-langfuse:
    image: langfuse/langfuse:latest
    container_name: saarathi-langfuse
    ports:
      - "3001:3000"
    environment:
      - DATABASE_URL=postgresql://sarthi:${POSTGRES_PASSWORD}@saarathi-postgres:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_SECRET:-langfuse-secret}
      - NEXTAUTH_URL=http://localhost:3001
      - SALT=${LANGFUSE_SALT:-langfuse-salt}
    depends_on:
      - saarathi-postgres
    restart: unless-stopped

  saarathi-sandbox:
    build: ./apps/sandbox
    container_name: saarathi-sandbox
    ports:
      - "5001:5000"
    environment:
      - SANDBOX_SECRET=${SANDBOX_SECRET:-sarthi-local}
    user: "1001"
    restart: unless-stopped
```

---

## 16. Complete Phase Execution Order

```
PHASE 0  ✅  IterateSwarm base infra — done
PHASE 1  ✅  OntologyAI pivot: schemas, agents v1, workflows — done

PHASE 2  🔨  NOW — LLM unification + graph memory
  □ apps/ai/src/config/llm.py             universal client
  □ apps/ai/src/config/langfuse.py        observability
  □ Grep-replace AzureOpenAI everywhere → get_llm_client()
  □ graph_memory_agent.py → OpenAIClient (not AzureOpenAIClient)
  □ docker-compose: neo4j + langfuse + sandbox appended
  □ make up → make health → all 12 containers green
  □ migration 007 applied
  □ make test-unit → 125 green
  □ git tag v2.0.0

PHASE 3  🔲  Tier 1 + Core Services
  □ tone_filter.py           DSPy-compiled, jargon validator
  □ dspy_signatures/         all 4 signatures
  □ dspy_compiled/           compiled weights, git-tracked
  □ telegram_notifier.py     inline keyboard HITL
  □ apps/core telegram.go    webhook + sendDM
  □ schemas/findings.py      all Pydantic contracts v4.1
  □ chief_of_staff_agent.py
  □ ingestion_agent.py
  □ bank_statement_parser.py
  □ apps/sandbox/            Dockerfile + server.py
  □ make test-unit → 160 green
  □ git tag v2.3.0

PHASE 4  🔲  Tier 2 Intelligence
  □ cfo_agent.py
  □ risk_agent.py            + compliance_calendar seeded (India 2026)
  □ bi_agent.py
  □ market_intel_agent.py    + crawler_agent expanded
  □ jurisdiction_agent.py    [new v4.1]
  □ fundraise_readiness_agent.py [new v4.1]
  □ tax_intelligence_agent.py    [new v4.1]
  □ grant_credit_agent.py        [new v4.1]
  □ make test-unit → 195 green
  □ git tag v3.0.0

PHASE 5  🔲  Tier 3 Operations + HITL
  □ finance_ops_agent.py
  □ accounting_ops_agent.py    [new v4.1]
  □ legal_ops_agent.py
  □ hr_ops_agent.py
  □ revops_agent.py
  □ admin_ops_agent.py
  □ procurement_ops_agent.py   [new v4.1]
  □ cap_table_ops_agent.py     [new v4.1]
  □ grant_ops_agent.py         [new v4.1]
  □ business_os_workflow.go    full, with Continue-As-New
  □ onboarding_workflow.go
  □ weekly_checkin_workflow.go
  □ HITL gate tested end-to-end Telegram → approve → execute
  □ make test-e2e → 20/20 green
  □ git tag v3.5.0

PHASE 6  🔲  Production Hardening + Evals
  □ DSPy eval suite           15 evals, ≥13/15 must pass
  □ Circuit breaker           all external calls
  □ Rate limiter              Telegram, Razorpay, Zoho, Crawl4AI
  □ .github/workflows/ci.yml  unit + lint (no LLM)
  □ .github/workflows/e2e.yml manual trigger, full stack
  □ All Langfuse traces       < 8s p95 latency
  □ make test-llm → ≥13/15 green
  □ git tag v4.0-alpha

PHASE 7  🔲  v4.0.0 — THE REAL MILESTONE
  □ One real founder signs up via Telegram
  □ Completes onboarding (6 questions, < 10 minutes)
  □ Uploads a real bank statement (any Indian bank)
  □ Receives a real CFO finding (no jargon, ₹ amounts)
  □ Approves one action via Telegram inline keyboard
  □ Reports: "This saved me time"
  THAT is v4.0.0. Not before.

PHASE 8  🔲  v4.1.0 — Global Expansion
  □ Jurisdiction agent live for US + UK + EU
  □ Grant agent: SBIR, Innovate UK, Horizon Europe
  □ Tax intelligence: QSBS, R&D credits
  □ Fundraise readiness agent live
  □ First non-India founder onboarded
```

---

## 17. What Does Not Change (v4.0 → v4.1)

```
Telegram as primary interface          ✅ correct globally
HITL gate model                        ✅ required everywhere
OSS bootstrapped stack ($0/mo)         ✅ structural cost advantage
ToneFilter jargon-free output          ✅ universal
Real Docker + Real LLM test rule       ✅ non-negotiable
Agent hierarchy Tier 0–4               ✅ correct architecture
Pydantic output contracts              ✅ type safety is not geography
DSPy prompt optimization               ✅ works globally
Langfuse observability                 ✅ works globally
Universal OpenAI SDK (no AzureOpenAI)  ✅ enforced
Neo4j + Graphiti memory layer          ✅ locked in
v4.0.0 tag condition                   ✅ first real founder, not code
```

---

## 18. The Moat

1. **INDIA-FIRST COMPLIANCE DEPTH**
   GST/TDS/PF/ESIC/PT/DPDP/MCA — no US tool will build this. No enterprise vendor will price it for pre-seed founders.

2. **COMPANY-SPECIFIC MEMORY (Qdrant + Neo4j)**
   After 6 months: "You've done this exact stall pattern 3 times. Here's what broke it last time." Graphiti makes this possible. A competitor starting fresh has to rebuild from zero.

3. **$0/MONTH INFRASTRUCTURE**
   Docker OSS stack. 85%+ gross margins at scale. Competitors on managed cloud can't price this low.

4. **THE RELATIONSHIP COMPOUNDS**
   Trust between founder and OntologyAI grows every week. Every intervention, rating, and outcome improves the model for this specific company. Not transferable.

5. **BRAND POSITIONING ENTERPRISE CAN'T COPY**
   No enterprise vendor can say "don't worry, I've got this" to a scared 26-year-old founder at 11pm. Their legal team, brand, and sales motion won't allow it.

6. **GRANT DETECTION = FOUND MONEY**
   "There's a ₹40 lakh DPIIT grant you qualify for." No other tool watches this continuously per company. First time OntologyAI finds a grant the founder didn't know about — that's lifetime retention.

---

## 19. Success Metrics

### Week 1 with real founder:
- Onboarding completed < 10 minutes
- First bank statement processed < 30 seconds
- First CFO finding delivered, zero jargon
- At least one action approved via Telegram inline key

### Month 1:
- 5+ hours/week saved (founder-reported)
- Zero compliance deadlines missed
- ≥ 3 Finance Ops tasks executed autonomously
- DSPy eval score ≥ 0.75 maintained
- All Langfuse traces < 8s p95

### The real metric:
**"Would you recommend OntologyAI to another founder?"**

**Target:** 8/10 by founder #5.

---

**Document Version:** 4.1  
**Last Updated:** March 2026  
**Status:** ✅ CANONICAL — Single Source of Truth
