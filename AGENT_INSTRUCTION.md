# AGENT_INSTRUCTION.md
## OntologyAI — SOP Runtime Implementation
### Version 1.0 | Internal Design Doc → Code | TDD-First

***

## READ BEFORE TOUCHING A SINGLE FILE

```
You are implementing the OntologyAI Internal Ops SOP Runtime.
This is NOT a greenfield project. You are extending an existing
polyglot codebase (IterateSwarm → OntologyAI) that already has:

  ✅ Go Fiber API gateway         (apps/core)
  ✅ Temporal orchestration       (Go + Python workers)
  ✅ Python LangGraph agents      (apps/ai)
  ✅ Redpanda event bus
  ✅ PostgreSQL + Qdrant
  ✅ Azure LLM via OpenAI SDK
  ✅ Langfuse self-hosted
  ✅ Real-Docker TDD discipline

YOUR JOB: Add the SOP runtime layer ON TOP.
Do not rewrite. Do not restructure. Extend only.

TESTING LAW (non-negotiable):
  Write the test first.
  Make it fail.
  Write code to make it pass.
  Real Docker services only.
  Real Azure LLM only.
  Zero mocks on external infra.
```

***

## PHASE 0 — BASELINE VERIFICATION
*Confirm the existing system is green before touching anything.*

- [ ] **0.1** Run `docker compose up -d` — all containers healthy
- [ ] **0.2** Run `bash scripts/test_ontology_ai.sh` — all existing tests pass
- [ ] **0.3** Confirm Azure LLM reachable:
  ```bash
  cd apps/ai
  uv run python -c "
  from src.config.llm import get_llm_client, get_chat_model
  client = get_llm_client()
  r = client.chat.completions.create(
      model=get_chat_model(),
      messages=[{'role':'user','content':'ping'}],
      max_tokens=5
  )
  print('LLM OK:', r.model)
  "
  ```
- [ ] **0.4** Git tag the baseline: `git tag v4.2-baseline`

***

## PHASE 1 — CANONICAL EVENT ENVELOPE
*Every event in OntologyAI has exactly one envelope shape. Define it here.*

### 1.1 — Write the test FIRST

**File:** `apps/ai/tests/test_event_envelope.py`

```python
# Write these tests. They will FAIL until Phase 1 code is written.
import pytest, uuid
from datetime import datetime, timezone
from src.schemas.event_envelope import EventEnvelope, EventSource

class TestEventEnvelope:

    def test_valid_razorpay_envelope_passes(self):
        env = EventEnvelope(
            event_id=str(uuid.uuid4()),
            founder_id=str(uuid.uuid4()),
            source=EventSource.RAZORPAY,
            event_name="payment.captured",
            topic="finance.revenue.captured",
            sop_name="SOP_REVENUE_RECEIVED",
            payload_ref="raw_events:abc123",
            payload_hash="sha256:deadbeef",
            occurred_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            trace_id=str(uuid.uuid4()),
            idempotency_key="razorpay:pay_abc123:v1",
        )
        assert env.source == EventSource.RAZORPAY
        assert env.sop_name == "SOP_REVENUE_RECEIVED"

    def test_unknown_event_name_raises(self):
        with pytest.raises(ValueError):
            EventEnvelope(
                event_id=str(uuid.uuid4()),
                founder_id=str(uuid.uuid4()),
                source=EventSource.RAZORPAY,
                event_name="",            # empty — must fail
                topic="finance.revenue.captured",
                sop_name="SOP_REVENUE_RECEIVED",
                payload_ref="raw_events:abc123",
                payload_hash="sha256:x",
                occurred_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=str(uuid.uuid4()),
                idempotency_key="razorpay::v1",
            )

    def test_payload_ref_never_contains_raw_json(self):
        """payload_ref must be a storage reference, not raw JSON"""
        with pytest.raises(ValueError):
            env = EventEnvelope(
                event_id=str(uuid.uuid4()),
                founder_id=str(uuid.uuid4()),
                source=EventSource.RAZORPAY,
                event_name="payment.captured",
                topic="finance.revenue.captured",
                sop_name="SOP_REVENUE_RECEIVED",
                payload_ref='{"amount": 5000}',   # raw JSON — must FAIL
                payload_hash="sha256:x",
                occurred_at=datetime.now(timezone.utc),
                received_at=datetime.now(timezone.utc),
                trace_id=str(uuid.uuid4()),
                idempotency_key="razorpay:pay_x:v1",
            )
```

Run: `uv run pytest tests/test_event_envelope.py -v` → **expect FAIL**

### 1.2 — Implement

**File:** `apps/ai/src/schemas/event_envelope.py`

```python
from __future__ import annotations
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, field_validator
import re

class EventSource(str, Enum):
    RAZORPAY          = "razorpay"
    ZOHO_BOOKS        = "zoho_books"
    GOOGLE_WORKSPACE  = "google_workspace"
    ESIGN             = "esign"
    TELEGRAM          = "telegram"
    CRON              = "cron"
    AWS_COST          = "aws_cost"
    EMAIL_FORWARD     = "email_forward"

class EventEnvelope(BaseModel):
    event_id:         str
    founder_id:       str
    source:           EventSource
    event_name:       str
    topic:            str
    sop_name:         str
    payload_ref:      str    # "raw_events:<id>" or "files:<path>" — NEVER raw JSON
    payload_hash:     str
    occurred_at:      datetime
    received_at:      datetime
    trace_id:         str
    idempotency_key:  str
    version:          str = "v1"
    schema_version:   str = "v1"

    @field_validator("event_name")
    @classmethod
    def event_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("event_name must not be empty")
        return v

    @field_validator("payload_ref")
    @classmethod
    def payload_ref_is_reference(cls, v: str) -> str:
        """
        payload_ref must be a storage reference, not raw JSON.
        
        Valid prefixes: raw_events:, files:, s3:, pg:
        
        Raises:
            ValueError: If payload_ref contains raw JSON or has invalid prefix
        """
        VALID_PREFIXES = ("raw_events:", "files:", "s3:", "pg:")
        if v.startswith("{") or v.startswith("["):
            raise ValueError(
                "payload_ref must be a storage reference, not raw JSON. "
                "Store in PostgreSQL first, pass the row ID."
            )
        if not any(v.startswith(p) for p in VALID_PREFIXES):
            raise ValueError(
                f"payload_ref must start with one of {VALID_PREFIXES}. "
                f"Got: {v!r}. Store raw JSON in PostgreSQL and pass the row ID."
            )
        return v
```

**File:** `apps/core/internal/events/envelope.go`

