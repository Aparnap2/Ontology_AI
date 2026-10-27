# Connector Contracts — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

Every capability op the control plane can invoke, its authority requirement, its
verification route, and its failure semantics.

---

## 1. The contract

Every op, without exception, must satisfy all five:

| # | Requirement | Enforced at |
|---|---|---|
| 1 | Operation name is inside the trusted allowlist | `capability_ops.py:433-436` |
| 2 | `role_caps` is neither `None` nor empty | `capability_ops.py:426-432` |
| 3 | Risk tier comes from trusted state | `policy.py:41-48` |
| 4 | Execute is preceded by an atomic idempotency claim | `ingress.py:112-122` |
| 5 | A governed write is verified before the claim is committed | `ingress.py:180-189` |

Ops are frozen vocabulary, built at module level
(`src/mission/capability_ops.py:248-300` — `_read_op`, `_search_op`, `_write_op`)
and reused identically by the vendor vocabulary module
(`src/mission/capability_ops_vendor.py`).

---

## 2. Op inventory

`READ_COUNTERPART` at `src/mission/verify.py:28-34` is the authoritative
verification route map.

| Op | Kind | Governed | Capability | Read counterpart | Verification route |
|---|---|---|---|---|---|
| `salesforce.read` | read | no | crm | — | n/a |
| `salesforce.update` | **write** | yes | crm | `salesforce.read` | read-back |
| `slack.search` | search | no | messaging | — | n/a |
| `slack.send` | **write** | yes | messaging | `slack.search` | read-back |
| `jira.search` | search | no | project | — | n/a |
| `jira.read` | read | no | project | — | n/a |
| `jira.create` | **write** | yes | project | `jira.read` | read-back, keyed on the id minted at write time |
| `jira.update` | **write** | yes | project | `jira.read` | read-back |
| `notion.read` | read | no | knowledge | — | n/a |
| `notion.update` | **write** | yes | knowledge | `notion.read` | read-back |

Vendor ops (`src/mission/capability_ops_vendor.py`) intentionally have **no**
read counterpart and use the vendor-specific `incident.verify_recovery` path
instead — fail-closed, never a silent pass (documented at `verify.py:24-27`).

---

## 3. Read-back derivation per op

`src/mission/verify.py:70-85 _read_params_for`:

| Write op | Read-back params |
|---|---|
| `salesforce.update` | `{"object_type": "opportunity", "record_id": params["record_id"]}` |
| `jira.update` | `{"jql": f"key = {params['issue_id']}"}` |
| `jira.create` | `{"jql": f"key = {result}"}` — `result` is the id returned by the write (`:79`) |
| `notion.update` | `{"page_id": params["page_id"]}` |
| `slack.send` | `{"channel": params["channel"], "query": str(params["text"])[:80]}` |

`jira.create` is the reason `verify_write` takes a `result` parameter
(`verify.py:124`): the record id does not exist until the write mints it.

### Expectation derivation — and its limit

`src/mission/verify.py:88-104 derive_expected`:

| Op | Derived expectations |
|---|---|
| `jira.update`, `salesforce.update` | `params["fields"]` |
| `notion.update` | `params["data"]` |
| `jira.create` | `{"key": <returned id>}` |
| everything else | `{}` → `INDETERMINATE`, fail closed |

**`derive_expected` builds expectations FROM the write.** A passing read-back
therefore proves transport fidelity only — *"the fields I sent are the fields
that arrived"* — never semantic correctness.

The outcome is labelled `expectation_source="derived_from_write"`
(`verify.py:57-59`, applied at `:219-242`) so it cannot be misread as independent
confirmation. **The limitation stands.** See `TESTING_STRATEGY.md` §7.

---

## 4. Adapter mapping

Parameter names are not identical across systems. The mapping lives in the op
executors (`src/mission/capability_ops.py`):

