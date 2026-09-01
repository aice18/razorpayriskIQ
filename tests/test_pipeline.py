"""
End-to-End Integration and Latency Benchmark Tests for Razorpay RiskIQ Sentinel.
Tests hotpath ingestion, idempotency deduplication, dynamic ReAct agent, async worker pipeline with DLQ,
active learning feedback buffers & auto-retraining, and shadow challenger evaluation.
"""

import time
import pytest
from fastapi.testclient import TestClient
from api.main import app
from scoring.risk_scorer import RiskScorer
from graph.entity_graph import EntityGraph
from streaming.feature_store import FeatureStore
from streaming.async_worker import AsyncInvestigationPipeline
from streaming.idempotency import IdempotencyEngine
from scoring.retraining_pipeline import ActiveLearningRetrainer

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

    # Warm-up request to avoid cold-start TestClient initialization overhead
    client.post("/api/ingest", json=payload)

    t0 = time.time()
    resp = client.post("/api/ingest", json={**payload, "customer_id": "cust_lat_002"})
    t1 = time.time()
    latency_ms = (t1 - t0) * 1000.0

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ingested"
    assert data["rail"] == "synchronous_hotpath"
    assert "score" in data
    assert "action" in data
    assert latency_ms < 50.0


def test_idempotency_deduplication_replay():
    payload = {
        "amount": 999.0,
        "customer_id": "cust_idem_001",
        "merchant_id": "merch_idem_001",
        "merchant_category": "ECOMMERCE_RETAIL",
        "payment_method": "UPI_INTENT",
        "upi_vpa": "idem_user@okhdfcbank",
        "device_id": "dev_idem_001",
        "ip_address_hash": "ip_idem_001",
        "card_fingerprint": "card_idem_001",
        "idempotency_key": "unique_idempotency_test_key_001"
    }

    # 1. First Ingestion
    resp1 = client.post("/api/ingest", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_idempotent_replay"] is False

    # 2. Duplicate Replay within TTL
    resp2 = client.post("/api/ingest", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_idempotent_replay"] is True
    assert data2["action"] == data1["action"]
    assert data2["score"] == data1["score"]


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

    # Trigger Active Learning Retraining Pipeline
    retrain_resp = client.post("/api/active-learning/retrain")
    assert retrain_resp.status_code == 200
    retrain_data = retrain_resp.json()
    assert retrain_data["status"] == "success"
    assert "challenger_validation_pr_auc" in retrain_data
    assert "promoted_to_champion" in retrain_data


def test_razorpay_webhook_ingestion():
    import json
    import hmac
    import hashlib

    webhook_payload = {
        "event": "payment.authorized",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_rzp_hook_001",
                    "amount": 250000, # 2500.00 INR (paise)
                    "currency": "INR",
                    "status": "authorized",
                    "method": "card",
                    "contact": "+919876543210",
                    "email": "customer@example.com",
                    "notes": {
                        "device_id": "dev_rzp_test_001",
                        "ip": "103.21.244.1",
                        "merchant_id": "merch_rzp_ecom_01",
                        "country": "IN"
                    }
                }
            }
        }
    }

    body_bytes = json.dumps(webhook_payload).encode("utf-8")
    secret = "rzp_webhook_secret_sandbox_2026"
    valid_sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

    # 1. Test with valid HMAC signature
    resp = client.post(
        "/api/razorpay/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "x-razorpay-signature": valid_sig}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["razorpay_payment_id"] == "pay_test_rzp_hook_001"
    assert "decision" in data
    assert data["decision"]["score"] >= 0.0

    # 2. Test with invalid HMAC signature (should be rejected)
    bad_resp = client.post(
        "/api/razorpay/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "x-razorpay-signature": "invalid_signature_hash"}
    )
    assert bad_resp.status_code == 400


def test_crossborder_and_dispute_deflection():
    # 1. Ingest a cross-border transaction with Non-3DS mode
    payload = {
        "amount": 650.0,
        "currency": "USD",
        "customer_id": "cust_xb_test_01",
        "merchant_id": "merch_crossborder_saas",
        "merchant_category": "CROSSBORDER_SAAS",
        "payment_method": "CARD_CREDIT",
        "auth_mode": "NON_3DS_FRICTIONLESS",
        "is_cross_border": True,
        "locality": "US-NYC-Manhattan",
        "delivery_days_est": 3.0,
        "device_id": "dev_xb_test_01",
        "ip_address_hash": "ip_xb_test_01",
        "card_fingerprint": "card_xb_test_01",
        "geo_country": "US",
        "customer_home_country": "US"
    }

    resp = client.post("/api/ingest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_mode"] == "NON_3DS_FRICTIONLESS"
    assert data["is_cross_border"] == True

    # 2. Test Pre-dispute deflection endpoint
    deflect_resp = client.post(f"/api/dispute/deflect/{data['transaction_id']}")
    assert deflect_resp.status_code == 200
    deflect_data = deflect_resp.json()
    assert deflect_data["status"] == "DEFLECTED_PRE_DISPUTE"
    assert deflect_data["vamp_ratio_protected"] == True


def test_preemptive_quarantine_endpoint():
    # 1. Call quarantine endpoint on a seed device
    quarantine_payload = {
        "node_id": "dev_cluster_ring_seed",
        "reason": "CONFIRMED_CARD_TESTING_BOTNET",
        "max_hops": 2
    }
    q_resp = client.post("/api/graph/quarantine", json=quarantine_payload)
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["status"] == "quarantined"

    # 2. Ingest transaction with quarantined device -> should be immediately blocked
    ingest_payload = {
        "amount": 250.0,
        "currency": "INR",
        "customer_id": "cust_victim_adjacent",
        "merchant_id": "merch_ecom_04",
        "device_id": "dev_cluster_ring_seed",
        "ip_address_hash": "ip_norm_adj",
        "card_fingerprint": "card_norm_adj",
        "geo_country": "IN",
        "customer_home_country": "IN"
    }
    ing_resp = client.post("/api/ingest", json=ingest_payload)
    assert ing_resp.status_code == 200
    ing_data = ing_resp.json()
    assert ing_data["action"] == "BLOCK"
    assert ing_data["rule_fired"] == "RULE_PREEMPTIVE_GRAPH_QUARANTINE_BLOCK"
    assert ing_data["is_preemptively_quarantined"] == True

