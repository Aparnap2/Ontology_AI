"""TDD tests for OntologyMappingWorkflow (PRD §8.3 / §16.3).

Run FIRST — must FAIL, then implement ontology_mapping_workflow.py to pass.

Key behaviors asserted:
  * discovery candidates -> canonical objects (using object_types models),
  * links created via resolve_link where evidence exists,
  * provenance attached (source_refs),
  * ambiguity kept as unresolved question instead of invented structure,
  * returns patches to ontology_objects, ontology_links, unresolved_questions,
  * specialist="OntologyMapper".
"""
import pytest

from src.schemas.specialist_response import SpecialistResponse
from src.ontology.object_types import OBJECT_TYPES


def _make_workflow():
    from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
    return OntologyMappingWorkflow()


class TestOntologyMappingCandidatesToObjects:
    def test_converts_candidates_to_canonical_objects(self):
        wf = _make_workflow()
        discovery_notes = [{
            "source_refs": ["n1"],
            "candidates": {
                "parties": [{
                    "id": "p-acme", "kind": "customer", "name": "Acme",
                    "status": "active", "owner": "alice",
                }],
                "engagements": [{
                    "id": "e-deal", "kind": "deal", "title": "Big Deal",
                    "status": "active", "owner": "bob", "value": 50000.0,
                }],
            },
        }]
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            discovery_notes=discovery_notes,
        )
        patch = resp.engagement_state_patch
        objects = patch["ontology_objects"]
        assert "Party" in objects and "Engagement" in objects
        # Objects must validate against canonical models
        Party = OBJECT_TYPES["Party"]
        Engagement = OBJECT_TYPES["Engagement"]
        Party(**objects["Party"][0])
        Engagement(**objects["Engagement"][0])

    def test_attaches_source_refs_provenance(self):
        wf = _make_workflow()
        discovery_notes = [{
            "source_refs": ["n1"],
            "candidates": {
                "parties": [{
                    "id": "p-acme", "kind": "customer", "name": "Acme",
                    "status": "active", "owner": "alice",
                }],
            },
        }]
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            discovery_notes=discovery_notes,
        )
        party = resp.engagement_state_patch["ontology_objects"]["Party"][0]
        assert "n1" in party["source_refs"]


class TestOntologyMappingLinks:
    def test_creates_link_via_resolve_link(self):
        wf = _make_workflow()
        discovery_notes = [{
            "source_refs": ["n1"],
            "candidates": {
                "parties": [{
                    "id": "p-acme", "kind": "customer", "name": "Acme",
                    "status": "active", "owner": "alice",
                }],
                "engagements": [{
                    "id": "e-deal", "kind": "deal", "title": "Big Deal",
                    "status": "active", "owner": "bob",
                }],
            },
        }]
        # Inject a link resolver that asserts the party<->engagement link exists
        fake_db = {
            ("Party", "p-acme", "party_engagement"): ["e-deal"],
        }
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            discovery_notes=discovery_notes,
            link_db=fake_db,
        )
        links = resp.engagement_state_patch["ontology_links"]
        assert any(l["name"] == "party_engagement" for l in links)


class TestOntologyMappingAmbiguity:
    def test_ambiguity_becomes_unresolved_question(self):
        wf = _make_workflow()
        discovery_notes = [{
            "source_refs": ["n1"],
            "candidates": {
                "parties": [{
                    "id": "p-x", "kind": "customer", "name": "Unknown Co",
                    "status": "active",
                    # ambiguous: no clear owner, conflicting hints
                    "ambiguous": True,
                }],
            },
        }]
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            discovery_notes=discovery_notes,
        )
        # Ambiguity must NOT be guessed; it becomes an unresolved question
        assert resp.unresolved_questions
        # And the ambiguous object should not be finalized as canonical
        parties = resp.engagement_state_patch["ontology_objects"].get("Party", [])
        assert all(p.get("id") != "p-x" for p in parties)


class TestOntologyMappingResponse:
    def test_returns_ontology_mapper_response(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            discovery_notes=[{
                "source_refs": ["n1"],
                "candidates": {
                    "parties": [{
                        "id": "p-acme", "kind": "customer", "name": "Acme",
                        "status": "active", "owner": "alice",
                    }],
                },
            }],
        )
        assert isinstance(resp, SpecialistResponse)
        assert resp.specialist == "OntologyMapper"
        assert resp.workflow_name == "OntologyMappingWorkflow"
        assert "ontology_objects" in resp.engagement_state_patch
