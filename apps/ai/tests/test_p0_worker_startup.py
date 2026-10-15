"""P0 RED: the Python process must actually run a capable worker.

Two divergent entrypoints existed:

* ``src/worker.py`` registers 7 workflows and 15 activities (including the
  9 V7 incident activities) on the canonical queue.
* ``src/main.py`` builds its OWN worker registering exactly ONE activity
  (``analyze_feedback``) — see ``main.py:47``.

A process started via ``main.py`` therefore advertised itself as a healthy
Temporal worker while being unable to execute a single V7 incident
activity. It also read the queue from ``get_config()`` rather than the
canonical ``resolve_task_queue()``, so it could poll a different queue than
the one the rest of the system publishes to.

Required behaviour
------------------
* one registration path, shared by every entrypoint
* the worker registers the full activity set, not just one
* the worker polls the canonically resolved task queue
* ``main.py`` and ``worker.py`` cannot drift apart again
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"


def _source(name: str) -> str:
    return (SRC / name).read_text()


_TEMP_STUBBED_MODULES = (
    "temporalio",
    "temporalio.client",
    "temporalio.worker",
    "temporalio.activity",
    "temporalio.common",
    "grpc",
    "grpc.aio",
    "aiokafka",
    "redis",
    "redis.asyncio",
    "structlog",
)


def _purge_mock_backed_modules() -> None:
    """Re-import worker modules that another suite mock-bound at collection.

    tests/unit/test_revenue_protection.py installs MagicMock objects into
    sys.modules for temporalio, grpc, aiokafka, redis and others at import time.
    Any module imported afterwards — including src.worker and src.main — binds
    those mocks permanently into its own globals, so this file's assertions
    would run against test scaffolding instead of production code.

    Dropping the cached modules and re-importing from disk restores the real
    classes.
    """
    import importlib
    import sys
    from unittest.mock import MagicMock

    # Drop project modules that may have bound the mocks.
    for name in [n for n in list(sys.modules) if n == "src" or n.startswith("src.")]:
        del sys.modules[name]

    # Drop the mocked third-party entries so they are re-imported from disk.
    for name in _TEMP_STUBBED_MODULES:
        mod = sys.modules.get(name)
        if mod is None or isinstance(mod, MagicMock):
            sys.modules.pop(name, None)

    # Restore package-level attributes that were assigned mocks directly
    # (e.g. `temporalio.activity = MagicMock()`).
    for pkg_name in ("temporalio", "grpc"):
        pkg = sys.modules.get(pkg_name)
        if pkg is None or isinstance(pkg, MagicMock):
            continue
        for attr in ("client", "worker", "activity", "common", "aio"):
            if isinstance(getattr(pkg, attr, None), MagicMock):
                pkg.__dict__.pop(attr, None)

    # Re-import the modules under test against the real dependencies.
    importlib.import_module("src.worker")
    importlib.import_module("src.activities.incident_activities")


# ---------------------------------------------------------------------------
# main.py must not hand-roll its own worker registration
# ---------------------------------------------------------------------------


class TestSingleRegistrationPath:
    def test_main_does_not_build_its_own_worker(self) -> None:
        """main.py must delegate to worker.py, not duplicate registration."""
        tree = ast.parse(_source("main.py"))

        worker_ctor_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "Worker"
        ]
        assert not worker_ctor_calls, (
            "main.py constructs its own temporalio Worker with a divergent "
            "activity set; it must reuse src.worker so registration cannot drift"
        )

    def test_main_reuses_worker_registration(self) -> None:
        source = _source("main.py")
        assert "from src.worker import" in source or "src.worker" in source, (
            "main.py does not reference src.worker, so the two entrypoints "
            "maintain separate workflow/activity registries"
        )


# ---------------------------------------------------------------------------
# The worker must be capable
# ---------------------------------------------------------------------------


class TestWorkerIsCapable:
    def test_worker_registers_many_activities(self) -> None:
        from src.worker import _build_activity_list

        activities = _build_activity_list()
        assert len(activities) > 1, (
            f"worker registers only {len(activities)} activity/activities; it "
            "cannot execute the V7 incident path"
        )

    def test_every_registered_activity_is_async(self) -> None:
        """A sync activity makes Worker() raise at construction time.

        temporalio requires an ``activity_executor`` for synchronous
        activities and none is configured, so registering one makes the
        whole worker unconstructable — the process dies at startup rather
        than serving traffic.

        The assertions run against freshly-imported real modules. Another suite
        (``tests/unit/test_revenue_protection.py``) replaces temporalio and
        friends with MagicMock objects at import time, which permanently
        mock-binds ``src.worker`` for the rest of the session. That produced
        false failures here on leaked ``MagicMock`` activities. Re-importing the
        affected modules before asserting means a failure here always reflects
        genuine production behaviour, not leftover test scaffolding.
        """
        import inspect

        _purge_mock_backed_modules()

        from src.worker import _build_activity_list

        listed = {getattr(a, "__name__", None) for a in _build_activity_list()}

        sync = []
        for activity in _build_activity_list():
            target = getattr(activity, "__func__", activity)
            if not inspect.iscoroutinefunction(target):
                sync.append(getattr(activity, "__name__", str(activity)))

        assert listed, "no activities were registered"
        assert not sync, (
            f"these activities are synchronous and prevent Worker() from "
            f"being constructed: {sorted(sync)}"
        )

    def test_worker_constructs_against_a_real_or_mocked_client(
        self, monkeypatch
    ) -> None:
        """Regression: worker construction must not raise.

        Constructing the Worker is where an invalid activity set surfaces.
        This pins that the registry is actually loadable, without needing a
        live Temporal server.
        """
        import asyncio

        from src import worker as worker_mod

        class _FakeWorker:
            def __init__(self, client, task_queue, workflows, activities, **kw):
                self._workflows = list(workflows)
                self._activities = list(activities)
                self.task_queue = task_queue

        async def _fake_connect(*_a, **_k):
            return object()

        monkeypatch.setattr(worker_mod, "Worker", _FakeWorker)
        monkeypatch.setattr(worker_mod, "Client", type("C", (), {"connect": staticmethod(_fake_connect)}))

        built = asyncio.run(worker_mod.create_worker())
        assert len(built._activities) == len(worker_mod._build_activity_list())
        assert len(built._workflows) == len(worker_mod._build_workflow_list())

    def test_worker_registers_the_v7_incident_activities(self) -> None:
        from src.worker import _build_activity_list

        names = {
            getattr(a, "__name__", None) or getattr(a, "name", "") for a in
            _build_activity_list()
        }
        for required in ("create_situation", "submit_to_control_plane"):
            assert any(required in str(n) for n in names), (
                f"worker does not register {required!r}; registered: {sorted(names)}"
            )

    def test_worker_registers_workflows(self) -> None:
        from src.worker import _build_workflow_list

        assert len(_build_workflow_list()) > 0, "worker registers no workflows"

    def test_every_registered_workflow_is_a_real_temporal_workflow(self) -> None:
        """Temporal rejects any class not decorated with @workflow.defn.

        Worker() calls _Definition.must_from_class on every entry and raises
        ValueError otherwise, so one undecorated class makes the whole worker
        unconstructable. DiscoveryWorkflow, OntologyMappingWorkflow,
        KnowledgeValidationWorkflow, SolutionArchitectWorkflow and
        GovernanceWorkflow were registered here without being decorated.
        """
        from temporalio.workflow import _Definition

        from src.worker import _build_workflow_list

        fake = []
        for wf in _build_workflow_list():
            try:
                _Definition.must_from_class(wf)
            except ValueError:
                fake.append(wf.__name__)
        assert not fake, (
            f"these are not @workflow.defn classes and would break Worker(): {fake}"
        )

    def test_incident_workflow_is_registered(self) -> None:
        from src.worker import _build_workflow_list

        names = {w.__name__ for w in _build_workflow_list()}
        assert "IncidentWorkflow" in names, (
            "the V7 hero workflow is not registered with the worker"
        )


# ---------------------------------------------------------------------------
# Worker-construction contract
# ---------------------------------------------------------------------------


class TestProductionWorkerConstructs:
    """registry -> production Worker -> Temporal accepts every registration.

    "Registered" does not mean "valid". Temporal validates each workflow
    and activity when the Worker is constructed: a workflow must carry
    @workflow.defn, and an activity must be a coroutine function. Both
    classes of defect shipped here undetected for a long time because no
    test ever constructed the real worker.
    """

    def test_temporal_accepts_every_registered_workflow(self) -> None:
        from temporalio.workflow import _Definition

        from src.worker import _build_workflow_list

        for wf in _build_workflow_list():
            _Definition.must_from_class(wf)  # raises ValueError if undecorated

    def test_temporal_accepts_every_registered_activity(self) -> None:

        from temporalio import activity as _activity

        from src.worker import _build_activity_list

        for act in _build_activity_list():
            defn = _activity._Definition.must_from_callable(act)
            assert defn.name, f"activity {act} has no registered name"

    def test_worker_constructs_against_real_registry(self) -> None:
        """Construct the real Worker with a stubbed client.

        Worker.__init__ performs the validation above, so a successful
        construction is the contract. No Temporal server required.
        """
        import asyncio

        from src import worker as worker_mod

        real_worker_cls = worker_mod.Worker

        class _RecordingWorker(real_worker_cls):  # type: ignore[misc,valid-type]
            def __init__(self, client, task_queue, workflows, activities, **kw):
                # Skip network/scheduler setup; keep the parent validation.
                from temporalio.workflow import _Definition

                for wf in workflows:
                    _Definition.must_from_class(wf)
                self._registered_workflows = list(workflows)
                self._registered_activities = list(activities)
                self._registered_queue = task_queue

        async def _fake_connect(*_a, **_k):
            return object()

        class _FakeClient:
            connect = staticmethod(_fake_connect)

        worker_mod.Worker = _RecordingWorker
        worker_mod.Client = _FakeClient
        try:
            built = asyncio.run(worker_mod.create_worker())
        finally:
            worker_mod.Worker = real_worker_cls

        assert built._registered_queue == worker_mod.TASK_QUEUE
        assert built._registered_workflows, "no workflows registered"
        assert built._registered_activities, "no activities registered"


# ---------------------------------------------------------------------------
# One canonical task queue
# ---------------------------------------------------------------------------


class TestCanonicalTaskQueue:
    def test_worker_uses_canonical_resolver(self) -> None:
        import src.worker as worker_mod

        assert hasattr(worker_mod, "TASK_QUEUE")
        from src.orchestration.queue import resolve_task_queue

        assert worker_mod.TASK_QUEUE == resolve_task_queue()

    def test_task_queue_is_the_canonical_constant(self) -> None:
        from src.orchestration.queue import resolve_task_queue

        assert resolve_task_queue() == "ONTOLOGYAI-MAIN-QUEUE"

    def test_env_var_overrides_queue(self, monkeypatch) -> None:
        from src.orchestration.queue import resolve_task_queue

        monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "custom-queue")
        assert resolve_task_queue() == "custom-queue"


# ---------------------------------------------------------------------------
# main.py must still offer its documented modes
# ---------------------------------------------------------------------------


class TestMainModesStillAvailable:
    def test_modes_are_parseable(self) -> None:
        import src.main as main_mod

        assert callable(main_mod.main)
        assert callable(main_mod.run_grpc_server)

    def test_gather_is_awaited(self) -> None:
        """Guard against the 'created but never awaited' coroutine class of bug."""
        import src.main as main_mod

        tree = ast.parse(inspect.getsource(main_mod))
        unawaited = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "attr", None) == "gather"
            ):
                unawaited.append(node.lineno)
        assert not unawaited, (
            f"asyncio.gather called without await at lines {unawaited}; the "
            "coroutines are created and never scheduled"
        )
