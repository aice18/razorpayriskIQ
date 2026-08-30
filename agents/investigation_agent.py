"""
1. Investigation Agent (Deterministic, Pure Python - No LLM).
Assembles structured evidence package (anomalies, velocity spikes, graph topology, ring membership).
"""

from typing import Dict, Any, List

class InvestigationAgent:
    """Extracts structured evidence package for flagged transactions."""
    
    def investigate(self, txn: Dict[str, Any], features: Dict[str, Any], score: float) -> Dict[str, Any]:
        """
        Builds deterministic evidence payload from raw features and graph metrics.
        """
        txn_id = txn["transaction_id"]
        anomalies: List[Dict[str, str]] = []

        # Amount anomaly check
        z_cust = features.get("amount_zscore_vs_customer", 0.0)
        if z_cust >= 3.0:
            anomalies.append({
                "type": "amount_deviation",
                "detail": f"{round(z_cust, 1)}x standard deviation above customer average spend"
            })

        # Velocity check
        v5m = features.get("velocity_5m", 0)
        if v5m >= 4:
            anomalies.append({
                "type": "velocity_spike",
                "detail": f"{v5m} transactions attempted in the last 5 minutes"
            })

        # Device reuse check
        deg_dev = features.get("entity_degree_device", 1)
        if deg_dev >= 3:
            anomalies.append({
                "type": "shared_device",
                "detail": f"Device linked to {deg_dev} distinct customer accounts"
            })

        # First seen checks
        if features.get("is_new_device"):
            anomalies.append({
                "type": "new_device",
                "detail": "First time transaction processed from this device fingerprint"
            })

        if features.get("is_new_ip"):
            anomalies.append({
                "type": "new_ip",
                "detail": "Transaction originating from an unseen IP hash"
            })

        # Geo check
        if features.get("geo_deviation", 0.0) > 0.0:
            anomalies.append({
                "type": "geo_mismatch",
                "detail": f"Transaction country ({txn.get('geo_country')}) differs from home country ({txn.get('customer_home_country')})"
            })

        # Ring membership check
        comp_size = features.get("component_size", 1)
        is_ring = features.get("is_ring_suspect", False) or comp_size >= 6

        ring_membership = {
            "ring_detected": is_ring,
            "component_size": comp_size,
            "device_degree": deg_dev,
            "ip_degree": features.get("entity_degree_ip", 1),
            "connected_customers_count": len(features.get("connected_customers", []))
        }

        if is_ring:
            anomalies.append({
                "type": "abuse_ring_cluster",
                "detail": f"Part of a detected connected graph component containing {comp_size} linked entities"
            })

        return {
            "transaction_id": txn_id,
            "customer_id": txn["customer_id"],
            "merchant_id": txn["merchant_id"],
            "amount": txn["amount"],
            "score": score,
            "anomalies": anomalies,
            "ring_membership": ring_membership
        }
