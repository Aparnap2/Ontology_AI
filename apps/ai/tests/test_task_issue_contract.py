"""RED contract: Task (planned work) and Issue (deviation) are SEPARATE types.

Expected to FAIL until `Task` exists in src/ontology/object_types.py and
`Issue` carries deviation fields. Rejects `Issue(kind="task")` conflation.
"""
import pytest
from pydantic import ValidationError

from src.ontology.object_types import Issue, Task

TASK_FIELDS = {
    "owner", "due_date", "status", "priority",
    "linked_requirement", "external_ref",
}
ISSUE_FIELDS = {
    "severity", "detected_at", "root_cause", "affected_entities",
    "owner", "resolution", "escalation",
}


class TestTaskIssueContract:
    def test_task_has_planned_work_fields(self):
        # Arrange / Act
        fields = set(Task.model_fields)
        # Assert
        assert TASK_FIELDS <= fields

    def test_issue_has_deviation_fields(self):
        # Arrange / Act
        fields = set(Issue.model_fields)
        # Assert
        assert ISSUE_FIELDS <= fields

    def test_task_and_issue_are_separate_types(self):
        # Arrange / Act / Assert
        assert Task is not Issue
        assert set(Task.model_fields) != set(Issue.model_fields)

    def test_rejects_issue_kind_task_conflation(self):
        # Arrange: "task" is not a valid Issue kind — planned work ≠ deviation
        # Act / Assert
        with pytest.raises(ValidationError):
            Issue(
                id="i-1", kind="task", severity="high", status="open",
                summary="conflated", detected_at="2026-01-01T00:00:00Z",
                root_cause="unknown", affected_entities=[],
                resolution=None, escalation=False,
            )

    def test_models_reject_extra_fields(self):
        # Arrange / Act / Assert
        assert Task.model_config.get("extra") == "forbid"
        assert Issue.model_config.get("extra") == "forbid"
        with pytest.raises(ValidationError):
            Task(
                id="t-9", owner="u-1", due_date=None, status="open",
                priority="medium", linked_requirement="r-1",
                external_ref="JIRA-1", unknown_field="boom",
            )
