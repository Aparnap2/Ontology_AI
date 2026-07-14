"""
ChiefOfStaffWorkflow — On-Demand Q&A (renamed from QAWorkflow).

Orchestrates on-demand question answering:
1. Run QAAgent activity to answer the question
2. Send Slack notification with the answer
3. Handle errors by sending failure notification

Canonical name: "ChiefOfStaffWorkflow"
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities at module level for workflow context
with workflow.unsafe.imports_passed_through():
    from src.activities.run_qa_agent import run_qa_agent
    from src.activities.send_slack_message import send_slack_message
    # OntologyAI V4.2: optional MissionState -> Ontology enrichment helper.
    from src.ontology.adapter import mission_state_to_ontology


@workflow.defn(name="ChiefOfStaffWorkflow")
class ChiefOfStaffWorkflow:
    """
    ChiefOfStaffWorkflow for answering on-demand questions.

    This workflow:
    1. Executes run_qa_agent activity to answer the question
    2. Sends Slack notification with the answer
    3. Handles failures by sending error notification to Slack
    """

    @workflow.run
    async def run(self, input: dict) -> dict:
        """
        Execute the Chief of Staff workflow.

        Args:
            input: dict with keys:
                - tenant_id: str (required)
                - question: str (required)
                - notify_channel: str (optional, defaults to #qa)

        Returns:
            dict with keys:
                - ok: bool
                - tenant_id: str
                - question: str
                - qa_result: dict (from QAAgent)
                - slack_result: dict (from send_slack_message)
                - error: str (only if ok=False)
        """
        tenant_id = input.get("tenant_id", "")
        question = input.get("question", "")
        notify_channel = input.get("notify_channel", "#qa")

        if not tenant_id:
            return {"ok": False, "error": "tenant_id is required"}

        if not question:
            return {"ok": False, "error": "question is required"}

        # ── OntologyAI V4.2: optional MissionState → Ontology enrichment ──
        # Additive + non-breaking: only runs when a ``mission_state`` dict is
        # supplied in the input. Any failure is swallowed (logged) so the
        # existing Q&A flow is never affected. Existing MissionState access in
        # downstream activities is untouched.
        ontology_context: dict = {}
        raw_mission_state = input.get("mission_state")
        if raw_mission_state is not None:
            try:
                ontology_context = mission_state_to_ontology(raw_mission_state)
            except Exception as enrich_exc:  # pragma: no cover - defensive
                workflow.logger.warning(
                    f"Ontology enrichment skipped for {tenant_id}: {enrich_exc}"
                )
                ontology_context = {}

        workflow.logger.info(f"ChiefOfStaffWorkflow starting for tenant {tenant_id}: {question[:50]}...")

        # Retry policy for activities
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=1),
            maximum_attempts=3,
            non_retryable_error_types=["ValueError"],
        )

        # Step 1: Run QAAgent
        try:
            qa_result = await workflow.execute_activity(
                run_qa_agent,
                args=[tenant_id, question],
                retry_policy=retry_policy,
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=2),
            )

            if not qa_result.get("ok"):
                error_msg = qa_result.get("error", "Unknown error")
                workflow.logger.error(f"QAAgent failed: {error_msg}")

                # Send failure notification
                await workflow.execute_activity(
                    send_slack_message,
                    f"❌ QAAgent failed for {tenant_id}: {error_msg}",
                    retry_policy=retry_policy,
                    start_to_close_timeout=timedelta(minutes=2),
                )

                return {"ok": False, "tenant_id": tenant_id, "question": question, "error": error_msg, "ontology_context": ontology_context}

            workflow.logger.info(f"QAAgent completed: {qa_result.get('answer', '')[:100]}")

        except Exception as e:
            workflow.logger.error(f"QAAgent activity failed: {e}")

            # Send failure notification
            await workflow.execute_activity(
                send_slack_message,
                f"❌ ChiefOfStaffWorkflow failed for {tenant_id}: {str(e)}",
                retry_policy=retry_policy,
                start_to_close_timeout=timedelta(minutes=2),
            )

            return {"ok": False, "tenant_id": tenant_id, "question": question, "error": str(e)}

        # Step 2: Send Slack notification with answer
        try:
            answer = qa_result.get("answer", "No answer generated")
            slack_blocks = qa_result.get("slack_blocks", [])

            slack_result = await workflow.execute_activity(
                send_slack_message,
                args=[answer, slack_blocks] if slack_blocks else [answer],
                retry_policy=retry_policy,
                start_to_close_timeout=timedelta(minutes=2),
            )

            workflow.logger.info(f"Slack notification sent: {slack_result}")

        except Exception as e:
            workflow.logger.error(f"Slack notification failed: {e}")
            # Don't fail the workflow if Slack fails — just log
            slack_result = {"ok": False, "error": str(e)}

        return {
            "ok": True,
            "tenant_id": tenant_id,
            "question": question,
            "qa_result": qa_result,
            "slack_result": slack_result,
        }
