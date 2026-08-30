"""
Production-Grade Entity Graph Store with Bounded Neighborhood Traversal,
Mega-Hub Dampening, and Fast Subgraph Extraction.
"""

import networkx as nx
from typing import Dict, List, Any, Set, Tuple, Optional
from collections import defaultdict, deque

class EntityGraph:
    """
    Dynamic Graph tracking Customer-Device-IP-Card-Merchant topologies.
    Engineered for low-latency payment evaluation with bounded multi-hop
    neighborhoods and mega-hub dampening (preventing public WiFi / NAT IP explosion).
    """
    
    def __init__(self, max_hub_degree: int = 150):
        self.graph = nx.Graph()
        self.max_hub_degree = max_hub_degree
        # Cache for fast 1-hop lookups: node -> set of neighbors
        self.node_types: Dict[str, str] = {}
        # Track entity degree counts directly for O(1) feature access
        self.device_customers: Dict[str, Set[str]] = defaultdict(set)
        self.ip_customers: Dict[str, Set[str]] = defaultdict(set)
        self.card_customers: Dict[str, Set[str]] = defaultdict(set)

    def add_transaction(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests transaction nodes & edges, updates index, and returns topological risk metrics.
        """
        customer = str(txn["customer_id"])
        device = str(txn["device_id"])
        ip = str(txn["ip_address_hash"])
        card = str(txn["card_fingerprint"])
        merchant = str(txn["merchant_id"])

        # Register node types
        self.node_types[customer] = "customer"
        self.node_types[device] = "device"
        self.node_types[ip] = "ip"
        self.node_types[card] = "card"
        self.node_types[merchant] = "merchant"

        self.graph.add_node(customer, node_type="customer")
        self.graph.add_node(device, node_type="device")
        self.graph.add_node(ip, node_type="ip")
        self.graph.add_node(card, node_type="card")
        self.graph.add_node(merchant, node_type="merchant")

        # Add edges
        self.graph.add_edge(customer, device, relation="USED_DEVICE")
        self.graph.add_edge(customer, card, relation="USED_CARD")
        self.graph.add_edge(device, ip, relation="SEEN_ON_IP")
        
        # Connect merchant only for graph visualization
        self.graph.add_edge(customer, merchant, relation="PAID_MERCHANT")

        # Update fast entity-customer indices (with degree capping)
        if len(self.device_customers[device]) < self.max_hub_degree:
            self.device_customers[device].add(customer)
        if len(self.ip_customers[ip]) < self.max_hub_degree:
            self.ip_customers[ip].add(customer)
        if len(self.card_customers[card]) < self.max_hub_degree:
            self.card_customers[card].add(customer)

        return self.get_entity_metrics(customer, device, ip, card)

    def get_entity_metrics(self, customer_id: str, device_id: str, ip_hash: str, card_fp: str) -> Dict[str, Any]:
        """
        Extracts bounded topological graph metrics in sub-5ms.
        Uses BFS with k=2 max hops, ignoring merchant mega-hubs.
        """
        deg_dev = len(self.device_customers.get(device_id, set()))
        deg_ip = len(self.ip_customers.get(ip_hash, set()))
        deg_card = len(self.card_customers.get(card_fp, set()))

        # Bounded 2-hop connected component calculation
        connected_customers: Set[str] = set()
        connected_customers.add(customer_id)

        # 1-hop via shared device or card
        for c in self.device_customers.get(device_id, set()):
            connected_customers.add(c)
        for c in self.card_customers.get(card_fp, set()):
            connected_customers.add(c)

        # 2-hop expansion via connected customers' other devices (bounded)
        if len(connected_customers) > 1 and len(connected_customers) < 50:
            secondary_devs = set()
            for c in list(connected_customers)[:15]:
                if self.graph.has_node(c):
                    for nbr in self.graph.neighbors(c):
                        if self.node_types.get(nbr) == "device" and nbr != device_id:
                            secondary_devs.add(nbr)
            for d in secondary_devs:
                for c in self.device_customers.get(d, set()):
                    connected_customers.add(c)
                    if len(connected_customers) >= 100:
                        break

        component_size = len(connected_customers)
        # Ring suspect if shared device connects >= 4 distinct accounts AND high degree centrality
        is_ring = (deg_dev >= 4) or (component_size >= 8 and deg_dev >= 3) or (deg_card >= 3)
        ring_density_score = round(min(1.0, (deg_dev * 0.25 + deg_card * 0.35 + component_size * 0.05) / 3.0), 3)

        return {
            "entity_degree_device": deg_dev,
            "entity_degree_ip": deg_ip,
            "entity_degree_card": deg_card,
            "component_size": component_size,
            "is_ring_suspect": is_ring,
            "ring_density_score": ring_density_score,
            "connected_customers": list(connected_customers)[:25]
        }

    def extract_subgraph(self, customer_id: str, max_depth: int = 2, max_nodes: int = 40) -> Dict[str, Any]:
        """
        Extracts bounded subgraph centered around customer_id for Vis.js visualization.
        """
        if not self.graph.has_node(customer_id):
            return {"nodes": [], "edges": []}

        subgraph_nodes = {customer_id}
        queue = deque([(customer_id, 0)])
        visited = {customer_id}

        while queue and len(subgraph_nodes) < max_nodes:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for nbr in self.graph.neighbors(curr):
                # Skip merchant nodes if depth > 0 to prevent star-topology explosion
                if self.node_types.get(nbr) == "merchant" and depth > 0:
                    continue
                if nbr not in visited:
                    visited.add(nbr)
                    subgraph_nodes.add(nbr)
                    queue.append((nbr, depth + 1))
                    if len(subgraph_nodes) >= max_nodes:
                        break

        sub = self.graph.subgraph(subgraph_nodes)

        nodes = []
        for n in sub.nodes():
            n_type = self.node_types.get(n, "unknown")
            nodes.append({
                "id": n,
                "label": n if len(n) <= 18 else f"{n[:15]}...",
                "title": f"Node: {n} ({n_type})",
                "type": n_type
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
        """Clears all stored graph and index state."""
        self.graph.clear()
        self.node_types.clear()
        self.device_customers.clear()
        self.ip_customers.clear()
        self.card_customers.clear()
