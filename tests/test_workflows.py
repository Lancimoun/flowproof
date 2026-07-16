import tempfile
import unittest
from pathlib import Path

from flowproof import InvalidTransition, WorkflowStore


class WorkflowStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = WorkflowStore(Path(self.tempdir.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def test_safe_event_completes_through_rules(self) -> None:
        result = self.store.ingest("evt-safe", "invoice.paid", {"amount": 25})
        self.assertEqual(result["route"], "rules")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["duplicate"])

    def test_high_risk_event_waits_for_human_approval(self) -> None:
        result = self.store.ingest(
            "evt-risk", "payment.requested", {"amount": 2500}
        )
        self.assertEqual(result["route"], "human_review")
        self.assertEqual(result["status"], "pending_approval")

    def test_ambiguous_event_routes_to_ai_assist_without_calling_a_model(self) -> None:
        result = self.store.ingest(
            "evt-ai", "email.received", {"needs_interpretation": True}
        )
        self.assertEqual(result["route"], "ai_assist")
        self.assertEqual(result["status"], "pending_approval")

    def test_duplicate_webhook_returns_same_workflow(self) -> None:
        first = self.store.ingest("evt-repeat", "invoice.paid", {"amount": 25})
        second = self.store.ingest("evt-repeat", "invoice.paid", {"amount": 25})
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(
            [event["action"] for event in second["audit"]],
            ["workflow_created", "duplicate_received"],
        )

    def test_reviewer_decision_is_recorded_in_audit_history(self) -> None:
        pending = self.store.ingest(
            "evt-approve", "payment.requested", {"risk_score": 0.9}
        )
        decided = self.store.decide(pending["id"], "approve", "Lance")
        self.assertEqual(decided["status"], "approved")
        self.assertEqual(decided["audit"][-1]["action"], "workflow_approved")
        self.assertEqual(decided["audit"][-1]["detail"]["reviewer"], "Lance")

    def test_completed_workflow_cannot_be_decided(self) -> None:
        completed = self.store.ingest("evt-done", "invoice.paid", {})
        with self.assertRaises(InvalidTransition):
            self.store.decide(completed["id"], "reject", "Lance")

    def test_approved_workflow_failure_schedules_bounded_retry(self) -> None:
        pending = self.store.ingest(
            "evt-retry", "payment.requested", {"requires_approval": True}
        )
        approved = self.store.decide(pending["id"], "approve", "Lance")

        failed = self.store.record_failure(approved["id"], "provider timeout")

        self.assertEqual(failed["status"], "retry_pending")
        self.assertEqual(failed["attempt_count"], 1)
        self.assertEqual(failed["max_attempts"], 3)
        self.assertEqual(failed["audit"][-1]["action"], "attempt_failed")
        self.assertEqual(failed["audit"][-1]["detail"]["error"], "provider timeout")

    def test_retry_budget_exhaustion_dead_letters_workflow(self) -> None:
        pending = self.store.ingest(
            "evt-dead", "email.received", {"needs_interpretation": True}
        )
        workflow = self.store.decide(pending["id"], "approve", "Lance")

        for attempt in range(1, 4):
            workflow = self.store.record_failure(
                workflow["id"], f"failure {attempt}"
            )

        self.assertEqual(workflow["status"], "dead_letter")
        self.assertEqual(workflow["attempt_count"], 3)
        self.assertEqual(workflow["audit"][-1]["action"], "workflow_dead_lettered")
        with self.assertRaises(InvalidTransition):
            self.store.record_failure(workflow["id"], "failure 4")

    def test_pending_approval_cannot_record_execution_failure(self) -> None:
        pending = self.store.ingest(
            "evt-not-approved", "payment.requested", {"amount": 2500}
        )
        with self.assertRaises(InvalidTransition):
            self.store.record_failure(pending["id"], "must not execute")


if __name__ == "__main__":
    unittest.main()
