"""OntologyAI V5.1 — Canonical 12-node workflow vocabulary.

The platform authors workflows in its own vendor-neutral vocabulary of 12 node
kinds, then compiles them to n8n (a managed, invisible runtime — clients never
interact with n8n directly). Each node kind below declares its category, the
human-readable label shown in the workspace canvas palette, its required fields,
and a ``to_n8n`` mapping describing how the compiler lowers it to an n8n node
type + key wiring.

This module is intentionally dependency-free (stdlib only) so it can be
imported from Python activities and unit-tested without the full app stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

NodeCategory = Literal["trigger", "action", "logic", "io"]


@dataclass(frozen=True)
class NodeKind:
    """A single canonical node kind and its n8n compilation mapping."""

    kind: str
    label: str
    category: NodeCategory
    required_fields: tuple[str, ...] = ()
    # n8n node type (typeVersion omitted; compiler pins a sane default).
    n8n_type: str = ""
    # Developer note describing key wiring from the node config -> n8n params.
    n8n_wiring: str = ""

    def to_n8n(self) -> dict:
        """Return the n8n node-type descriptor for this kind."""
        return {
            "type": self.n8n_type,
            "wiring": self.n8n_wiring,
            "required_fields": list(self.required_fields),
        }


# ──────────────────────────────────────────────────────────────────────────
# Canonical 12-node vocabulary (PRD §7 / v5.1-final-spec.md)
# ──────────────────────────────────────────────────────────────────────────
NODE_KINDS: dict[str, NodeKind] = {
    # ── Triggers ──────────────────────────────────────────────────────────
    "trigger.manual": NodeKind(
        kind="trigger.manual",
        label="Manual Trigger",
        category="trigger",
        required_fields=(),
        n8n_type="n8n-nodes-base.manualTrigger",
        n8n_wiring="Emits a single empty item when run manually.",
    ),
    "trigger.schedule": NodeKind(
        kind="trigger.schedule",
        label="Schedule Trigger",
        category="trigger",
        required_fields=("cron",),
        n8n_type="n8n-nodes-base.scheduleTrigger",
        n8n_wiring="cron -> parameters.rule.interval -> cron expression.",
    ),
    "trigger.webhook": NodeKind(
        kind="trigger.webhook",
        label="Webhook Trigger",
        category="trigger",
        required_fields=("path", "method"),
        n8n_type="n8n-nodes-base.webhook",
        n8n_wiring="path -> parameters.path; method -> parameters.httpMethod.",
    ),
    # ── Actions ───────────────────────────────────────────────────────────
    "action.http": NodeKind(
        kind="action.http",
        label="HTTP Request",
        category="action",
        required_fields=("url", "method"),
        n8n_type="n8n-nodes-base.httpRequest",
        n8n_wiring="url -> parameters.url; method -> parameters.method; "
        "headers/body -> parameters.headers / parameters.body.",
    ),
    "action.llm": NodeKind(
        kind="action.llm",
        label="LLM Call",
        category="action",
        required_fields=("prompt", "model"),
        n8n_type="n8n-nodes-base.lmChatOpenAi",
        n8n_wiring="prompt -> messages; model -> parameters.model. "
        "Paired with an AI node for completion.",
    ),
    "action.db_query": NodeKind(
        kind="action.db_query",
        label="DB Query",
        category="action",
        required_fields=("connection", "query"),
        n8n_type="n8n-nodes-base.postgres",
        n8n_wiring="connection -> credentials; query -> parameters.query "
        "(operation=executeQuery).",
    ),
    "action.db_write": NodeKind(
        kind="action.db_write",
        label="DB Write",
        category="action",
        required_fields=("connection", "table", "operation"),
        n8n_type="n8n-nodes-base.postgres",
        n8n_wiring="connection -> credentials; table/operation -> "
        "parameters.table / parameters.operation.",
    ),
    "action.transform": NodeKind(
        kind="action.transform",
        label="Transform",
        category="action",
        required_fields=("expression",),
        n8n_type="n8n-nodes-base.set",
        n8n_wiring="expression -> parameters.assignments (field mappings).",
    ),
    "action.code": NodeKind(
        kind="action.code",
        label="Code",
        category="action",
        required_fields=("language", "code"),
        n8n_type="n8n-nodes-base.code",
        n8n_wiring="language -> parameters.language; code -> parameters.jsCode.",
    ),
    # ── Logic ─────────────────────────────────────────────────────────────
    "logic.branch": NodeKind(
        kind="logic.branch",
        label="Branch",
        category="logic",
        required_fields=("condition",),
        n8n_type="n8n-nodes-base.if",
        n8n_wiring="condition -> parameters.conditions; true/false outputs "
        "become the two output branches.",
    ),
    "logic.merge": NodeKind(
        kind="logic.merge",
        label="Merge",
        category="logic",
        required_fields=("mode",),
        n8n_type="n8n-nodes-base.merge",
        n8n_wiring="mode -> parameters.mode (append / combine).",
    ),
    # ── IO ────────────────────────────────────────────────────────────────
    "io.notify": NodeKind(
        kind="io.notify",
        label="Notify",
        category="io",
        required_fields=("channel", "message"),
        n8n_type="n8n-nodes-base.slack",
        n8n_wiring="channel -> parameters.channel; message -> parameters.text.",
    ),
}


def all_node_kinds() -> list[str]:
    """Return the sorted list of all canonical node kind identifiers."""
    return sorted(NODE_KINDS.keys())


def get_node_kind(kind: str) -> NodeKind:
    """Return a ``NodeKind`` by identifier, raising ``KeyError`` if unknown."""
    return NODE_KINDS[kind]


# Self-consistency guard: exactly 12 kinds, each with a category + n8n mapping.
def _validate() -> None:
    assert len(NODE_KINDS) == 12, f"expected 12 node kinds, got {len(NODE_KINDS)}"
    for nk in NODE_KINDS.values():
        assert nk.category in ("trigger", "action", "logic", "io")
        assert nk.n8n_type, f"{nk.kind} missing n8n_type"
        assert nk.to_n8n()["type"], f"{nk.kind} missing to_n8n mapping"


_validate()
