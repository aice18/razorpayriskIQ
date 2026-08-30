# Repo Structure & Submission Checklist — Sentinel

## Folder layout

```
sentinel/
├── README.md
├── ARCHITECTURE.md
├── SECURITY.md                 # explicit defense-only statement
├── docs/
│   ├── PRD.md
│   ├── TRD.md
│   ├── SCREEN_FLOW.md
│   ├── DATA_MODEL.md
│   ├── AGENT_SPEC.md
│   ├── API_SPEC.md
│   └── EVAL_PLAN.md
├── generator/                  # synthetic transaction + label generator
├── streaming/                  # Kafka/Flink glue (reused/adapted from KavachX)
├── graph/                      # entity graph build + ring/community detection
├── scoring/                    # feature combination + ML model
├── agents/
│   ├── investigation.py
│   ├── reasoning.py             # Claude API call + fallback template
│   └── decision.py
├── api/                        # FastAPI app
├── dashboard/                  # reused/adapted KavachX dashboard
├── eval/
│   ├── run_eval.py
│   └── results/                # generated metrics reports, committed for judges to see
└── tests/
```

## README.md outline

1. One-paragraph problem statement + why abuse-ring detection specifically.
2. Architecture diagram (from TRD).
3. **Metrics table** (from eval/results) — near the top, not buried at the bottom.
4. How to run it locally (docker-compose or equivalent, one command if possible).
5. Explicit "Defense-only" statement.
6. Link to the 5-minute pitch video.
7. "What I'd build next" — shows maturity and forward thinking without overclaiming what exists today.

## Submission checklist (mapped to buildathon requirements)

- [ ] Public repo, clean commit history (not one giant commit)
- [ ] Architecture clearly shown (diagram + written walkthrough)
- [ ] Working detector with measured precision/recall on a genuine held-out set
- [ ] False-positive cost reported
- [ ] Every decision explainable, bounded (fixed action set), and gated (thresholds, not free-form LLM choice)
- [ ] One failure case shown, handled gracefully
- [ ] Explicit statement: strictly defense-only, no offense-capable code shipped
- [ ] 5-minute pitch video: problem → live demo → architecture → metrics → what's next
- [ ] No real data, no real PII, anywhere

## Pitch video outline (5 minutes)

1. **0:00–0:45** — the problem: why per-transaction scoring misses coordinated rings, concretely (the ₹87,000 example is a good cold open).
2. **0:45–2:30** — live demo: a ring transaction flows through the system, graph explorer shows the connected component, case detail shows the narrative, decision + audit trail shown.
3. **2:30–3:30** — architecture walkthrough, emphasizing what's reused (KavachX pipeline) vs. new (graph + agent layer) — this signals engineering maturity, not just a weekend hack.
4. **3:30–4:30** — metrics, stated plainly, including the false-positive cost and the one failure case.
5. **4:30–5:00** — what's next / how this would harden for production.
