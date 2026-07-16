"""TDD tests for executable_workflow_draft re-export (PRD §12.7).

Written BEFORE implementation. Run first — must FAIL, then implement to pass.
"""


class TestExecutableWorkflowDraftReexport:
    """Re-export path from ontology.workflow_drafts must work."""

    def test_module_reexports_symbol(self):
        from src.schemas import executable_workflow_draft as mod
        assert hasattr(mod, "ExecutableWorkflowDraft")

    def test_symbol_is_same_as_source_of_truth(self):
        from src.ontology.workflow_drafts import ExecutableWorkflowDraft as Source
        from src.schemas.executable_workflow_draft import ExecutableWorkflowDraft as Reexport
        assert Reexport is Source

    def test_can_construct_draft(self):
        from src.schemas.executable_workflow_draft import ExecutableWorkflowDraft
        draft = ExecutableWorkflowDraft(
            id="draft-1",
            runtime="n8n",
            name="Invoice Approval",
            source_workflow_spec_id="ws-001",
        )
        assert draft.id == "draft-1"
        assert draft.status == "draft"
