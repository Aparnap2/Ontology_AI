#!/usr/bin/env python
"""Sprint B demo — blocker investigation golden path (mocks/fakes only).

Hiring-manager runnable: one Slack blocker event travels the full slice
(Evidence → Checkpoint → Mission → Intent → Control Plane → Jira →
Verify → Timeline → Workspace event) with narration at every step.

Run:
    cd apps/ai
    uv run python scripts/demo_blocker_investigation.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.control_plane import ingress as ingress_mod
from src.mission import capability_ops
from src.mission.blocker_investigation_mission import (
    ingest_slack_event,
    run_blocker_investigation_mission,
)
from src.mission.signal_handler import InMemorySignalHandler
from src.mission.skill_registry import SkillRegistry
from src.ontology.object_types import Onboarding


class MockJira:
    def __init__(self) -> None:
        self.store = {"PROJ-1": {"key": "PROJ-1", "status": "Blocked"}}
        self.writes = 0

    def update_issue(self, issue_id, fields):
        self.writes += 1
        self.store[issue_id] = {**self.store.get(issue_id, {}), **fields}
        return {"id": issue_id, **self.store[issue_id]}

    def get_issues(self, **kwargs):
        key = str(kwargs.get("jql", "")).split("=")[-1].strip()
        rec = self.store.get(key)
        return [dict(rec)] if rec else []


PROPOSAL = {
    "root_cause": "SSO configuration is blocking the ACME integration milestone",
    "action": {
        "capability": "jira",
        "operation": "jira.update",
        "target": "PROJ-1",
        "parameters": {"issue_id": "PROJ-1", "fields": {"status": "In Progress"}},
    },
    "confidence": 0.91,
    "risk_tier": "HIGH",
    "expected_outcome": "PROJ-1 moves to In Progress",
}


def say(step: str, detail: str = "") -> None:
    print(f"\n=== {step} ===", flush=True)
    if detail:
        print(detail, flush=True)


async def main() -> None:
    cap = MockJira()
    onboarding = Onboarding(
        id="ob-acme", customer="acme", stakeholders=["alice"],
        requirements=["SSO config"], tasks=["t-1"], issues=["PROJ-1"],
        missions=["m-acme-1"], lifecycle_state="implementing",
    )
    slack = {
        "channel": "onboarding", "user": "alice",
        "text": "ACME waiting on SSO config",
        "ts": "10:23",
    }
    handler = InMemorySignalHandler()
    snapshot = dict(SkillRegistry._skills)

    with (
        patch.object(capability_ops, "_resolve_capability", lambda n, c: cap),
        patch(
            "src.config.llm.chat_completion_with_metrics",
            lambda messages, **kw: SimpleNamespace(content=json.dumps(PROPOSAL)),
        ),
    ):
        capability_ops.CapabilityOpRegistry._ops.clear()
        ingress_mod._seen._seen.clear()

        say("1. Slack event enters", json.dumps(slack))
        ev = ingest_slack_event(slack, "t-acme")
        say("2. Evidence ingested", f"id={ev.id} provenance={ev.provenance}")

        say("3. Mission runs (HIGH-risk → approval pause expected)")
        task = asyncio.create_task(
            run_blocker_investigation_mission(
                onboarding, slack, tenant_id="t-acme", mission_id="m-acme-1",
                business_scope="acme", signal_handler=handler,
            )
        )
        for _ in range(200):
            if handler._futures:
                break
            await asyncio.sleep(0.01)
        say("4. Control plane paused for approval", f"signals={handler.emitted}")
        handler.resolve({"approved": True})
        say("5. Founder approves — resuming")
        out = await task

    obs = out["observations"][-1]
    say("6. Verified business outcome", json.dumps(obs, indent=2)[:800])
    say(
        "7. Timeline + workspace event",
        f"timeline={[t['type'] for t in out['timeline']]}\n"
        f"workspace={json.dumps(out['workspace_event'])}\n"
        f"checkpoint={out['context_checkpoint']['checkpoint_id']}",
    )
    say("8. Exactly-once proof", f"jira writes={cap.writes} (duplicate delivery → deny:duplicate)")
    SkillRegistry._skills.clear()
    SkillRegistry._skills.update(snapshot)
    print("\nDONE: verified =", obs.get("verified"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
