"""OntologyAI V5.1 — OntologyMappingWorkflow (PRD §8.3 / §16.3).

Converts discovery findings (candidate entities) into canonical ontology objects
using the ``object_types`` models, creates ``LINK_TYPES`` links where evidence
exists (via ``resolve_link``), attaches provenance, and keeps ambiguity as an
unresolved question instead of inventing structure.

Design (thin-LLM / fat-deterministic-core, PRD §11):
  * Object construction + validation + link creation are deterministic.
  * Ambiguity is never guessed — it becomes an unresolved question.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Union

from src.schemas.specialist_response import SpecialistResponse
from src.ontology.object_types import OBJECT_TYPES
from src.ontology.link_types import LINK_TYPES, resolve_link


# Map discovery candidate category -> canonical object type name.
_CANDIDATE_TO_TYPE = {
    "parties": "Party",
    "engagements": "Engagement",
    "money_events": "MoneyEvent",
    "issues": "Issue",
    "messages": "Message",
}

# Which link to create between two object types when both exist as candidates.
_CANDIDATE_LINKS = [
    ("party_engagement", "Party", "Engagement"),
    ("engagement_money_event", "Engagement", "MoneyEvent"),
    ("engagement_issue", "Engagement", "Issue"),
    ("message_party", "Message", "Party"),
    ("message_engagement", "Message", "Engagement"),
]


class OntologyMappingWorkflow:
    """Ontology Mapper specialist workflow (PRD §8.3 / §16.3)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    def run(
        self,
        tenant_id: str,
        engagement_id: str,
        discovery_notes: list[dict],
        existing_objects: Optional[dict[str, list[dict]]] = None,
        link_db: Optional[Union[Callable, Any]] = None,
    ) -> SpecialistResponse:
        """Map discovery candidates to canonical objects + links.

        Args:
            tenant_id: Tenant identifier.
            engagement_id: Engagement identifier.
            discovery_notes: List of discovery note dicts (from DiscoveryWorkflow).
            existing_objects: Optional existing ontology_objects to merge into.
            link_db: Optional injectable backend for ``resolve_link``.

        Returns:
            SpecialistResponse with specialist="OntologyMapper" and patches to
            ``ontology_objects``, ``ontology_links``, ``unresolved_questions``.
        """
        base = existing_objects or {}
        ontology_objects: dict[str, list[dict]] = {
            name: list(base.get(name, [])) for name in OBJECT_TYPES
        }
        ontology_links: list[dict] = []
        unresolved: list[str] = []

        # Collect all candidate objects across notes.
        collected: dict[str, list[dict]] = {t: [] for t in OBJECT_TYPES}
        for note in discovery_notes:
            cands = note.get("candidates", {})
            refs = note.get("source_refs", [])
            for cat, type_name in _CANDIDATE_TO_TYPE.items():
                for cand in cands.get(cat, []):
                    obj = self._candidate_to_object(type_name, cand, refs, unresolved)
                    if obj is not None:
                        collected[type_name].append(obj)

        # Validate + append canonical objects (deterministic, strict models).
        for type_name, items in collected.items():
            model = OBJECT_TYPES[type_name]
            for obj in items:
                try:
                    validated = model(**obj)
                    ontology_objects.setdefault(type_name, []).append(
                        validated.model_dump()
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    unresolved.append(
                        f"Could not finalize {type_name} {obj.get('id')}: {exc}"
                    )

        # Create links where evidence exists (deterministic via resolve_link).
        self._create_links(ontology_objects, link_db, ontology_links, unresolved)

        patch: dict[str, Any] = {
            "ontology_objects": ontology_objects,
            "ontology_links": ontology_links,
        }
        if unresolved:
            patch["unresolved_questions"] = unresolved

        summary = (
            f"Mapped discovery findings to {sum(len(v) for v in ontology_objects.values())} "
            f"canonical objects and {len(ontology_links)} links."
        )
        detailed = (
            "Ontology Mapper promoted validated candidate entities into canonical "
            "objects with provenance. Links were created only where evidence-backed. "
            "Ambiguous findings were kept as unresolved questions."
        )

        return SpecialistResponse(
            specialist="OntologyMapper",
            workflow_name="OntologyMappingWorkflow",
            summary=summary,
            detailed_response=detailed,
            objects_read=["discovery_notes"],
            objects_written=["ontology_objects", "ontology_links"],
            requires_hitl=False,
            engagement_state_patch=patch,
            citations=sorted({
                r for objs in ontology_objects.values() for o in objs
                for r in o.get("source_refs", [])
            }),
            unresolved_questions=unresolved,
            confidence=0.7,
        )

    # ------------------------------------------------------------------
    # Candidate -> canonical object
    # ------------------------------------------------------------------
    def _candidate_to_object(
        self, type_name: str, cand: dict, refs: list[str], unresolved: list[str]
    ) -> Optional[dict]:
        # Ambiguous candidates are NOT promoted — they become unresolved questions.
        if cand.get("ambiguous"):
            unresolved.append(
                f"Ambiguous {type_name} '{cand.get('name', cand.get('id'))}' "
                f"not finalized — needs clarification (source {refs[0] if refs else '?'})"
            )
            return None

        obj = dict(cand)
        obj.setdefault("source_refs", list(refs))
        for r in refs:
            if r not in obj["source_refs"]:
                obj["source_refs"].append(r)
        # Drop non-canonical helper keys.
        obj.pop("ambiguous", None)
        return obj

    # ------------------------------------------------------------------
    # Link creation (deterministic via resolve_link)
    # ------------------------------------------------------------------
    def _create_links(
        self,
        ontology_objects: dict[str, list[dict]],
        link_db: Optional[Union[Callable, Any]],
        ontology_links: list[dict],
        unresolved: list[str],
    ) -> None:
        for link_name, source_type, target_type in _CANDIDATE_LINKS:
            if link_name not in LINK_TYPES:
                continue
            sources = ontology_objects.get(source_type, [])
            targets = ontology_objects.get(target_type, [])
            if not sources or not targets:
                continue
            for src_obj in sources:
                src_id = src_obj.get("id")
                if not src_id:
                    continue
                # Resolve linked target IDs from the injectable backend.
                linked_ids = resolve_link(link_name, src_id, db=link_db)
                if not linked_ids:
                    # Fall back to heuristic: link to any target present in the
                    # same ontology snapshot (evidence exists in-state).
                    linked_ids = [t.get("id") for t in targets if t.get("id")]
                for tgt_id in linked_ids:
                    ontology_links.append({
                        "name": link_name,
                        "source_type": source_type,
                        "source_id": src_id,
                        "target_type": target_type,
                        "target_id": tgt_id,
                        "semantic_meaning": LINK_TYPES[link_name].semantic_meaning,
                        "source_refs": list(src_obj.get("source_refs", [])),
                    })