```go
package events

import "time"

type EventSource string

const (
    SourceRazorpay         EventSource = "razorpay"
    SourceZohoBooks        EventSource = "zoho_books"
    SourceGoogleWorkspace  EventSource = "google_workspace"
    SourceESign            EventSource = "esign"
    SourceTelegram         EventSource = "telegram"
    SourceCron             EventSource = "cron"
    SourceAWSCost          EventSource = "aws_cost"
    SourceEmailForward     EventSource = "email_forward"
)

type EventEnvelope struct {
    EventID        string      `json:"event_id"`
    FounderID      string      `json:"founder_id"`
    Source         EventSource `json:"source"`
    EventName      string      `json:"event_name"`
    Topic          string      `json:"topic"`
    SOPName        string      `json:"sop_name"`
    PayloadRef     string      `json:"payload_ref"`     // "raw_events:<uuid>" — NEVER raw payload
    PayloadHash    string      `json:"payload_hash"`
    OccurredAt     time.Time   `json:"occurred_at"`
    ReceivedAt     time.Time   `json:"received_at"`
    TraceID        string      `json:"trace_id"`
    IdempotencyKey string      `json:"idempotency_key"`
    Version        string      `json:"version"`
}
```

Run: `uv run pytest tests/test_event_envelope.py -v` → **expect PASS**

***

## PHASE 2 — EVENT DICTIONARY
*One event → one topic → one SOP. Enforced in code.*

### 2.1 — Write the test FIRST

**File:** `apps/ai/tests/test_event_dictionary.py`

```python
from src.config.event_dictionary import EventDictionary, UnknownEventError
import pytest

class TestEventDictionary:

    def test_razorpay_payment_captured_maps_correctly(self):
        d = EventDictionary()
        entry = d.resolve(source="razorpay", event_name="payment.captured")
        assert entry.topic   == "finance.revenue.captured"
        assert entry.sop     == "SOP_REVENUE_RECEIVED"

    def test_zoho_invoice_created_maps_correctly(self):
        d = EventDictionary()
        entry = d.resolve(source="zoho_books", event_name="invoice.created")
        assert entry.topic   == "finance.ap.invoice_created"
        assert entry.sop     == "SOP_VENDOR_INVOICE_RECEIVED"

    def test_cron_weekly_briefing_maps_correctly(self):
        d = EventDictionary()
        entry = d.resolve(source="cron", event_name="ops.cron.weekly")
        assert entry.sop     == "SOP_WEEKLY_BRIEFING"

    def test_unknown_event_raises(self):
        d = EventDictionary()
        with pytest.raises(UnknownEventError):
            d.resolve(source="razorpay", event_name="nonexistent.event")

    def test_every_sop_has_exactly_one_mapping(self):
        """No two (source, event_name) pairs can map to the same SOP
        from different sources — enforce uniqueness."""
        d = EventDictionary()
        all_entries = d.all_entries()
        seen_keys = set()
        for e in all_entries:
            key = (e.source, e.event_name)
            assert key not in seen_keys, f"Duplicate key: {key}"
            seen_keys.add(key)
```

Run: `uv run pytest tests/test_event_dictionary.py -v` → **expect FAIL**

### 2.2 — Implement

**File:** `apps/ai/src/config/event_dictionary.py`

