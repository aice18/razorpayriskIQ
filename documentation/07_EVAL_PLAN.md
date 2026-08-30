# Evaluation Plan — Sentinel

This document is arguably the single most important artifact for the submission — the track's stated bar is "honest metrics including false-positive cost," and "one cherry-picked match proves nothing."

## 1. Held-out set methodology

- Generate the full synthetic dataset with ground-truth labels (`label_is_fraud`, `label_ring_id`).
- Split by **time**, not randomly — e.g., first 70% of generated timeline is used for any threshold-tuning, last 30% is the held-out set, touched exactly once, at the end.
- Strip all label fields before data enters the actual scoring/agent pipeline; only reattach at evaluation time to compute metrics. This mirrors production reality and prevents label leakage.
- Held-out set should contain a realistic mix: majority normal, a meaningful minority of velocity fraud, a smaller minority of ring fraud, and a handful of deliberately ambiguous/borderline cases.

## 2. Metrics to report

| Metric | What it tells you |
|---|---|
| Precision | Of everything flagged, how much was actually fraud |
| Recall | Of all actual fraud, how much was caught |
| F1 | Balance of the two |
| PR-AUC | Threshold-independent view of the scoring model's quality |
| False-positive rate | Of all normal transactions, how many were wrongly flagged |
| False-positive cost estimate | (# false positives) × (assumed cost per wrongly-blocked/step-up transaction, e.g. lost sale + support friction) — even a rough estimate, clearly labeled as an assumption, is far better than omitting this |
| p95 decision latency | End-to-end time from transaction to final decision, for flagged cases |
| Throughput | Sustained events/sec the pipeline handled during the demo run |

Report these in a single table in the README and on the Metrics dashboard screen — don't bury them.

## 3. Ring-detection-specific evaluation

Separately from overall precision/recall, report:
- Of the synthetic rings actually injected, how many were detected as connected components above the ring-size threshold (ring-level recall).
- Any rings detected that weren't actually injected (false ring detections) — report honestly if this happens.

## 4. Demonstrating one graceful failure

Pick (don't cherry-pick a flattering one — pick a genuinely hard one) a held-out case where the system's initial score was ambiguous or wrong, and show:
- What the system decided (e.g., REVIEW rather than a confident BLOCK or ALLOW).
- Why the ambiguity happened (e.g., legitimate shared family device that superficially looks ring-like).
- That the system escalated rather than silently erring — this is what "explainable, bounded, gated" and the track's honesty bar are actually asking for.

## 5. What NOT to do

- Don't report only accuracy — it's close to meaningless when fraud is a minority class.
- Don't tune thresholds on the held-out set and then report metrics from that same set.
- Don't omit false-positive cost because it makes the numbers look less clean — the track explicitly asks for it.
