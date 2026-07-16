"""FastAPI adapter for the FlowProof workflow ledger."""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .core import InvalidTransition, WorkflowStore


class WebhookRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1, max_length=100)


class FailureRequest(BaseModel):
    error: str = Field(min_length=1, max_length=500)


store = WorkflowStore(os.getenv("FLOWPROOF_DATABASE", "flowproof.db"))
app = FastAPI(
    title="FlowProof",
    version="0.1.0",
    description="A reliability workbench for deterministic and AI-assisted automations.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/webhooks", status_code=201)
def receive_webhook(
    request: WebhookRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, Any]:
    try:
        result = store.ingest(idempotency_key, request.event_type, request.payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result["duplicate"]:
        # A replay created nothing, so 201 Created would misreport the outcome.
        response.status_code = 200
    return result


@app.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    try:
        return store.get(workflow_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="workflow not found") from error


@app.post("/workflows/{workflow_id}/decision")
def decide_workflow(workflow_id: str, request: DecisionRequest) -> dict[str, Any]:
    try:
        return store.decide(workflow_id, request.decision, request.reviewer)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="workflow not found") from error
    except InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/workflows/{workflow_id}/failure")
def record_workflow_failure(
    workflow_id: str, request: FailureRequest
) -> dict[str, Any]:
    try:
        return store.record_failure(workflow_id, request.error)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="workflow not found") from error
    except InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
