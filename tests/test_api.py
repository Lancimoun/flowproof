"""Contract tests for the FastAPI adapter.

The core ledger is stdlib-only and always testable. This module covers the HTTP
surface, so it skips cleanly when FastAPI is not installed rather than breaking
the dependency-free core run.
"""

import os
import tempfile
import unittest
import warnings
from pathlib import Path

_TEMPDIR = tempfile.TemporaryDirectory()
os.environ["FLOWPROOF_DATABASE"] = str(Path(_TEMPDIR.name) / "api-test.db")

try:
    from fastapi.testclient import TestClient

    from flowproof.api import app, store

    client: "TestClient | None" = TestClient(app)
except ImportError:  # pragma: no cover - exercised only without FastAPI installed
    client = None
    store = None


def tearDownModule() -> None:
    # Windows will not unlink the temp DB while SQLite still holds the handle.
    if store is not None:
        store.close()
    _TEMPDIR.cleanup()


@unittest.skipIf(client is None, "fastapi/httpx2 not installed")
class HealthContractTests(unittest.TestCase):
    def test_health_reports_ok_and_version(self) -> None:
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "version": "0.1.0"})


@unittest.skipIf(client is None, "fastapi/httpx2 not installed")
class WarningPolicyContractTests(unittest.TestCase):
    def test_starlette_warning_policy_is_applied_after_import_and_can_fail(
        self,
    ) -> None:
        from run_tests import configure_warning_policy
        from starlette.exceptions import StarletteDeprecationWarning

        original_filters = warnings.filters[:]
        try:
            configure_warning_policy()
            with self.assertRaises(StarletteDeprecationWarning):
                warnings.warn("contract probe", StarletteDeprecationWarning)
        finally:
            warnings.filters[:] = original_filters


@unittest.skipIf(client is None, "fastapi/httpx2 not installed")
class WebhookContractTests(unittest.TestCase):
    def test_new_delivery_returns_201_created(self) -> None:
        response = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "api-new"},
            json={"event_type": "invoice.paid", "payload": {"amount": 25}},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["route"], "rules")
        self.assertEqual(body["status"], "completed")
        self.assertFalse(body["duplicate"])

    def test_replayed_delivery_returns_200_not_201(self) -> None:
        """A retried webhook created nothing, so it must not report 201 Created."""
        headers = {"Idempotency-Key": "api-replay"}
        body = {"event_type": "invoice.paid", "payload": {"amount": 25}}
        first = client.post("/webhooks", headers=headers, json=body)
        second = client.post("/webhooks", headers=headers, json=body)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertTrue(second.json()["duplicate"])

    def test_missing_idempotency_key_is_rejected(self) -> None:
        response = client.post(
            "/webhooks", json={"event_type": "invoice.paid", "payload": {}}
        )
        self.assertEqual(response.status_code, 422)

    def test_blank_idempotency_key_is_rejected(self) -> None:
        response = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "   "},
            json={"event_type": "invoice.paid", "payload": {}},
        )
        self.assertEqual(response.status_code, 422)

    def test_blank_event_type_is_rejected(self) -> None:
        response = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "api-blank-event"},
            json={"event_type": "", "payload": {}},
        )
        self.assertEqual(response.status_code, 422)

    def test_high_risk_delivery_is_held_for_review(self) -> None:
        response = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "api-risk"},
            json={"event_type": "payment.requested", "payload": {"amount": 2500}},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["route"], "human_review")
        self.assertEqual(response.json()["status"], "pending_approval")


