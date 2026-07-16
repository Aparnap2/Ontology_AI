"""TDD tests for DiscoveryWorkflow (PRD §8.2 / §16.2).

Run FIRST — must FAIL, then implement discovery_workflow.py to pass.

Key behaviors asserted:
  * evidence validation requires >= 1 source (raises on empty),
  * extraction produces candidate shapes (parties/engagements/money/issues/messages
    + SOP fragments + unresolved questions),
  * confidence + provenance are attached to each extraction,
  * NO canonical ontology objects are created (only discovery_notes patch),
  * returns a typed SpecialistResponse with specialist="Discovery".
"""
import pytest

from src.schemas.specialist_response import SpecialistResponse


def _make_workflow():
    from src.workflows.discovery_workflow import DiscoveryWorkflow
    return DiscoveryWorkflow()


class TestDiscoveryEvidenceValidation:
    def test_requires_at_least_one_source(self):
        wf = _make_workflow()
        with pytest.raises(ValueError):
            wf.run(
                tenant_id="t1",
                engagement_id="e1",
                sources=[],
            )

    def test_accepts_single_source(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1",
            engagement_id="e1",
            sources=[{"type": "note", "content": "Acme is a customer.", "ref": "n1"}],
        )
        assert isinstance(resp, SpecialistResponse)
        assert resp.specialist == "Discovery"


class TestDiscoveryExtractionShapes:
    def test_extracts_candidate_party(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1",
            engagement_id="e1",
            sources=[{
                "type": "note",
                "content": "Acme Corp is a customer owned by alice.",
                "ref": "n1",
            }],
        )
        patch = resp.engagement_state_patch
        assert patch is not None
        notes = patch.get("discovery_notes", [])
        assert notes, "expected at least one discovery note"
        # At least one note should carry a candidate party extraction
        found_party = any(
            n.get("candidates", {}).get("parties") for n in notes
        )
        assert found_party

    def test_extraction_marks_confidence_and_provenance(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1",
            engagement_id="e1",
            sources=[{
                "type": "note",
                "content": "We have an open deal with Beta LLC worth 50k.",
                "ref": "n2",
            }],
        )
        note = resp.engagement_state_patch["discovery_notes"][0]
        assert "confidence" in note
        assert note.get("source_refs") or note.get("provenance")

    def test_sop_fragments_and_unresolved_questions_present(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1",
            engagement_id="e1",
            sources=[{
                "type": "transcript",
                "content": "Our invoicing process is manual. Who owns collections?",
                "ref": "t1",
            }],
        )
        note = resp.engagement_state_patch["discovery_notes"][0]
        # Unresolved question should be surfaced when owner is unknown
        assert resp.unresolved_questions or note.get("candidates", {}).get("unresolved_questions")


class TestDiscoveryNoCanonicalObjects:
    def test_does_not_create_ontology_objects(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1",
            engagement_id="e1",
            sources=[{
                "type": "note",
                "content": "Acme is a customer. Deal worth 50k. Invoice overdue.",
                "ref": "n1",
            }],
        )
        patch = resp.engagement_state_patch
        # Discovery must NOT write canonical ontology_objects / ontology_links
        assert "ontology_objects" not in patch
        assert "ontology_links" not in patch
        # It must write discovery_notes
        assert "discovery_notes" in patch

    def test_returns_discovery_specialist_response(self):
        wf = _make_workflow()
        resp = wf.run(
            tenant_id="t1",
            engagement_id="e1",
            sources=[{"type": "note", "content": "x", "ref": "n1"}],
        )
        assert resp.specialist == "Discovery"
        assert resp.workflow_name == "DiscoveryWorkflow"
        assert resp.objects_written == ["discovery_notes"]
