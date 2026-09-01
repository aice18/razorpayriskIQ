"""
Deterministic Decision Policy Agent for Razorpay RiskIQ Sentinel.
Maps calibrated ML risk probabilities, multi-tenant merchant category policies,
TreeSHAP feature attributions, and ring topology to bounded actions:
ALLOW, STEP-UP AUTH (3DS / OTP), REVIEW, BLOCK.
100% reproducible, auditable, and zero-hallucination.
"""

from typing import Dict, Any, Optional

ALLOWED_ACTIONS = {"ALLOW", "STEP-UP AUTH", "REVIEW", "BLOCK"}


class DecisionAgent:
    """Bounded, policy-gated multi-tenant decision engine for payment risk triage."""
    
    ALLOWED_ACTIONS = ALLOWED_ACTIONS

    def decide(self, score: float, evidence: Dict[str, Any], merchant_category: Optional[str] = None) -> Dict[str, Any]:
        """
        Applies deterministic multi-tenant policy matrix to select action and record firing rule.
        """
        ring_info = evidence.get("ring_membership", {})
        is_ring = ring_info.get("ring_detected", False)
        comp_size = ring_info.get("component_size", 1)
        is_quarantined = ring_info.get("is_preemptively_quarantined", False) or evidence.get("is_preemptively_quarantined", False)
        category = merchant_category or evidence.get("merchant_profile", {}).get("category_risk", "STANDARD")
        is_non_3ds = evidence.get("is_non_3ds", False)
        is_cross_border = evidence.get("is_cross_border", False)
        service_cb_risk = float(evidence.get("service_chargeback_risk", 0.0))

        # 1. Immediate Preemptive Graph Quarantine Intercept (Tiered Policy)
        quarantine_tier = evidence.get("quarantine_tier") or ring_info.get("quarantine_tier")
        if is_quarantined:
            if quarantine_tier == "SOFT_CHALLENGE":
                return {
                    "transaction_id": evidence.get("transaction_id"),
                    "score": score,
                    "action": "STEP-UP AUTH",
                    "rule_fired": "RULE_PREEMPTIVE_SOFT_QUARANTINE_3DS_STEP_UP",
                    "is_ring_driven": True,
                    "merchant_category": category,
                    "shield_action": "PREEMPTIVE_LIABILITY_SHIFT_STEP_UP"
                }
            else:
                return {
                    "transaction_id": evidence.get("transaction_id"),
                    "score": score,
                    "action": "BLOCK",
                    "rule_fired": "RULE_PREEMPTIVE_GRAPH_QUARANTINE_BLOCK",
                    "is_ring_driven": True,
                    "merchant_category": category,
                    "shield_action": "PREEMPTIVE_LOSS_AVOIDED"
                }

        # Category-Specific Thresholds
        if category in ("GAMING_CRYPTO", "HIGH", "CROSSBORDER_SAAS", "GLOBAL_EXPORTER"):
            step_up_threshold = 0.20
            block_threshold = 0.55
        elif category in ("UTILITY_BILLPAY", "VERY_LOW"):
            step_up_threshold = 0.40
            block_threshold = 0.75
        else:
            step_up_threshold = 0.25
            block_threshold = 0.60

        # Multi-Tenant Policy Matrix
        if score < step_up_threshold:
            action = "ALLOW"
            rule_fired = "RULE_FASTPATH_LOW_RISK_ALLOW"

        elif step_up_threshold <= score < block_threshold:
            if is_ring and comp_size >= 4:
                action = "REVIEW"
                rule_fired = "RULE_MEDIUM_RISK_ABUSE_RING_ESCALATE_REVIEW"
            elif is_cross_border and is_non_3ds:
                # Dynamically step up to 3DS to shift fraud liability to issuer without full drop-off
                action = "STEP-UP AUTH"
                rule_fired = "RULE_CROSSBORDER_DYNAMIC_3DS_LIABILITY_SHIFT"
            elif service_cb_risk >= 0.50:
                action = "REVIEW"
                rule_fired = "RULE_HIGH_SERVICE_DISPUTE_DEFLECTION_ALERT"
            else:
                action = "STEP-UP AUTH"
                rule_fired = "RULE_MEDIUM_RISK_DYNAMIC_3DS_STEP_UP"

        else:  # score >= block_threshold
            if is_ring:
                action = "BLOCK"
                rule_fired = "RULE_HIGH_CONFIDENCE_RING_FRAUD_BLOCK"
            elif is_cross_border and is_non_3ds:
                action = "BLOCK"
                rule_fired = "RULE_CROSSBORDER_NON_3DS_ZERO_LIABILITY_BLOCK"
            else:
                action = "BLOCK"
                rule_fired = "RULE_HIGH_RISK_VELOCITY_OR_ANOMALY_BLOCK"

        assert action in self.ALLOWED_ACTIONS, f"Invalid action generated: {action}"

        return {
            "transaction_id": evidence.get("transaction_id"),
            "score": score,
            "action": action,
            "rule_fired": rule_fired,
            "is_ring_driven": is_ring,
            "merchant_category": category,
            "shield_action": "LIABILITY_OPTIMIZED"
        }