```python
from dataclasses import dataclass
from typing import List

@dataclass
class DictionaryEntry:
    source:      str
    event_name:  str
    topic:       str
    sop:         str
    employees:   list[str]

class UnknownEventError(Exception):
    pass

_REGISTRY: List[DictionaryEntry] = [
    # ── RAZORPAY ──────────────────────────────────────────────────
    DictionaryEntry("razorpay","payment.captured",       "finance.revenue.captured",       "SOP_REVENUE_RECEIVED",       ["Bookkeeper","CFO"]),
    DictionaryEntry("razorpay","payment.failed",         "finance.revenue.failed",         "SOP_PAYMENT_FAILURE",        ["AR/AP Clerk"]),
    DictionaryEntry("razorpay","subscription.activated", "finance.subscription.new",       "SOP_NEW_SUBSCRIPTION",       ["Bookkeeper","CFO"]),
    DictionaryEntry("razorpay","subscription.halted",    "finance.subscription.halted",    "SOP_SUBSCRIPTION_HALTED",    ["AR/AP Clerk","CFO"]),
    DictionaryEntry("razorpay","subscription.cancelled", "finance.subscription.cancelled", "SOP_CHURN_DETECTED",         ["CFO","BI Analyst"]),
    DictionaryEntry("razorpay","invoice.paid",           "finance.invoice.paid",           "SOP_INVOICE_SETTLED",        ["AR/AP Clerk"]),
    DictionaryEntry("razorpay","invoice.expired",        "finance.invoice.expired",        "SOP_INVOICE_OVERDUE",        ["AR/AP Clerk"]),
    DictionaryEntry("razorpay","payout.processed",       "finance.payout.processed",       "SOP_PAYOUT_RECORDED",        ["Bookkeeper"]),
    DictionaryEntry("razorpay","payout.failed",          "finance.payout.failed",          "SOP_PAYOUT_FAILURE",         ["Bookkeeper","EA"]),
    DictionaryEntry("razorpay","transaction.created",    "finance.transaction.new",        "SOP_TRANSACTION_INGESTED",   ["Bookkeeper"]),
    DictionaryEntry("razorpay","refund.created",         "finance.refund.created",         "SOP_REFUND_RECORDED",        ["Bookkeeper","CFO"]),
    # ── ZOHO BOOKS ────────────────────────────────────────────────
    DictionaryEntry("zoho_books","invoice.created",      "finance.ap.invoice_created",     "SOP_VENDOR_INVOICE_RECEIVED",["AR/AP Clerk"]),
    DictionaryEntry("zoho_books","invoice.overdue",      "finance.ap.overdue",             "SOP_INVOICE_OVERDUE_AP",     ["AR/AP Clerk","CFO"]),
    DictionaryEntry("zoho_books","invoice.payment_made", "finance.ap.paid",                "SOP_PAYMENT_RECORDED",       ["Bookkeeper"]),
    DictionaryEntry("zoho_books","expense.created",      "finance.expense.new",            "SOP_EXPENSE_INGESTED",       ["Bookkeeper"]),
    DictionaryEntry("zoho_books","bill.created",         "finance.bill.new",               "SOP_BILL_RECEIVED",          ["AR/AP Clerk"]),
    DictionaryEntry("zoho_books","contact.created",      "ops.vendor.new",                 "SOP_NEW_VENDOR_ONBOARD",     ["Procurement","Legal"]),
    DictionaryEntry("zoho_books","journal.created",      "finance.journal.new",            "SOP_JOURNAL_RECORDED",       ["Bookkeeper"]),
    # ── GOOGLE WORKSPACE ──────────────────────────────────────────
    DictionaryEntry("google_workspace","calendar.new_event",  "ops.calendar.new_event",    "SOP_MEETING_PREP",           ["Virtual EA"]),
    DictionaryEntry("google_workspace","calendar.upcoming",   "ops.calendar.upcoming",     "SOP_MEETING_BRIEF",          ["Virtual EA"]),
    DictionaryEntry("google_workspace","team.new_member",     "people.team.new_member",    "SOP_EMPLOYEE_ONBOARD",       ["HR Coordinator"]),
    DictionaryEntry("google_workspace","team.offboard",       "people.team.offboard",      "SOP_EMPLOYEE_OFFBOARD",      ["HR","IT Admin"]),
    DictionaryEntry("google_workspace","drive.contract_new",  "legal.contract.new",        "SOP_CONTRACT_INGESTED",      ["Contracts Coordinator"]),
    # ── ESIGN ─────────────────────────────────────────────────────
    DictionaryEntry("esign","document.sent",     "legal.esign.sent",      "SOP_ESIGN_TRACKING_START", ["Contracts Coordinator"]),
    DictionaryEntry("esign","document.viewed",   "legal.esign.viewed",    "SOP_ESIGN_VIEWED",         ["Contracts Coordinator"]),
    DictionaryEntry("esign","document.signed",   "legal.esign.completed", "SOP_CONTRACT_EXECUTED",    ["Contracts Coordinator","Knowledge Manager"]),
    DictionaryEntry("esign","document.declined", "legal.esign.declined",  "SOP_ESIGN_DECLINED",       ["Contracts Coordinator","EA"]),
    DictionaryEntry("esign","document.expired",  "legal.esign.expired",   "SOP_ESIGN_EXPIRED",        ["Contracts Coordinator"]),
    # ── TELEGRAM ──────────────────────────────────────────────────
    DictionaryEntry("telegram","file.csv",          "ingestion.file.csv",          "SOP_FILE_INGESTION",        ["Bookkeeper"]),
    DictionaryEntry("telegram","pdf.bank_statement","ingestion.pdf.bank_statement","SOP_BANK_STATEMENT_INGEST", ["Bookkeeper","CFO"]),
    DictionaryEntry("telegram","pdf.invoice",       "ingestion.pdf.invoice",       "SOP_VENDOR_INVOICE_RECEIVED",["AR/AP Clerk"]),
    DictionaryEntry("telegram","pdf.contract",      "ingestion.pdf.contract",      "SOP_CONTRACT_INGESTED",     ["Contracts Coordinator"]),
    DictionaryEntry("telegram","pdf.tax_notice",    "ingestion.pdf.tax_notice",    "SOP_TAX_NOTICE_RECEIVED",   ["Compliance Tracker"]),
    DictionaryEntry("telegram","image.receipt",     "ingestion.image.receipt",     "SOP_RECEIPT_INGESTED",      ["Bookkeeper"]),
    DictionaryEntry("telegram","query.inbound",     "ops.query.inbound",           "SOP_FOUNDER_QUERY",         ["Chief of Staff"]),
    DictionaryEntry("telegram","decision.logged",   "ops.decision.logged",         "SOP_DECISION_LOGGED",       ["Knowledge Manager"]),
    # ── CRON ──────────────────────────────────────────────────────
    DictionaryEntry("cron","ops.cron.weekly",         "ops.cron.weekly",         "SOP_WEEKLY_BRIEFING",       ["Chief of Staff"]),
    DictionaryEntry("cron","compliance.cron.daily",   "compliance.cron.daily",   "SOP_COMPLIANCE_CHECK",      ["Compliance Tracker"]),
    DictionaryEntry("cron","infra.cron.cost",         "infra.cron.cost",         "SOP_CLOUD_COST_REVIEW",     ["IT Admin"]),
    DictionaryEntry("cron","finance.cron.ar_aging",   "finance.cron.ar_aging",   "SOP_AR_AGING_CHECK",        ["AR/AP Clerk"]),
    DictionaryEntry("cron","legal.cron.expiry",       "legal.cron.expiry",       "SOP_CONTRACT_EXPIRY_CHECK", ["Contracts Coordinator"]),
    DictionaryEntry("cron","intel.cron.policy",       "intel.cron.policy",       "SOP_POLICY_CRAWL",          ["Policy Watcher"]),
    DictionaryEntry("cron","infra.cron.saas_audit",   "infra.cron.saas_audit",   "SOP_SAAS_AUDIT",            ["IT Admin"]),
    DictionaryEntry("cron","people.cron.payroll",     "people.cron.payroll",     "SOP_PAYROLL_PREP",          ["Payroll Clerk"]),
    DictionaryEntry("cron","finance.cron.monthend",   "finance.cron.monthend",   "SOP_MONTH_END_CLOSE",       ["Bookkeeper","CFO"]),
    # ── AWS COST ──────────────────────────────────────────────────
    DictionaryEntry("aws_cost","cloud.daily_cost", "infra.cloud.daily_cost", "SOP_CLOUD_COST_REVIEW",    ["IT Admin"]),
    DictionaryEntry("aws_cost","cloud.spike",      "infra.cloud.spike",      "SOP_CLOUD_COST_ALERT",     ["IT Admin","CFO"]),
    DictionaryEntry("aws_cost","cloud.new_service","infra.cloud.new_service","SOP_NEW_SERVICE_DETECTED", ["IT Admin"]),
    DictionaryEntry("aws_cost","cloud.waste",      "infra.cloud.waste",      "SOP_RESOURCE_WASTE",       ["IT Admin"]),
    # ── EMAIL FORWARD ─────────────────────────────────────────────
    DictionaryEntry("email_forward","email.inbound","ingestion.email.inbound","SOP_FILE_INGESTION",["Bookkeeper"]),
]

class EventDictionary:
    def __init__(self):
        self._index = {(e.source, e.event_name): e for e in _REGISTRY}

    def resolve(self, source: str, event_name: str) -> DictionaryEntry:
        key = (source, event_name)
        if key not in self._index:
            raise UnknownEventError(
                f"No mapping for source='{source}' event_name='{event_name}'. "
                f"Add it to event_dictionary.py before handling."
            )
        return self._index[key]

    def all_entries(self) -> list[DictionaryEntry]:
        return list(self._index.values())
```

Run: `uv run pytest tests/test_event_dictionary.py -v` → **expect PASS**

Also implement mirror in Go:

**File:** `apps/core/internal/events/dictionary.go`

