# ADR-008: Multi-Runtime Compiler Architecture

## Status
Accepted

## Context
V5.1 originally shipped two deterministic compilers: `n8n` (automation runtime) and `custom_agent` (generic agent config). As the product matured, three distinct agent-runtime patterns emerged: typed Python agents (PydanticAI), Go-native agents (ADK-Go), and sandboxed utility agents (smolagents). Adding compiler logic for each inside a single `custom_agent_compiler.py` would violate separation of concerns and produce a single monolith.

The product director confirmed: **LangGraph + OntologyAI remains the single control plane and authoring brain**. n8n, ADK-Go, PydanticAI, and smolagents are runtime targets — never competing "brains." The canonical `ExecutableWorkflowDraft` is the one truth from which all runtime-specific code is generated deterministically.

## Decision
1. **OntologyAI + LangGraph** remain the single product control plane and authoring brain.
2. Every deployable workflow is represented as a canonical `ExecutableWorkflowDraft`.
3. **Deterministic compilers** translate the canonical draft into each runtime target's native format.
4. A single `RuntimeCompiler` ABC defines the contract: `compile(draft: dict) -> dict`.
5. A `get_compiler(runtime: str) -> RuntimeCompiler` factory routes by runtime name.
6. **Runtime selection** uses a deterministic `choose_runtime(traits, client_stack)` function based on workflow traits.
7. Each compiler lives in its own module under `runtime/`:
   - `n8n_compiler.py` — existing; wrapped by `N8NCompiler`
   - `adk_go_compiler.py` — new; generates `main.go` + `tools.go`
   - `pydantic_ai_compiler.py` — new; generates `agent.py` w/ Pydantic model + tool decorators
   - `python_agent_compiler.py` — new; generates smolagents-style CodeAgent
8. Governance approval gates remain required before ANY compile+deploy sequence.
9. smolagents is restricted to sandboxed worker subtasks only (never control plane).
10. The LLM proposes workflow structure (steps, decision points, approvals) but **never writes export payload** — that is the compiler's deterministic job.

## Consequences
- **Positive:** Runtime targets are swappable without changing the product brain.
- **Positive:** No framework soup — each runtime has a narrow, well-defined role.
- **Positive:** Byte-stable, reproducible, testable exports for every target.
- **Negative:** Each new runtime target requires a new compiler module.
- **Negative:** Generated ADK-Go/PydanticAI code must be manually reviewed by client teams before production use.

## Runtime Target Selection Matrix
| Workflow Trait | Recommended Runtime | Compiler Module |
|---|---|---|
| Scheduled/webhook-heavy, integration-heavy | n8n | n8n_compiler.py |
| Client stack requires Go | ADK-Go | adk_go_compiler.py |
| Client stack is Python with typed outputs | PydanticAI | pydantic_ai_compiler.py |
| Sandboxed utility subtask | smolagents | python_agent_compiler.py |

## Implementation
- `RuntimeCompiler` ABC in `runtime/base.py`
- `N8NCompiler` wrapper in `runtime/n8n.py` (delegates to existing `compile_n8n()`)
- `ADKGoCompiler` in `runtime/adk_go_compiler.py`
- `PydanticAICompiler` in `runtime/pydantic_ai_compiler.py`
- `PythonAgentCompiler` in `runtime/python_agent_compiler.py`
- Factory `get_compiler()` in `runtime/__init__.py`
- 15 TDD tests in `tests/test_runtime_compilers.py` (5 ABC contract, 3 ADK-Go, 3 PydanticAI, 2 PythonAgent, 2 factory)
- Governance guard in compile/deploy Temporal activity enforces approval before any compiler runs
