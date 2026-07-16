# FlowProof

**A reliability workbench for AI-assisted automations.** FlowProof makes the operational guarantees around an automation visible: duplicate protection, deterministic routing, human approval, and an append-only audit history.

This is a local `v0.1` vertical slice. It does not call an AI provider yet and it is not deployed. Ambiguous work is routed to an `ai_assist` queue behind human approval, so a future model adapter can be added without weakening the safety boundary.

## What works now

- `POST /webhooks` accepts an `Idempotency-Key` and creates at most one workflow.
- Safe events complete through deterministic rules.
- High-risk events route to `human_review` and wait for a decision.
- Ambiguous events route to `ai_assist` but do not call a model or trigger a side effect.
- `approve` and `reject` decisions require a named reviewer.
- Every creation, duplicate delivery, and decision is recorded in SQLite.
- Six stdlib tests cover routing, idempotency, approval, and invalid transitions.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
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

## Next slices

- Retry policy with bounded attempts and dead-letter state.
- Pluggable AI adapter with recorded prompts/responses and deterministic fallback.
- Small dashboard for the approval queue and audit timeline.
- CI and container packaging before any public release.

## Portfolio distinction

Agent Reliability Arena evaluates model behavior. FlowProof evaluates the workflow around a model: delivery, routing, approvals, retries, and traceability.

MIT licensed. Built by Lance Jilliard Galicia.
