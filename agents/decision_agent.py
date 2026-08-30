"""
3. Decision Agent (Deterministic Rule Policy - No LLM).
Maps risk scores and graph ring topology to bounded actions: ALLOW, STEP-UP AUTH, REVIEW, BLOCK.
Guaranteed to be 100% reproducible and auditable.
"""

from typing import Dict, Any

class DecisionAgent:
    """Bounded, policy-gated decision engine for transaction risk triage."""
    
    # Bounded set of allowed actions
    ALLOWED_ACTIONS = {"ALLOW", "STEP-UP AUTH", "REVIEW", "BLOCK"}

    def decide(self, score: float, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies deterministic policy matrix to select action and record firing rule.
        """
        ring_info = evidence.get("ring_membership", {})
        is_ring = ring_info.get("ring_detected", False)

        if score < 0.40:
            action = "ALLOW"
            rule_fired = "RULE_SCORE_BELOW_0.40_AUTO_ALLOW"

        elif 0.40 <= score <= 0.70:
            if is_ring:
                action = "REVIEW"
                rule_fired = "RULE_SCORE_MEDIUM_WITH_RING_FLAG_ESCALATE_REVIEW"
            else:
                action = "STEP-UP AUTH"
                rule_fired = "RULE_SCORE_MEDIUM_NO_RING_STEP_UP_AUTHENTICATION"

        else:  # score > 0.70
            action = "BLOCK"
            rule_fired = "RULE_SCORE_ABOVE_0.70_AUTO_BLOCK"

        # Assert action is strictly within bounded set
        assert action in self.ALLOWED_ACTIONS, f"Invalid action generated: {action}"

        return {
            "transaction_id": evidence.get("transaction_id"),
            "score": score,
            "action": action,
            "rule_fired": rule_fired,
            "is_ring_driven": is_ring
        }
