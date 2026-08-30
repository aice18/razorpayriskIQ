"""
High-Concurrency Hot-Path Load & Latency Benchmark Harness for Razorpay RiskIQ Sentinel.
Benchmarks synchronous hot-path execution latency (p50, p95, p99 < 15ms)
and concurrent throughput under high load.
"""

import time
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any
import numpy as np

from generator.transaction_generator import TransactionGenerator
from streaming.feature_store import FeatureStore
from graph.entity_graph import EntityGraph
from scoring.risk_scorer import RiskScorer
from agents.decision_agent import DecisionAgent


def run_benchmark(total_requests: int = 2000, concurrency: int = 8) -> Dict[str, Any]:
    """Runs high-throughput load benchmark on the hot-path decision pipeline."""
    print(f"Initializing Benchmark Harness (Total Requests={total_requests}, Concurrency={concurrency})...")
    
    generator = TransactionGenerator(seed=999)
    events = generator.generate_batch(count=total_requests, holdout_ratio=0.0)
    
    feature_store = FeatureStore()
    graph = EntityGraph()
    scorer = RiskScorer()
    decider = DecisionAgent()

    latencies_ms = []
    decisions = {"ALLOW": 0, "STEP-UP AUTH": 0, "REVIEW": 0, "BLOCK": 0}

    # Warmup
    for evt in events[:50]:
        feat = feature_store.compute_and_update(evt)
        g_feat = graph.add_transaction(evt)
        comb = {**feat, **g_feat, "amount": float(evt["amount"])}
        sc = scorer.predict_score(comb, merchant_category=evt.get("merchant_category"))
        dec = decider.decide(sc, {"transaction_id": evt["transaction_id"], "ring_membership": {"ring_detected": g_feat["is_ring_suspect"], "component_size": g_feat["component_size"]}})

    # Benchmark hot path single-event execution latency
    print("Measuring isolated per-transaction hot-path latency...")
    for evt in events[50:]:
        t0 = time.perf_counter()
        
        # 1. Feature Store (< 1.5ms)
        feat = feature_store.compute_and_update(evt)
        
        # 2. Graph Metrics (< 1.0ms)
        g_feat = graph.add_transaction(evt)
        
        # 3. Combine Vector
        comb = {**feat, **g_feat, "amount": float(evt["amount"])}
        
        # 4. Calibrated ML Scoring (< 0.8ms)
        score = scorer.predict_score(comb, merchant_category=evt.get("merchant_category"))
        
        # 5. Policy Decision (< 0.2ms)
        fast_evid = {
            "transaction_id": evt["transaction_id"],
            "ring_membership": {"ring_detected": g_feat["is_ring_suspect"], "component_size": g_feat["component_size"]}
        }
        dec = decider.decide(score, fast_evid)
        
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)
        action = dec.get("action", "ALLOW")
        decisions[action] = decisions.get(action, 0) + 1

    # Measure total concurrent throughput
    start_concurrent = time.time()
    def _worker_exec(slice_events):
        for e in slice_events:
            f = feature_store.compute_and_update(e)
            g = graph.add_transaction(e)
            c = {**f, **g, "amount": float(e["amount"])}
            s = scorer.predict_score(c, merchant_category=e.get("merchant_category"))
            d = decider.decide(s, {"transaction_id": e["transaction_id"], "ring_membership": {"ring_detected": g["is_ring_suspect"], "component_size": g["component_size"]}})

    chunk_size = len(events) // concurrency
    chunks = [events[i*chunk_size:(i+1)*chunk_size] for i in range(concurrency)]
    
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(_worker_exec, chunks))
    
    concurrent_time = time.time() - start_concurrent
    rps = round(total_requests / concurrent_time, 1)

    lat_arr = np.array(latencies_ms)
    p50 = round(float(np.percentile(lat_arr, 50)), 2)
    p90 = round(float(np.percentile(lat_arr, 90)), 2)
    p95 = round(float(np.percentile(lat_arr, 95)), 2)
    p99 = round(float(np.percentile(lat_arr, 99)), 2)
    p99_9 = round(float(np.percentile(lat_arr, 99.9)), 2)
    max_lat = round(float(np.max(lat_arr)), 2)
    mean_lat = round(float(np.mean(lat_arr)), 2)

    sla_met = (p99 <= 15.0)

    summary = {
        "benchmark_config": {
            "total_requests_benchmarked": len(latencies_ms),
            "concurrency_threads": concurrency,
            "throughput_rps": rps
        },
        "hotpath_latency_sla_ms": {
            "target_sla_ms": 15.0,
            "mean": mean_lat,
            "p50": p50,
            "p90": p90,
            "p95": p95,
            "p99": p99,
            "p99_9": p99_9,
            "max": max_lat,
            "sla_compliant": sla_met
        },
        "decision_distribution": decisions
    }

    os.makedirs("eval/results", exist_ok=True)
    bench_file = "eval/results/benchmark_report.json"
    with open(bench_file, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=======================================================")
    print(f"HOT-PATH SLA & LOAD BENCHMARK (Throughput: {rps} RPS)")
    print(f"p50 Latency:  {p50:.2f} ms")
    print(f"p95 Latency:  {p95:.2f} ms")
    print(f"p99 Latency:  {p99:.2f} ms (Target SLA < 15.0ms) -> {'PASS' if sla_met else 'FAIL'}")
    print("=======================================================\n")
    return summary


if __name__ == "__main__":
    run_benchmark(total_requests=2000, concurrency=8)
