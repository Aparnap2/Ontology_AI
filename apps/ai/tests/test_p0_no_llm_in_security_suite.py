"""P0: the deterministic security suite must never call a live LLM.

Why this test exists
--------------------
``tests/test_agentic_capability.py`` made 40 real provider calls and failed
with ``openai.AuthenticationError: 401 Invalid API Key``. That is not a
security finding — it means the *deterministic* gate was silently coupled to
a credential. A control-plane boundary that can only be tested when an API
key happens to be valid is not a boundary that can be relied upon.

This module turns

    "I think these tests don't call the LLM"

into an enforced invariant. It patches the repository's single LLM factory
boundary (``src.config.llm``) so that ANY attempt to reach a provider raises,
then executes representative control-plane and security paths and asserts
they still work.

The boundary patched is the production one the rest of the codebase uses, not
``openai.OpenAI`` directly, so the guard survives provider changes.
"""

from __future__ import annotations

import pytest

#: The production boundary. Everything that reaches a model must pass through
#: one of these attributes.
LLM_BOUNDARY_ATTRS = (
    "chat_completion",
    "chat_completion_with_metrics",
    "chat_completion_json",
    "get_llm_client",
    "get_embedding_client",
    "get_chat_model",
    "get_embedding_model",
)


class LiveLLMCallAttempted(AssertionError):
    """Raised when guarded code tries to reach a live model."""


@pytest.fixture
def no_llm(monkeypatch):
    """Make every path to a live model fail loudly.

    Yields the list of attempts, which must stay empty.
    """
    import src.config.llm as llm

    attempts: list[str] = []

    def _blocked(name: str):
        def _raise(*_args, **_kwargs):
            attempts.append(name)
            raise LiveLLMCallAttempted(
                f"deterministic test attempted a live LLM call via {name}()"
            )

        return _raise

    for attr in LLM_BOUNDARY_ATTRS:
        if hasattr(llm, attr):
            monkeypatch.setattr(llm, attr, _blocked(attr))

    # Also block direct SDK construction, which bypasses the factory.
    import openai

    monkeypatch.setattr(
        openai, "OpenAI", _blocked("openai.OpenAI"), raising=False
    )
    monkeypatch.setattr(
        openai, "AsyncOpenAI", _blocked("openai.AsyncOpenAI"), raising=False
    )
    return attempts


# ---------------------------------------------------------------------------
# The guard itself must work
# ---------------------------------------------------------------------------


def test_guard_actually_blocks_the_boundary(no_llm) -> None:
    """Sanity check: if this fails, the guard is worthless."""
    import src.config.llm as llm

    with pytest.raises(LiveLLMCallAttempted):
        llm.chat_completion([{"role": "user", "content": "hello"}])

    assert no_llm, "the guard did not record the attempt"


# ---------------------------------------------------------------------------
# The deterministic security surface must run with the LLM blocked
# ---------------------------------------------------------------------------


class TestControlPlaneRunsWithoutLLM:
    def test_full_control_plane_path_is_llm_free(self, no_llm) -> None:
        """authorize -> policy -> idempotency -> execute -> audit, no model."""
        from src.control_plane.contracts import ActionIntent
        from src.control_plane.idempotency import reset_seen
        from src.control_plane.ingress import submit_intent

        reset_seen()
        intent = ActionIntent(
            capability="vendor",
            operation="vendor_ticket.create",
            target_reference="vendor-acme-001",
            requested_parameters={"vendor_id": "v1", "incident_id": "INC-1"},
            reason="vendor incident",
            evidence_ids=["ev-1"],
            expected_outcome="ticket raised",
            confidence=0.9,
            requested_by="untrusted-planner",
        )
        trusted = {
            "tenant_id": "t1",
            "mission_id": "m-llm-free",
            "employee_id": "e1",
            "actor_identity": "system",
            "permissions": ["vendor_ticket.create"],
        }

        import asyncio

        result = asyncio.run(submit_intent(intent, trusted))

        assert result["decision"] == "permit:executed", result
        assert no_llm == [], f"LLM used during control-plane execution: {no_llm}"

    def test_authorization_denial_is_llm_free(self, no_llm) -> None:
        """An unauthorized intent must be rejected with no model involved."""
        import asyncio

        from src.control_plane.contracts import ActionIntent
        from src.control_plane.idempotency import reset_seen
        from src.control_plane.ingress import submit_intent

        reset_seen()
        intent = ActionIntent(
            capability="jira",
            operation="jira.create",
            target_reference="PROJ-1",
            requested_parameters={"risk_tier": "LOW"},
            reason="prompt injection attempt",
            evidence_ids=[],
            expected_outcome="issue created",
            confidence=1.0,
            requested_by="injected-planner",
        )
        trusted = {
            "tenant_id": "t1",
            "mission_id": "m-llm-free-deny",
            "employee_id": "e1",
            "actor_identity": "system",
            "permissions": ["vendor_ticket.create"],
        }

        result = asyncio.run(submit_intent(intent, trusted))

        assert result["decision"].startswith("deny"), result
        assert no_llm == [], f"LLM used while rejecting an attack: {no_llm}"

    def test_atomic_claim_is_llm_free(self, no_llm) -> None:
        """The concurrency guard must not depend on a model."""
        import asyncio

        from src.control_plane.idempotency import SeenSet, reset_seen

        reset_seen()
        seen = SeenSet()
        winners: list[bool] = []

        async def contend(owner: str) -> None:
            await asyncio.sleep(0)
            winners.append(seen.claim("k", owner, "h"))

        asyncio.run(_gather(contend))

        assert winners.count(True) == 1
        assert no_llm == [], f"LLM used while claiming idempotency: {no_llm}"


