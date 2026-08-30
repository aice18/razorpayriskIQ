# API Spec — Sentinel (FastAPI)

Minimal REST surface — just enough to drive the dashboard and the eval harness. Not designed as a public/production API.

## `POST /ingest`
Internal use by the generator (or a manual test client). Accepts one transaction event, pushes to Kafka.

## `GET /feed?status=flagged&limit=50`
Returns recent transactions for the Live Feed screen, with score and status.

**Response (200):**
```json
{
  "items": [
    {"transaction_id": "txn_00123456", "score": 0.91, "status": "flagged", "timestamp": "..."}
  ]
}
```

## `GET /case/{transaction_id}`
Returns the full case: Investigation Agent evidence, Reasoning Agent narrative, Decision Agent output, and any override.

## `GET /graph/{transaction_id}`
Returns the local subgraph (nodes + edges) for the Risk Graph Explorer, centered on the transaction's entities.

## `POST /case/{transaction_id}/override`
Analyst overrides a decision. Requires a `reason` field. Writes to the audit log; never mutates the original Decision Agent output (append-only).

**Request:**
```json
{"new_action": "ALLOW", "reason": "Confirmed legitimate — customer travel notified in advance"}
```

## `GET /metrics/eval`
Runs (or returns cached results of) the offline eval harness against the held-out set. Returns precision, recall, F1, PR-AUC, false-positive rate, false-positive cost estimate, and latency percentiles.

## `GET /metrics/failure-case`
Returns one specific held-out example chosen to demonstrate graceful failure handling (see EVAL_PLAN.md) — for the dashboard's Metrics screen and for the pitch video.
