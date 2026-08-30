"""
End-to-End Integration and Latency Benchmark Tests for Razorpay RiskIQ.
"""

import time
import pytest
from fastapi.testclient import TestClient
from api.main import app
from scoring.risk_scorer import RiskScorer
from graph.entity_graph import EntityGraph
from streaming.feature_store import FeatureStore

client = TestClient(app)

def test_ml_scorer_prediction_and_attributions():
    scorer = RiskScorer()
    
    # Normal transaction features
    normal_feat = {
        "amount": 1200.0,
        "velocity_1m": 1,
        "velocity_5m": 1,
        "velocity_1h": 1,
        "device_velocity_5m": 1,
        "amount_zscore_vs_customer": 0.2,
        "amount_zscore_vs_merchant": 0.1,
        "is_new_device": False,
        "is_new_ip": False,
        "is_new_card": False,
        "geo_deviation": 0.0,
        "entity_degree_device": 1,
        "entity_degree_ip": 1,
        "entity_degree_card": 1,
        "component_size": 1,
        "ring_density_score": 0.0,
        "is_ring_suspect": False
    }

    score_norm = scorer.predict_score(normal_feat)
    assert 0.0 <= score_norm < 0.25

    # Fraud ring features
    fraud_feat = {
        "amount": 85000.0,
        "velocity_1m": 4,
        "velocity_5m": 8,
        "velocity_1h": 12,
        "device_velocity_5m": 8,
        "amount_zscore_vs_customer": 4.8,
        "amount_zscore_vs_merchant": 3.9,
        "is_new_device": True,
        "is_new_ip": True,
        "is_new_card": True,
        "geo_deviation": 1.0,
        "entity_degree_device": 14,
        "entity_degree_ip": 12,
        "entity_degree_card": 4,
        "component_size": 22,
        "ring_density_score": 0.95,
        "is_ring_suspect": True
    }

    score_fraud = scorer.predict_score(fraud_feat)
    assert score_fraud >= 0.70

    attrs = scorer.explain_prediction(fraud_feat, score_fraud)
    assert len(attrs) >= 3
    assert attrs[0]["feature"] == "Abuse Ring Topology"

def test_api_hotpath_latency_and_response():
    payload = {
        "amount": 2499.0,
        "customer_id": "cust_lat_001",
        "merchant_id": "merch_lat_001",
        "device_id": "dev_lat_001",
        "ip_address_hash": "ip_lat_001",
        "card_fingerprint": "card_lat_001",
        "geo_country": "IN",
        "customer_home_country": "IN"
    }

    t0 = time.time()
    resp = client.post("/api/ingest", json=payload)
    t1 = time.time()
    latency_ms = (t1 - t0) * 1000.0

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ingested"
    assert data["rail"] == "synchronous_hotpath"
    assert "score" in data
    assert "action" in data
    # Ensure hot-path API response SLA is under 50ms
    assert latency_ms < 50.0

def test_feed_and_case_endpoints():
    feed_resp = client.get("/api/feed?limit=10")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert "items" in feed_data
    assert len(feed_data["items"]) > 0

    sample_txn_id = feed_data["items"][0]["transaction_id"]
    case_resp = client.get(f"/api/case/{sample_txn_id}")
    assert case_resp.status_code == 200
    case_data = case_resp.json()
    assert case_data["transaction_id"] == sample_txn_id
    assert "evidence" in case_data
    assert "narrative" in case_data
    assert "decision" in case_data

def test_analyst_override_workflow():
    feed_resp = client.get("/api/feed?limit=5")
    sample_txn_id = feed_resp.json()["items"][0]["transaction_id"]

    override_payload = {
        "new_action": "ALLOW",
        "reason": "Verified user identity and genuine travel receipt via high-touch concierge."
    }

    resp = client.post(f"/api/case/{sample_txn_id}/override", json=override_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["override"]["new_action"] == "ALLOW"
