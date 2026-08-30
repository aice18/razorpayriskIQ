# PRD — Sentinel: Abuse-Ring & Fraud-Spike Detection Agent

**Track:** Razorpay AI Buildathon — Track 02, AI Risk Manager
**Author:** [Your name]
**Status:** Draft v1
**Timeline:** 2–3 weeks (buildathon submission)

## 1. Problem

Fraud on payment platforms increasingly comes from **coordinated abuse rings** — clusters of accounts sharing a device, IP, or card — rather than isolated bad actors. Point-in-time transaction scoring (a single probability per transaction) misses this: it never looks at *who else* touches the same device, card, or IP. Analysts are left correlating this manually across dashboards, which doesn't scale and is slow.

Razorpay's own Shield Risk Engine already does ML-based fraud/chargeback scoring on individual payment behavior. Sentinel is not a replacement — it's the layer above: an agentic system that takes anomaly signals and **investigates relationships between entities** to catch rings that per-transaction scoring structurally cannot see, then produces a bounded, auditable decision plus a human-readable case file.

## 2. Goals

1. Detect abuse rings — clusters of accounts/transactions linked via shared device, IP, or card — with measured precision/recall on a held-out synthetic test set.
2. Fold in transaction-velocity anomalies (rapid repeated attempts, sudden spend spikes) as a contributing signal, not a separate product.
3. Produce a bounded, explainable decision per case (ALLOW / STEP-UP AUTH / REVIEW / BLOCK) with a full audit trail — never a silent action.
4. Demonstrate the system handling one failure case gracefully (escalate to human review rather than being confidently wrong).

## 3. Non-Goals (explicitly out of scope for this build)

- Not a general-purpose fraud-probability model for every transaction (Shield already exists for that).
- Not a chargeback-evidence responder or AML/KYC compliance engine — those are separate tracks/problems; mixing them in dilutes the measured deliverable.
- Not offense-capable in any way (no code that could be used to *generate* fraud patterns undetected, probe defenses, or evade detection). Strictly defense-only per the track's rule.
- Not using a live/real merchant dataset — synthetic, clearly labeled data only.
- No LLM in the actual allow/block decision path (see TRD) — kept deterministic and auditable.

## 4. Users / Stakeholders

- **Primary:** Risk analyst at a payments company, reviewing flagged cases.
- **Secondary:** Merchant, indirectly protected from fraud loss and unnecessary false declines.
- **Judge/evaluator lens:** someone scoring this needs to see honest metrics, a real held-out test, and a defensible architecture — treat the judge as a third user of this PRD.

## 5. User Stories

- As a risk analyst, I see a live feed of flagged transactions ranked by risk score, so I can triage.
- As a risk analyst, when I open a case, I see the full evidence — which entities it shares with other accounts, velocity anomalies, and the ring it may belong to — summarized in plain language, so I don't have to piece it together myself.
- As a risk analyst, I can see *why* the system reached ALLOW/STEP-UP/REVIEW/BLOCK, with the exact features and thresholds that drove it, so I can trust or override it.
- As a judge, I can see precision/recall/F1/PR-AUC/false-positive rate on a held-out set I know the system never trained on, plus what a false positive costs in practice.

## 6. Success Metrics

| Metric | Target (stretch) |
|---|---|
| Precision @ chosen threshold | Report honestly — no target gaming |
| Recall @ chosen threshold | Report honestly |
| PR-AUC | > 0.7 on synthetic held-out set |
| False-positive rate | Explicitly reported alongside cost estimate |
| p95 decision latency | < 2s per case (excluding batch eval) |
| Audit trail completeness | 100% of decisions have logged evidence |

## 7. Constraints

- Strictly defense-only (per track rules) — this must be stated explicitly in the README and enforced in the codebase (no adversarial/generation tooling shipped).
- All data synthetic, clearly labeled as such everywhere (dashboard, README, pitch).
- Solo build, 2–3 weeks, reusing existing KavachX pipeline (Kafka → Flink → Redis → ML → Dashboard) rather than building streaming infra from scratch.

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Synthetic data is unrealistic, metrics look artificially good | Model ring/velocity patterns off public fraud-ring research; deliberately inject noisy/ambiguous cases, not just clean-cut fraud |
| Scope creep back into chargebacks/AML | Keep this PRD as the single source of truth; anything not in Goals is cut |
| LLM calls introduce non-determinism into judged metrics | LLM used only for narrative explanation, never for the score or decision (see TRD) |
| Running out of time before polish | Time-box Week 3 hard; a working core + honest metrics beats a polished shell |
