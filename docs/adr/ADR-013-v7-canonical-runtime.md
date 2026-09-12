# ADR-013: V7 Canonical Runtime and Compat Surface

## Status
Accepted

## Context
V7 must make the existing cognitive machinery domain-neutral before any
Vendor/SLA/Incident entities are added. Without a freeze, new domain
types leak into the runtime and onboarding-specific paths get forked
instead of generalized (issue #67).

## Decision
Canonical runtime: `src/mission/` + `src/control_plane/` (+ `src/context/`
checkpoint assembly, `src/connectors/` executor-side clients via
capability bindings only).
Compat-only (frozen, no new callers): `workflows/` LangGraph verticals,
`V6ConnectorRegistry`/old `get_connector`, `Onboarding`/`Task` models,
onboarding missions/configs/tests.

## Consequences
- Positive: Vendor/SLA/Incident land on a neutral checkpoint/target seam.
- Positive: onboarding callers keep working via deprecated alias (dual-write).
- Negative: compat surface still ships until dual-write migration completes.

## References
- Issue #67; ADR-010/011/012.