```go
package events

import "fmt"

type DictionaryEntry struct {
    Source    EventSource
    EventName string
    Topic     string
    SOPName   string
    Employees []string
}

var registry = []DictionaryEntry{
    {SourceRazorpay, "payment.captured",       "finance.revenue.captured",       "SOP_REVENUE_RECEIVED",        []string{"Bookkeeper","CFO"}},
    {SourceRazorpay, "payment.failed",          "finance.revenue.failed",         "SOP_PAYMENT_FAILURE",         []string{"AR/AP Clerk"}},
    {SourceRazorpay, "subscription.activated",  "finance.subscription.new",       "SOP_NEW_SUBSCRIPTION",        []string{"Bookkeeper","CFO"}},
    {SourceRazorpay, "subscription.halted",     "finance.subscription.halted",    "SOP_SUBSCRIPTION_HALTED",     []string{"AR/AP Clerk","CFO"}},
    {SourceRazorpay, "subscription.cancelled",  "finance.subscription.cancelled", "SOP_CHURN_DETECTED",          []string{"CFO","BI Analyst"}},
    {SourceRazorpay, "invoice.paid",             "finance.invoice.paid",           "SOP_INVOICE_SETTLED",         []string{"AR/AP Clerk"}},
    {SourceRazorpay, "invoice.expired",          "finance.invoice.expired",        "SOP_INVOICE_OVERDUE",         []string{"AR/AP Clerk"}},
    {SourceRazorpay, "payout.processed",         "finance.payout.processed",       "SOP_PAYOUT_RECORDED",         []string{"Bookkeeper"}},
    {SourceRazorpay, "payout.failed",            "finance.payout.failed",          "SOP_PAYOUT_FAILURE",          []string{"Bookkeeper","EA"}},
    {SourceRazorpay, "transaction.created",      "finance.transaction.new",        "SOP_TRANSACTION_INGESTED",    []string{"Bookkeeper"}},
    {SourceRazorpay, "refund.created",           "finance.refund.created",         "SOP_REFUND_RECORDED",         []string{"Bookkeeper","CFO"}},
    // add all other sources following same pattern...
}

var index map[string]DictionaryEntry

func init() {
    index = make(map[string]DictionaryEntry)
    for _, e := range registry {
        key := fmt.Sprintf("%s::%s", e.Source, e.EventName)
        index[key] = e
    }
}

func Resolve(source EventSource, eventName string) (DictionaryEntry, error) {
    key := fmt.Sprintf("%s::%s", source, eventName)
    e, ok := index[key]
    if !ok {
        return DictionaryEntry{}, fmt.Errorf(
            "no mapping for source=%q event_name=%q — add to dictionary.go",
            source, eventName,
        )
    }
    return e, nil
}
```

***

## PHASE 3 — DATABASE MIGRATIONS
*Append-only. Never touch existing tables.*

### 3.1 — Write test FIRST

**File:** `apps/core/internal/db/raw_events_test.go`

```go
// tests/test_raw_events_db.go
// Must run against real Docker PostgreSQL
func TestRawEventInsertAndFetch(t *testing.T) {
    db := connectTestDB(t) // reuse existing test DB helper
    id := uuid.New().String()
    _, err := db.Exec(`
        INSERT INTO raw_events (id, founder_id, source, event_name, topic,
            sop_name, payload_hash, payload_body, received_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
    `, id, "founder_test", "razorpay", "payment.captured",
       "finance.revenue.captured", "SOP_REVENUE_RECEIVED",
       "sha256:abc", `{"payment_id":"pay_test"}`)
    require.NoError(t, err)

    var count int
    db.QueryRow("SELECT COUNT(*) FROM raw_events WHERE id=$1", id).Scan(&count)
    assert.Equal(t, 1, count)
}
```

Run: `go test ./internal/db -run TestRawEvent -v` → **expect FAIL**

### 3.2 — Implement migration

**File:** `apps/core/internal/db/migrations/009_sarthi_sop_runtime.sql`

```sql
-- ──────────────────────────────────────────────────────────────
-- MIGRATION 009: OntologyAI SOP Runtime tables
-- APPEND ONLY. Never drop existing tables.
-- ──────────────────────────────────────────────────────────────

-- Raw event archive — every event ever received, unmodified
CREATE TABLE IF NOT EXISTS raw_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id      UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    source          VARCHAR(50) NOT NULL,
    event_name      VARCHAR(100) NOT NULL,
    topic           VARCHAR(150) NOT NULL,
    sop_name        VARCHAR(100) NOT NULL,
    payload_hash    VARCHAR(100) NOT NULL,    -- SHA-256 of raw body
    payload_body    JSONB NOT NULL,           -- raw payload stored once here
    signature_valid BOOLEAN DEFAULT TRUE,
    received_at     TIMESTAMPTZ DEFAULT NOW(),
    idempotency_key VARCHAR(200),
    UNIQUE(idempotency_key)                   -- dedup at DB level
);
CREATE INDEX IF NOT EXISTS raw_events_founder_source
    ON raw_events(founder_id, source, received_at DESC);

-- SOP execution jobs — one row per SOP invocation
CREATE TABLE IF NOT EXISTS sop_jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id       UUID NOT NULL REFERENCES founders(id),
    raw_event_id     UUID REFERENCES raw_events(id),
    sop_name         VARCHAR(100) NOT NULL,
    temporal_run_id  VARCHAR(200),
    status           VARCHAR(30) DEFAULT 'pending',
    -- pending | running | completed | failed | hitl_waiting
    hitl_level       VARCHAR(10),  -- low | medium | high
    input_ref        VARCHAR(200), -- "sop_jobs:<uuid>" passed to Temporal
    output_ref       VARCHAR(200),
    error_message    TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sop_jobs_founder_sop
    ON sop_jobs(founder_id, sop_name, created_at DESC);

-- Connector states — OAuth tokens, sync cursors
CREATE TABLE IF NOT EXISTS connector_states (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id      UUID NOT NULL REFERENCES founders(id),
    connector       VARCHAR(50) NOT NULL,   -- razorpay | zoho_books | etc
    access_token    TEXT,                   -- encrypted at app layer
    refresh_token   TEXT,
    token_expires_at TIMESTAMPTZ,
    last_sync_at    TIMESTAMPTZ,
    backfill_done   BOOLEAN DEFAULT FALSE,
    backfill_cursor VARCHAR(200),
    health          VARCHAR(20) DEFAULT 'active',  -- active | degraded | dead
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(founder_id, connector)
);

-- Dead letter queue — events that failed processing
CREATE TABLE IF NOT EXISTS dead_letter_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_event_id    UUID REFERENCES raw_events(id),
    founder_id      UUID,
    failure_reason  TEXT NOT NULL,
    retry_count     INT DEFAULT 0,
    last_retry_at   TIMESTAMPTZ,
    resolved        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Transactions — normalized ledger
CREATE TABLE IF NOT EXISTS transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id      UUID NOT NULL REFERENCES founders(id),
    raw_event_id    UUID REFERENCES raw_events(id),
    txn_date        DATE NOT NULL,
    description     TEXT NOT NULL,
    debit           NUMERIC(18,2) DEFAULT 0,
    credit          NUMERIC(18,2) DEFAULT 0,
    balance         NUMERIC(18,2),
    category        VARCHAR(50),
    category_confidence FLOAT,
    source          VARCHAR(50),   -- hdfc | icici | razorpay | zoho | manual
    external_id     VARCHAR(200),  -- payment_id / txn_id from source
    qdrant_point_id VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(founder_id, external_id)
);
CREATE INDEX IF NOT EXISTS transactions_founder_date
    ON transactions(founder_id, txn_date DESC);

-- Accounts payable
CREATE TABLE IF NOT EXISTS accounts_payable (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id      UUID NOT NULL REFERENCES founders(id),
    vendor_name     VARCHAR(200) NOT NULL,
    amount          NUMERIC(18,2) NOT NULL,
    currency        CHAR(3) DEFAULT 'INR',
    due_date        DATE,
    invoice_number  VARCHAR(100),
    source          VARCHAR(50),
    status          VARCHAR(30) DEFAULT 'pending_approval',
    raw_event_id    UUID REFERENCES raw_events(id),
    approved_at     TIMESTAMPTZ,
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Compliance calendar
CREATE TABLE IF NOT EXISTS compliance_calendar (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    founder_id      UUID NOT NULL REFERENCES founders(id),
    jurisdiction    VARCHAR(20) DEFAULT 'IN',
    filing_type     VARCHAR(100) NOT NULL,  -- GST_MONTHLY | TDS_Q1 | etc
    due_date        DATE NOT NULL,
    description     TEXT,
    status          VARCHAR(30) DEFAULT 'pending',
    data_ref        VARCHAR(200),           -- prepared filing data reference
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- SOP output findings — typed results from every SOP
CREATE TABLE IF NOT EXISTS sop_findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sop_job_id      UUID REFERENCES sop_jobs(id),
    founder_id      UUID NOT NULL REFERENCES founders(id),
    sop_name        VARCHAR(100) NOT NULL,
    finding_type    VARCHAR(50),
    headline        TEXT,
    body            TEXT,
    do_this         TEXT,
    hitl_risk       VARCHAR(10),
    telegram_sent   BOOLEAN DEFAULT FALSE,
    telegram_msg_id VARCHAR(100),
    is_good_news    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

Apply: `psql $DATABASE_URL -f apps/core/internal/db/migrations/009_sarthi_sop_runtime.sql`

Run: `go test ./internal/db -run TestRawEvent -v` → **expect PASS**

***

## PHASE 4 — GO WEBHOOK HANDLERS
*Validate → persist raw event → publish envelope to Redpanda. Nothing else.*

### 4.1 — Write tests FIRST

**File:** `apps/core/internal/api/razorpay_test.go`

```go
func TestRazorpaySignatureValid(t *testing.T) {
    // Construct a test payload and compute valid HMAC-SHA256
    // Assert handler returns 200 and persists raw_event row
}

func TestRazorpaySignatureInvalid(t *testing.T) {
    // Send bad signature header
    // Assert handler returns 401
    // Assert NO raw_event row persisted
}

func TestRazorpayUnknownEventSentToDLQ(t *testing.T) {
    // Send valid signature but unrecognized event_name
    // Assert raw_event persisted with status = "unknown_event"
    // Assert dead_letter_events row created
    // Assert NO SOP triggered
}

func TestRazorpayPaymentCapturedPublishesToRedpanda(t *testing.T) {
    // Send valid payment.captured payload
    // Assert message published to "finance.revenue.captured" topic
    // Assert sop_jobs row created with sop_name = "SOP_REVENUE_RECEIVED"
}
```

Run: `go test ./internal/api -run TestRazorpay -v` → **expect FAIL**

### 4.2 — Implement

**File:** `apps/core/internal/api/razorpay.go`

```go
package api

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"

    "github.com/gofiber/fiber/v2"
    "your/module/internal/db"
    "your/module/internal/events"
    "your/module/internal/redpanda"
)

