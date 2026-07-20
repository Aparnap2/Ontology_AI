# ADR-009: Replace n8n with Windmill as the Execution Runtime

## Status
Proposed

## Context

ADR-007 (initial runtime selection, superseded by this decision) chose n8n as the canonical execution runtime for OntologyAI workflow deployment. n8n was selected for its visual workflow builder, webhook triggers, and broad integration catalogue — all of which accelerated early prototyping of scheduled/webhook-heavy automation workflows.

As the product matured toward enterprise-grade deployments (V5.1 → V6), three structural concerns emerged with n8n:

1. **Licensing constraints.** n8n's "Fair-code" license (Sustainable Use License + n8n Enterprise License) restricts production concurrency, advanced RBAC, and audit logging to paid enterprise tiers. Self-hosting the full feature set requires a commercial agreement, which contradicts OntologyAI's AGPL distribution model and creates friction for customers who require self-hosted, no-restriction deployments.

2. **Limited RBAC and audit.** n8n's open-source edition offers coarse workspace-level permissions only — no fine-grained role-based access control (RBAC), no per-script/flow audit trails, and no secrets management. Enterprise features (LDAP/SAML, audit logs, secrets vault) are gated behind the paid license.

3. **Approval steps require external orchestration.** n8n does not natively support pause-and-resume (approval) steps in the open-source edition. OntologyAI currently implements HITL (Human-In-The-Loop) approvals via Temporal `SignalWorkflow` + `AwaitWithTimeout` — a pattern that works but lives outside the runtime, adding an extra coordination layer.

Windmill — an open-source (AGPL) automation runtime — addresses all three concerns natively:

- **AGPL license**: Full source access, self-hostable without restrictions, compatible with OntologyAI's licensing model.
- **Native RBAC**: Workspace-level roles (admin, developer, viewer), folder-level permissions, per-script ACLs, audit trails for every run.
- **Built-in approval steps**: Flows support `suspend` nodes that pause execution until a human approves or rejects — matching OntologyAI's HITL pattern without Temporal signal coordination.
- **Secrets management**: Native `wmill.get_variable()` / `wmill.set_variable()` API for sensitive values, with encryption at rest.
- **20+ languages**: Scripts can be written in Python, TypeScript, Go, Rust, Bash, SQL, and more — not just n8n's JavaScript/Node.js.

Windmill is production-deployed by its maintainers (Windmill Labs) handling 10M+ runs/month and is used in production by enterprises including Docker, Netlify, and PwC.

## Decision

