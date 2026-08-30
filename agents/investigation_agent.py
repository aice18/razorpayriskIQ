"""
Autonomous ReAct Investigation Agent for Razorpay RiskIQ.
Executes specialized tools (Graph Topology, Merchant Baseline, Velocity Spikes, Device Intelligence),
synthesizes local feature attributions, and generates an auditable tool trace.
"""

from typing import Dict, Any, List, Optional
from agents.agent_tools import (
    EntityGraphTool,
    MerchantProfileTool,
    VelocityAnomalyTool,
    DeviceIntelligenceTool
)

class InvestigationAgent:
    """Autonomous investigator coordinating multi-tool evidence collection and attribution synthesis."""
    
    def __init__(self):
        self.graph_tool = EntityGraphTool()
        self.merchant_tool = MerchantProfileTool()
        self.velocity_tool = VelocityAnomalyTool()
        self.device_tool = DeviceIntelligenceTool()

    def investigate(
        self,
        txn: Dict[str, Any],
        features: Dict[str, Any],
        score: float,
        graph_store: Optional[Any] = None,
        feature_store: Optional[Any] = None,
        attributions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes investigation tools in sequence, recording reasoning thoughts and tool outputs.
        """
        txn_id = txn["transaction_id"]
        tool_traces = []

        # Tool 1: Velocity & Amount Inspection
        v_result = self.velocity_tool.execute(txn, features)
        tool_traces.append({
            "step": 1,
            "tool": self.velocity_tool.name,
            "thought": "Evaluate short-term transaction velocity and historical customer amount standard deviation.",
            "observation": v_result["assessment"],
            "data": v_result
        })

        # Tool 2: Entity Graph & Topology Analysis
        if graph_store is not None:
            g_result = self.graph_tool.execute(txn, graph_store)
        else:
            # Fallback if graph_store reference not passed
            g_result = {
                "tool": self.graph_tool.name,
                "device_degree": features.get("entity_degree_device", 1),
                "ip_degree": features.get("entity_degree_ip", 1),
                "card_degree": features.get("entity_degree_card", 1),
                "component_size": features.get("component_size", 1),
                "is_ring_suspect": features.get("is_ring_suspect", False),
                "ring_density_score": features.get("ring_density_score", 0.0),
                "connected_accounts": features.get("connected_customers", []),
                "assessment": (
                    f"Abuse ring topology detected ({features.get('component_size', 1)} linked accounts)"
                    if features.get("is_ring_suspect")
                    else "Standard entity degree centrality."
                )
            }
        tool_traces.append({
            "step": 2,
            "tool": self.graph_tool.name,
            "thought": "Traverse 2-hop entity neighborhood to detect shared device clusters and synthetic rings.",
            "observation": g_result["assessment"],
            "data": g_result
        })

        # Tool 3: Merchant Risk Profiling
        m_result = self.merchant_tool.execute(txn, feature_store)
        tool_traces.append({
            "step": 3,
            "tool": self.merchant_tool.name,
            "thought": "Compare ticket size against merchant historical baseline and category risk profile.",
            "observation": m_result["assessment"],
            "data": m_result
        })

        # Tool 4: Device & Geo Intelligence
        d_result = self.device_tool.execute(txn, features)
        tool_traces.append({
            "step": 4,
            "tool": self.device_tool.name,
            "thought": "Check device first-seen status, cross-border geo deviation, and IP consistency.",
            "observation": d_result["assessment"],
            "data": d_result
        })

        # Assemble unified anomaly list
        anomalies: List[Dict[str, str]] = []
        if g_result.get("is_ring_suspect"):
            anomalies.append({
                "type": "abuse_ring_cluster",
                "detail": f"Coordinated ring detected: {g_result['component_size']} accounts linked across device/card."
            })
        if v_result.get("is_velocity_spike"):
            anomalies.append({
                "type": "velocity_spike",
                "detail": f"High velocity burst: {v_result['velocity_5m']} txns in 5m window."
            })
        if v_result.get("is_amount_spike"):
            anomalies.append({
                "type": "amount_deviation",
                "detail": f"Amount is +{round(v_result['customer_amount_zscore'], 1)} sigma above customer baseline."
            })
        if d_result.get("has_geo_mismatch"):
            anomalies.append({
                "type": "geo_mismatch",
                "detail": f"Geo country '{d_result['txn_geo']}' differs from home country '{d_result['home_geo']}'."
            })
        if d_result.get("is_new_device"):
            anomalies.append({
                "type": "new_device",
                "detail": "First time transaction processed from this device fingerprint."
            })

        return {
            "transaction_id": txn_id,
            "customer_id": txn["customer_id"],
            "merchant_id": txn["merchant_id"],
            "amount": float(txn["amount"]),
            "score": score,
            "anomalies": anomalies,
            "tool_traces": tool_traces,
            "attributions": attributions or [],
            "ring_membership": {
                "ring_detected": g_result.get("is_ring_suspect", False),
                "component_size": g_result.get("component_size", 1),
                "device_degree": g_result.get("device_degree", 1),
                "ip_degree": g_result.get("ip_degree", 1),
                "connected_customers": g_result.get("connected_accounts", [])
            }
        }
