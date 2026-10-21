# Persistence Boundary — OntologyAI

Branch `feature/ontologyai-onboarding-restructure` · HEAD `cd7fe05`

> **In-memory = process-local protection.**
> **A persistent store = restart-safe protection.**
>
> **These are not the same, and the current code is the former.**

This document exists because conflating the two produces a false safety claim.
Every table below says what the store is backed by *today* and what a restart
costs.

---

## 1. The statement, plainly

Four control-plane stores are **in-memory, process-local, and not restart-safe**:

| Module | Backing | Restart cost |
|---|---|---|
| `src/control_plane/audit.py` | module-level `AUDIT_LOG: list` (`:14`) | **The entire audit trail is lost.** |
| `src/control_plane/idempotency.py` | `SeenSet` in a process singleton (`:269`) | **All idempotency records are lost. At-most-once does not survive a restart.** |
| `src/control_plane/concurrency.py` | `VersionStore` in a process singleton (`:41`) | **All version state is lost.** Optimistic concurrency silently resets. |
| `src/mission/cost_latency.py` | in-memory dicts (`:82`) | **All cost/latency metrics are lost.** |

None of these is durable. None of these survives a process restart, a container
redeploy, or a crash.

### The consequence that matters

**A process restart loses the audit trail, idempotency records and version
state, so at-most-once does NOT survive a restart.**

The lease in the idempotency claim (`idempotency.py:62`, `:143-145`) makes an
**in-process crash recoverable** — a worker that dies mid-execution inside the
same process does not wedge the key forever. **It does not make a restart safe.**
A restarted process has an empty `SeenSet` and will happily execute a key that
was already committed.

The module docstring is accurate about the mechanism and does not overclaim:
`idempotency.py:94-101` states that production binds the same key to Temporal
idempotency ids and Redpanda exactly-once keys "where the store is durable rather
than this process", and that only the atomicity primitive differs
(`INSERT ... ON CONFLICT DO NOTHING` in Postgres, `SET NX` in Redis). **That
binding does not exist in this repository today.**

---

## 2. Store table

| Store | Module | Backing today | Scope | Durable? | A restart costs |
|---|---|---|---|---|---|
| Audit log | `src/control_plane/audit.py:14` | `AUDIT_LOG: list[dict[str, Any]]` | process | **NO** | Every audit event ever written in that process |
| Idempotency claims | `src/control_plane/idempotency.py:108`, `:269` | `dict[str, _Entry]` behind `threading.Lock` | process | **NO** | All at-most-once guarantees for keys claimed before the restart |
| Target versions | `src/control_plane/concurrency.py:23`, `:41` | `dict[str, int]` | process | **NO** | Optimistic-concurrency state; `current()` returns `None` for every key |
| Cost / latency | `src/mission/cost_latency.py:83` | `dict[str, MissionMetrics]` | instance | **NO** | All token/cost/latency metrics |
| Capability op registry | `src/mission/capability_ops.py:388` | class attribute `dict[str, CapabilityOp]` | process | **NO** | Rebuilt on first access via `_ensure_loaded()` (`:390-394`) — **stateless, so no real loss** |
| Execution trace | `src/mission/observability.py:53` | in-memory span dict | request | **NO** | Spans; superseded by OTel export where configured |
| MissionState | `src/session/mission_state.py` | **Postgres** via `asyncpg` (`:104`, `:170`) | durable | **yes** | nothing — but see §4 |
| Session messages | `src/session/context.py` | **Postgres** via `asyncpg` (`:53`, `:104`) | durable | **yes** | nothing |
| MRR snapshots | `src/agents/bi/nodes.py:679-683` | **Postgres** via `psycopg2` | durable | **yes** | nothing — but see §4 on credentials |

---

## 3. What the lease actually buys

`src/control_plane/idempotency.py`:

```
CLAIM(key) --+-- already claimed --> DUPLICATE
             +-- claimed          --> EXECUTE
                                          +-- success --> COMMIT
                                          +-- failure --> RELEASE
```

| Mechanism | Line | What it protects against | What it does NOT protect against |
|---|---|---|---|
| Atomic claim under `threading.Lock` | `:107`, `:131-153` | Concurrent execution **within one process** | Anything after a restart |
| Owner token on commit/release | `:232-241` | A stale worker freeing or completing another owner's claim | A fresh process with an empty store |
| Lease, `DEFAULT_LEASE_SECONDS = 300.0` | `:62`, `:143-145` | A worker that **dies in-process** wedging the key forever | A restart — there is nothing left to expire |
| `COMMITTED` is terminal | `:165`, `:195-205` | A lease sweep releasing a completed key | A restart discarding the terminal marker |

Read the lease row carefully: it converts *wedged forever* into *retryable after
five minutes*. That is a liveness property. It is not a durability property, and
it is not a substitute for one.

---