1. **Replace n8n with Windmill as the canonical/default execution runtime target** for OntologyAI workflow deployment.
2. The existing `RuntimeCompiler` ABC remains unchanged — a new `WindmillCompiler` is added alongside the existing compilers.
3. The `ExecutableWorkflowDraft.runtime` literal set expands to include `"windmill"`.
4. The `choose_runtime(traits, client_stack)` function is updated to prefer `"windmill"` for scheduled/webhook-heavy and integration-heavy workflows (replacing n8n's default slot).
5. The n8n compiler and deployer are **retained for backward compatibility** — existing deployments continue to work, and users may opt into n8n via explicit runtime selection.
6. Windmill becomes the primary target for new workflows.

## Windmill API Surface

The following API endpoints are used by the Windmill compiler and deployer. All calls are authenticated with a **Bearer token** (workspace-scoped) in the `Authorization` header.

### Authentication

```
Authorization: Bearer {workspace_token}
```

Workspace tokens are created via the Windmill UI or API (admin-only endpoint). Tokens are scoped to a single workspace and support granular permissions.

### Create Script

```
POST /api/w/{workspace}/scripts/create
Content-Type: application/json
Authorization: Bearer {token}

{
  "path": "u/user/my_script",
  "summary": "Script description",
  "content": "def main(): ...",
  "language": "python3",
  "kind": "script",
  "tag": "default"
}
```

| Field | Description |
|---|---|
| `path` | Canonical script path (e.g. `u/{workspace}/{name}` or `f/{folder}/{name}`) |
| `summary` | Human-readable description |
| `content` | Script source code |
| `language` | One of `python3`, `typescript`, `go`, `bash`, `rust`, `sql`, `graphql`, `docker`, `nativets` |
| `kind` | Always `"script"` for standalone scripts |
| `tag` | Deployment tag (`"default"` is recommended) |

### Create Flow

Flows are created via the async dependencies endpoint:

```
POST /api/w/{workspace}/jobs/run/flow_dependencies_async
```

A flow definition JSON consists of:

```json
{
  "summary": "Flow summary",
  "description": "Flow description",
  "modules": [
    {
      "id": "step_1",
      "type": "script",
      "path": "u/user/step_one",
      "input_transforms": {
        "input_field": {"expr": "prev_result.some_field"}
      }
    },
    {
      "id": "approval_1",
      "type": "approval",
      "summary": "Review and approve",
      "description": "Human must approve before continuing",
      "email": "admin@example.com",
      "suspend": true,
      "input_transforms": {
        "reason": {"expr": "\"Please review the output of step 1\""}
      }
    },
    {
      "id": "step_2",
      "type": "script",
      "path": "u/user/step_two",
      "input_transforms": {
        "input_field": {"expr": "approval_1.result"}
      }
    }
  ],
  "failure_modules": []
}
```

Module types include:
- `script` — run a Windmill script
- `flow` — invoke a subflow
- `forloop` / `whileloop` — iteration
- `branch` / `branchall` — conditional branching
- `approval` — HITL suspend/resume
- `identity` — pass-through transform
- `rawscript` — inline script (no persistent path)

### Run Script

```
POST /api/w/{workspace}/jobs/run/p/{path}
Content-Type: application/json
Authorization: Bearer {token}

{"arg1": "value1"}
```

Returns a job UUID immediately. Job status can be polled via:

```
GET /api/w/{workspace}/jobs/completed/list?job_kind=script&order_by=created_at
```

### Run Flow

Same endpoint as script run, using the flow's path:

```
POST /api/w/{workspace}/jobs/run/p/{path}
```

Returns a job UUID. Flow jobs include sub-job information in the completion response.

### Webhooks

Every script and flow is automatically assigned a webhook URL:

```
POST /api/w/{workspace}/jobs/run/p/{path}/webhook/{token}
```

Authentication is handled via the path token — either as a Bearer token or as a query parameter:

```
POST /api/w/{workspace}/jobs/run/p/{path}?token={webhook_token}
```

### Secrets / Variables

Windmill provides a built-in variables store with read/write via API and SDK:

**Read variable (in Python script):**
```python
import wmill
value = wmill.get_variable("u/user/my_api_key")
```

**Write variable (in Python script):**
```python
import wmill
wmill.set_variable("u/user/my_api_key", "new_value")
```

**Create variable via API:**
```
POST /api/w/{workspace}/variables/create
Content-Type: application/json
Authorization: Bearer {token}

{
  "path": "u/user/my_api_key",
  "value": "sk-...",
  "description": "API key for external service",
  "is_secret": true
}
```

## Architecture Changes

### Compiler

**Current state:** `n8n_compiler.py` produces `{"nodes": [...], "connections": [...]}` — an n8n workflow JSON document with typed nodes, positions, and wiring.

**New state:** `windmill_compiler.py` produces Windmill-native payloads:

- For **scripts**: A Python/TypeScript function body + path + schema (input types, output types, summary).
- For **flows**: A flow definition JSON with a `modules` array. Each module maps to a step, subflow, loop, branch, suspend (approval), or identity transform. Input transforms use `{"expr": "previous_step.field"}` syntax for data wiring.
- For **approvals**: A `{"type": "approval", "suspend": true}` module replaces the current Temporal `SignalWorkflow` + `AwaitWithTimeout` HITL pattern. The flow pauses natively until the approval is granted or denied via the Windmill UI or API.

The `WindmillCompiler` class implements `RuntimeCompiler`:

```python
# runtime/windmill_compiler.py  (proposed)

class WindmillCompiler(RuntimeCompiler):
    """Compiler targeting the Windmill runtime (AGPL automation server).

    Produces Windmill script/flow payloads from a canonical
    ``ExecutableWorkflowDraft``. Scripts are generated as Python functions with
    Pydantic-like input schemas. Flows use the Windmill modules array format
    with native approval (suspend) steps replacing Temporal HITL signals.
    """

    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        ...
```

Output format:

```python
{
    "runtime": "windmill",
    "kind": "script" | "flow",
    "files": {
        "script.py": "def main(context: ...):\n    ...",
        "schema.json": "{...}",
        # For flows:
        "flow.json": "{ \"modules\": [...] }",
    }
}
```

### Deployer

**Current state:** `deploy_to_n8n()` in `runtime/deployers.py` POSTs compiled n8n workflow JSON to a running n8n instance via `N8nClient`.

**New state:** `deploy_to_windmill()` in `runtime/deployers.py`:

1. **Create the script** via `POST /api/w/{workspace}/scripts/create` (or update via `POST /api/w/{workspace}/scripts/update`).
2. **Set secrets/variables** via `POST /api/w/{workspace}/variables/create` for each credential in the draft.
3. **Create the flow** (if applicable) via the flow dependencies endpoint.
4. **Return** a `DeployerResult` with `workflow_id` set to the Windmill script/flow path and `export_url` set to the Windmill instance URL + path.

```python
# In runtime/deployers.py  (proposed addition)

def deploy_to_windmill(
    draft: dict[str, Any],
    credentials: dict[str, Any],
) -> DeployerResult:
    """Deploy a compiled Windmill script/flow to a running Windmill instance.

    Args:
        draft: The compiled Windmill payload dict (must have ``runtime``,
            ``kind``, ``files``).
        credentials: Dict containing:
            - ``url``: Windmill API base URL (e.g. ``https://windmill.example.com``).
            - ``token``: Workspace-scoped Bearer token.
            - ``workspace``: Windmill workspace id.

    Returns:
        A :class:`DeployerResult` with the outcome.
    """
    ...
```

### Compiler Registry Update

The `_COMPILERS` dict in `runtime/__init__.py` gains a new entry:

```python
_COMPILERS: dict[str, Type[RuntimeCompiler]] = {
    "n8n": N8NCompiler,
    "windmill": WindmillCompiler,   # NEW — primary default
    "adk_go": ADKGoCompiler,
    "pydantic_ai": PydanticAICompiler,
    "python_agent": PythonAgentCompiler,
}
```

### Multi-Runtime Strategy (ADR-08 Amendment)

The runtime target selection matrix from ADR-008 is updated:

| Workflow Trait | Recommended Runtime | Compiler Module |
|---|---|---|
| **Scheduled/webhook-heavy, integration-heavy** | **Windmill** (was n8n) | **windmill_compiler.py** |
| Client stack requires Go | ADK-Go | adk_go_compiler.py |
| Client stack is Python with typed outputs | PydanticAI | pydantic_ai_compiler.py |
| Sandboxed utility subtask | smolagents | python_agent_compiler.py |
| Legacy n8n deployments (backward compat) | n8n | n8n_compiler.py |

### HITL Approval Pattern Change

**Current (Temporal-only):**
```
Workflow dispatch → step runs → AwaitWithTimeout(HITL_SIGNAL_NAME, timeout)
    → User sends SignalWorkflow("hitl-approval")
    → Workflow resumes → next step
```

**New (Windmill-native):**
```
Flow module[1] (script) → module[2] (approval, suspend=true)
    → User approves via Windmill UI or REST API
    → Flow executes module[3] (script) automatically
```

The Temporal signal infrastructure remains for non-Windmill runtimes but is no longer required for Windmill-deployed approval workflows. The approval step metadata (who can approve, notification email) is encoded in the Windmill flow module definition.

## Consequences

### Positive
- **Enterprise-ready RBAC and audit** — Windmill provides workspace-level roles, folder-level permissions, per-script ACLs, and full run audit trails out of the box, all under AGPL.
- **No licensing friction** — AGPL-licensed core means self-hosted deployments have no feature restrictions. No enterprise license negotiation needed for RBAC, concurrency, or audit.
- **20+ language support** — Scripts can be authored in Python 3, TypeScript, Go, Rust, Bash, SQL, and more, unlocking teams that prefer non-JS runtimes.
- **Native secrets management** — The `wmill` SDK and variables API replaces the need for external vault integration for most use cases.
- **Built-in approval steps** — Windmill's `suspend` module eliminates the need for Temporal HITL signal coordination for human-in-the-loop approvals. Approval flows are self-contained within the runtime.
- **Webhook triggers with token auth** — Automatically generated per-script/flow webhook URLs with path-based token authentication reduce the security surface vs. shared API keys.
- **Existing architecture preserved** — The `RuntimeCompiler` ABC, `get_compiler()` factory, and deployer pattern remain unchanged. Adding `WindmillCompiler` and `deploy_to_windmill()` is additive, not disruptive.

### Negative
- **Migration effort required** — All compiler logic for the default runtime must be rewritten. The existing `n8n_compiler.py` (218 lines) is replaced by `windmill_compiler.py` of comparable or greater complexity due to flow module support.
- **Deployer rewrite** — `deploy_to_windmill()` must handle script creation, variable setup, and optional flow creation — more endpoints than the current single `POST /workflows` n8n deployer.
- **Existing n8n workflows become legacy** — Users with deployed n8n workflows must either leave them on n8n (backward compat) or manually migrate. No automated n8n → Windmill migration path exists in this ADR.
- **New team learning curve** — Team members familiar with n8n's node/connection model must learn Windmill's script/flow/module model and the `wmill` SDK.
- **Windmill is younger than n8n** — Windmill's ecosystem (community integrations, marketplace templates) is smaller than n8n's. Some niche connectors may require custom script writing.

### Migration Path
1. Add `WindmillCompiler` as a new compiler module alongside existing compilers (no existing code changed).
2. Add `deploy_to_windmill()` to `runtime/deployers.py`.
3. Update the compiler registry (`_COMPILERS`) and `choose_runtime()` to prefer `"windmill"` for new workflows.
4. Update `ExecutableWorkflowDraft.runtime` literal type to include `"windmill"`.
5. Keep n8n compiler/deployer for backward compatibility.
6. Document the migration guide for existing n8n users.
7. Future: Add automated n8n-to-Windmill conversion tool if demand warrants.

## Implementation

- `WindmillCompiler` in `runtime/windmill_compiler.py` — implements `RuntimeCompiler` contract
- `deploy_to_windmill()` in `runtime/deployers.py` — Windmill API deployer
- Compiler registry update in `runtime/__init__.py` — add `"windmill": WindmillCompiler`
- `_choose_runtime` update — change default for scheduled/webhook-heavy from `"n8n"` to `"windmill"`
- `ExecutableWorkflowDraft` model update — add `"windmill"` to `runtime` literal
- Test suite: 15+ TDD tests in `tests/test_runtime_compilers.py` (5 ABC contract, 5 WindmillScript, 5 WindmillFlow)
- Integration test: Real Windmill API interaction (skipped in CI unless `WINDMILL_URL` + `WINDMILL_TOKEN` are set)
- Governance guard unchanged — approval gates remain required before any compile+deploy sequence
