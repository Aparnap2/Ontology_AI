"""V6 worker import-gate tests.

Proves that the V6 worker path imports cleanly WITHOUT the 5 legacy V5.2
integrations (stripe, plaid, erpnext, hubspot, quickbooks) by default, and
that the ``LEGACY_INTEGRATIONS`` env flag re-enables them with a deprecation
warning.

The legacy integration modules themselves are NOT deleted (SAFE_DELETION_PROTOCOL);
they are simply gated out of the V6 worker import path.
"""
import logging
import os
import sys

import pytest

from src.integrations import (
    LEGACY_INTEGRATION_MODULES,
    LEGACY_INTEGRATIONS_ENV,
    legacy_integrations_enabled,
)

_MISSING = object()


def _pop_legacy_modules() -> dict[str, object]:
    """Evict legacy integration modules; return their prior ``sys.modules`` entries.

    The eviction is a *view* of the gate under test, not a permanent mutation:
    ``_restore_legacy_modules`` puts the exact prior state back. Evicting without
    restoring made a later suite's ``@patch("src.integrations.erpnext.MOCK_MODE",
    ...)`` re-import a fresh module while that suite still held a stale
    ``get_erpnext_snapshot`` bound to the evicted module, producing
    order-dependent failures in ``tests/unit/integrations/``.
    """
    saved = {mod: sys.modules.get(mod, _MISSING) for mod in LEGACY_INTEGRATION_MODULES}
    for mod in LEGACY_INTEGRATION_MODULES:
        sys.modules.pop(mod, None)
    return saved


def _restore_legacy_modules(saved: dict[str, object]) -> None:
    """Restore the exact ``sys.modules`` entries captured by the eviction."""
    for mod, original in saved.items():
        if original is _MISSING:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = original


def test_legacy_integrations_disabled_by_default():
    """Without LEGACY_INTEGRATIONS set, the gate is closed."""
    os.environ.pop(LEGACY_INTEGRATIONS_ENV, None)
    assert legacy_integrations_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "on", "yes", "TRUE"])
def test_legacy_integrations_enabled_with_flag(value):
    """LEGACY_INTEGRATIONS=1 (and truthy variants) opens the gate."""
    os.environ[LEGACY_INTEGRATIONS_ENV] = value
    try:
        assert legacy_integrations_enabled() is True
    finally:
        os.environ.pop(LEGACY_INTEGRATIONS_ENV, None)


def test_legacy_integrations_enabled_logs_deprecation(caplog):
    """Enabling legacy integrations emits a deprecation warning."""
    os.environ[LEGACY_INTEGRATIONS_ENV] = "1"
    try:
        with caplog.at_level(logging.WARNING, logger="ontology_ai.integrations"):
            legacy_integrations_enabled()
        assert any("DEPRECATION" in r.message for r in caplog.records)
    finally:
        os.environ.pop(LEGACY_INTEGRATIONS_ENV, None)


def test_integrations_package_does_not_import_legacy_modules():
    """Importing src.integrations must not pull in the 5 legacy modules."""
    os.environ.pop(LEGACY_INTEGRATIONS_ENV, None)
    saved = _pop_legacy_modules()
    try:
        import src.integrations  # noqa: F401

        loaded = {m for m in sys.modules if m in LEGACY_INTEGRATION_MODULES}
        assert loaded == set(), f"legacy modules imported: {loaded}"
    finally:
        _restore_legacy_modules(saved)


def test_worker_imports_cleanly_without_legacy_integrations():
    """The V6 worker entry imports without loading any legacy integration module."""
    pytest.importorskip("temporalio", reason="temporalio not installed")
    os.environ.pop(LEGACY_INTEGRATIONS_ENV, None)
    saved = _pop_legacy_modules()
    try:
        import src.worker  # noqa: F401

        loaded = {m for m in sys.modules if m in LEGACY_INTEGRATION_MODULES}
        assert loaded == set(), f"legacy modules imported by worker: {loaded}"
    finally:
        _restore_legacy_modules(saved)