# SECURITY POLICY — Razorpay RiskIQ (Sentinel)

## Strictly Defense-Only Declaration

Razorpay RiskIQ (Sentinel) is built exclusively as a **defensive security & risk intelligence platform** for detecting abuse rings, velocity anomalies, and fraudulent payment patterns.

### Express Scope & Safety Constraints

1. **No Offense Capabilities**: This repository contains zero code or capabilities intended for generating evasion attacks, probing active fraud defenses, exploiting payment gateways, or automating unauthorized transactions.
2. **Synthetic Data Only**: All datasets, transaction IDs, customer records, device identifiers, card fingerprints, and IP hashes used or generated in this project are 100% synthetic and randomly created by the internal generator.
3. **No PII Transmission or Retention**: Real Personally Identifiable Information (PII) is neither accepted nor processed. All entity values (IPs, credit card numbers) are irreversibly fingerprinted/hashed before graph insertion or LLM reasoning prompts.
4. **Deterministic Decision Enforcement**: The artificial intelligence components (LLMs) function strictly in an explainability/narrative capacity. Actual decision gating (`ALLOW`, `STEP-UP AUTH`, `REVIEW`, `BLOCK`) is handled by deterministic, auditable, and unit-tested rule engines.
