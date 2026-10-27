# ADR-010: Onboarding as Domain Aggregate, Mission as Bounded Work Unit

## Status
Accepted

## Context
OntologyAI targets Closed-Won → First Value for B2B SaaS onboarding.
The business lifecycle (handoff, kickoff, implementation, go-live,
hypercare) spans Sales, CS, Product/Engineering with long-lived state,
many stakeholders, and cross-system blockers. Modeling this as a flat
`Mission.kind = onboarding` collapses lifecycle state, ownership, and
audit into an AI work ticket. It cannot hold contracts, milestones,
or M1-M6 progress independently of any single agent run.

## Decision
`Onboarding` is a first-class business lifecycle aggregate owning:
Customer, Contract/Commitments, Stakeholders, Requirements,
Tasks, Issues/Blockers, Events, and Missions M1-M6.
`Mission` is a bounded AI work unit operating *within* one onboarding
(M1 Validate Handoff, M2 Prepare Kickoff, M3 Investigate Blocker,
M4 Recover Milestone, M5 Detect Drift, M6 Readiness Review).
Never model onboarding as `Mission.kind`. One Customer has
0..n Onboardings; one Onboarding has 0..n Missions.

```
Customer ──enters──> Onboarding ──contains──> Missions M1-M6
                        │                         │
                        │              Employees (Handoff/Ops/Process Analyst)
                        │                         │ executes via
                        └─────────────┬───────────┘
                                      ▼
                              Actions → Outcomes (verified)
```

## Consequences
- Positive: lifecycle survives across missions, retries, approvals.
- Positive: M1-M6 share one state truth (PostgreSQL), agents stay bounded.
- Positive: timeline/workspace reads Onboarding, not scattered missions.
- Negative: requires Onboarding aggregate + Mission linkage migration.

## Alternatives Rejected
- `Mission.kind = onboarding`: rejected — no place for contract,
  milestones, or multi-mission audit; lifecycle dies with the ticket.
- `Opportunity owns missions directly`: rejected — conflates sales
  truth (Salesforce) with delivery truth; breaks handoff boundary.
- Generic `Project` aggregate: rejected — loses onboarding-specific
  invariants (DoD, readiness, SOP governance).

## References
- `OntologyAI_PRD_28_08.md`: Final vertical (Closed-Won → First Value);
  Core ontology (~20 entities, Onboarding/Milestone/Task/Blocker);
  Exact MVP mission catalog M1-M6; AI workforce (3 employees).
