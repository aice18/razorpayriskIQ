"""
Unit tests for Autonomous Agent Triad (Investigation, Reasoning, Decision).
"""

import pytest
from agents.investigation_agent import InvestigationAgent
from agents.reasoning_agent import ReasoningAgent
from agents.decision_agent import DecisionAgent

def test_investigation_and_decision_pipeline():
    investigator = InvestigationAgent()
    reasoner = ReasoningAgent()
    decider = DecisionAgent()

    txn = {
        "transaction_id": "txn_test_001",
        "customer_id": "cust_101",
        "merchant_id": "merch_101",
        "amount": 95000.0,
        "geo_country": "US",
        "customer_home_country": "IN"
    }

    features = {
        "velocity_5m": 6,
        "entity_degree_device": 12,
        "component_size": 14,
        "is_ring_suspect": True,
        "amount_zscore_vs_customer": 4.5,
        "is_new_device": True,
        "is_new_ip": True,
        "geo_deviation": 1.0
    }

    score = 0.92

    # 1. Evidence extraction
    evidence = investigator.investigate(txn, features, score)
    assert evidence["transaction_id"] == "txn_test_001"
    assert evidence["ring_membership"]["ring_detected"] == True
    assert len(evidence["anomalies"]) >= 4

    # 2. Reasoning narrative (fallback template test)
    narrative = reasoner.explain(evidence)
    assert "headline" in narrative
    assert "narrative" in narrative

    # 3. Deterministic Decision Gating
    decision = decider.decide(score, evidence)
    assert decision["action"] == "BLOCK"
    assert decision["rule_fired"] == "RULE_SCORE_ABOVE_0.70_AUTO_BLOCK"

def test_medium_risk_ring_escalation_to_review():
    decider = DecisionAgent()
    evidence = {
        "transaction_id": "txn_test_002",
        "ring_membership": {"ring_detected": True}
    }
    decision = decider.decide(0.55, evidence)
    assert decision["action"] == "REVIEW"
    assert decision["rule_fired"] == "RULE_SCORE_MEDIUM_WITH_RING_FLAG_ESCALATE_REVIEW"

def test_medium_risk_no_ring_step_up():
    decider = DecisionAgent()
    evidence = {
        "transaction_id": "txn_test_003",
        "ring_membership": {"ring_detected": False}
    }
    decision = decider.decide(0.55, evidence)
    assert decision["action"] == "STEP-UP AUTH"
    assert decision["rule_fired"] == "RULE_SCORE_MEDIUM_NO_RING_STEP_UP_AUTHENTICATION"
