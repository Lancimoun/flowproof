"""The provider-free core, used as a library. Runnable, and CI runs it.

The README advertises a "provider-free core" and, until this file existed,
documented only the HTTP API. That is the right level for a service — `POST
/webhooks` is the contract and `receive_webhook` is merely its handler — but it
left the claim that the core stands alone with nothing a reader could try.

Everything below uses an in-memory SQLite database: no install, no credentials, no
network, no provider. That is the claim, executed rather than asserted.

The output is deliberately free of workflow ids. They are UUIDs, so printing one
would make this example's output different on every run — and the README quotes
this output verbatim, with a test that re-runs the file and compares. A demo whose
output cannot be pinned cannot be checked, and an unchecked example is the thing
that rots first.

Run it:  python -m examples.ledger_demo
"""

from flowproof.core import InvalidTransition, WorkflowStore


def main() -> None:
    store = WorkflowStore(database=":memory:", max_attempts=3)
    try:
        # 1. Routing is deterministic and reads the payload, not the event name.
        #    A small safe amount completes through rules; nothing is queued.
        safe = store.ingest("evt-safe", "refund.requested", {"amount": 40})
        print(f"safe event    : status={safe['status']}  route={safe['route']}")

        # 2. Idempotency is keyed on the Idempotency-Key, not the payload.
        #    A replay creates nothing and says so.
        replay = store.ingest("evt-safe", "refund.requested", {"amount": 40})
        print(f"replayed      : duplicate={replay['duplicate']}  same_id={replay['id'] == safe['id']}")

        # 3. Risk routes to a human and WAITS. No model is contacted.
        risky = store.ingest("evt-risk", "payout.requested", {"amount": 5000})
        print(f"risky event   : status={risky['status']}  route={risky['route']}")

        # 4. A decision needs a named reviewer, and only from a valid state.
        decided = store.decide(risky["id"], "approve", "lance")
        print(f"decided       : status={decided['status']}")
        try:
            store.decide(risky["id"], "approve", "lance")
        except InvalidTransition as exc:
            print(f"decided twice : refused -> {type(exc).__name__}")

        # 5. Ambiguous input also waits for a human — routed to `ai_assist`
        #    WITHOUT calling a model. Only once approved can it run, and fail.
        job = store.ingest("evt-job", "sync.requested", {"needs_interpretation": True})
        print(f"ambiguous     : status={job['status']}  route={job['route']}")
        store.decide(job["id"], "approve", "lance")

        # 6. Failures are durable and bounded. The third is terminal.
        for attempt in range(1, 4):
            state = store.record_failure(job["id"], f"attempt {attempt} failed")
            print(f"failure {attempt}     : status={state['status']}")

        # 7. The audit trail is append-only: every step above is still there.
        trail = store.get(job["id"])["audit"]
        print(f"audit trail   : {len(trail)} entries, oldest={trail[0]['action']}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
