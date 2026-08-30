"""
Unit tests for Autonomous Dynamic ReAct Agent Triad and Tool Execution.
"""

import pytest
from agents.investigation_agent import InvestigationAgent
from agents.reasoning_agent import ReasoningAgent
from agents.decision_agent import DecisionAgent
from agents.agent_tools import (
    EntityGraphTool,
    MerchantProfileTool,
    VelocityAnomalyTool,
    DeviceIntelligenceTool
)
from graph.entity_graph import EntityGraph


def test_agent_tools_execution():
    graph = EntityGraph()
    v_tool = VelocityAnomalyTool()
    m_tool = MerchantProfileTool()
    d_tool = DeviceIntelligenceTool()

    txn = {
        "transaction_id": "txn_tool_001",
        "customer_id": "cust_001",
        "merchant_id": "merch_crypto_01",
        "amount": 25000.0,
        "device_id": "dev_001",
        "ip_address_hash": "ip_001",
        "card_fingerprint": "card_001",
        "geo_country": "SG",
        "customer_home_country": "IN"
    }

    features = {
        "velocity_1m": 3,
        "velocity_5m": 5,
        "velocity_1h": 8,
        "device_velocity_5m": 5,
        "amount_zscore_vs_customer": 4.2,
        "is_new_device": True,
        "is_new_ip": True,
        "geo_deviation": 1.0
    }

    v_res = v_tool.execute(txn, features)
    assert v_res["is_velocity_spike"] is True
    assert v_res["is_amount_spike"] is True

    m_res = m_tool.execute(txn, None)
    assert m_res["category_risk"] == "HIGH"

    d_res = d_tool.execute(txn, features)
    assert d_res["has_geo_mismatch"] is True
    assert d_res["is_new_device"] is True


def test_investigation_and_decision_pipeline():
    investigator = InvestigationAgent()
    reasoner = ReasoningAgent()
    decider = DecisionAgent()

    txn = {
        "transaction_id": "txn_test_001",
        "customer_id": "cust_101",
        "merchant_id": "merch_101",
        "amount": 95000.0,
        "device_id": "dev_101",
        "ip_address_hash": "ip_101",
        "card_fingerprint": "card_101",
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

    score = 0.88

    # 1. Evidence extraction with dynamic ReAct tool traces
    evidence = investigator.investigate(txn, features, score)
    assert evidence["transaction_id"] == "txn_test_001"
    assert evidence["ring_membership"]["ring_detected"] is True
    assert len(evidence["tool_traces"]) >= 2
    assert len(evidence["anomalies"]) >= 2

    # 2. Reasoning narrative
    narrative = reasoner.explain(evidence)
    assert "headline" in narrative
    assert "narrative" in narrative

    # 3. Deterministic Decision Gating
    decision = decider.decide(score, evidence)
    assert decision["action"] == "BLOCK"
    assert decision["rule_fired"] == "RULE_HIGH_CONFIDENCE_RING_FRAUD_BLOCK"


def test_medium_risk_ring_escalation_to_review():
    decider = DecisionAgent()
    evidence = {
        "transaction_id": "txn_test_002",
        "ring_membership": {"ring_detected": True, "component_size": 5}
    }
    decision = decider.decide(0.45, evidence)
    assert decision["action"] == "REVIEW"
    assert decision["rule_fired"] == "RULE_MEDIUM_RISK_ABUSE_RING_ESCALATE_REVIEW"


def test_medium_risk_no_ring_step_up():
    decider = DecisionAgent()
    evidence = {
        "transaction_id": "txn_test_003",
        "ring_membership": {"ring_detected": False, "component_size": 1}
    }
    decision = decider.decide(0.45, evidence)
    assert decision["action"] == "STEP-UP AUTH"
    assert decision["rule_fired"] == "RULE_MEDIUM_RISK_DYNAMIC_3DS_STEP_UP"
