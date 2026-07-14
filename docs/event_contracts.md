# OntologyAI Event Contracts

## Redpanda Topics

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `ontology_ai.ingress.events` | API Gateway | Decision Engine | Raw webhook events |
| `ontology_ai.decision.requests` | Decision Engine | Workflow Service | Watchlist evaluation requests |
| `ontology_ai.decision.results` | Decision Engine | Delivery Service | Guardian decisions |
| `ontology_ai.workflow.triggers` | Workflow Service | Decision Engine | Scheduled triggers |
| `ontology_ai.delivery.requests` | Workflow Service | Delivery Service | Outbound notification requests |
| `ontology_ai.delivery.results` | Delivery Service | API Gateway | Delivery status |
| `ontology_ai.memory.updates` | Any Service | Memory Service | Context updates |
| `ontology_ai.hitl.decisions` | Decision Engine | API Gateway | Human approval outcomes |

---

## Event Schemas

### 1. Ingress Event (`ontology_ai.ingress.events`)

```json
{
  "event_id": "uuid",
  "tenant_id": "string",
  "source": "stripe|slack|telegram|razorpay",
  "event_type": "string",
  "timestamp": "RFC3339",
  "payload": {
    "raw": "base64 encoded",
    "normalized": {}
  }
}
```

### 2. Decision Request (`ontology_ai.decision.requests`)

```json
{
  "request_id": "uuid",
  "tenant_id": "string",
  "event_id": "string",
  "signals": {},
  "patterns": ["FG-01", "BG-03"],
  "triggered_at": "RFC3339"
}
```

### 3. Decision Result (`ontology_ai.decision.results`)

```json
{
  "decision_id": "uuid",
  "request_id": "string",
  "tenant_id": "string",
  "should_alert": true,
  "severity": "critical|warning|info",
  "pattern_name": "string",
  "insight": "string",
  "confidence": 0.85,
  "hitl_required": true,
  "timestamp": "RFC3339"
}
```

### 4. Delivery Request (`ontology_ai.delivery.requests`)

```json
{
  "delivery_id": "uuid",
  "tenant_id": "string",
  "decision_id": "string",
  "channel": "slack|telegram",
  "recipient": "string",
  "message": {},
  "timestamp": "RFC3339"
}
```

### 5. Memory Update (`ontology_ai.memory.updates`)

```json
{
  "update_id": "uuid",
  "tenant_id": "string",
  "entity_type": "episode|entity|edge",
  "entity_id": "string",
  "operation": "create|update|delete",
  "payload": {},
  "timestamp": "RFC3339"
}
```

---

## Contract Tests (TDD)

```python
# test_event_contracts.py

def test_ingress_event_validates():
    schema = IngressEvent()
    event = {
        "event_id": "123",
        "tenant_id": "tenant-1",
        "source": "stripe",
        "event_type": "payment.succeeded",
        "timestamp": "2026-04-27T12:00:00Z",
        "payload": {"normalized": {}}
    }
    assert schema.validate(event) is not None

def test_decision_result_has_required_fields():
    schema = DecisionResult()
    result = {
        "decision_id": "123",
        "request_id": "456",
        "tenant_id": "tenant-1",
        "should_alert": True,
        "severity": "critical",
        "pattern_name": "FG-01",
        "confidence": 0.85
    }
    assert schema.validate(result)

def test_tenant_isolation_in_event():
    # Tenant A's event should never contain Tenant B's data
    pass
```

---

## Topic Creation (Auto-provisioned)

The Go API Gateway already creates these topics in `client.go`:
- `ontology_ai.slack.events`
- `ontology_ai.stripe.events`
- `ontology_ai.guardian.results`
- `ontology_ai.hitl.decisions`

Add remaining topics to `ensureTopic()` in `internal/redpanda/client.go`.