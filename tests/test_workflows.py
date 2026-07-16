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


if __name__ == "__main__":
    unittest.main()
