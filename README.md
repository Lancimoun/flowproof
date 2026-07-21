<h1 align="center">FlowProof</h1>

<p align="center"><strong>A reliability workbench for AI-assisted automations.</strong><br/>
Makes the operational guarantees around an automation <em>visible</em>: duplicate protection, deterministic routing, human approval, bounded retries, dead letters, and an append-only audit history.</p>

<p align="center">
  <a href="https://github.com/Lancimoun/flowproof/actions/workflows/ci.yml"><img src="https://github.com/Lancimoun/flowproof/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/core-provider--free%20·%20stdlib-5ed7bd?style=flat-square" alt="Provider-free core">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License: MIT">
</p>

<p align="center">
  <a href="https://lancimoun.github.io/flowproof/"><strong>▶ Live demo</strong></a> ·
  <a href="#what-works-now">What works now</a> ·
  <a href="#api">API</a> ·
  <a href="#run-locally">Run locally</a> ·
  <a href="#verify">Verify</a>
</p>

---

## What it is

FlowProof evaluates the **workflow around a model**, not the model itself — delivery, routing, approvals, retries, and traceability. Agent Reliability Arena scores what a model *says*; FlowProof proves what the system *does* with it.

This is a local `v0.1` vertical slice. It does not call an AI provider yet and is not deployed as a service. Ambiguous work is routed to an `ai_assist` queue **behind human approval**, so a future model adapter can be added without weakening the safety boundary.

## What works now

- **Idempotent delivery** — `POST /webhooks` with an `Idempotency-Key` creates at most one workflow. First delivery returns `201`; a replay returns `200` with the original workflow and `duplicate: true`, because the retry created nothing.
- **Deterministic routing** — safe events complete through rules; high-risk events route to `human_review` and wait; ambiguous events route to `ai_assist` **without** calling a model or firing a side effect.
- **Named-reviewer approval** — decisions require a named reviewer; deciding a workflow that is not `pending_approval` returns `409`.
- **Bounded retries → dead letter** — a failed attempt is durable and capped at **three**: failures one and two become `retry_pending`; failure three becomes `dead_letter` and can never run again.
- **Append-only audit** — every creation, duplicate, decision, failed attempt, and dead letter is recorded in SQLite and cannot be edited away.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `POST` | `/webhooks` | Idempotent workflow creation (`Idempotency-Key`) |
| `GET` | `/workflows/{id}` | Fetch a workflow and its full audit trail |
| `POST` | `/workflows/{id}/decision` | Named-reviewer approve / reject |
| `POST` | `/workflows/{id}/failure` | Record a failed attempt (bounded → `dead_letter`) |

## Live demo

**▶ [lancimoun.github.io/flowproof/](https://lancimoun.github.io/flowproof/)** — a self-contained walkthrough of safe routing, human approval, idempotent replay, bounded retries, dead letters, and the audit ledger. Served free from GitHub Pages out of `/docs`, with no backend and no external assets. Open `docs/index.html` locally for the same thing offline.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn flowproof.api:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API. Example:

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

**35 tests:** 9 stdlib tests pin the core ledger, 19 contract tests pin the HTTP surface (replay, retry, `404`, `409`, `422`), and 7 static-demo tests keep the public illustration honest, self-contained, and responsive.

The reliability core is **provider-free and stdlib-only by design** — so that command needs no install: the 9 core tests run and the 19 API tests report as skipped. Run it from the virtualenv to exercise the HTTP surface too. The guarantees stay testable offline, and the FastAPI and future AI adapters sit thinly around them.

## Next slices

- Pluggable AI adapter with recorded prompts/responses and deterministic fallback.
- Connect the static demo to the real approval queue, only after a deployment target is explicitly approved.
- Container packaging before any live service release.

---

<p align="center"><sub>MIT · Built by <a href="https://github.com/Lancimoun">Architect L.</a> with Claude Code</sub></p>
