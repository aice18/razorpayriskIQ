"""
2. Reasoning / Explanation Agent (Claude API + Fallback Template).
Converts structured Investigation Agent evidence into analyst-readable narratives.
Guaranteed to never alter risk scores or decisions.
"""

import os
import json
from typing import Dict, Any

class ReasoningAgent:
    """Generates plain-language analyst narrative from evidence JSON."""
    
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
You are a Senior Risk Analyst for Razorpay Sentinel. Summarize the following structured transaction investigation evidence into a clear analyst case brief.

STRICT INSTRUCTIONS:
- Do NOT alter scores or suggest decisions. Only summarize evidence.
- Produce a JSON response with keys 'headline' and 'narrative'.
- No speculation beyond the provided evidence.

Evidence:
{json.dumps(evidence, indent=2)}
"""

        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=300,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )

        content_text = response.content[0].text
        # Parse JSON from response
        if "{" in content_text and "}" in content_text:
            json_str = content_text[content_text.find("{"):content_text.rfind("}")+1]
            return json.loads(json_str)
        
        return {
            "headline": "Risk Investigation Brief",
            "narrative": content_text
        }

    def _generate_template_narrative(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic, reliable template fallback when LLM API is unreachable."""
        txn_id = evidence["transaction_id"]
        score = evidence["score"]
        anomalies = evidence.get("anomalies", [])
        ring = evidence.get("ring_membership", {})
        
        if ring.get("ring_detected"):
            comp_size = ring.get("component_size", 0)
            dev_deg = ring.get("device_degree", 0)
            headline = f"High Risk: Suspected Abuse Ring Member ({comp_size} linked accounts)"
            narrative = (
                f"Transaction {txn_id} (Risk Score: {score}) exhibits coordinated ring behavior. "
                f"The transaction device is linked to {dev_deg} distinct customer accounts within a graph component "
                f"of size {comp_size}. Key anomalies detected: " +
                "; ".join([a["detail"] for a in anomalies]) + "."
            )
        elif len(anomalies) > 0:
            primary_anomaly = anomalies[0]["detail"]
            headline = f"Risk Flag (Score {score}): {anomalies[0]['type'].replace('_', ' ').title()}"
            narrative = (
                f"Transaction {txn_id} was flagged with a risk score of {score}. "
                f"Primary indicator: {primary_anomaly}. Total anomalies identified: {len(anomalies)}."
            )
        else:
            headline = f"Standard Review Case (Score {score})"
            narrative = f"Transaction {txn_id} reached flagged threshold (Score: {score}) for automated analyst review."

        return {
            "transaction_id": txn_id,
            "headline": headline,
            "narrative": narrative,
            "is_fallback": True
        }
