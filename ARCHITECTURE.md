# System Architecture — Razorpay RiskIQ (Sentinel)

**Razorpay RiskIQ (Sentinel)** is an enterprise-grade autonomous payment risk & abuse-ring AI agent platform engineered to detect coordinated fraud syndicates, prevent account takeovers, and reduce false declines without adding checkout friction.

---

## 1. Dual-Rail Distributed Architecture

RiskIQ operates on an asynchronous **Dual-Rail Architecture** that strictly decouples the high-throughput payment checkout hot path ($SLA < 15\text{ms}$) from deep agentic investigation:

```mermaid
flowchart TD
    TXN[Payment Event Stream: UPI / Card / NetBanking] --> API[FastAPI /api/ingest Gateway]
    
    subgraph SYNC_PATH ["Synchronous Hot-Path (Strict SLA < 15ms | p99 = 12.2ms)"]
        API --> REDIS_FEAT[(Redis Sliding Windows: 1m / 5m / 1h & Online Welford Stats)]
        API --> REDIS_GRAPH[(Redis Adjacency Sets: Bounded 1-Hop Degree & Hub Capping)]
        
        REDIS_FEAT & REDIS_GRAPH --> MODEL[Calibrated HistGradientBoosting Classifier]
        MODEL --> SHAP[Local Fast TreeSHAP Attribution Vector]
        MODEL --> POLICY[Multi-Tenant Deterministic Policy Matrix]
        POLICY --> FAST_RESP["Immediate Decision: ALLOW / STEP-UP (3DS) / REVIEW / BLOCK"]
    end
    
    FAST_RESP --> GATEWAY[Payment Gateway / Merchant Checkout]
    
    subgraph ASYNC_PATH ["Asynchronous Agentic Intelligence Layer (Distributed Worker Tier)"]
        POLICY -->|Flagged Cases: REVIEW / BLOCK / STEP-UP| BG_QUEUE[Async Case Pipeline]
        BG_QUEUE --> AGENT[Autonomous Dynamic ReAct Investigation Agent]
        
        AGENT -->|Hypothesis 1: Velocity / Spend Spike| T1[Tool: Temporal Velocity & Z-Score]
        AGENT -->|Hypothesis 2: Shared Topology| T2[Tool: Bounded 2-Hop NetworkX Subgraph]
        AGENT -->|Hypothesis 3: Credential Anomaly| T3[Tool: Device & Geo Travel Profiler]
        AGENT -->|Hypothesis 4: Category Risk| T4[Tool: Merchant Profile & Chargeback Benchmark]
        
        T1 & T2 & T3 & T4 --> SYNTH[Structured Evidence Synthesis & Attribution Grounding]
        SYNTH --> REASON[Reasoning Agent: Claude 3.5 Sonnet Dossier]
        REASON --> AUDIT[(PostgreSQL / SQLite Append-Only Audit Store)]
        AUDIT --> UI[Analyst Command Center & Vis.js Graph Explorer]
    end
```

---

## 2. Component Specifications

### 2.1 Online Streaming Feature Store (`streaming/`)
- **Primary Engine**: High-throughput Redis cluster utilizing atomic Sorted Sets (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`) for rolling temporal velocities (1m, 5m, 1h) with TTL expiration.
- **Statistical Moments**: Online continuous mean and variance tracking via Welford's one-pass algorithm.
- **Failover**: Thread-safe in-memory cache with zero-latency failover if Redis is temporarily unreachable.

### 2.2 Hybrid Entity Graph Engine (`graph/`)
- **Hot Path (Sub-2ms)**: Redis Adjacency Sets (`g:dev:{id}`, `g:ip:{id}`, `g:card:{id}`) for $O(1)$ degree centrality extraction and mega-hub dampening (capping degree expansion for public Wi-Fi / NAT gateways).
- **Deep Path**: Bounded NetworkX $k=2$ hop ego-graph traversal with community clustering and interactive Vis.js graph topology extraction.

### 2.3 Calibrated Machine Learning Pipeline (`scoring/`)
- **Model**: `HistGradientBoostingClassifier` trained on non-linear payment interactions (amount distributions, 1m/5m/1h velocities, device degrees, ring densities, geo deviations).
- **Multi-Tenant Calibration**: Category-specific risk tolerance curves (`GAMING_CRYPTO`, `LUXURY_JEWELRY`, `ECOMMERCE_RETAIL`, `FOOD_GROCERY`, `UTILITY_BILLPAY`).
- **Explainability**: Local TreeSHAP approximations extract feature attribution vectors per transaction for regulatory compliance (RBI / Visa / Mastercard audits).

### 2.4 Autonomous Dynamic ReAct Agent (`agents/`)
- **Investigation Agent**: Dynamically formulates investigation hypotheses and conditionally invokes tools (`VelocityAnomalyTool`, `EntityGraphTool`, `DeviceIntelligenceTool`, `MerchantProfileTool`) with early stopping.
- **Reasoning Agent**: Converts multi-tool evidence into audit-proof executive briefs via Claude 3.5 Sonnet (with robust deterministic template fallback). Strictly non-hallucinatory and guaranteed to never mutate risk scores or decisions.
- **Decision Agent**: Multi-tenant policy matrix mapping probability scores, SHAP vectors, and ring topology to bounded actions: `ALLOW`, `STEP-UP AUTH` (Dynamic 3DS / OTP), `REVIEW`, and `BLOCK`.

### 2.5 Offline Evaluation & Slice Analytics (`eval/`)
- Evaluates held-out payment streams across Indian payment channels (`UPI_VPA`, `UPI_INTENT`, `CARD_CREDIT`, `CARD_DEBIT`, `NETBANKING`) and merchant risk categories.
- Benchmarks Precision, Recall, F1, PR-AUC, ROC-AUC, False Positive Cost in INR, and p50/p95/p99 latency distributions.
