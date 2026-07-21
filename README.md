# FlowProof

[![CI](https://github.com/Lancimoun/flowproof/actions/workflows/ci.yml/badge.svg)](https://github.com/Lancimoun/flowproof/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**A reliability workbench for AI-assisted automations.** FlowProof makes the operational guarantees around an automation visible: duplicate protection, deterministic routing, human approval, bounded retries, dead letters, and an append-only audit history.

This is a local `v0.1` vertical slice. It does not call an AI provider yet and it is not deployed. Ambiguous work is routed to an `ai_assist` queue behind human approval, so a future model adapter can be added without weakening the safety boundary.

## What works now

- `POST /webhooks` accepts an `Idempotency-Key` and creates at most one workflow. A first delivery returns `201 Created`; a replay returns `200 OK` carrying the original workflow and `duplicate: true`, because a retry created nothing.
- Safe events complete through deterministic rules.
- High-risk events route to `human_review` and wait for a decision.
- Ambiguous events route to `ai_assist` but do not call a model or trigger a side effect.
- `approve` and `reject` decisions require a named reviewer; deciding a workflow that is not `pending_approval` returns `409`.
- Approved work can record an execution failure through `POST /workflows/{id}/failure`. Attempts are durable and bounded at three; failures one and two become `retry_pending`, while failure three becomes `dead_letter` and cannot run again.
- Every creation, duplicate delivery, decision, failed attempt, and dead letter is recorded in SQLite.
- 35 tests: 9 stdlib tests pin the core ledger, 19 contract tests pin the HTTP surface including replay, retry, `404`, `409`, and `422` responses, and 7 static-demo tests keep the public illustration honest, self-contained, and responsive.

## Static demo

Open `docs/index.html` directly in a browser. It is a self-contained, canned walkthrough of safe routing, human approval, idempotent replay, bounded retries, dead letters, and the append-only audit ledger. It does not call the API, a model, or any external asset.

**▶ Live demo:** [lancimoun.github.io/flowproof/](https://lancimoun.github.io/flowproof/) — served free from GitHub Pages out of the `/docs` folder, no backend and no external assets.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn flowproof.api:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API.

Example:

```bash
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: payment-42" \
  -d '{"event_type":"payment.requested","payload":{"amount":2500}}'
```

## Verify

```powershell
python -m unittest discover tests -v
```

The core ledger is stdlib-only, so that command needs no install: the 9 core tests run and the 19 API contract tests report as skipped. Run the same command from the virtualenv to exercise the HTTP surface as well:

```powershell
.\.venv\Scripts\python -m unittest discover tests -v
```

Keeping the reliability core provider-free and dependency-free is deliberate — the guarantees stay testable offline, and the FastAPI and future AI adapters sit thinly around them.

## Next slices

- Pluggable AI adapter with recorded prompts/responses and deterministic fallback.
- Connect the static demo to the real approval queue only after a deployment target is explicitly approved.
- Container packaging before a live service release.

## Portfolio distinction

Agent Reliability Arena evaluates model behavior. FlowProof evaluates the workflow around a model: delivery, routing, approvals, retries, and traceability.

MIT licensed. Built by [Architect L.](https://github.com/Lancimoun) with Claude Code.
