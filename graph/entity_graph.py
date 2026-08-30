"""
Entity Graph store and community/ring detection module for RiskIQ Sentinel.
Maintains a dynamic NetworkX graph tracking relationships between Customer, Device,
IP, Card, and Merchant nodes.
"""

import networkx as nx
from typing import Dict, List, Any, Set, Tuple, Optional

class EntityGraph:
    """Dynamic graph managing entities and tracking connected components / abuse rings."""
    
    def __init__(self):
        self.graph = nx.Graph()

    def add_transaction(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates the graph with nodes and edges from a transaction event,
        and returns updated topological graph metrics for the transaction's entities.
        """
        customer = txn["customer_id"]
        device = txn["device_id"]
        ip = txn["ip_address_hash"]
        card = txn["card_fingerprint"]
        merchant = txn["merchant_id"]

        # Add nodes with types
        self.graph.add_node(customer, node_type="customer")
        self.graph.add_node(device, node_type="device")
        self.graph.add_node(ip, node_type="ip")
        self.graph.add_node(card, node_type="card")
        self.graph.add_node(merchant, node_type="merchant")

        # Add connecting edges
        self.graph.add_edge(customer, device, relation="USED_DEVICE")
        self.graph.add_edge(customer, card, relation="USED_CARD")
        self.graph.add_edge(device, ip, relation="SEEN_ON_IP")
        self.graph.add_edge(customer, merchant, relation="PAID_MERCHANT")

        # Compute graph features for this transaction
        return self.get_entity_metrics(customer, device, ip, card)

    def _get_customer_neighbors(self, entity_node: str) -> Set[str]:
        """Returns the set of distinct customer_ids connected to an entity node."""
        if not self.graph.has_node(entity_node):
            return set()
        
        # Direct customer neighbors
        direct_custs = {n for n in self.graph.neighbors(entity_node) if self.graph.nodes[n].get("node_type") == "customer"}
        
        # 2-hop neighbors through device or card nodes only (avoid IP mega-hubs)
        two_hop_custs = set()
        for neighbor in self.graph.neighbors(entity_node):
            nbr_type = self.graph.nodes[neighbor].get("node_type")
            if nbr_type in ("device", "card"):
                for n2 in self.graph.neighbors(neighbor):
                    if self.graph.nodes[n2].get("node_type") == "customer":
                        two_hop_custs.add(n2)
                    
        return direct_custs.union(two_hop_custs)


    def get_entity_metrics(self, customer_id: str, device_id: str, ip_hash: str, card_fp: str) -> Dict[str, Any]:
        """Extracts topological ring & degree metrics for specified entities."""
        device_customers = self._get_customer_neighbors(device_id)
        ip_customers = self._get_customer_neighbors(ip_hash)
        card_customers = self._get_customer_neighbors(card_fp)

        # Build Customer-Device-IP-Card subgraph to find component size
        # Exclude merchant nodes from component size calculation so normal popular merchants don't join all users
        c_subgraph_nodes = set()
        if self.graph.has_node(customer_id):
            # Breadth-first search up to 4 hops excluding merchant nodes
            visited = set()
            queue = [customer_id]
            while queue:
                curr = queue.pop(0)
                if curr in visited:
                    continue
                visited.add(curr)
                if self.graph.nodes[curr].get("node_type") != "merchant":
                    c_subgraph_nodes.add(curr)
                    for nbr in self.graph.neighbors(curr):
                        if nbr not in visited and self.graph.nodes[nbr].get("node_type") != "merchant":
                            queue.append(nbr)

        # Count distinct customers in this entity component
        component_customers = {
            n for n in c_subgraph_nodes if self.graph.nodes[n].get("node_type") == "customer"
        }

        component_size = len(component_customers)
        is_ring = component_size >= 6  # Threshold for abuse ring classification

        return {
            "entity_degree_device": len(device_customers),
            "entity_degree_ip": len(ip_customers),
            "entity_degree_card": len(card_customers),
            "component_size": component_size,
            "is_ring_suspect": is_ring,
            "connected_customers": list(component_customers)[:20]  # cap sample list
        }

    def extract_subgraph(self, customer_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        Extracts a localized subgraph (nodes and edges formatted for D3/vis.js visualization)
        centered around a customer ID.
        """
        if not self.graph.has_node(customer_id):
            return {"nodes": [], "edges": []}

        subgraph_nodes = set([customer_id])
        current_layer = set([customer_id])

        for _ in range(max_depth):
            next_layer = set()
            for node in current_layer:
                for nbr in self.graph.neighbors(node):
                    if self.graph.nodes[nbr].get("node_type") != "merchant" or len(subgraph_nodes) < 30:
                        next_layer.add(nbr)
            subgraph_nodes.update(next_layer)
            current_layer = next_layer

        sub = self.graph.subgraph(subgraph_nodes)

        nodes = []
        for n in sub.nodes():
            nodes.append({
                "id": n,
                "label": n,
                "type": sub.nodes[n].get("node_type", "unknown")
            })

        edges = []
        for u, v, data in sub.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "relation": data.get("relation", "CONNECTED")
            })

        return {"nodes": nodes, "edges": edges}

    def clear(self):
        """Clears the graph."""
        self.graph.clear()