type RazorpayHandler struct {
    secret    string
    store     db.RawEventStore
    producer  redpanda.Producer
    dict      *events.Dictionary
}

func (h *RazorpayHandler) Handle(c *fiber.Ctx) error {
    // 1. Verify HMAC-SHA256
    sig := c.Get("X-Razorpay-Signature")
    if !h.verifySignature(c.Body(), sig) {
        return c.Status(401).JSON(fiber.Map{"error": "invalid signature"})
    }

    // 2. Parse event name from body — handle JSON parse errors
    var raw map[string]interface{}
    if err := json.Unmarshal(c.Body(), &raw); err != nil {
        // Log error and return 400 — invalid JSON payload
        return c.Status(400).JSON(fiber.Map{"error": "invalid_json", "details": err.Error()})
    }
    eventName, ok := raw["event"].(string)
    if !ok || eventName == "" {
        // Missing or invalid event name — DLQ for investigation
        h.store.InsertDLQ(c.Context(), "unknown", "missing_event_name", c.Body())
        return c.Status(200).JSON(fiber.Map{"status": "dlq_missing_event_name"})
    }

    // 3. Resolve via event dictionary
    entry, err := h.dict.Resolve(events.SourceRazorpay, eventName)
    if err != nil {
        // Unknown event → DLQ, return 200 to Razorpay (don't fail the webhook)
        h.store.InsertDLQ(c.Context(), eventName, "unknown_event", c.Body())
        return c.Status(200).JSON(fiber.Map{"status": "unknown_event_dlq"})
    }

    // 4. Persist raw event FIRST (payload stored here, not in Temporal)
    rawEventID, err := h.store.InsertRawEvent(c.Context(), db.RawEvent{
        FounderID:   resolveFounderFromAPIKey(c),
        Source:      "razorpay",
        EventName:   eventName,
        Topic:       entry.Topic,
        SOPName:     entry.SOPName,
        PayloadHash: computeHash(c.Body()),
        PayloadBody: c.Body(),
    })
    if err != nil {
        // Duplicate idempotency key — already processed
        if isDuplicateKey(err) {
            return c.Status(200).JSON(fiber.Map{"status": "duplicate"})
        }
        return c.Status(500).JSON(fiber.Map{"error": "storage_failed"})
    }

    // 5. Publish envelope (ref only, not raw payload) — handle publish errors
    envelope := events.EventEnvelope{
        Source:     events.SourceRazorpay,
        EventName:  eventName,
        Topic:      entry.Topic,
        SOPName:    entry.SOPName,
        PayloadRef: "raw_events:" + rawEventID,
        // ... other fields
    }
    if err := h.producer.Publish(entry.Topic, envelope); err != nil {
        // Publish failed — DLQ the event for retry, return 500
        h.store.InsertDLQ(c.Context(), eventName, "publish_failed", c.Body())
        return c.Status(500).JSON(fiber.Map{"error": "publish_failed", "details": err.Error()})
    }

    return c.Status(200).JSON(fiber.Map{"status": "accepted"})
}

func (h *RazorpayHandler) verifySignature(body []byte, sig string) bool {
    mac := hmac.New(sha256.New, []byte(h.secret))
    mac.Write(body)
    expected := hex.EncodeToString(mac.Sum(nil))
    return hmac.Equal([]byte(expected), []byte(sig))
}
```

**File:** `apps/core/internal/api/telegram.go`

```go
// Key rules:
// 1. File uploads: persist to disk/S3, store file_path in raw_events.payload_body
// 2. Text messages: classify intent (question | decision | command)
// 3. NEVER classify files in this handler — only persist + route
// 4. DocumentClassifier runs in Python SOP, not here

