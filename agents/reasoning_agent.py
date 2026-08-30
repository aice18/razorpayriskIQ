"""
Reasoning & Case Dossier Agent for Razorpay RiskIQ.
Converts structured Investigation Agent evidence, tool traces, and SHAP attributions
into analyst-ready executive briefs via Claude API (or deterministic template fallback).
Guaranteed to never alter risk scores or policy decisions.
"""

import os
import json
from typing import Dict, Any, List

class ReasoningAgent:
    """Generates plain-language analyst narrative and case dossier from multi-tool evidence."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = None
        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception:
                self.client = None

    def explain(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes investigation evidence JSON and produces headline + plain language narrative.
        """
        # Try Claude API first if client is available
        if self.client:
            try:
                narrative_data = self._call_claude(evidence)
                if narrative_data:
                    return narrative_data
            except Exception:
                pass  # Fall back gracefully

        # Fallback to deterministic template generator
        return self._generate_template_narrative(evidence)

    def _call_claude(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""
You are a Senior Risk Analyst for Razorpay RiskIQ (Sentinel). Summarize the following structured transaction investigation evidence into a clear, audit-proof analyst case brief.

STRICT INSTRUCTIONS:
- Do NOT alter scores or suggest decisions. Only summarize facts from tools and attributions.
- Produce a JSON response with keys 'headline', 'narrative', and 'recommended_action_rationale'.
- Ground all statements strictly in the provided evidence.

Investigation Evidence:
{json.dumps(evidence, indent=2)}
"""

        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=350,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )

        content_text = response.content[0].text
        if "{" in content_text and "}" in content_text:
            json_str = content_text[content_text.find("{"):content_text.rfind("}")+1]
            return json.loads(json_str)
        
        return {
            "headline": "Risk Investigation Brief",
            "narrative": content_text,
            "recommended_action_rationale": "Review tool traces and SHAP attributions for confirmation."
        }

    def _generate_template_narrative(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic, auditable template fallback when LLM API is unreachable."""
        txn_id = evidence["transaction_id"]
        score = evidence["score"]
        anomalies = evidence.get("anomalies", [])
        ring = evidence.get("ring_membership", {})
        attributions = evidence.get("attributions", [])
        
        # Build SHAP summary
        top_attrs = [f"{a['feature']} ({a['value']})" for a in attributions[:2]] if attributions else []
        attr_str = f" Key contributing model factors: {', '.join(top_attrs)}." if top_attrs else ""

        if ring.get("ring_detected"):
            comp_size = ring.get("component_size", 0)
            dev_deg = ring.get("device_degree", 0)
            headline = f"High Risk: Suspected Abuse Ring Member ({comp_size} linked accounts)"
            narrative = (
                f"Transaction {txn_id} (ML Risk Score: {score}) exhibits coordinated abuse ring patterns. "
                f"The device fingerprint is actively linked to {dev_deg} distinct customer accounts across a "
                f"graph component of {comp_size} entities.{attr_str} "
                f"Anomalies detected: " + "; ".join([a["detail"] for a in anomalies]) + "."
            )
            rationale = "High-density device sharing across multiple accounts indicates syndicated fraud; recommend blocking or step-up authentication."
        elif len(anomalies) > 0:
            primary_anomaly = anomalies[0]["detail"]
            headline = f"Risk Alert (Score {score}): {anomalies[0]['type'].replace('_', ' ').title()}"
            narrative = (
                f"Transaction {txn_id} flagged with ML risk score of {score}. "
                f"Primary anomaly: {primary_anomaly}.{attr_str} "
                f"Total behavioral deviations identified: {len(anomalies)}."
            )
            rationale = "Elevated velocity or spend deviation exceeds baseline threshold; requires verification."
        else:
            headline = f"Standard Review Case (Score {score})"
            narrative = f"Transaction {txn_id} processed with ML risk score {score}.{attr_str}"
            rationale = "Score falls within acceptable standard operating band."

        return {
            "transaction_id": txn_id,
            "headline": headline,
            "narrative": narrative,
            "recommended_action_rationale": rationale,
            "is_fallback": True
        }