@unittest.skipIf(client is None, "fastapi/httpx2 not installed")
class WorkflowReadContractTests(unittest.TestCase):
    def test_known_workflow_exposes_audit_history(self) -> None:
        created = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "api-read"},
            json={"event_type": "invoice.paid", "payload": {"amount": 10}},
        ).json()

        response = client.get(f"/workflows/{created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [event["action"] for event in response.json()["audit"]],
            ["workflow_created"],
        )

    def test_unknown_workflow_returns_404(self) -> None:
        response = client.get("/workflows/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "workflow not found")


@unittest.skipIf(client is None, "fastapi/httpx2 not installed")
class DecisionContractTests(unittest.TestCase):
    def _pending_workflow_id(self, key: str) -> str:
        return client.post(
            "/webhooks",
            headers={"Idempotency-Key": key},
            json={"event_type": "payment.requested", "payload": {"risk_score": 0.9}},
        ).json()["id"]

    def test_approval_records_named_reviewer(self) -> None:
        workflow_id = self._pending_workflow_id("api-approve")
        response = client.post(
            f"/workflows/{workflow_id}/decision",
            json={"decision": "approve", "reviewer": "Lance"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["audit"][-1]["action"], "workflow_approved")
        self.assertEqual(body["audit"][-1]["detail"]["reviewer"], "Lance")

    def test_blank_reviewer_is_rejected(self) -> None:
        workflow_id = self._pending_workflow_id("api-blank-reviewer")
        response = client.post(
            f"/workflows/{workflow_id}/decision",
            json={"decision": "approve", "reviewer": ""},
        )
        self.assertEqual(response.status_code, 422)

    def test_unsupported_decision_is_rejected(self) -> None:
        workflow_id = self._pending_workflow_id("api-bad-decision")
        response = client.post(
            f"/workflows/{workflow_id}/decision",
            json={"decision": "maybe", "reviewer": "Lance"},
        )
        self.assertEqual(response.status_code, 422)

    def test_deciding_a_completed_workflow_returns_409(self) -> None:
        completed = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "api-completed"},
            json={"event_type": "invoice.paid", "payload": {"amount": 5}},
        ).json()
        response = client.post(
            f"/workflows/{completed['id']}/decision",
            json={"decision": "reject", "reviewer": "Lance"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("pending_approval", response.json()["detail"])

    def test_decision_on_unknown_workflow_returns_404(self) -> None:
        response = client.post(
            "/workflows/does-not-exist/decision",
            json={"decision": "approve", "reviewer": "Lance"},
        )
        self.assertEqual(response.status_code, 404)


@unittest.skipIf(client is None, "fastapi/httpx2 not installed")
class RetryContractTests(unittest.TestCase):
    def _approved_workflow_id(self, key: str) -> str:
        workflow_id = client.post(
            "/webhooks",
            headers={"Idempotency-Key": key},
            json={"event_type": "email.received", "payload": {"needs_interpretation": True}},
        ).json()["id"]
        return client.post(
            f"/workflows/{workflow_id}/decision",
            json={"decision": "approve", "reviewer": "Lance"},
        ).json()["id"]

    def test_failures_retry_then_dead_letter_at_the_bounded_limit(self) -> None:
        workflow_id = self._approved_workflow_id("api-retry-limit")

        for attempt in range(1, 4):
            response = client.post(
                f"/workflows/{workflow_id}/failure",
                json={"error": f"provider failure {attempt}"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["attempt_count"], attempt)

        self.assertEqual(response.json()["status"], "dead_letter")
        self.assertEqual(response.json()["audit"][-1]["action"], "workflow_dead_lettered")

    def test_failure_before_approval_returns_409(self) -> None:
        workflow_id = client.post(
            "/webhooks",
            headers={"Idempotency-Key": "api-retry-before-approval"},
            json={"event_type": "payment.requested", "payload": {"amount": 2500}},
        ).json()["id"]
        response = client.post(
            f"/workflows/{workflow_id}/failure", json={"error": "must not run"}
        )
        self.assertEqual(response.status_code, 409)

    def test_blank_failure_reason_is_rejected(self) -> None:
        workflow_id = self._approved_workflow_id("api-retry-blank-error")
        response = client.post(
            f"/workflows/{workflow_id}/failure", json={"error": ""}
        )
        self.assertEqual(response.status_code, 422)

    def test_whitespace_failure_reason_is_rejected(self) -> None:
        workflow_id = self._approved_workflow_id("api-retry-space-error")
        response = client.post(
            f"/workflows/{workflow_id}/failure", json={"error": "   "}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "error is required")

    def test_failure_on_unknown_workflow_returns_404(self) -> None:
        response = client.post(
            "/workflows/does-not-exist/failure", json={"error": "provider timeout"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "workflow not found")


if __name__ == "__main__":
    unittest.main()