func (h *TelegramHandler) HandleUpdate(c *fiber.Ctx) error {
    // parse Telegram Update
    // if message.document → persist file → produce to ingestion.file.{ext}
    // if message.photo   → persist file → produce to ingestion.image.receipt
    // if message.text    → produce to ops.query.inbound (CoS will classify)
    // Always return 200 to Telegram
}
```

Run: `go test ./internal/api -v` → **expect PASS**

***

## PHASE 5 — TEMPORAL WORKFLOW REDESIGN
*Parent = pure router. Children = SOP executors. Pass refs not payloads.*

### 5.1 — Write tests FIRST

**File:** `apps/core/internal/workflow/sop_router_test.go`

```go
func TestSOPRouterSpawnsCorrectChildWorkflow(t *testing.T) {
    // Use Temporal's test workflow env
    // Signal with event envelope containing sop_name=SOP_REVENUE_RECEIVED
    // Assert child workflow SOP_REVENUE_RECEIVED was started
    // Assert parent did NOT execute SOP logic itself
}

func TestContinueAsNewTriggersBeforeLimit(t *testing.T) {
    // Simulate 5000 events
    // Assert Continue-As-New fired before 10000
}

func TestDuplicateEnvelopeShortCircuits(t *testing.T) {
    // Send same idempotency_key twice
    // Assert second invocation returns immediately without spawning child
}
```

### 5.2 — Implement

**File:** `apps/core/internal/workflow/business_os_workflow.go`

```go
package workflow

import (
    "go.temporal.io/sdk/workflow"
    "your/module/internal/events"
)

const ContinueAsNewThreshold = 5000

type BusinessOSState struct {
    EventsProcessed int
    FounderID       string
    SeenKeys        map[string]bool
}

func BusinessOSWorkflow(ctx workflow.Context, founderID string) error {
    state := BusinessOSState{
        FounderID: founderID,
        SeenKeys:  make(map[string]bool),
    }

    ch := workflow.GetSignalChannel(ctx, "ontology_ai.business.events")

    for {
        // Continue-As-New BEFORE hitting Temporal history limits
        if state.EventsProcessed >= ContinueAsNewThreshold {
            return workflow.NewContinueAsNewError(ctx, BusinessOSWorkflow, founderID)
        }

        var envelope events.EventEnvelope
        ch.Receive(ctx, &envelope)

        // Idempotency — skip duplicates
        if state.SeenKeys[envelope.IdempotencyKey] {
            continue
        }
        state.SeenKeys[envelope.IdempotencyKey] = true
        state.EventsProcessed++

        // Spawn child workflow — parent does NOT execute SOP logic
        childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
            WorkflowID: "sop:" + envelope.SOPName + ":" + envelope.EventID,
            TaskQueue:  "AI_TASK_QUEUE",
        })
        workflow.ExecuteChildWorkflow(childCtx, envelope.SOPName, envelope)
        // Fire and continue — parent does not wait for SOP completion
    }
}
```

**File:** `apps/core/internal/workflow/cron_workflows.go`

```go
// Separate scheduled workflows for crons — NOT signals in BusinessOSWorkflow
// Each cron fires a new child workflow directly

func WeeklyBriefingCron(ctx workflow.Context) error {
    // Runs every Monday 09:00 IST
    // Produces envelope to SOP_WEEKLY_BRIEFING child
}

func ComplianceCheckCron(ctx workflow.Context) error {
    // Runs daily 06:00 IST
}

func CloudCostCron(ctx workflow.Context) error {
    // Runs daily 06:30 IST
}
// ... register all crons from event dictionary
```

***

## PHASE 6 — PYTHON SOP REGISTRY AND BASE CLASS

### 6.1 — Write test FIRST

**File:** `apps/ai/tests/test_sop_registry.py`

```python
from src.sops.registry import SOPRegistry
import pytest

def test_all_dictionary_sops_have_registered_executor():
    from src.config.event_dictionary import _REGISTRY
    registry = SOPRegistry()
    sops_in_dict = {e.sop for e in _REGISTRY}
    for sop_name in sops_in_dict:
        if sop_name == "SOP_FILE_INGESTION":
            continue  # router, not executor
        assert registry.has(sop_name), \
            f"SOP '{sop_name}' in dictionary but no executor registered. Add it."

def test_registry_returns_correct_executor_class():
    from src.sops.revenue_received import RevenueReceivedSOP
    registry = SOPRegistry()
    executor = registry.get("SOP_REVENUE_RECEIVED")
    assert isinstance(executor, RevenueReceivedSOP)
```

### 6.2 — Implement

**File:** `apps/ai/src/sops/base.py`

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any

class SOPResult(BaseModel):
    sop_name:      str
    founder_id:    str
    success:       bool
    fire_alert:    bool = False
    hitl_risk:     str = "low"   # low | medium | high
    headline:      str = ""
    do_this:       str = ""
    is_good_news:  bool = False
    output:        dict = {}
    error:         str | None = None

class BaseSOP(ABC):
    sop_name: str

    @abstractmethod
    async def execute(self, payload_ref: str, founder_id: str) -> SOPResult:
        """Fetch payload from PostgreSQL via payload_ref, execute SOP, return result."""
        ...

    def fetch_payload(self, payload_ref: str) -> dict:
        """Resolve payload_ref → PostgreSQL row → return parsed dict."""
        # "raw_events:<uuid>" → SELECT payload_body FROM raw_events WHERE id=<uuid>
        ...
```

**File:** `apps/ai/src/sops/registry.py`

```python
from src.sops.base import BaseSOP

_REGISTRY: dict[str, BaseSOP] = {}

def register(sop: BaseSOP):
    _REGISTRY[sop.sop_name] = sop

class SOPRegistry:
    def has(self, sop_name: str) -> bool:
        return sop_name in _REGISTRY

    def get(self, sop_name: str) -> BaseSOP:
        if sop_name not in _REGISTRY:
            raise KeyError(f"No executor for SOP '{sop_name}'. Register it in registry.py")
        return _REGISTRY[sop_name]

# Auto-import all SOPs so they self-register
from src.sops import (
    revenue_received,
    bank_statement_ingest,
    vendor_invoice_received,
    employee_onboard,
    compliance_check,
    meeting_prep,
    weekly_briefing,
    decision_logged,
)
```

***

## PHASE 7 — THE THREE PRIORITY SOPs
*Implement these three first. They prove the full pipeline.*

### SOP 1 — SOP_REVENUE_RECEIVED

**File:** `apps/ai/tests/test_sop_revenue_received.py`

