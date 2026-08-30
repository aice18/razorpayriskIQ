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