## 4. Migration status

### 4.1 The Go side

Migrations are applied by `apps/core/cmd/migrate`
(`cmd/migrate/main.go:41-46`, runner at `:139-190`), discovered from two
directories whose numeric prefixes collide:

- `internal/db/migrations` — `001..010`
- `migrations` — `001..005`, `011..012`

Ordering is resolved by sorting on the numeric prefix across both directories
(`main.go:177-182`), which correctly interleaves them.

### 4.2 The Python side

**There is no migration mechanism.** No Alembic, no DDL runner, no schema
versioning for tables the Python service writes (`mission_states`,
`session_messages`, `mrr_snapshots`). `apps/core/cmd/migrate` covers the Go side
only. A table the Python side depends on must already exist because some Go
migration created it — an implicit, undeclared coupling.

### 4.3 The migration history is itself inconsistent

`cmd/migrate/main.go:142-145` states the problem in the runner's own comment, and
reading the files confirms it:

| File | Line | Declares |
|---|---|---|
| `internal/db/migrations/001_sarthi_sop_runtime.sql` | `:10` | `CREATE TABLE IF NOT EXISTS raw_events (... founder_id UUID NOT NULL ...)` |
| `internal/db/migrations/002_sarthi_v1.sql` | `:20` | `CREATE TABLE IF NOT EXISTS raw_events (... tenant_id VARCHAR(50) NOT NULL ...)` |

Both use `CREATE TABLE IF NOT EXISTS`, so the second is **silently skipped**.
The table keeps `founder_id`; every later query written against `tenant_id` fails
at runtime, not at migration time. `002_sarthi_v1.sql` contains **zero** `ALTER
TABLE` statements, so it cannot reconcile the difference either.

The ordering half — `003_saarathi_pivot` rewriting the same tables — is handled
by the interleaved sort. The column-shape half is unresolved.

**Consequence: a fresh-database bootstrap does not complete correctly.** The
migrations apply without error and produce a schema that does not match what the
code expects. This is worse than a migration failure, because it is silent.

---

## 5. Honest capability statement

| Can be claimed | Cannot be claimed |
|---|---|
| At-most-once holds **within a single process lifetime** | At-most-once holds **across a restart** |
| Authorization, policy and the capability allowlist are enforced | That a **durable** audit trail exists |
| Read-back verification runs under the write's authority | That the audit trail is **complete after a crash** |
| A denied read-back is INDETERMINATE, never VERIFIED | That anything here is **restart-safe** |
| An expired lease releases an in-process claim | That the lease survives a restart (there is nothing to survive) |
| The lease prevents a wedged key in-process | That the system is safe for **multi-replica deployment** |

For a **single-process deployment where restart-loss is stated to operators**, the
current boundary is coherent. For anything else it is not, and the difference is
recorded here rather than inferred.

---

## 6. What a persistent store would change

The primitives are already named in `idempotency.py:94-101`:

| Store | Durable replacement | Primitive | The claim protocol stays identical |
|---|---|---|---|
| `SeenSet` | Postgres | `INSERT ... ON CONFLICT DO NOTHING` | yes — claim/commit/release, owner token, lease, payload hash |
| `SeenSet` | Redis | `SET NX` with TTL | yes |
| `VersionStore` | Postgres | transactional compare-and-swap (`concurrency.py:16-21` already describes this) | yes |
| `AUDIT_LOG` | Postgres append-only table | `INSERT` | yes — `append_event` already accepts an injected `store` (`audit.py:17-28`) |

Note `audit.py:28` and `audit.py:45`: `append_event` and `list_events` already
take an optional `store` parameter and fall back to the module-level list. The
seam for a durable backend **already exists** and is unused.

---

## 7. Verification status

| Claim | Evidence | Status |
|---|---|---|
| The stores are in-memory and process-local | Read of `audit.py:14`, `idempotency.py:108,269`, `concurrency.py:22,40`, `cost_latency.py:83` | **VERIFIED** by direct inspection |
| At-most-once holds under concurrency in-process | 23 + 5 passing tests, n = 2/4/10/100 | **VERIFIED** |
| Lease recovery on expiry | `test_expired_lease_is_reclaimable` | **VERIFIED** |
| Lease recovery on real worker death | none | **PARTIAL** — expiry proven with a clock |
| At-most-once survives a restart | none — and the guarantee does not hold | **KNOWN GAP** |
| Audit survives a restart | none — and it does not | **KNOWN GAP** |
| Version state survives a restart | none — and it does not | **KNOWN GAP** |
| A fresh-database bootstrap produces a correct schema | `001`/`002` column conflict | **KNOWN GAP** |
| The Python side has migrations | none exist | **KNOWN GAP** |

The three restart claims are not gaps in testing. They are gaps in the
architecture, and no test can close them — a test that restarts the process and
asserts at-most-once would correctly **fail**.
