"""P0 RED: a clean clone must build the Go module.

Vulnerability
-------------
``.gitignore`` ignores ``gen/`` wholesale, but ``apps/core/go.mod``
contains::

    replace github.com/Aparnap2/iterate_swarm/gen/go => ../../gen/go

The hand-maintained module metadata that ``replace`` points at
(``gen/go/go.mod`` and ``gen/go/go.sum``) was therefore untracked. Anyone
who cloned the repository — a new contributor, a CI runner, a deploy
target — got::

    replacement directory ../../gen/go does not exist

and *no* Go package could be built at all. ``ci-go.yml`` already runs
``buf generate``, but that only emits ``*.pb.go``; it never creates the
module file, so CI failed at module resolution too.

Required behaviour
------------------
* ``gen/go/go.mod`` and ``gen/go/go.sum`` are TRACKED (stable, hand-owned)
* generated ``*.pb.go`` stay UNTRACKED (reproducible via ``buf generate``)
* the ``replace`` target resolves without machine-local state
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GEN_GO = REPO_ROOT / "gen" / "go"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout


def _tracked() -> set[str]:
    return set(_git("ls-files").split())


# ---------------------------------------------------------------------------
# The module metadata the replace directive depends on must be tracked
# ---------------------------------------------------------------------------


class TestGenGoModuleIsTracked:
    def test_gen_go_go_mod_is_tracked(self) -> None:
        assert "gen/go/go.mod" in _tracked(), (
            "gen/go/go.mod is untracked, so a clean clone cannot resolve the "
            "replace directive in apps/core/go.mod"
        )

    def test_gen_go_go_sum_is_tracked(self) -> None:
        assert "gen/go/go.sum" in _tracked(), (
            "gen/go/go.sum is untracked, so a clean clone fails dependency "
            "verification for the gen/go module"
        )

    def test_module_path_matches_the_replace_directive(self) -> None:
        declared = _git("show", "HEAD:apps/core/go.mod") if False else (
            REPO_ROOT / "apps/core/go.mod"
        ).read_text()
        replace = re.search(
            r"replace\s+(\S+)\s+=>\s+(\S+)", declared
        )
        assert replace is not None, "apps/core/go.mod has no replace directive"

        module_path, target = replace.group(1), replace.group(2)
        module_decl = (GEN_GO / "go.mod").read_text()
        assert f"module {module_path}" in module_decl, (
            f"gen/go/go.mod declares a different module path than the replace "
            f"directive expects ({module_path})"
        )
        assert (REPO_ROOT / "apps/core" / target).resolve() == GEN_GO.resolve(), (
            f"replace target {target} does not resolve to {GEN_GO}"
        )


# ---------------------------------------------------------------------------
# Generated code must stay out of git (it is reproducible)
# ---------------------------------------------------------------------------


class TestGeneratedCodeStaysUntracked:
    def test_pb_go_files_are_not_tracked(self) -> None:
        tracked_pb = [p for p in _tracked() if p.endswith(".pb.go")]
        assert not tracked_pb, (
            f"generated protobuf files are tracked and will drift: {tracked_pb}"
        )

    def test_buf_generation_is_declared(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text()
        assert "buf" in makefile and "generate" in makefile, (
            "no buf generate target: clean clones cannot reproduce gen/"
        )

    def test_proto_sources_are_tracked(self) -> None:
        protos = [p for p in _tracked() if p.endswith(".proto")]
        assert protos, "no .proto sources are tracked, so nothing can be generated"
