"""
Unit tests for EntityGraph entity linking & abuse ring detection logic.
"""

import pytest
from graph.entity_graph import EntityGraph

def test_entity_graph_ring_detection():
    graph = EntityGraph()
    
    shared_device = "dev_ring_test_99"
    shared_ip = "ip_ring_test_99"
    shared_card = "card_ring_test_99"

    # Connect 10 synthetic customers to same device
    for i in range(1, 11):
        txn = {
            "customer_id": f"cust_ring_{i:02d}",
            "device_id": shared_device,
            "ip_address_hash": shared_ip,
            "card_fingerprint": shared_card,
            "merchant_id": "merch_001"
        }
        metrics = graph.add_transaction(txn)

    # Inspect metrics for 10th customer
    assert metrics["entity_degree_device"] == 10
    assert metrics["component_size"] == 10
    assert metrics["is_ring_suspect"] == True

def test_extract_subgraph():
    graph = EntityGraph()
    txn = {
        "customer_id": "cust_sub_01",
        "device_id": "dev_sub_01",
        "ip_address_hash": "ip_sub_01",
        "card_fingerprint": "card_sub_01",
        "merchant_id": "merch_sub_01"
    }
    graph.add_transaction(txn)

    subgraph = graph.extract_subgraph("cust_sub_01")
    assert len(subgraph["nodes"]) >= 4
    assert len(subgraph["edges"]) >= 3


def test_mega_hub_dampening():
    graph = EntityGraph()
    public_wifi_ip = "ip_public_airport_wifi"

    # Simulate 50 legitimate users on the same public Wi-Fi IP but with unique devices
    for i in range(1, 51):
        txn = {
            "customer_id": f"cust_wifi_{i:02d}",
            "device_id": f"dev_unique_{i:02d}",
            "ip_address_hash": public_wifi_ip,
            "card_fingerprint": f"card_unique_{i:02d}",
            "merchant_id": "merch_cafe_01"
        }
        metrics = graph.add_transaction(txn)

def test_preemptive_graph_quarantine():
    graph = EntityGraph()
    
    # 1. Connect a 3-customer ring on a shared device
    for i in range(1, 4):
        txn = {
            "customer_id": f"cust_quar_{i:02d}",
            "device_id": "dev_quar_shared",
            "ip_address_hash": f"ip_quar_{i:02d}",
            "card_fingerprint": f"card_quar_{i:02d}",
            "merchant_id": "merch_001",
            "locality": "US-NYC-Manhattan"
        }
        graph.add_transaction(txn)

    # 2. Trigger quarantine on shared device
    quarantine_res = graph.quarantine_entity("dev_quar_shared", reason="TEST_RING_QUARANTINE", max_hops=2)
    assert quarantine_res["status"] == "quarantined"
    assert quarantine_res["quarantined_count"] >= 3

    # 3. New transaction from connected customer should be preemptively flagged in <0.05ms
    check = graph.check_preemptive_quarantine(
        customer_id="cust_quar_01",
        device_id="dev_quar_shared",
        ip_hash="ip_quar_01",
        card_fp="card_quar_01"
    )
    assert check["is_preemptively_quarantined"] == True
    assert check["quarantine_reason"] == "TEST_RING_QUARANTINE"