```python
import pytest, uuid
from src.sops.revenue_received import RevenueReceivedSOP
from src.schemas.finance import RevenueReceivedInput

# These run against REAL PostgreSQL + REAL Azure LLM
class TestSOPRevenueReceived:

    @pytest.fixture
    def sop(self): return RevenueReceivedSOP()

    @pytest.mark.asyncio
    async def test_normal_payment_logs_silently(self, sop, seed_founder):
        """Regular payment below milestone should log without Telegram alert"""
        raw_event_id = seed_raw_event(
            source="razorpay",
            event_name="payment.captured",
            payload={
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_test123",
                            "amount": 5000_00,  # ₹5000 in paise
                            "currency": "INR",
                            "method": "upi",
                            "description": "SaaS subscription",
                            "captured": True,
                        }
                    }
                }
            }
        )
        result = await sop.execute(
            payload_ref=f"raw_events:{raw_event_id}",
            founder_id=seed_founder
        )
        assert result.success is True
        assert result.fire_alert is False   # below milestone, silent

    @pytest.mark.asyncio
    async def test_mrr_milestone_fires_positive_trigger(self, sop, seed_founder):
        """Crossing ₹5L MRR should fire a celebratory alert"""
        # Seed enough previous revenue so this payment crosses ₹5L MRR
        seed_mrr_state(seed_founder, mrr_before=490_000)
        raw_event_id = seed_raw_event(source="razorpay", event_name="payment.captured",
            payload={"payload":{"payment":{"entity":{"id":"pay_mrr","amount":1500000,
            "currency":"INR","method":"card","description":"Enterprise plan"}}}})
        result = await sop.execute(f"raw_events:{raw_event_id}", seed_founder)
        assert result.fire_alert is True
        assert result.is_good_news is True
        assert "MRR" in result.headline or "5L" in result.headline

    @pytest.mark.asyncio
    async def test_concentration_risk_fires_when_customer_exceeds_30_pct(self, sop, seed_founder):
        # Seed: one customer is already 28% of 90-day revenue
        # This payment pushes them to 34%
        result = await sop.execute(...)
        assert "concentration" in result.output.get("alerts", [])
```

**File:** `apps/ai/src/sops/revenue_received.py`

```python
from src.sops.base import BaseSOP, SOPResult
from src.config.llm import get_llm_client, get_chat_model
from src.db.transactions import insert_transaction, get_90_day_revenue_by_customer
from src.db.raw_events import fetch_raw_event
from src.memory.qdrant_client import upsert_memory
from src.sops.registry import register

class RevenueReceivedSOP(BaseSOP):
    sop_name = "SOP_REVENUE_RECEIVED"

    async def execute(self, payload_ref: str, founder_id: str) -> SOPResult:
        # 1. Fetch payload from PostgreSQL
        raw = fetch_raw_event(payload_ref)
        entity = raw["payload"]["payment"]["entity"]

        # 2. Categorize (auto high confidence — it's revenue)
        amount_inr = entity["amount"] / 100  # paise → rupees

        # 3. Write transaction
        insert_transaction(founder_id=founder_id,
            txn_date=today(), description=entity.get("description","Payment"),
            credit=amount_inr, category="Revenue", confidence=1.0,
            source="razorpay", external_id=entity["id"])

        # 4. Update CFO state + check milestones
        milestones = check_mrr_milestones(founder_id, amount_inr)
        concentration = check_concentration_risk(founder_id, entity.get("customer_id"))

        # 5. Log to Qdrant memory
        upsert_memory(founder_id=founder_id,
            content=f"Revenue ₹{amount_inr:,.0f} received via Razorpay: {entity.get('description')}",
            memory_type="transaction", source="razorpay")

        fire = bool(milestones or concentration)
        headline = ""
        if milestones:
            headline = f"You just crossed {milestones[0]} 🎉 Runway updated."
        elif concentration:
            headline = f"This customer is now {concentration['pct']:.0f}% of your revenue — worth watching."

        return SOPResult(sop_name=self.sop_name, founder_id=founder_id,
            success=True, fire_alert=fire,
            headline=headline, is_good_news=bool(milestones),
            hitl_risk="low",
            output={"milestones": milestones, "concentration": concentration})

register(RevenueReceivedSOP())
```

### SOP 2 — SOP_BANK_STATEMENT_INGEST

**File:** `apps/ai/tests/test_sop_bank_statement_ingest.py`

```python
class TestBankStatementIngest:

    @pytest.mark.asyncio
    async def test_hdfc_csv_ingested_correctly(self):
        """Real HDFC CSV → normalized transactions → PostgreSQL"""

    @pytest.mark.asyncio
    async def test_duplicate_transactions_skipped(self):
        """Second upload of same CSV should skip all duplicates"""
        # Upload once
        result1 = await sop.execute(...)
        # Upload same file again
        result2 = await sop.execute(...)
        assert result2.output["transactions_skipped"] == result1.output["transactions_ingested"]
        assert result2.output["transactions_ingested"] == 0

    @pytest.mark.asyncio
    async def test_low_confidence_transaction_flagged(self):
        """Category confidence < 0.7 must produce review flag"""

    @pytest.mark.asyncio
    async def test_runway_below_90_days_fires_alert(self):
        """If 13-week forecast shows < 90 days runway, fire_alert must be True"""

    @pytest.mark.asyncio
    async def test_telegram_message_contains_no_jargon(self):
        """Output headline must pass ToneFilter jargon validator"""
        from src.schemas.validators import BANNED_JARGON
        result = await sop.execute(...)
        for term in BANNED_JARGON:
            assert term.lower() not in result.headline.lower()
```

### SOP 3 — SOP_WEEKLY_BRIEFING

**File:** `apps/ai/tests/test_sop_weekly_briefing.py`

```python
class TestWeeklyBriefing:

    @pytest.mark.asyncio
    async def test_briefing_contains_max_5_items(self):
        result = await sop.execute(payload_ref="cron", founder_id=seed_founder)
        items = result.output.get("items", [])
        assert len(items) <= 5

    @pytest.mark.asyncio
    async def test_briefing_always_includes_at_least_one_positive_if_exists(self):
        seed_positive_event(seed_founder)  # e.g. MRR milestone
        result = await sop.execute(...)
        items = result.output.get("items", [])
        assert any(i.get("is_good_news") for i in items)

    @pytest.mark.asyncio
    async def test_briefing_output_is_jargon_free(self):
        result = await sop.execute(...)
        from src.schemas.validators import BANNED_JARGON
        full_text = result.headline + " " + result.do_this
        for term in BANNED_JARGON:
            assert term.lower() not in full_text.lower()

    @pytest.mark.asyncio
    async def test_briefing_uses_real_azure_llm_not_mock(self):
        """Confirm the LLM was actually called — Langfuse trace exists"""
        result = await sop.execute(...)
        # Assert Langfuse has a trace for this execution
        assert langfuse_has_trace(result.output.get("trace_id"))
```

***

## PHASE 8 — FULL E2E TESTS

**File:** `apps/ai/tests/test_e2e_sop_flows.py`

