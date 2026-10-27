"""Integration modules for OntologyAI.

The V6 worker path imports only V6-relevant connectors (jira, slack, notion,
salesforce). The legacy V5.2 integrations (stripe, plaid, erpnext, hubspot,
quickbooks) are gated behind the ``LEGACY_INTEGRATIONS`` env flag and emit a
deprecation warning when enabled. They are NOT imported by the V6 worker path
by default.
"""
import logging
import os

log = logging.getLogger("ontology_ai.integrations")

#: Env flag that re-enables legacy V5.2 integrations (stripe/plaid/erpnext/hubspot/quickbooks).
LEGACY_INTEGRATIONS_ENV = "LEGACY_INTEGRATIONS"

#: Modules considered legacy V5.2 integrations — gated out of the V6 worker path.
LEGACY_INTEGRATION_MODULES = (
    "src.integrations.stripe",
    "src.integrations.plaid",
    "src.integrations.erpnext",
    "src.integrations.hubspot",
    "src.integrations.quickbooks",
)


def legacy_integrations_enabled() -> bool:
    """Return True when legacy V5.2 integrations are enabled via ``LEGACY_INTEGRATIONS``.

    Defaults to disabled: the V6 worker path must not import legacy integrations.
    Emits a deprecation warning when enabled.
    """
    enabled = os.getenv(LEGACY_INTEGRATIONS_ENV, "0").lower() in ("1", "true", "on", "yes")
    if enabled:
        log.warning(
            "DEPRECATION: legacy V5.2 integrations (stripe, plaid, erpnext, hubspot, quickbooks) "
            "enabled via %s=1. These are deprecated in the V6 worker path and will be removed.",
            LEGACY_INTEGRATIONS_ENV,
        )
    return enabled
