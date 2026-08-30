"""
Deterministic Decision Policy Agent for Razorpay RiskIQ.
Maps calibrated ML risk probabilities, SHAP feature attributions, and ring topology
to bounded actions: ALLOW, STEP-UP AUTH (3DS), REVIEW, BLOCK.
100% reproducible, auditable, and zero-hallucination.
"""

from typing import Dict, Any

class DecisionAgent:
    """Bounded, policy-gated decision engine for transaction risk triage."""
    
    ALLOWED_ACTIONS = {"ALLOW", "STEP-UP AUTH", "REVIEW", "BLOCK"}

    def decide(self, score: float, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies deterministic policy matrix to select action and record firing rule.
        """
        ring_info = evidence.get("ring_membership", {})
        is_ring = ring_info.get("ring_detected", False)
        comp_size = ring_info.get("component_size", 1)

        # Policy Matrix
        if score < 0.25:
            action = "ALLOW"
            rule_fired = "RULE_FASTPATH_LOW_RISK_ALLOW"

        elif 0.25 <= score < 0.60:
            if is_ring:
                action = "REVIEW"
                rule_fired = "RULE_MEDIUM_RISK_ABUSE_RING_ESCALATE_REVIEW"
            else:
                action = "STEP-UP AUTH"
                rule_fired = "RULE_MEDIUM_RISK_STEP_UP_AUTHENTICATION"

        else:  # score >= 0.60
            if is_ring:
                action = "BLOCK"
                rule_fired = "RULE_HIGH_CONFIDENCE_RING_FRAUD_BLOCK"
            else:
                action = "BLOCK"
                rule_fired = "RULE_HIGH_RISK_VELOCITY_FRAUD_BLOCK"

        # Assert action is strictly within bounded set
        assert action in self.ALLOWED_ACTIONS, f"Invalid action generated: {action}"

        return {
            "transaction_id": evidence.get("transaction_id"),
            "score": score,
            "action": action,
            "rule_fired": rule_fired,
            "is_ring_driven": is_ring
        }