async def _gather(contend) -> None:
    import asyncio

    await asyncio.gather(*(contend(f"o{i}") for i in range(50)))


class TestSecuritySuitesAreMarkedDeterministic:
    """The deterministic gate must be able to exclude live-model evaluation."""

    def test_live_llm_suites_are_marked(self) -> None:
        """Suites that reach a provider must carry the `llm` marker."""
        from pathlib import Path

        tests_dir = Path(__file__).resolve().parent
        live = [
            "test_agentic_capability.py",
            "agentic/test_agentic_ai.py",
            "integration/test_real_llm_integration.py",
            "integration/test_mission_live_infra.py",
            "integration/test_fixes_integration.py",
            "e2e/test_agentic_pipeline.py",
            "e2e/test_rag_evaluation.py",
        ]
        unmarked = [
            rel for rel in live
            if "pytest.mark.llm" not in (tests_dir / rel).read_text()
        ]
        assert not unmarked, f"live-LLM suites missing the llm marker: {unmarked}"

    def test_llm_marker_is_not_overwritten(self) -> None:
        """A later ``pytestmark = [...]`` silently discarded the llm marker.

        Matching the string was not enough: both files carried the marker text
        yet reassigned pytestmark afterwards, so the marker had no effect and
        the deterministic gate still ran live-LLM tests.
        """
        from pathlib import Path

        tests_dir = Path(__file__).resolve().parent
        import ast

        bad = []
        # ALL eight live-LLM suites, not just the two that were previously
        # caught. Scoping this to the known-bad files let a third file carry
        # an inert marker undetected.
        for rel in (
            "integration/test_mission_live_infra.py",
            "integration/test_fixes_integration.py",
            "integration/test_real_llm_integration.py",
            "integration/hardening/test_pipeline_e2e.py",
            "test_agentic_capability.py",
            "agentic/test_agentic_ai.py",
            "e2e/test_agentic_pipeline.py",
            "e2e/test_rag_evaluation.py",
        ):
            tree = ast.parse((tests_dir / rel).read_text())
            assigns = [
                n for n in ast.walk(tree)
                if isinstance(n, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "pytestmark"
                    for t in n.targets
                )
            ]
            # Every assignment must carry the llm marker, not just the first.
            for a in assigns:
                if "pytest.mark.llm" not in ast.unparse(a.value):
                    bad.append(f"{rel}:{a.lineno}")
        assert not bad, (
            f"pytestmark reassigned without the llm marker, silently "
            f"discarding it: {bad}"
        )

    def test_marker_is_registered(self) -> None:
        import tomllib
        from pathlib import Path

        app_root = Path(__file__).resolve().parents[1]
        cfg = tomllib.loads((app_root / "pyproject.toml").read_text())
        markers = cfg["tool"]["pytest"]["ini_options"]["markers"]
        assert any(m.startswith("llm:") for m in markers), (
            "the `llm` marker must be registered in pyproject.toml so the "
            "deterministic gate can exclude it explicitly"
        )
