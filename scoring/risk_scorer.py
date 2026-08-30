"""
Hybrid Risk Scoring Engine combining Graph Topology features and Velocity/Amount anomaly metrics.
Produces a continuous risk score strictly bounded between 0.00 and 1.00.
"""

from typing import Dict, Any
import numpy as np

class RiskScorer:
    """Interpretable, deterministic risk scoring model for payment transactions."""
    
    def __init__(self):
        # Model feature weights (tuned for high recall on abuse rings and velocity spikes)
        self.weights = {
            "velocity_5m": 0.15,
            "device_velocity_5m": 0.18,
            "amount_zscore_vs_customer": 0.12,
            "amount_zscore_vs_merchant": 0.08,
            "is_new_device": 0.05,
            "is_new_ip": 0.04,
            "geo_deviation": 0.08,
            "entity_degree_device": 0.22,
            "entity_degree_ip": 0.15,
            "component_size": 0.25
        }

    def predict_score(self, features: Dict[str, Any]) -> float:
        """
        Computes continuous risk probability score [0.0, 1.0] from feature vector.
        """
        v5m = features.get("velocity_5m", 0)
        dev_v5m = features.get("device_velocity_5m", 0)
        z_cust = max(features.get("amount_zscore_vs_customer", 0.0), 0.0)
        z_merch = max(features.get("amount_zscore_vs_merchant", 0.0), 0.0)
        
        deg_dev = features.get("entity_degree_device", 1)
        deg_ip = features.get("entity_degree_ip", 1)
        comp_size = features.get("component_size", 1)

        # Baseline score for normal transactions
        score = 0.05

        # 1. Abuse Ring Topology Signals
        if features.get("is_ring_suspect") or comp_size >= 6 or deg_dev >= 6 or deg_ip >= 6:
            score += 0.65
        elif deg_dev >= 3 or deg_ip >= 3:
            score += 0.25

        # 2. Velocity Fraud Signals
        if v5m >= 4 or dev_v5m >= 4:
            score += 0.40
        elif v5m >= 3:
            score += 0.15

        # 3. Amount Anomaly Signals
        if z_cust >= 5.0:
            score += 0.35
        elif z_cust >= 3.0:
            score += 0.20

        # 4. Geo Mismatch
        if features.get("geo_deviation", 0.0) > 0.0:
            score += 0.15

        # Clip final score between 0.02 and 0.98
        final_score = round(float(np.clip(score, 0.02, 0.98)), 3)
        return final_score


