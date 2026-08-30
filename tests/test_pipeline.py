"""
End-to-End Integration and Latency Benchmark Tests for Razorpay RiskIQ Sentinel.
Tests hotpath ingestion, dynamic ReAct agent, async worker pipeline with DLQ,
active learning feedback buffers, and shadow challenger evaluation.
"""

import time
import pytest
from fastapi.testclient import TestClient
from api.main import app
from scoring.risk_scorer import RiskScorer
from graph.entity_graph import EntityGraph
from streaming.feature_store import FeatureStore
from streaming.async_worker import AsyncInvestigationPipeline

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
        "vpa_handle_risk": 0.0,
        "is_qr_intent": False,
        "device_sim_bound": True,
        "entity_degree_device": 1,
        "entity_degree_ip": 1,
        "entity_degree_card": 1,
        "component_size": 1,
        "ring_density_score": 0.0,
        "is_ring_suspect": False
    }

    score_norm = scorer.predict_score(normal_feat)
    assert 0.0 <= score_norm < 0.30

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
        "vpa_handle_risk": 0.85,
        "is_qr_intent": False,
        "device_sim_bound": False,
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
    assert len(attrs) >= 2
    assert any("Abuse Ring" in a["feature"] or "Ring" in a["feature"] for a in attrs)


def test_api_hotpath_latency_and_response():
    payload = {
        "amount": 2499.0,
        "customer_id": "cust_lat_001",
        "merchant_id": "merch_lat_001",
        "merchant_category": "ECOMMERCE_RETAIL",
        "payment_method": "UPI_INTENT",
        "upi_vpa": "cust_lat_001@okhdfcbank",
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
    assert latency_ms < 50.0


def test_async_pipeline_metrics_and_shadow():
    resp = client.get("/api/pipeline/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "queue_size" in data
    assert "processed_count" in data
    assert "dlq_size" in data

    shadow_payload = {
        "amount": 5400.0,
        "customer_id": "cust_sh_001",
        "merchant_id": "merch_gaming_01",
        "merchant_category": "GAMING_CRYPTO",
        "payment_method": "CARD_CREDIT",
        "device_id": "dev_sh_001",
        "ip_address_hash": "ip_sh_001",
        "card_fingerprint": "card_sh_001"
    }
    sh_resp = client.post("/api/shadow/evaluate", json=shadow_payload)
    assert sh_resp.status_code == 200
    sh_data = sh_resp.json()
    assert "champion" in sh_data
    assert "challenger" in sh_data
    assert "divergence" in sh_data


def test_active_learning_and_override_workflow():
    feed_resp = client.get("/api/feed?limit=5")
    sample_txn_id = feed_resp.json()["items"][0]["transaction_id"]

    override_payload = {
        "new_action": "ALLOW",
        "reason": "Customer confirmed authentic high-value transaction via biometric 3DS verification."
    }

    resp = client.post(f"/api/case/{sample_txn_id}/override", json=override_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["override"]["new_action"] == "ALLOW"

    stats_resp = client.get("/api/active-learning/stats")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert "buffered_training_samples" in stats_data
    assert stats_data["buffered_training_samples"] >= 1