| Intent param | Connector param | Op |
|---|---|---|
| `assignee` or `owner` | `assignee` | `jira.create` (`:213-224`) — Jira's vocabulary |
| `fields` | `fields` | `jira.update`, `salesforce.update` |
| `data` | `data` | `notion.update` |
| `channel`, `text` | `channel`, `text` | `slack.send` |

Tenant binding: every op executor receives `tenant_id` and resolves its
connector via `_resolve_capability(capability, _config_for(tenant_id))`
(`capability_ops.py:201-241`).

---

## 5. Failure semantics

`src/mission/capability_ops_vendor.py:72-88`:

| Error class | Meaning | Retried | Tests |
|---|---|---|---|
| `VendorOpError` | base | no | — |
| `VendorRetryableError` | transient: HTTP 500, 429, timeout, connection refused | yes, bounded | `TestVendorHTTP500`, `TestVendorHTTP429`, `TestVendorTimeout`, `TestVendorConnectionRefused` |
| `VendorTerminalError` | validation / not-found / auth | **never** | `TestVendorInvalidPayload` |

Hard cap: 3 attempts, then raise and log. No unbounded retries.

On a terminal error during a governed write the claim is **released**, not
committed, so the key stays retryable — but the error is raised, never converted
into a success (`src/control_plane/ingress.py:170-176`).

---

## 6. Verification state machine

`src/mission/verify.py:20-22`, `:61-67`:

```
                 ┌─ no read counterpart ──→ verified=False + rollback_metadata
                 │
  verify_write ──┼─ expected == {} ────────→ INDETERMINATE
                 │
                 ├─ denied by allowlist ──→ INDETERMINATE ("read_back_not_permitted")
                 │
                 ├─ no record returned ───→ NOT_VERIFIED (mismatch="record")
                 │
                 ├─ all fields match ─────→ VERIFIED
                 ├─ some fields match ─────→ PARTIALLY_VERIFIED
                 └─ none match ───────────→ NOT_VERIFIED (mismatch=<field>)
```

Rules:

- `verified = (state == "VERIFIED")` and nothing else (`:61-67`)
- `INDETERMINATE` **never** promotes to `VERIFIED`
- An exception inside verification never propagates — verification must not raise
  (`:187`)
- A denied read-back is an authorization failure, not a data mismatch
  (`:190-211`)

---

## 7. Connector boundary — NOT enforced

| Stated boundary | Reality |
|---|---|
| "Agents never hold DB credentials or issue arbitrary SQL" | **Prose only. Not enforced by any test.** `src/agents/bi/nodes.py:679,683`, `src/session/mission_state.py:104,170`, `src/session/context.py:53,104` read `DATABASE_URL` and issue raw SQL from agent/session modules. |
| "An op may only touch its own tenant's resources" | **Request tenant is bound, target tenant is not checked.** `tests/adversarial/test_tenant_isolation.py:132` pins this deliberately so it cannot be silently "fixed": a `t-acme` intent targeting a foreign record still executes. |
| Cross-tenant evidence is rejected on assembly | VERIFIED — `test_tenant_isolation.py::test_assemble_rejects_cross_tenant_evidence` |

Recording a connector-returned record faithfully is not a leak; authority leak
would be. The pinned gap is about **authority**, not recording
(`test_tenant_isolation.py:126-131`).

---

## 8. Contract status

| Contract element | Status |
|---|---|
| Allowlist enforced on every op | VERIFIED — `tests/test_p0_capability_allowlist.py` (8) |
| Authority before side effect | VERIFIED — `tests/test_p0_authorization_boundary.py` (9) |
| At-most-once per key | VERIFIED **in-process** — 23 + 5 tests |
| Read-back under write authority | VERIFIED — 9 tests |
| Terminal vs retryable classification | VERIFIED — `tests/test_failure_injection.py` |
| Semantic correctness of a write | **NOT PROVEN** — `derive_expected` is derived from the write |
| Target-resource tenant match | **KNOWN GAP** — pinned, not built |
| Cross-restart idempotency | **NOT RESTART-SAFE** — see `PERSISTENCE_BOUNDARY.md` |
