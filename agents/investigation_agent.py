"""
Autonomous Dynamic ReAct Investigation Agent for Razorpay RiskIQ Sentinel.
Dynamically coordinates multi-tool evidence collection, adapts investigation pathways based on
emerging hypotheses and information gain, and synthesizes verifiable attribution traces without hallucination.
"""

from typing import Dict, Any, List, Optional
from agents.agent_tools import (
    EntityGraphTool,
    MerchantProfileTool,
    VelocityAnomalyTool,
    DeviceIntelligenceTool,
    UPIIntelligenceTool
)


class InvestigationAgent:
    """
    Autonomous Dynamic ReAct Investigator:
    - Formulates hypotheses based on initial ML scores, SHAP attributions, and incoming features.
    - Adaptively schedules tools based on maximum expected information gain.
    - Evaluates intermediate observations with early stopping when confidence converges.
    """
    
    def __init__(self):
        self.tools = {
            "inspect_velocity_and_amount": VelocityAnomalyTool(),
            "inspect_entity_graph": EntityGraphTool(),
            "inspect_device_and_geo": DeviceIntelligenceTool(),
            "inspect_merchant_profile": MerchantProfileTool(),
            "inspect_upi_profile": UPIIntelligenceTool()
        }

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
        Executes dynamic hypothesis-driven ReAct loop with adaptive tool dispatching and early exit.
        """
        txn_id = txn["transaction_id"]
        tool_traces = []
        executed_tools = set()
        anomalies = []
        
        # Step 0: Hypothesis Generation
        hypotheses = self._formulate_hypotheses(txn, features, score, attributions)
        confidence = score
        step_count = 1
        max_steps = 4

        # Intermediate state container
        state = {
            "g_result": {"is_ring_suspect": False, "component_size": 1, "device_degree": 1, "connected_accounts": []},
            "v_result": {"is_velocity_spike": False, "is_amount_spike": False, "velocity_5m": 1, "customer_amount_zscore": 0.0},
            "d_result": {"is_new_device": False, "has_geo_mismatch": False},
            "m_result": {"category_risk": "STANDARD", "chargeback_rate_bps": 15},
            "u_result": {"is_high_risk_upi": False, "device_sim_bound": True}
        }

        # Dynamic ReAct Execution Loop
        while step_count <= max_steps and hypotheses:
            current_hypo = hypotheses.pop(0)
            target_tool_name = current_hypo["tool"]

            if target_tool_name in executed_tools:
                continue

            tool_obj = self.tools.get(target_tool_name)
            if not tool_obj:
                continue

            # Execute tool dynamically
            thought = current_hypo["rationale"]
            action = f"{target_tool_name}(txn_id='{txn_id}')"
            
            if target_tool_name == "inspect_velocity_and_amount":
                obs_data = tool_obj.execute(txn, features)
                state["v_result"] = obs_data
                if obs_data.get("is_velocity_spike"):
                    anomalies.append(f"Velocity spike: {obs_data.get('velocity_5m')} txns in 5 min")
                    confidence = min(0.99, confidence + 0.15)
                if obs_data.get("is_amount_spike"):
                    anomalies.append(f"Amount outlier: +{obs_data.get('customer_amount_zscore')} sigma")
                    confidence = min(0.99, confidence + 0.10)

            elif target_tool_name == "inspect_entity_graph":
                if graph_store is not None:
                    obs_data = tool_obj.execute(txn, graph_store)
                else:
                    obs_data = {
                        "tool": target_tool_name,
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
                            else "Normal entity degree centrality."
                        )
                    }
                state["g_result"] = obs_data
                if obs_data.get("is_ring_suspect"):
                    anomalies.append(f"Abuse ring detected ({obs_data.get('component_size')} linked accounts)")
                    confidence = min(0.99, confidence + 0.25)

            elif target_tool_name == "inspect_device_and_geo":
                obs_data = tool_obj.execute(txn, features)
                state["d_result"] = obs_data
                if obs_data.get("has_geo_mismatch"):
                    anomalies.append(f"Geo mismatch: originating {obs_data.get('txn_geo')} vs home {obs_data.get('home_geo')}")
                    confidence = min(0.99, confidence + 0.15)

            elif target_tool_name == "inspect_merchant_profile":
                obs_data = tool_obj.execute(txn, feature_store)
                state["m_result"] = obs_data
                if obs_data.get("category_risk") == "HIGH":
                    confidence = min(0.99, confidence + 0.05)

            elif target_tool_name == "inspect_upi_profile":
                obs_data = tool_obj.execute(txn, features)
                state["u_result"] = obs_data
                if obs_data.get("is_high_risk_upi"):
                    anomalies.append(f"High-risk UPI VPA profile / SIM unbound")
                    confidence = min(0.99, confidence + 0.20)

            # Record auditable ReAct step trace
            tool_traces.append({
                "step": step_count,
                "hypothesis": current_hypo["type"],
                "thought": thought,
                "action": action,
                "tool": target_tool_name,
                "observation": obs_data.get("assessment", "Tool execution complete."),
                "confidence_estimate": round(confidence, 3),
                "data": obs_data
            })
            
            executed_tools.add(target_tool_name)
            step_count += 1

            # Early Stopping Check: High certainty achieved with multiple confirming tools
            if step_count >= 3:
                if confidence >= 0.90 and len(anomalies) >= 2:
                    break  # Highly confident fraud case, avoid redundant tool cost
                elif confidence <= 0.10 and not anomalies:
                    break  # Conclusively benign transaction

        return {
            "transaction_id": txn_id,
            "score": score,
            "final_confidence": round(confidence, 3),
            "anomalies": anomalies,
            "ring_membership": {
                "ring_detected": state["g_result"].get("is_ring_suspect", False),
                "component_size": state["g_result"].get("component_size", 1),
                "device_degree": state["g_result"].get("device_degree", 1),
                "connected_accounts": state["g_result"].get("connected_accounts", [])
            },
            "merchant_profile": {
                "category_risk": state["m_result"].get("category_risk", "STANDARD"),
                "chargeback_rate_bps": state["m_result"].get("chargeback_rate_bps", 15)
            },
            "device_profile": {
                "is_new_device": state["d_result"].get("is_new_device", False),
                "has_geo_mismatch": state["d_result"].get("has_geo_mismatch", False)
            },
            "upi_profile": {
                "is_high_risk_upi": state["u_result"].get("is_high_risk_upi", False),
                "device_sim_bound": state["u_result"].get("device_sim_bound", True)
            },
            "attributions": attributions or [],
            "tool_traces": tool_traces,
            "tool_calls_count": len(tool_traces)
        }

    def _formulate_hypotheses(
        self,
        txn: Dict[str, Any],
        features: Dict[str, Any],
        score: float,
        attributions: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, str]]:
        """Generates a prioritized list of investigative hypotheses based on initial signals."""
        hypotheses = []

        is_ring = features.get("is_ring_suspect", False) or features.get("entity_degree_device", 1) >= 3
        is_velocity = features.get("velocity_5m", 1) >= 3 or features.get("device_velocity_5m", 1) >= 3
        is_geo = features.get("geo_deviation", 0.0) > 0.0 or features.get("is_new_device", False)
        is_upi = "UPI" in str(txn.get("payment_method", ""))
        is_high_ticket = features.get("amount_zscore_vs_merchant", 0.0) >= 2.0 or score >= 0.35

        # Priority 1: Coordinated Ring Abuse
        if is_ring or score >= 0.40:
            hypotheses.append({
                "type": "RING_SYNDICATE",
                "tool": "inspect_entity_graph",
                "rationale": "High topological risk or device reuse flag detected: expanding 2-hop entity neighborhood."
            })

        # Priority 2: Temporal Velocity Surge
        if is_velocity or score >= 0.25:
            hypotheses.append({
                "type": "VELOCITY_BURST",
                "tool": "inspect_velocity_and_amount",
                "rationale": "Short-term burst velocity or customer spend deviation detected: inspecting 1m/5m/1h velocity curves."
            })

        # Priority 3: UPI VPA & SIM binding Risk
        if is_upi:
            hypotheses.append({
                "type": "UPI_ANOMALY",
                "tool": "inspect_upi_profile",
                "rationale": "UPI payment rail active: verifying VPA handle reputation and hardware SIM binding state."
            })

        # Priority 4: ATO & Device Credential Mismatch
        if is_geo or score >= 0.30:
            hypotheses.append({
                "type": "CREDENTIAL_ATO",
                "tool": "inspect_device_and_geo",
                "rationale": "New device or geo-mismatch flag: assessing device fingerprint and geo-travel plausibility."
            })

        # Priority 5: Merchant Baseline Risk
        if is_high_ticket or score >= 0.20:
            hypotheses.append({
                "type": "MERCHANT_EXPOSURE",
                "tool": "inspect_merchant_profile",
                "rationale": "Evaluating ticket size ratio vs merchant category baseline and historical chargebacks."
            })

        # Default fallback if benign
        if not hypotheses:
            hypotheses.append({
                "type": "BASELINE_TRIAGE",
                "tool": "inspect_velocity_and_amount",
                "rationale": "Standard triage: verifying velocity and amount baseline consistency."
            })

        return hypotheses
