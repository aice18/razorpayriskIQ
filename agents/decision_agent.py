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
        category = merchant_category or evidence.get("merchant_profile", {}).get("category_risk", "STANDARD")

        # Category-Specific Thresholds
        if category in ("GAMING_CRYPTO", "HIGH"):
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
            else:
                action = "STEP-UP AUTH"
                rule_fired = "RULE_MEDIUM_RISK_DYNAMIC_3DS_STEP_UP"

        else:  # score >= block_threshold
            if is_ring:
                action = "BLOCK"
                rule_fired = "RULE_HIGH_CONFIDENCE_RING_FRAUD_BLOCK"
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
            "merchant_category": category
        }
