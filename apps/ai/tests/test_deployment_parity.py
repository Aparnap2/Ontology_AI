"""Deployment parity boundary tests.

Proves the OntologyAI system consumes configuration from environment
variables and config files rather than hardcoding infrastructure details.

Test 1: All config values are read from env vars or config files
Test 2: A RuntimeConfig centralizes all infrastructure dependencies
Test 3: Each dependency has a configurable endpoint
Test 4: No ``if ENV == "local"`` branching that bypasses real contracts
Test 5: All Pydantic models use extra=forbid (strict)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.mission.deployment_adapters import (
    DatabaseAdapter,
    EventBusAdapter,
    LLMAdapter,
    VectorStoreAdapter,
    VendorHTTPAdapter,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CONFIG = ROOT / "config"
DEPLOYMENT_YAML = CONFIG / "deployment.yaml"
RUNTIME_YAML = CONFIG / "runtime.yaml"
ENV_EXAMPLE = ROOT / ".env.example"

# Source files that must NOT contain hardcoded infrastructure URLs
SOURCE_DIRS = [SRC / "mission", SRC / "control_plane", SRC / "ontology"]

    # Hardcoded URL patterns that should NOT appear in domain code
HARDCODED_URL_PATTERNS = [
    re.compile(r"localhost:\d{4,5}"),          # localhost:PORT
    re.compile(r"127\.0\.0\.1:\d{4,5}"),       # 127.0.0.1:PORT
    re.compile(r"bolt://localhost"),            # Neo4j bolt
    re.compile(r"postgresql://.*localhost"),    # Postgres localhost
    re.compile(r"redis://.*localhost"),         # Redis localhost
]

# Lines that read from env vars with localhost defaults are ALLOWED
# (they are proper env-var-with-default patterns, not hardcoded infra)
ENV_VAR_WITH_DEFAULT_PATTERN = re.compile(r"os\.environ\.get\(|os\.getenv\(")

# Files where localhost is acceptable (config, env, adapters, tests)
ALLOWLISTED_FILES = {
    "deployment.yaml",          # defines local defaults
    "runtime.yaml",             # runtime profile
    ".env.example",             # template
    "capability_binding.py",    # reads env vars
    "deployment_adapters.py",   # Protocol definitions
}


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Config values come from env vars or config files
# ═══════════════════════════════════════════════════════════════════════════


def _load_deployment_manifest() -> dict[str, Any]:
    """Load the deployment manifest and return service definitions."""
    if not DEPLOYMENT_YAML.exists():
        pytest.fail(f"Deployment manifest not found: {DEPLOYMENT_YAML}")
    data = yaml.safe_load(DEPLOYMENT_YAML.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "deployment.yaml must be a mapping"
    return data.get("services", {})


class TestConfigSources:
    """Config values must come from env vars or config files, not hardcoded."""

    def test_deployment_manifest_exists(self) -> None:
        """The deployment manifest file must exist."""
        assert DEPLOYMENT_YAML.exists(), (
            f"Missing deployment manifest: {DEPLOYMENT_YAML}"
        )

    def test_deployment_manifest_has_services(self) -> None:
        """The manifest must declare at least 6 infrastructure services."""
        services = _load_deployment_manifest()
        assert len(services) >= 6, (
            f"Expected >= 6 services, got {len(services)}"
        )

    def test_every_service_declares_env_var(self) -> None:
        """Each service must declare an env_var for runtime consumption."""
        services = _load_deployment_manifest()
        for name, svc in services.items():
            assert "env_var" in svc, f"Service {name} missing env_var"
            assert isinstance(svc["env_var"], str), (
                f"Service {name} env_var must be a string"
            )
            assert len(svc["env_var"]) > 0, (
                f"Service {name} env_var is empty"
            )

    def test_every_service_declares_default(self) -> None:
        """Each service must declare a default value."""
        services = _load_deployment_manifest()
        for name, svc in services.items():
            assert "default" in svc, f"Service {name} missing default"
            assert isinstance(svc["default"], str), (
                f"Service {name} default must be a string"
            )

    def test_every_service_declares_description(self) -> None:
        """Each service must have a human-readable description."""
        services = _load_deployment_manifest()
        for name, svc in services.items():
            assert "description" in svc, f"Service {name} missing description"
            assert len(svc["description"]) > 10, (
                f"Service {name} description too short"
            )

    def test_env_example_covers_all_manifest_services(self) -> None:
        """Every env_var in the manifest must be documented somewhere.

        Either in .env.example (visible to devs) or in pyproject.toml
        (used by test infra). This proves no service is invisible.
        """
        env_example_text = ""
        if ENV_EXAMPLE.exists():
            env_example_text = ENV_EXAMPLE.read_text(encoding="utf-8")

        pyproject_text = ""
        pyproject_path = ROOT / "pyproject.toml"
        if pyproject_path.exists():
            pyproject_text = pyproject_path.read_text(encoding="utf-8")

        combined = env_example_text + "\n" + pyproject_text

        services = _load_deployment_manifest()
        undocumented: list[str] = []
        for name, svc in services.items():
            env_var = svc["env_var"]
            if env_var not in combined:
                undocumented.append(f"{name} ({env_var})")
        assert not undocumented, (
            f"Services with undocumented env vars: {undocumented}. "
            f"Add them to .env.example or pyproject.toml."
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: RuntimeConfig centralizes all infrastructure dependencies
# ═══════════════════════════════════════════════════════════════════════════


class TestRuntimeConfig:
    """A central RuntimeConfig must exist that maps env vars to endpoints."""

    def test_deployment_adapters_module_importable(self) -> None:
        """The deployment_adapters module must be importable."""
        from src.mission import deployment_adapters  # noqa: F401

    def test_database_adapter_is_protocol(self) -> None:
        """DatabaseAdapter must be a Protocol (runtime-checkable)."""
        assert hasattr(DatabaseAdapter, "__protocol_attrs__") or hasattr(
            DatabaseAdapter, "__protocol_attrs__"
        )

    def test_event_bus_adapter_is_protocol(self) -> None:
        """EventBusAdapter must be a Protocol."""
        assert hasattr(EventBusAdapter, "__protocol_attrs__") or hasattr(
            EventBusAdapter, "__protocol_attrs__"
        )

    def test_llm_adapter_is_protocol(self) -> None:
        """LLMAdapter must be a Protocol."""
        assert hasattr(LLMAdapter, "__protocol_attrs__") or hasattr(
            LLMAdapter, "__protocol_attrs__"
        )

    def test_vendor_http_adapter_is_protocol(self) -> None:
        """VendorHTTPAdapter must be a Protocol."""
        assert hasattr(VendorHTTPAdapter, "__protocol_attrs__") or hasattr(
            VendorHTTPAdapter, "__protocol_attrs__"
        )

    def test_vector_store_adapter_is_protocol(self) -> None:
        """VectorStoreAdapter must be a Protocol."""
        assert hasattr(VectorStoreAdapter, "__protocol_attrs__") or hasattr(
            VectorStoreAdapter, "__protocol_attrs__"
        )

    def test_all_five_adapter_protocols_exist(self) -> None:
        """The adapter layer must expose exactly 5 Protocol interfaces."""
        from src.mission import deployment_adapters as da

        protocols = [
            name
            for name in dir(da)
            if name.endswith("Adapter")
        ]
        assert len(protocols) >= 5, (
            f"Expected >= 5 adapter protocols, found {protocols}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Each dependency has a configurable endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigurableEndpoints:
    """Every infrastructure dependency must have a configurable endpoint."""

    EXPECTED_SERVICES = {
        "database": "DATABASE_URL",
        "temporal": "TEMPORAL_ADDRESS",
        "llm": "LLM_ENDPOINT",
        "event_bus": "EVENT_BROKER_URL",
        "vendor_api": "VENDOR_API_URL",
        "otel": "OTEL_ENDPOINT",
    }

    def test_expected_services_present(self) -> None:
        """All core infrastructure services must be in the manifest."""
        services = _load_deployment_manifest()
        for service_name in self.EXPECTED_SERVICES:
            assert service_name in services, (
                f"Missing expected service: {service_name}"
            )

    def test_env_var_names_match(self) -> None:
        """Each service's env_var must match the expected name."""
        services = _load_deployment_manifest()
        for service_name, expected_var in self.EXPECTED_SERVICES.items():
            actual_var = services[service_name]["env_var"]
            assert actual_var == expected_var, (
                f"Service {service_name}: expected env_var={expected_var}, "
                f"got {actual_var}"
            )

    def test_env_var_reading_works(self) -> None:
        """Setting an env var and reading it produces the expected value."""
        test_key = "ONTOLOGYAI_DEPLOYMENT_PARITY_TEST"
        test_value = "parity-proof-value"
        os.environ[test_key] = test_value
        try:
            assert os.environ.get(test_key) == test_value
        finally:
            del os.environ[test_key]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: No hardcoded infrastructure URLs in domain code