```python
# Full stack tests — real Docker, real LLM, real Redpanda, real Temporal

class TestE2ERevenueReceived:
    """Razorpay payment.captured → full SOP execution → PostgreSQL row"""

    @pytest.mark.asyncio
    async def test_razorpay_payment_captured_full_flow(self, http_client):
        # 1. Simulate valid Razorpay webhook to Go Fiber
        payload = build_razorpay_payment_captured_payload(amount=7500_00)
        sig = compute_razorpay_hmac(payload, secret=os.environ["RAZORPAY_WEBHOOK_SECRET"])
        resp = await http_client.post(
            "/webhooks/razorpay",
            content=payload,
            headers={"X-Razorpay-Signature": sig}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # 2. Wait for Temporal to process (poll sop_jobs table)
        job = await wait_for_sop_job(sop_name="SOP_REVENUE_RECEIVED", timeout=30)
        assert job["status"] == "completed"

        # 3. Assert transaction persisted
        txn = await get_transaction_by_external_id("pay_test_flow")
        assert txn is not None
        assert txn["category"] == "Revenue"


class TestE2EBankStatementIngest:
    """Telegram PDF upload → SOP_BANK_STATEMENT_INGEST → transactions"""

    @pytest.mark.asyncio
    async def test_telegram_hdfc_pdf_full_flow(self, http_client, sample_hdfc_pdf):
        resp = await http_client.post("/webhooks/telegram",
            json=build_telegram_document_update(sample_hdfc_pdf))
        assert resp.status_code == 200
        job = await wait_for_sop_job("SOP_BANK_STATEMENT_INGEST", timeout=60)
        assert job["status"] == "completed"
        count = await count_transactions(founder_id=TEST_FOUNDER_ID)
        assert count > 0


class TestE2EWeeklyBriefing:
    """Monday 9am cron → SOP_WEEKLY_BRIEFING → Telegram message"""

    @pytest.mark.asyncio
    async def test_weekly_briefing_cron_fires_and_produces_message(self):
        # Trigger the weekly cron manually
        trigger_temporal_cron("WeeklyBriefingCron")
        job = await wait_for_sop_job("SOP_WEEKLY_BRIEFING", timeout=60)
        assert job["status"] == "completed"
        finding = await get_latest_finding("SOP_WEEKLY_BRIEFING")
        assert finding["telegram_sent"] is True
        assert len(finding["headline"]) > 10
```

***

## PHASE 9 — CONNECTOR LAYER

### 9.1 Razorpay backfill

**File:** `apps/core/internal/connectors/razorpay/backfill.go`

```go
// On first connect: pull last 90 days via Razorpay Fetch Payments API
// Convert each to payment.captured envelope
// Push to Redpanda with idempotency_key = "razorpay:backfill:{payment_id}"
// Duplicate protection in PostgreSQL UNIQUE(idempotency_key) handles re-runs
```

### 9.2 Zoho Books polling fallback

**File:** `apps/core/internal/connectors/zoho_books/poller.go`

```go
// Temporal scheduled workflow: every 15 minutes
// Fetch invoices modified since last_sync_at
// Normalize to zoho_books event envelopes
// Publish to Redpanda
// Update connector_states.last_sync_at
```

### 9.3 Google Workspace poller

**File:** `apps/core/internal/connectors/google_workspace/poller.go`

```go
// Calendar: Google Calendar Push Notifications (webhook) + 15min polling fallback
// Drive /contracts/ folder: polling every 15min for new files
// Directory: polling every 15min for new/removed users
```

***

## PHASE 10 — UPDATE TEST RUNNER

**File:** `scripts/test_ontology_ai.sh`

```bash
#!/bin/bash
set -e

echo "═══════════════════════════════════════════════"
echo " SARTHI Full Test Suite — Real Docker + Azure"
echo "═══════════════════════════════════════════════"

# ── 1. Infrastructure health ──────────────────────
echo "[1/6] Checking Docker services..."
REQUIRED="temporal redpanda postgres qdrant langfuse neo4j"
for svc in $REQUIRED; do
    docker compose ps | grep "$svc" | grep -q "healthy\|running" || {
        echo "✗ $svc not healthy. Run: docker compose up -d"
        exit 1
    }
    echo "  ✓ $svc"
done

# ── 2. Azure LLM connectivity ─────────────────────
echo "[2/6] Checking Azure LLM..."
cd apps/ai
uv run python -c "
from src.config.llm import get_llm_client, get_chat_model
r = get_llm_client().chat.completions.create(
    model=get_chat_model(),
    messages=[{'role':'user','content':'ping'}],
    max_tokens=3
)
print('  ✓ Azure LLM:', r.model)
"

# ── 3. Event Dictionary tests ─────────────────────
echo "[3/6] Event dictionary + envelope tests..."
uv run pytest tests/test_event_dictionary.py tests/test_event_envelope.py \
    -v --tb=short --timeout=30

# ── 4. Python SOP unit tests ──────────────────────
echo "[4/6] Python SOP tests (real LLM, real Docker)..."
uv run pytest tests/test_sop_*.py \
    -v --tb=short --timeout=90 -x

# ── 5. Go tests ───────────────────────────────────
echo "[5/6] Go tests..."
cd ../core
go test ./... -v -timeout=60s

# ── 6. E2E flows ──────────────────────────────────
echo "[6/6] E2E flows..."
cd ../ai
uv run pytest tests/test_e2e_sop_flows.py \
    -v --tb=short --timeout=120 -x

echo ""
echo "═══════════════════════════════════════════════"
echo " ALL TESTS PASSED ✓"
echo " OntologyAI SOP Runtime is operational."
echo "═══════════════════════════════════════════════"
```

***

## DEFINITION OF DONE

This implementation is complete only when **all** of the following are true:

```
✅ Migration 009 applied — all new tables exist
✅ Event Dictionary covers all 48 events from design doc
✅ Razorpay payment.captured webhook verified, persisted, routed
✅ Telegram PDF bank statement classified and routed
✅ BusinessOSWorkflow spawns child workflows (not executes SOPs itself)
✅ Continue-As-New fires at 5000 events (not at Temporal's hard limit)
✅ Payloads passed by ref (raw_events:uuid), never inline in Temporal state
✅ SOP_REVENUE_RECEIVED passes all unit + E2E tests
✅ SOP_BANK_STATEMENT_INGEST deduplicates correctly
✅ SOP_WEEKLY_BRIEFING produces max 5 items, jargon-free
✅ All SOP outputs pass ToneFilter jargon validator
✅ Langfuse traces every SOP execution
✅ All tests use real Docker, real Azure LLM, zero mocks
✅ bash scripts/test_ontology_ai.sh → all green
```

```
DO NOT MARK COMPLETE IF:
✗ Any test uses pytest-mock on Docker infrastructure
✗ Any Temporal workflow passes raw JSON in signals
✗ Any founder-facing string contains banned jargon
✗ E2E test does not actually trigger a Temporal child workflow
```
