"""Deterministic workflow routing, idempotency, approvals, and audit history."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class InvalidTransition(ValueError):
    """Raised when a workflow decision is not valid for its current state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowStore:
    """SQLite-backed workflow ledger with deterministic routing rules."""

    def __init__(
        self, database: str | Path = "flowproof.db", max_attempts: int = 3
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._max_attempts = max_attempts
        self._connection = sqlite3.connect(str(database), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    route TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
                );
                """
            )
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(workflows)")
            }
            if "attempt_count" not in columns:
                self._connection.execute(
                    "ALTER TABLE workflows ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"
                )
            if "max_attempts" not in columns:
                self._connection.execute(
                    "ALTER TABLE workflows ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3"
                )

    @staticmethod
    def _route(event_type: str, payload: dict[str, Any]) -> tuple[str, str, str]:
        risk_score = float(payload.get("risk_score", 0) or 0)
        amount = float(payload.get("amount", 0) or 0)
        if payload.get("requires_approval") or risk_score >= 0.7 or amount >= 1000:
            return "human_review", "pending_approval", "risk threshold"
        if payload.get("needs_interpretation"):
            return "ai_assist", "pending_approval", "ambiguous input"
        return "rules", "completed", "safe deterministic path"

    def ingest(
        self, idempotency_key: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        key = idempotency_key.strip()
        event = event_type.strip()
        if not key:
            raise ValueError("idempotency_key is required")
        if not event:
            raise ValueError("event_type is required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")

        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT id FROM workflows WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing:
                self._append_audit(existing["id"], "duplicate_received", {"key": key})
                result = self.get(existing["id"])
                result["duplicate"] = True
                return result

            route, status, reason = self._route(event, payload)
            workflow_id = str(uuid.uuid4())
            timestamp = _now()
            self._connection.execute(
                """
                INSERT INTO workflows
                    (id, idempotency_key, event_type, payload_json, route, status,
                     attempt_count, max_attempts, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    key,
                    event,
                    json.dumps(payload, sort_keys=True),
                    route,
                    status,
                    0,
                    self._max_attempts,
                    timestamp,
                    timestamp,
                ),
            )
            self._append_audit(
                workflow_id,
                "workflow_created",
                {"route": route, "status": status, "reason": reason},
            )
            result = self.get(workflow_id)
            result["duplicate"] = False
            return result

    def decide(self, workflow_id: str, decision: str, reviewer: str) -> dict[str, Any]:
        normalized = decision.strip().lower()
        if normalized not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        if not reviewer.strip():
            raise ValueError("reviewer is required")

        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT status FROM workflows WHERE id = ?", (workflow_id,)
            ).fetchone()
            if row is None:
                raise KeyError(workflow_id)
            if row["status"] != "pending_approval":
                raise InvalidTransition(
                    f"workflow is {row['status']}; only pending_approval can be decided"
                )
            status = "approved" if normalized == "approve" else "rejected"
            self._connection.execute(
                "UPDATE workflows SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), workflow_id),
            )
            self._append_audit(
                workflow_id,
                f"workflow_{status}",
                {"reviewer": reviewer.strip()},
            )
            return self.get(workflow_id)

    def record_failure(self, workflow_id: str, error: str) -> dict[str, Any]:
        """Record an execution failure and stop retrying at the stored limit."""
        reason = error.strip()
        if not reason:
            raise ValueError("error is required")

        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT status, attempt_count, max_attempts
                FROM workflows WHERE id = ?
                """,
                (workflow_id,),
            ).fetchone()
            if row is None:
                raise KeyError(workflow_id)
            if row["status"] not in {"approved", "retry_pending"}:
                raise InvalidTransition(
                    f"workflow is {row['status']}; only approved or retry_pending can fail"
                )

            attempt_count = row["attempt_count"] + 1
            status = (
                "dead_letter"
                if attempt_count >= row["max_attempts"]
                else "retry_pending"
            )
            self._connection.execute(
                """
                UPDATE workflows
                SET status = ?, attempt_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, attempt_count, _now(), workflow_id),
            )
            self._append_audit(
                workflow_id,
                "attempt_failed",
                {
                    "attempt": attempt_count,
                    "max_attempts": row["max_attempts"],
                    "error": reason,
                    "next_status": status,
                },
            )
            if status == "dead_letter":
                self._append_audit(
                    workflow_id,
                    "workflow_dead_lettered",
                    {"attempts": attempt_count, "last_error": reason},
                )
            return self.get(workflow_id)

    def get(self, workflow_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        if row is None:
            raise KeyError(workflow_id)
        audits = self._connection.execute(
            """
            SELECT action, detail_json, created_at
            FROM audit_events WHERE workflow_id = ? ORDER BY id
            """,
            (workflow_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "idempotency_key": row["idempotency_key"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "route": row["route"],
            "status": row["status"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "audit": [
                {
                    "action": audit["action"],
                    "detail": json.loads(audit["detail_json"]),
                    "created_at": audit["created_at"],
                }
                for audit in audits
            ],
        }

    def _append_audit(
        self, workflow_id: str, action: str, detail: dict[str, Any]
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO audit_events (workflow_id, action, detail_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (workflow_id, action, json.dumps(detail, sort_keys=True), _now()),
        )
