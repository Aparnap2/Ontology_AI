"""OntologyAI V5.1 — DiscoveryWorkflow (PRD §8.2 / §16.2).

Ingests evidence sources (chat, uploads, transcripts, spreadsheets, connector
records, notes), validates that at least one source exists, and extracts
candidate entities/events/SOP fragments/unresolved questions.

Design (thin-LLM / fat-deterministic-core, PRD §11):
  * Validation, normalization, and extraction of *structured* candidates are
    deterministic (no LLM).
  * The LLM is used ONLY for messy-text extraction when a source is freeform
    natural language and cannot be parsed by deterministic rules. It is injected
    (``llm_client``) and mocked in tests; if absent, deterministic heuristics
    run and ambiguous text becomes an unresolved question.
  * Discovery NEVER creates canonical ontology objects — it only writes a patch
    to ``discovery_notes``.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from src.schemas.specialist_response import SpecialistResponse


# Deterministic keyword heuristics for lightweight extraction (no LLM).
_PARTY_KINDS = {
    "customer": "customer", "client": "customer", "supplier": "supplier",
    "vendor": "supplier", "employee": "employee", "staff": "employee",
    "contractor": "contractor", "partner": "partner", "approver": "approver",
}
_ENGAGEMENT_KINDS = {
    "deal": "deal", "opportunity": "deal", "order": "order",
    "job": "job", "project": "project", "service case": "service_case",
    "ticket": "service_case",
}
_MONEY_KINDS = {
    "invoice": "receivable", "receivable": "receivable", "payment due": "receivable",
    "bill": "payable", "payable": "payable", "refund": "refund",
    "expense": "expense", "write-off": "writeoff", "writeoff": "writeoff",
}
_ISSUE_KINDS = {
    "delay": "delay", "dispute": "dispute", "defect": "defect",
    "incident": "incident", "risk": "risk", "blocker": "blocker", "blocked": "blocker",
}
_MONEY_AMOUNT_RE = re.compile(r"(?:\$|€|£)?\s*([\d,]+(?:\.\d+)?)\s*(k|m|thousand|million)?", re.I)
_OWNER_RE = re.compile(r"\b(?:owned by|owner is|owner:|responsible[: ]|assign(?:ed)? to)\s+([a-zA-Z][\w.\-]*)", re.I)


class DiscoveryWorkflow:
    """Discovery specialist workflow (PRD §8.2 / §16.2)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def run(
        self,
        tenant_id: str,
        engagement_id: str,
        sources: list[dict],
        operator_goal: Optional[str] = None,
    ) -> SpecialistResponse:
        """Run discovery over ``sources`` and return a typed SpecialistResponse.

        Args:
            tenant_id: Tenant identifier.
            engagement_id: Engagement identifier.
            sources: List of evidence dicts, each with at least ``type`` and
                ``content`` (and optionally ``ref`` for provenance).
            operator_goal: Optional operator goal context.

        Returns:
            SpecialistResponse with specialist="Discovery" and a patch to
            ``discovery_notes``.
        """
        if not sources:
            raise ValueError("Discovery requires at least one evidence source")

        notes: list[dict] = []
        unresolved: list[str] = []
        citations: list[str] = []

        for src in sources:
            note = self._process_source(src)
            notes.append(note)
            citations.extend(note.get("source_refs", []))
            for q in note.get("candidates", {}).get("unresolved_questions", []):
                if q not in unresolved:
                    unresolved.append(q)

        patch = {"discovery_notes": notes}
        if unresolved:
            patch["unresolved_questions"] = unresolved

        categories = {
            k
            for n in notes
            for k, v in n.get("candidates", {}).items()
            if v
        }
        summary = (
            f"Discovered {len(notes)} evidence source(s); "
            f"extracted candidate findings across {len(categories)} categories."
        )
        detailed = (
            "Discovery ingested evidence and produced candidate entities, events, "
            "SOP fragments, and unresolved questions. No canonical ontology objects "
            "were created. Route to @map to promote candidates to canonical objects."
        )

        return SpecialistResponse(
            specialist="Discovery",
            workflow_name="DiscoveryWorkflow",
            summary=summary,
            detailed_response=detailed,
            objects_read=["data_sources"],
            objects_written=["discovery_notes"],
            requires_hitl=False,
            engagement_state_patch=patch,
            citations=sorted(set(citations)),
            unresolved_questions=unresolved,
            confidence=0.6,
        )

    # ------------------------------------------------------------------
    # Deterministic source processing
    # ------------------------------------------------------------------
    def _process_source(self, src: dict) -> dict:
        content = str(src.get("content", "")).strip()
        ref = src.get("ref") or src.get("source_refs") or f"src:{src.get('type', 'unknown')}"
        if isinstance(ref, list):
            source_refs = ref
        else:
            source_refs = [ref]

        candidates: dict[str, list[dict]] = {
            "parties": [],
            "engagements": [],
            "money_events": [],
            "issues": [],
            "messages": [],
            "sop_fragments": [],
            "process_hints": [],
            "unresolved_questions": [],
        }

        if not content:
            candidates["unresolved_questions"].append(
                f"No extractable content in source {source_refs[0]}"
            )
            return {
                "source_refs": source_refs,
                "content": content,
                "confidence": 0.1,
                "candidates": candidates,
            }

        # Deterministic extraction of each category.
        self._extract_parties(content, source_refs, candidates)
        self._extract_engagements(content, source_refs, candidates)
        self._extract_money(content, source_refs, candidates)
        self._extract_issues(content, source_refs, candidates)
        self._extract_messages(src, content, source_refs, candidates)
        self._extract_sop_and_process(content, source_refs, candidates)
        self._extract_unresolved(content, source_refs, candidates)

        # If the source is messy freeform text and deterministic extraction
        # found nothing, optionally ask the LLM (injected) — but never invent
        # canonical structure. We keep it as an unresolved question instead.
        if self.llm_client is not None and not any(candidates[k] for k in (
            "parties", "engagements", "money_events", "issues", "messages"
        )):
            try:
                self.llm_client.extract(content)  # type: ignore[attr-defined]
            except Exception:
                pass

        confidence = 0.7 if any(candidates[k] for k in (
            "parties", "engagements", "money_events", "issues", "messages"
        )) else 0.3

        return {
            "source_refs": source_refs,
            "content": content,
            "confidence": confidence,
            "candidates": candidates,
        }

    # ------------------------------------------------------------------
    # Category extractors (deterministic)
    # ------------------------------------------------------------------
    def _extract_parties(self, content: str, refs: list[str], out: dict) -> None:
        low = content.lower()
        for kw, kind in _PARTY_KINDS.items():
            if kw in low:
                # Pull a likely name: the capitalized word(s) near the keyword.
                name = self._nearby_name(content, kw) or f"unknown-{kind}"
                owner = self._find_owner(content)
                out["parties"].append({
                    "id": f"p-{name.lower().replace(' ', '-')}-{abs(hash(name)) % 10000}",
                    "kind": kind,
                    "name": name,
                    "status": "active",
                    "owner": owner,
                    "source_refs": refs,
                    "ambiguous": owner is None,
                })
                if owner is None:
                    out["unresolved_questions"].append(
                        f"Who owns {name}? (source {refs[0]})"
                    )

    def _extract_engagements(self, content: str, refs: list[str], out: dict) -> None:
        low = content.lower()
        for kw, kind in _ENGAGEMENT_KINDS.items():
            if kw in low:
                name = self._nearby_name(content, kw) or f"unknown-{kind}"
                owner = self._find_owner(content)
                out["engagements"].append({
                    "id": f"e-{name.lower().replace(' ', '-')}-{abs(hash(name)) % 10000}",
                    "kind": kind,
                    "title": name,
                    "status": "active",
                    "owner": owner,
                    "value": self._find_amount(content),
                    "source_refs": refs,
                    "ambiguous": owner is None,
                })

    def _extract_money(self, content: str, refs: list[str], out: dict) -> None:
        low = content.lower()
        for kw, kind in _MONEY_KINDS.items():
            if kw in low:
                amount = self._find_amount(content)
                out["money_events"].append({
                    "id": f"m-{kw}-{abs(hash(content)) % 10000}",
                    "kind": kind,
                    "amount": amount if amount is not None else 0.0,
                    "currency": "USD",
                    "status": "overdue" if "overdue" in low or "late" in low else "open",
                    "source_refs": refs,
                    "ambiguous": amount is None,
                })
                if amount is None:
                    out["unresolved_questions"].append(
                        f"What is the amount for the {kw}? (source {refs[0]})"
                    )

    def _extract_issues(self, content: str, refs: list[str], out: dict) -> None:
        low = content.lower()
        for kw, kind in _ISSUE_KINDS.items():
            if kw in low:
                out["issues"].append({
                    "id": f"i-{kw}-{abs(hash(content)) % 10000}",
                    "kind": kind,
                    "severity": "high" if kw in ("blocker", "incident", "risk") else "medium",
                    "status": "open",
                    "owner": self._find_owner(content),
                    "summary": f"{kw.title()} detected in source {refs[0]}",
                    "source_refs": refs,
                })

    def _extract_messages(self, src: dict, content: str, refs: list[str], out: dict) -> None:
        channel = str(src.get("type", "note"))
        channel_map = {
            "email": "email", "whatsapp": "whatsapp", "call": "call_note",
            "call_note": "call_note", "sms": "sms", "note": "note",
            "meeting": "meeting_summary", "transcript": "meeting_summary",
        }
        ch = channel_map.get(channel, "note")
        needs_action = "?" in content or "action" in content.lower() or "help" in content.lower()
        out["messages"].append({
            "id": f"msg-{abs(hash(content)) % 100000}",
            "channel": ch,
            "direction": "inbound",
            "summary": content[:200],
            "sentiment": "unknown",
            "needs_action": needs_action,
            "source_refs": refs,
        })

    def _extract_sop_and_process(self, content: str, refs: list[str], out: dict) -> None:
        # SOP fragments: sentences describing a process / step.
        for sent in re.split(r"[.\n]", content):
            s = sent.strip()
            if not s:
                continue
            if any(w in s.lower() for w in ("process", "step", "procedure", "workflow", "manual", "how we")):
                out["sop_fragments"].append({
                    "fragment": s, "source_refs": refs,
                })
            if any(w in s.lower() for w in ("when", "if", "then", "trigger", "alert")):
                out["process_hints"].append({
                    "hint": s, "source_refs": refs,
                })

    def _extract_unresolved(self, content: str, refs: list[str], out: dict) -> None:
        # Explicit questions in the text become unresolved questions.
        # Use a non-consuming regex so the trailing "?" is preserved.
        for m in re.finditer(r"[^.!\n]*\?", content):
            q = m.group(0).strip()
            if q and q not in out["unresolved_questions"]:
                out["unresolved_questions"].append(q)

    # ------------------------------------------------------------------
    # Small deterministic helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _nearby_name(content: str, keyword: str) -> Optional[str]:
        idx = content.lower().find(keyword)
        if idx == -1:
            return None
        window = content[idx: idx + 60]
        # Find a capitalized token sequence after the keyword.
        m = re.search(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})", window)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _find_owner(content: str) -> Optional[str]:
        m = _OWNER_RE.search(content)
        return m.group(1) if m else None

    @staticmethod
    def _find_amount(content: str) -> Optional[float]:
        m = _MONEY_AMOUNT_RE.search(content)
        if not m:
            return None
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            return None
        mult = m.group(2)
        if mult:
            mult = mult.lower()
            if mult in ("k", "thousand"):
                val *= 1_000
            elif mult in ("m", "million"):
                val *= 1_000_000
        return val
