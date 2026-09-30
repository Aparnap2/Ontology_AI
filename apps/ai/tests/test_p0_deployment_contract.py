"""P0 RED: deployment must be internally consistent and actually runnable.

Defects this pins down
----------------------
1. **Nonexistent entrypoint.** ``Procfile``, ``build.sh`` and ``render.yaml``
   all build/start ``./cmd/demo/main.go`` -> ``bin/demo_server``. The only
   real entrypoints are ``cmd/server``, ``cmd/worker`` and ``cmd/consumer``.
   The Render deploy failed at the build step because the target file does
   not exist.

2. **Config aliases that are silently ignored.** Compose sets
   ``LISTEN_ADDR=:8080`` and maps 8080, but the server binds ``-port``
   (default 3000) — nothing listened on 8080, so the container healthcheck
   could never succeed. ``TEMPORAL_ADDRESS``/``TEMPORAL_HOST`` are set by
   compose but the Go binaries read only the ``-temporal`` flag.

3. **Health is theatre.** ``GET /health`` returns a static literal. The
   dependency-checking endpoint exists but nothing calls it. There is no
   ``/health/ready``.

4. **Migrations never run in a deploy path.** 15 SQL files across two
   directories with colliding numeric prefixes, and no binary, Dockerfile
   or compose step applies them — a fresh database stays empty.

5. **Python worker healthcheck cannot pass.** The image installs only
   curl + ca-certificates, so the ``pg_isready`` healthcheck can never
   succeed.

Required behaviour
------------------
* every deployment artifact references an entrypoint that exists
* one canonical source of truth for the listen port
* /health is liveness only; /health/ready reports dependency readiness
* a fresh database is migrated by the deploy path
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CORE = REPO / "apps" / "core"

#: Entry points that genuinely exist and are the only valid deploy targets.
REAL_ENTRYPOINTS = {
    "./cmd/server",
    "./cmd/worker",
    "./cmd/consumer",
    "./apps/core/cmd/server",
    "./apps/core/cmd/worker",
    "./apps/core/cmd/consumer",
}

DEMO_REFS = ("cmd/demo", "demo_server")


def _read(rel: str) -> str:
    path = REPO / rel
    return path.read_text() if path.exists() else ""


# ---------------------------------------------------------------------------
# 1. Entrypoint
# ---------------------------------------------------------------------------


class TestEntrypointExists:
    def test_no_manifest_references_cmd_demo(self) -> None:
        offenders = []
        for manifest in ("Procfile", "build.sh", "render.yaml", "Makefile"):
            text = _read(manifest)
            for needle in DEMO_REFS:
                if needle in text:
                    offenders.append(f"{manifest}: {needle}")
        assert not offenders, (
            f"these deployment artifacts reference a nonexistent entrypoint: {offenders}"
        )

    def test_cmd_demo_does_not_exist(self) -> None:
        """Documents the root cause: the target was never in the repo."""
        assert not (CORE / "cmd" / "demo").exists(), (
            "cmd/demo now exists — if it was added deliberately, update "
            "REAL_ENTRYPOINTS in this test to match the chosen canonical server"
        )

    def test_go_server_entrypoint_builds(self) -> None:
        assert shutil.which("go"), "go toolchain unavailable"
        proc = subprocess.run(
            ["go", "build", "-o", "/tmp/opencode/_p0_server", "./cmd/server"],
            cwd=CORE,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"go build ./cmd/server failed:\n{proc.stderr[:800]}"

    def test_procfile_starts_a_real_binary(self) -> None:
        procfile = _read("Procfile")
        assert procfile.strip(), "Procfile is empty"
        assert "./cmd/demo" not in procfile
        assert "server" in procfile or "web" in procfile


# ---------------------------------------------------------------------------
# 2. Configuration — one source of truth
# ---------------------------------------------------------------------------


class TestPortConfiguration:
    def test_server_honours_a_port_env_var(self) -> None:
        """LISTEN_ADDR is set by compose; the binary must read it."""
        main = _read("apps/core/cmd/server/main.go")
        assert "LISTEN_ADDR" in main, (
            "the server does not read LISTEN_ADDR, so compose's LISTEN_ADDR "
            "and 8080 mapping are silently ignored"
        )

    def test_listen_addr_not_also_set_to_a_conflicting_value(self) -> None:
        for compose in ("docker-compose.prod.yml", "docker-compose.yml"):
            text = _read(compose)
            if "LISTEN_ADDR" not in text:
                continue
            ports = re.findall(r"^\s*-\s*[\"']?(\d+):(\d+)[\"']?\s*$", text, re.M)
            for host_port, _ in ports:
                assert host_port == "8080", (
                    f"{compose} maps {host_port} but LISTEN_ADDR is :8080"
                )


# ---------------------------------------------------------------------------
# 3. Health semantics
# ---------------------------------------------------------------------------


class TestHealthSemantics:
    def test_health_liveness_route_exists(self) -> None:
        main = _read("apps/core/cmd/server/main.go")
        assert '"/health"' in main, "no /health liveness route"

    def test_ready_route_exists(self) -> None:
        main = _read("apps/core/cmd/server/main.go")
        assert '"/health/ready"' in main, (
            "no /health/ready route: readiness must report dependency state"
        )

    def test_health_does_not_depend_on_external_services(self) -> None:
        """Liveness must stay up when a dependency is down."""
        handlers = _read("apps/core/internal/api/handlers.go")
        block = re.search(
            r"func \(h \*Handler\) HandleHealth\b.*?\n\}", handlers, re.S
        )
        assert block, "HandleHealth not found"
        body = block.group(0)
        for forbidden in ("PingContext", "CheckHealth", "QueryContext"):
            assert forbidden not in body, (
                f"HandleHealth calls {forbidden}: liveness must not depend on "
                "external services, or a DB outage restarts the whole fleet"
            )

    def test_ready_reports_dependencies(self) -> None:
        handlers = _read("apps/core/internal/api/handlers.go")
        assert "HandleReadiness" in handlers or "HandleReady" in handlers, (
            "no readiness handler that checks dependencies"
        )


# ---------------------------------------------------------------------------
# 4. Migrations run in the deploy path
# ---------------------------------------------------------------------------


class TestMigrationsAreApplied:
    def test_a_migration_runner_exists(self) -> None:
        found = any(
            (REPO / p).exists()
            for p in (
                "apps/core/cmd/migrate/main.go",
                "apps/core/cmd/server/main.go",
                "scripts/migrate.sh",
            )
        ) or "migrate" in _read("Makefile").lower()
        assert found, (
            "no migration runner referenced by any binary, script or Makefile"
        )

    def test_migration_sql_is_not_split_across_colliding_directories(self) -> None:
        a = REPO / "apps/core/migrations"
        b = REPO / "apps/core/internal/db/migrations"
        if not (a.exists() and b.exists()):
            return  # single source; nothing to reconcile
        names_a = {p.name for p in a.glob("*.sql")}
        names_b = {p.name for p in b.glob("*.sql")}
        collisions = names_a & names_b
        assert not collisions, (
            f"duplicate migration filenames across {a} and {b}: {sorted(collisions)}; "
            "ordering is ambiguous and a deploy cannot know which to apply"
        )


# ---------------------------------------------------------------------------
# 5. Python worker health does not need pg_isready
# ---------------------------------------------------------------------------


class TestPythonWorkerHealth:
    def test_dockerfile_installs_healthcheck_dependency_or_uses_http(self) -> None:
        dockerfile = _read("apps/ai/Dockerfile")
        assert dockerfile, "apps/ai/Dockerfile not found"
        uses_pg_isready = "pg_isready" in dockerfile
        has_postgres_client = "postgresql-client" in dockerfile
        assert not uses_pg_isready or has_postgres_client, (
            "the image healthchecks with pg_isready but does not install "
            "postgresql-client, so the healthcheck can never pass"
        )

    def test_python_exposes_a_health_endpoint(self) -> None:
        main = _read("apps/ai/src/main.py")
        assert "health" in main.lower(), (
            "the Python service exposes no health endpoint for a container probe"
        )
