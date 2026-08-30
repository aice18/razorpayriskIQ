# ARCHITECTURE — Razorpay RiskIQ (Sentinel)

## 1. System Overview

Razorpay RiskIQ (Sentinel) is an autonomous, graph-agentic abuse-ring and fraud-spike intelligence platform built for Razorpay Risk Manager.

```mermaid
flowchart TD
    GEN[Synthetic Multi-Pattern Generator] --> KAFKA[Streaming Topic]
    KAFKA --> FLINK[Windowed Feature Store & Entity Graph Update]
    FLINK --> REDIS[(Redis Feature Store)]
    FLINK --> GRAPH[(NetworkX Entity Graph Store)]
    
    REDIS --> SCORE[Hybrid Scoring Engine\nRules + Graph Topology + Velocity ML]
    GRAPH --> SCORE
    
    SCORE -->|Score >= Flag Threshold (0.40)| INVEST[1. Investigation Agent\nDeterministic Evidence Package]
    SCORE -->|Score < 0.40| ALLOW[Fast-Path ALLOW\nLog & Bypass]
    
    INVEST --> REASON[2. Reasoning Agent\nClaude API Narrative + Fallback Template]
    REASON --> DECIDE[3. Decision Agent\nDeterministic Bounded Threshold Matrix]
    
    DECIDE --> AUDIT[(Immutable Audit Store)]
    DECIDE --> DASH[Analyst Command Center Dashboard]
    
    AUDIT --> DASH
    SCORE --> EVAL[Offline Evaluation Harness]
    EVAL --> METRICS[Held-Out Performance & FP Cost Report]
```

## 2. Key Component Specifications

### 2.1 Synthetic Stream Generator (`generator/`)
- Produces realistic real-time transaction events (Normal spend, Velocity fraud, Coordinated Abuse Rings, Ambiguous cases).
- Embeds temporal ground-truth labeling (`label_is_fraud`, `label_ring_id`, `is_holdout`) stripped before agent consumption to ensure honest held-out evaluation.

### 2.2 Feature Store & Entity Graph (`streaming/` & `graph/`)
- Maintains rolling window velocity counts (`velocity_1m`, `velocity_5m`, `velocity_1h`), device velocity, and spend z-scores.
- Dynamic NetworkX Entity Graph links `Customer`, `Device`, `IP`, `Card`, and `Merchant` nodes.
- Computes connected component sizes and degree centrality to detect multi-account abuse rings.

### 2.3 Hybrid Scoring Engine (`scoring/`)
- Integrates graph topological metrics (ring sizes, shared entity degrees) with statistical velocity and amount anomalies.
- Outputs continuous risk score bounded in $[0.02, 0.98]$.

### 2.4 Autonomous Multi-Agent Triad (`agents/`)
1. **Investigation Agent (Deterministic)**: Extracts entity degrees, anomaly flags, and connected customer lists into structured JSON.
2. **Reasoning Agent (LLM Case Narrative)**: Calls Claude API to generate concise analyst briefs. Integrates deterministic template fallback when API is unreachable. Zero influence on risk scores or decisions.
3. **Decision Agent (Bounded Threshold Matrix)**: Maps risk scores & ring topology to bounded actions (`ALLOW`, `STEP-UP AUTH`, `REVIEW`, `BLOCK`) with immutable rule logging.

### 2.5 Analyst Command Center & Immutable Audit Log (`api/`, `audit/`, `dashboard/`)
- Real-time dark mode visual dashboard with Live Stream Feed, Vis.js Entity Graph Explorer, Case Inspector, Analyst Override form, and Metrics Report view.
- FastAPI backend serving REST endpoints.
