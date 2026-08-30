# Agent Spec — Sentinel

Three agents, each with a strict input/output contract. Only one of them calls an LLM.

## 1. Investigation Agent (no LLM)

**Trigger:** risk score ≥ flag threshold.
**Input:** transaction_id, current feature vector, graph neighborhood (from Entity Graph query).
**Output (JSON):**
```json
{
  "transaction_id": "txn_00123456",
  "score": 0.91,
  "anomalies": [
    {"type": "amount_deviation", "detail": "17x customer's typical amount"},
    {"type": "new_device", "detail": "First transaction from this device"},
    {"type": "shared_entity", "detail": "Device linked to 14 other customer IDs in last 24h"}
  ],
  "ring_membership": {"ring_detected": true, "component_size": 14, "component_id": "comp_882"}
}
```
Pure Python — deterministic, unit-testable, no external calls.

## 2. Reasoning / Explanation Agent (Claude API)

**Purpose:** turn the Investigation Agent's structured output into a plain-language case narrative for the analyst. This agent explains; it does not decide.

**Input:** the Investigation Agent's JSON output.
**System prompt (guidance, not verbatim):** instruct the model to summarize only the evidence provided, avoid speculating beyond it, and produce a short analyst-readable paragraph plus a one-line headline risk category. No access to raw PII — only synthetic IDs and feature values ever reach this call.
**Output (JSON):**
```json
{
  "transaction_id": "txn_00123456",
  "headline": "Likely member of a 14-account device-sharing ring",
  "narrative": "This transaction is 17x the customer's typical spend, from a device that has processed transactions for 13 other distinct customer IDs in the past 24 hours..."
}
```

**Guardrail:** if the Claude API call fails or times out, the pipeline must fall back to a templated narrative built from the raw evidence (not block the decision on LLM availability).

## 3. Decision Agent (no LLM, deterministic)

**Input:** score + evidence (not the narrative — the decision must not depend on how something was phrased).
**Logic:** fixed, documented thresholds, e.g.:

| Score band | Ring detected? | Action |
|---|---|---|
| < 0.4 | — | ALLOW |
| 0.4 – 0.7 | No | STEP-UP AUTH |
| 0.4 – 0.7 | Yes | REVIEW |
| > 0.7 | — | BLOCK |

**Output:** action + the exact rule that fired, written to the Audit Log alongside the Investigation and Reasoning Agent outputs.

## Design principles (state these explicitly in the README)

1. **The LLM never decides.** It only narrates evidence that already exists. This keeps the graded metrics (precision/recall/etc.) meaningful and keeps the decision path auditable and reproducible.
2. **Every agent call is logged**, including Claude API latency and any fallback events, so the audit trail is complete even on failure paths.
3. **Bounded and gated:** the Decision Agent can only choose from a fixed, small action set — never an arbitrary or generated action.
