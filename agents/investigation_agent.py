"""
Autonomous Dynamic ReAct Investigation Agent for Razorpay RiskIQ Sentinel.
Dynamically coordinates multi-tool evidence collection, dynamically chooses investigation paths,
and synthesizes verifiable attribution traces without hallucination.
"""

from typing import Dict, Any, List, Optional
from agents.agent_tools import (
    EntityGraphTool,
    MerchantProfileTool,
    VelocityAnomalyTool,
    DeviceIntelligenceTool
)


class InvestigationAgent:
    """Autonomous ReAct investigator executing adaptive tool selection based on intermediate evidence."""
    
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
        Executes dynamic ReAct loop, adapting tool invocations based on emerging hypotheses.
        """
        txn_id = txn["transaction_id"]
        tool_traces = []
        step_count = 1

        # Determine primary hypotheses based on top SHAP attributions and initial feature signals
        is_suspect_ring = features.get("is_ring_suspect", False) or features.get("entity_degree_device", 1) >= 3
        is_velocity_burst = features.get("velocity_5m", 1) >= 3 or features.get("device_velocity_5m", 1) >= 3
        is_geo_deviant = features.get("geo_deviation", 0.0) > 0.0 or features.get("is_new_device", False)

        # ReAct Step 1: Dynamic Triage - Velocity & Spending Profile
        thought_1 = "Initial triage: inspect short-term velocity bursts and customer spend deviation."
        v_result = self.velocity_tool.execute(txn, features)
        tool_traces.append({
            "step": step_count,
            "tool": self.velocity_tool.name,
            "thought": thought_1,
            "action": f"execute({self.velocity_tool.name})",
            "observation": v_result["assessment"],
            "data": v_result
        })
        step_count += 1

        # ReAct Step 2: Entity Graph Neighborhood Traversal
        # Always run if high risk or ring flags or device reuse suspected
        if is_suspect_ring or score >= 0.30 or v_result.get("is_velocity_spike"):
            thought_2 = "Suspicious velocity or topological risk flag detected: expanding 2-hop entity graph neighborhood."
            if graph_store is not None:
                g_result = self.graph_tool.execute(txn, graph_store)
            else:
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
                "step": step_count,
                "tool": self.graph_tool.name,
                "thought": thought_2,
                "action": f"execute({self.graph_tool.name})",
                "observation": g_result["assessment"],
                "data": g_result
            })
            step_count += 1
        else:
            g_result = {"is_ring_suspect": False, "component_size": 1, "device_degree": 1}

        # ReAct Step 3: Device & Geo Intelligence
        # Prioritize if geo mismatch, new device, or ATO suspected
        if is_geo_deviant or score >= 0.40 or g_result.get("is_ring_suspect"):
            thought_3 = "Device or credential anomaly indicated: assessing device fingerprint, IP proxy, and geo travel."
            d_result = self.device_tool.execute(txn, features)
            tool_traces.append({
                "step": step_count,
                "tool": self.device_tool.name,
                "thought": thought_3,
                "action": f"execute({self.device_tool.name})",
                "observation": d_result["assessment"],
                "data": d_result
            })
            step_count += 1
        else:
            d_result = {"is_new_device": False, "has_geo_mismatch": False}

        # ReAct Step 4: Merchant Profile & Chargeback Benchmark
        # Run if ticket size is anomalous or merchant category is high risk
        if features.get("amount_zscore_vs_merchant", 0.0) >= 2.0 or score >= 0.35:
            thought_4 = "Evaluating merchant baseline ticket size and chargeback risk benchmark."
            m_result = self.merchant_tool.execute(txn, feature_store)
            tool_traces.append({
                "step": step_count,
                "tool": self.merchant_tool.name,
                "thought": thought_4,
                "action": f"execute({self.merchant_tool.name})",
                "observation": m_result["assessment"],
                "data": m_result
            })
            step_count += 1
        else:
            m_result = {"category_risk": "STANDARD", "chargeback_rate_bps": 15}

        # Synthesize collected evidence into auditable case structure
        anomalies = []
        if g_result.get("is_ring_suspect"):
            anomalies.append(f"Abuse ring detected ({g_result.get('component_size')} linked accounts)")
        if v_result.get("is_velocity_spike"):
            anomalies.append(f"Velocity spike: {v_result.get('velocity_5m')} txns in 5 minutes")
        if v_result.get("is_amount_spike"):
            anomalies.append(f"Amount outlier: +{v_result.get('customer_amount_zscore')} sigma")
        if d_result.get("has_geo_mismatch"):
            anomalies.append(f"Geo mismatch: originating {d_result.get('txn_geo')} vs home {d_result.get('home_geo')}")

        return {
            "transaction_id": txn_id,
            "score": score,
            "anomalies": anomalies,
            "ring_membership": {
                "ring_detected": g_result.get("is_ring_suspect", False),
                "component_size": g_result.get("component_size", 1),
                "device_degree": g_result.get("device_degree", 1),
                "connected_accounts": g_result.get("connected_accounts", [])
            },
            "merchant_profile": {
                "category_risk": m_result.get("category_risk", "STANDARD"),
                "chargeback_rate_bps": m_result.get("chargeback_rate_bps", 15)
            },
            "device_profile": {
                "is_new_device": d_result.get("is_new_device", False),
                "has_geo_mismatch": d_result.get("has_geo_mismatch", False)
            },
            "attributions": attributions or [],
            "tool_traces": tool_traces,
            "tool_calls_count": len(tool_traces)
        }