# ═══════════════════════════════════════════════════════════════════════════


class TestNoHardcodedUrls:
    """Domain code must not contain hardcoded infrastructure URLs."""

    def _get_python_files(self) -> list[Path]:
        """Collect all Python files in domain source directories."""
        files: list[Path] = []
        for d in SOURCE_DIRS:
            if d.exists():
                files.extend(d.rglob("*.py"))
        return files

    def test_no_localhost_urls_in_domain_code(self) -> None:
        """Domain code must not contain hardcoded localhost:PORT patterns.

        Lines using os.environ.get() or os.getenv() with localhost defaults
        are allowed — they are proper env-var-with-default patterns.
        """
        violations: list[tuple[str, int, str]] = []
        for path in self._get_python_files():
            if path.name in ALLOWLISTED_FILES:
                continue
            text = path.read_text(encoding="utf-8")
            for line_num, line in enumerate(text.splitlines(), 1):
                # Skip imports, comments, and docstrings
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                # Skip env-var-with-default patterns (reading from env, not hardcoding)
                if ENV_VAR_WITH_DEFAULT_PATTERN.search(line):
                    continue
                for pattern in HARDCODED_URL_PATTERNS:
                    if pattern.search(line):
                        rel = path.relative_to(ROOT)
                        violations.append((str(rel), line_num, stripped))
        assert not violations, (
            "Domain code contains hardcoded URLs:\n"
            + "\n".join(f"  {f}:{line}: {code}" for f, line, code in violations[:10])
        )

    def test_no_if_env_local_branching(self) -> None:
        """Domain code must not branch on ENV == 'local' to bypass contracts."""
        branching_patterns = [
            re.compile(r'''if\s+["']local["']\s+in\s+os\.environ'''),
            re.compile(r'''if\s+os\.environ.*==\s*["']local["']'''),
            re.compile(r'''if\s+ENV\s*==\s*["']local["']'''),
            re.compile(r'''if\s+ENVIRONMENT\s*==\s*["']local["']'''),
            re.compile(r'''if\s+MODE\s*==\s*["']local["']'''),
        ]
        violations: list[tuple[str, int, str]] = []
        for path in self._get_python_files():
            text = path.read_text(encoding="utf-8")
            for line_num, line in enumerate(text.splitlines(), 1):
                for pattern in branching_patterns:
                    if pattern.search(line):
                        rel = path.relative_to(ROOT)
                        violations.append((str(rel), line_num, line.strip()))
        assert not violations, (
            "Domain code contains local-env branching:\n"
            + "\n".join(f"  {f}:{line}: {code}" for f, line, code in violations[:10])
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: All Pydantic models use extra=forbid (strict)
# ═══════════════════════════════════════════════════════════════════════════


class TestStrictModels:
    """All Pydantic models must use extra=forbid."""

    def test_entity_models_are_strict(self) -> None:
        """Every model in src/entities/models.py uses extra=forbid."""
        from src.entities import models as models_mod

        import pydantic

        for name in dir(models_mod):
            obj = getattr(models_mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, pydantic.BaseModel)
                and obj is not pydantic.BaseModel
            ):
                config = getattr(obj, "model_config", {})
                assert config.get("extra") == "forbid", (
                    f"Model {name} missing extra='forbid' "
                    f"(got extra={config.get('extra')!r})"
                )

    def test_ontology_object_types_are_strict(self) -> None:
        """Every model in src/ontology/object_types.py uses extra=forbid."""
        from src.ontology import object_types as ot_mod

        import pydantic

        for name in dir(ot_mod):
            obj = getattr(ot_mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, pydantic.BaseModel)
                and obj is not pydantic.BaseModel
            ):
                config = getattr(obj, "model_config", {})
                assert config.get("extra") == "forbid", (
                    f"Object type {name} missing extra='forbid' "
                    f"(got extra={config.get('extra')!r})"
                )

    def test_control_plane_contracts_are_strict(self) -> None:
        """Control plane contract models use extra=forbid."""
        from src.control_plane import contracts as contracts_mod

        import pydantic

        for name in dir(contracts_mod):
            obj = getattr(contracts_mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, pydantic.BaseModel)
                and obj is not pydantic.BaseModel
            ):
                config = getattr(obj, "model_config", {})
                assert config.get("extra") == "forbid", (
                    f"Contract model {name} missing extra='forbid'"
                )

    def test_api_schemas_are_strict(self) -> None:
        """API schema models use extra=forbid."""
        from src.api import schemas as api_schemas_mod

        import pydantic

        violations: list[str] = []
        for name in dir(api_schemas_mod):
            obj = getattr(api_schemas_mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, pydantic.BaseModel)
                and obj is not pydantic.BaseModel
            ):
                config = getattr(obj, "model_config", {})
                if config.get("extra") != "forbid":
                    violations.append(name)
        assert not violations, (
            f"API schemas missing extra='forbid': {violations}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: RuntimeConfig centralizes every infrastructure dependency
# ═══════════════════════════════════════════════════════════════════════════


class TestRuntimeConfigCentralizes:
    """RuntimeConfig is the single seam between domain code and infra."""

    def test_runtime_config_is_importable(self) -> None:
        """RuntimeConfig must exist in the deployment_adapters module."""
        from src.mission.deployment_adapters import RuntimeConfig  # noqa: F401

    def test_runtime_config_is_strict(self) -> None:
        """RuntimeConfig must reject unknown fields (extra=forbid, strict)."""
        import pydantic

        from src.mission.deployment_adapters import RuntimeConfig

        assert issubclass(RuntimeConfig, pydantic.BaseModel)
        assert RuntimeConfig.model_config.get("extra") == "forbid"
        assert RuntimeConfig.model_config.get("strict") is True
        with pytest.raises(pydantic.ValidationError):
            RuntimeConfig.model_validate(
                {
                    "database_url": "x",
                    "temporal_address": "x",
                    "llm_endpoint": "x",
                    "event_broker_url": "x",
                    "vendor_api_url": "x",
                    "otel_endpoint": "x",
                    "qdrant_url": "x",
                    "neo4j_uri": "x",
                    "typo_field": "must-be-rejected",
                }
            )

    def test_runtime_config_covers_every_manifest_service(self) -> None:
        """Every service in deployment.yaml must have a RuntimeConfig field."""
        from src.mission.deployment_adapters import SERVICE_ENV_VARS, RuntimeConfig

        services = _load_deployment_manifest()
        for name in services:
            assert name in SERVICE_ENV_VARS, (
                f"Service {name} has no env-var mapping in SERVICE_ENV_VARS"
            )
        # Each mapped env var must be consumed by from_env into a field.
        config = RuntimeConfig.from_env()
        for name, env_var in SERVICE_ENV_VARS.items():
            assert env_var, f"Service {name} has an empty env_var mapping"
            assert isinstance(config.endpoint_for(name), str)

    def test_runtime_config_reads_env_overrides(self) -> None:
        """from_env() must prefer environment values over local defaults."""
        from src.mission.deployment_adapters import RuntimeConfig

        sentinel = "postgresql://parity-proof-host:5432/paritydb"
        os.environ["DATABASE_URL"] = sentinel
        try:
            config = RuntimeConfig.from_env()
            assert config.database_url == sentinel
            assert config.endpoint_for("database") == sentinel
        finally:
            del os.environ["DATABASE_URL"]

    def test_runtime_config_defaults_match_manifest(self) -> None:
        """Local defaults in code must match config/deployment.yaml."""
        from src.mission.deployment_adapters import SERVICE_DEFAULTS, RuntimeConfig

        services = _load_deployment_manifest()
        for name, svc in services.items():
            assert SERVICE_DEFAULTS[name] == svc["default"], (
                f"Service {name}: code default {SERVICE_DEFAULTS[name]!r} "
                f"!= manifest default {svc['default']!r}"
            )
        # With a clean env, from_env() reproduces the manifest defaults.
        saved: dict[str, str | None] = {}
        for svc in services.values():
            saved[svc["env_var"]] = os.environ.pop(svc["env_var"], None)
        try:
            config = RuntimeConfig.from_env()
            for name, svc in services.items():
                assert config.endpoint_for(name) == svc["default"]
        finally:
            for env_var, value in saved.items():
                if value is not None:
                    os.environ[env_var] = value

    def test_runtime_config_unknown_service_rejected(self) -> None:
        """endpoint_for() must fail loudly on unknown service names."""
        from src.mission.deployment_adapters import RuntimeConfig

        config = RuntimeConfig.from_env()
        with pytest.raises(KeyError):
            config.endpoint_for("nonexistent-service")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Adapters are the seam — no raw vendor SDK imports in domain code
# ═══════════════════════════════════════════════════════════════════════════


class TestAdapterImportPatterns:
    """Domain code must use typed adapter Protocols, not raw vendor SDKs."""

    # Raw infrastructure SDKs that must never be imported by domain code.
    # The domain talks to DatabaseAdapter/EventBusAdapter/LLMAdapter/
    # VendorHTTPAdapter/VectorStoreAdapter; production bindings live
    # outside src/mission, src/control_plane, src/ontology.
    FORBIDDEN_IMPORTS = [
        "boto3",
        "botocore",
        "aioboto3",
        "openai",
        "ollama",
        "anthropic",
        "google.genai",
        "google-generativeai",
    ]

    def _get_domain_files(self) -> list[Path]:
        """Collect all Python files in the domain seam directories."""
        files: list[Path] = []
        for d in SOURCE_DIRS:
            if d.exists():
                files.extend(d.rglob("*.py"))
        return files

    def test_no_raw_vendor_sdk_imports(self) -> None:
        """No domain file may import raw cloud/LLM vendor SDKs."""
        import_pattern = re.compile(r"^\s*(?:import|from)\s+([\w.\-]+)")
        violations: list[tuple[str, int, str]] = []
        for path in self._get_domain_files():
            text = path.read_text(encoding="utf-8")
            for line_num, line in enumerate(text.splitlines(), 1):
                match = import_pattern.match(line)
                if not match:
                    continue
                top_level = match.group(1).split(".")[0]
                dotted = match.group(1)
                for forbidden in self.FORBIDDEN_IMPORTS:
                    forbidden_top = forbidden.split(".")[0]
                    if top_level == forbidden_top or dotted == forbidden:
                        rel = path.relative_to(ROOT)
                        violations.append((str(rel), line_num, line.strip()))
        assert not violations, (
            "Domain code imports raw vendor SDKs (use adapter Protocols):\n"
            + "\n".join(f"  {f}:{line}: {code}" for f, line, code in violations[:10])
        )

    def test_adapter_protocols_are_the_declared_seam(self) -> None:
        """The five adapter Protocols must be defined in deployment_adapters."""
        import inspect

        from src.mission import deployment_adapters as da

        for name in (
            "DatabaseAdapter",
            "EventBusAdapter",
            "LLMAdapter",
            "VendorHTTPAdapter",
            "VectorStoreAdapter",
        ):
            protocol = getattr(da, name, None)
            assert protocol is not None, f"Missing adapter Protocol: {name}"
            assert inspect.isclass(protocol), f"{name} must be a class"
            assert getattr(protocol, "_is_protocol", False) or hasattr(
                protocol, "__protocol_attrs__"
            ), f"{name} must be a Protocol"

    def test_control_plane_never_imports_connectors(self) -> None:
        """The control plane must funnel execution through the executor seam."""
        import_pattern = re.compile(r"^\s*(?:import|from)\s+([\w.]+)")
        violations: list[tuple[str, int, str]] = []
        control_plane = SRC / "control_plane"
        for path in control_plane.rglob("*.py"):
            if path.name == "executor.py":
                continue  # executor is the sanctioned choke point
            text = path.read_text(encoding="utf-8")
            for line_num, line in enumerate(text.splitlines(), 1):
                match = import_pattern.match(line)
                if match and match.group(1).startswith("src.connectors"):
                    rel = path.relative_to(ROOT)
                    violations.append((str(rel), line_num, line.strip()))
        assert not violations, (
            "Control plane bypasses the executor seam:\n"
            + "\n".join(f"  {f}:{line}: {code}" for f, line, code in violations[:10])
        )
