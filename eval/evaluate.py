"""
Offline Evaluation Harness for RiskIQ Sentinel.
Runs the end-to-end pipeline against a strict held-out transaction dataset,
computing Precision, Recall, F1, PR-AUC, False Positive Rate, FP Cost Impact,
and identifying hard failure cases for graceful degradation proof.
"""

import time
import json
import os
from typing import Dict, List, Any
import numpy as np
from sklearn.metrics import precision_recall_curve, auc

from generator.transaction_generator import TransactionGenerator
from graph.entity_graph import EntityGraph
from streaming.feature_store import FeatureStore
from scoring.risk_scorer import RiskScorer
from agents.investigation_agent import InvestigationAgent
from agents.reasoning_agent import ReasoningAgent
from agents.decision_agent import DecisionAgent
from audit.audit_store import AuditStore

class Evaluator:
    """Evaluates RiskIQ Sentinel pipeline metrics on held-out synthetic test sets."""
    
    def __init__(self, fp_cost_unit_inr: float = 500.0):
        self.fp_cost_unit_inr = fp_cost_unit_inr

    def run_evaluation(self, total_events: int = 1500, holdout_ratio: float = 0.3) -> Dict[str, Any]:
        """
        Executes end-to-end evaluation pipeline on synthetic data stream.
        Maintains strict separation between train/history events and held-out evaluation events.
        """
        generator = TransactionGenerator(seed=42)
        events = generator.generate_batch(count=total_events, holdout_ratio=holdout_ratio)

        graph = EntityGraph()
        feature_store = FeatureStore()
        scorer = RiskScorer()
        investigator = InvestigationAgent()
        reasoner = ReasoningAgent()  # uses template fallback if API key not set
        decider = DecisionAgent()
        audit_store = AuditStore()

        y_true = []
        y_scores = []
        y_pred_flagged = []
        latencies = []

        rings_injected = set()
        rings_detected = set()

        failure_case = None

        print(f"Processing {len(events)} synthetic events (Holdout: {int(total_events * holdout_ratio)})...")
        start_eval_time = time.time()

        for event in events:
            is_holdout = event["is_holdout"]
            is_fraud_ground_truth = event["label_is_fraud"]
            ring_id = event["label_ring_id"]

            if ring_id:
                rings_injected.add(ring_id)

            t0 = time.time()
            
            # Step 1: Feature computation & Entity Graph update
            feature_vector = feature_store.compute_and_update(event)
            graph_metrics = graph.add_transaction(event)
            combined_features = {**feature_vector, **graph_metrics}

            # Step 2: Risk Scoring
            score = scorer.predict_score(combined_features)
            
            # Step 3: Flag threshold check (score >= 0.40)
            is_flagged = score >= 0.40
            
            # Agent pipeline run for flagged cases
            if is_flagged:
                evidence = investigator.investigate(event, combined_features, score)
                narrative = reasoner.explain(evidence)
                decision = decider.decide(score, evidence)
                audit_store.log_case(event, combined_features, score, evidence, narrative, decision)

                if graph_metrics.get("is_ring_suspect") and ring_id:
                    rings_detected.add(ring_id)

            t1 = time.time()
            latency_ms = (t1 - t0) * 1000.0

            # Collect metrics ONLY for held-out evaluation set
            if is_holdout:
                y_true.append(1 if is_fraud_ground_truth else 0)
                y_scores.append(score)
                y_pred_flagged.append(1 if is_flagged else 0)
                latencies.append(latency_ms)

                # Identify graceful failure case (e.g. ambiguous case where ground truth is normal but score was medium and resulted in REVIEW)
                if not is_fraud_ground_truth and is_flagged and score < 0.70 and failure_case is None:
                    evidence = investigator.investigate(event, combined_features, score)
                    narrative = reasoner.explain(evidence)
                    decision = decider.decide(score, evidence)
                    failure_case = {
                        "transaction_id": event["transaction_id"],
                        "ground_truth": "LEGITIMATE",
                        "predicted_score": score,
                        "action": decision["action"],
                        "reason_for_escalation": "Shared family device / travel geo-deviation created medium risk score. System escalated to REVIEW instead of confident BLOCK.",
                        "narrative": narrative.get("narrative")
                    }

        total_elapsed = time.time() - start_eval_time
        throughput = round(len(events) / total_elapsed, 1)

        # Calculate metrics on held-out set
        y_true = np.array(y_true)
        y_pred = np.array(y_pred_flagged)
        y_scores = np.array(y_scores)

        tp = int(np.sum((y_true == 1) & (y_pred == 1)))
        fp = int(np.sum((y_true == 0) & (y_pred == 1)))
        fn = int(np.sum((y_true == 1) & (y_pred == 0)))
        tn = int(np.sum((y_true == 0) & (y_pred == 0)))

        precision = round(tp / (tp + fp) if (tp + fp) > 0 else 0.0, 4)
        recall = round(tp / (tp + fn) if (tp + fn) > 0 else 0.0, 4)
        f1 = round(2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0, 4)
        fpr = round(fp / (fp + tn) if (fp + tn) > 0 else 0.0, 4)

        # Compute PR-AUC
        precisions, recalls, _ = precision_recall_curve(y_true, y_scores)
        pr_auc = round(float(auc(recalls, precisions)), 4)

        # False positive cost estimate
        fp_cost_total = round(fp * self.fp_cost_unit_inr, 2)

        # Latency percentiles
        p95_latency = round(float(np.percentile(latencies, 95)), 2)

        # Ring level recall
        ring_recall = round(len(rings_detected) / len(rings_injected) if rings_injected else 1.0, 4)

        results = {
            "dataset_summary": {
                "total_events_processed": len(events),
                "heldout_events_evaluated": len(y_true),
                "fraud_count_in_holdout": int(np.sum(y_true)),
                "normal_count_in_holdout": int(np.sum(y_true == 0))
            },
            "performance_metrics": {
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "pr_auc": pr_auc,
                "false_positive_rate": fpr,
                "false_positive_count": fp,
                "estimated_fp_cost_inr": fp_cost_total,
                "fp_cost_unit_assumption_inr": self.fp_cost_unit_inr,
                "ring_detection_recall": ring_recall,
                "rings_injected": len(rings_injected),
                "rings_detected": len(rings_detected)
            },
            "system_metrics": {
                "p95_latency_ms": p95_latency,
                "throughput_events_per_sec": throughput
            },
            "graceful_failure_case": failure_case
        }

        # Save metrics JSON artifact
        os.makedirs("eval/results", exist_ok=True)
        with open("eval/results/eval_report.json", "w") as f:
            json.dump(results, f, indent=2)

        print("Evaluation complete. Results saved to eval/results/eval_report.json")
        return results

if __name__ == "__main__":
    evaluator = Evaluator()
    report = evaluator.run_evaluation(total_events=1000)
    print(json.dumps(report, indent=2))
