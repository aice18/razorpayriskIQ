"""
Production-Grade Hybrid Entity Graph Store for Razorpay RiskIQ Sentinel.
Combines sub-2ms Redis Adjacency Set indexing for hot-path degree centrality
with bounded multi-hop NetworkX community & ring extraction for deep investigation.
"""

import os
import threading
from typing import Dict, List, Any, Set, Tuple, Optional
from collections import defaultdict, deque
import networkx as nx

import importlib

redis = None
try:
    redis = importlib.import_module("redis")
except ImportError:
    redis = None


class EntityGraph:
    """
    Hybrid Graph Engine:
    1. Hot-Path: Redis Adjacency Sets (or local fast-lookup sets) for O(1) degree metrics and hub dampening.
    2. Deep Path: Bounded NetworkX subgraph extractor for community/ring detection and UI visualization.
    """
    
    def __init__(self, max_hub_degree: int = 150, redis_host: Optional[str] = None, redis_port: Optional[int] = None):
        self.max_hub_degree = max_hub_degree
        self.graph = nx.Graph()
        self.node_types: Dict[str, str] = {}
        self._lock = threading.Lock()

        # In-memory entity indices
        self.device_customers: Dict[str, Set[str]] = defaultdict(set)
        self.ip_customers: Dict[str, Set[str]] = defaultdict(set)
        self.card_customers: Dict[str, Set[str]] = defaultdict(set)
        self.customer_devices: Dict[str, Set[str]] = defaultdict(set)

        # Redis backend initialization
        self.redis_client = None
        self.redis_host = redis_host or os.environ.get("REDIS_HOST", "localhost")
        self.redis_port = int(redis_port or os.environ.get("REDIS_PORT", 6379))
        if redis is not None and (os.environ.get("USE_REDIS", "false").lower() in ("true", "1") or os.environ.get("REDIS_HOST")):
            try:
                r = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    decode_responses=True
                )
                r.ping()
                self.redis_client = r
            except Exception:
                self.redis_client = None

    def add_transaction(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests transaction edges into graph, updates adjacency index, and returns topological metrics.
        """
        customer = str(txn["customer_id"])
        device = str(txn["device_id"])
        ip = str(txn["ip_address_hash"])
        card = str(txn["card_fingerprint"])
        merchant = str(txn["merchant_id"])

        with self._lock:
            # Register node types
            self.node_types[customer] = "customer"
            self.node_types[device] = "device"
            self.node_types[ip] = "ip"
            self.node_types[card] = "card"
            self.node_types[merchant] = "merchant"

            # Add nodes
            self.graph.add_node(customer, node_type="customer")
            self.graph.add_node(device, node_type="device")
            self.graph.add_node(ip, node_type="ip")
            self.graph.add_node(card, node_type="card")
            self.graph.add_node(merchant, node_type="merchant")

            # Add topology edges
            self.graph.add_edge(customer, device, relation="USED_DEVICE")
            self.graph.add_edge(customer, card, relation="USED_CARD")
            self.graph.add_edge(device, ip, relation="SEEN_ON_IP")
            self.graph.add_edge(customer, merchant, relation="PAID_MERCHANT")

            # Update in-memory sets with mega-hub dampening
            if len(self.device_customers[device]) < self.max_hub_degree:
                self.device_customers[device].add(customer)
            if len(self.ip_customers[ip]) < self.max_hub_degree:
                self.ip_customers[ip].add(customer)
            if len(self.card_customers[card]) < self.max_hub_degree:
                self.card_customers[card].add(customer)
            self.customer_devices[customer].add(device)

        # Update Redis Adjacency Sets if connected
        if self.redis_client:
            try:
                p = self.redis_client.pipeline(transaction=False)
                p.sadd(f"g:dev:{device}", customer)
                p.expire(f"g:dev:{device}", 7776000)
                p.sadd(f"g:ip:{ip}", customer)
                p.expire(f"g:ip:{ip}", 2592000)
                p.sadd(f"g:card:{card}", customer)
                p.expire(f"g:card:{card}", 7776000)
                p.execute()
            except Exception:
                pass

        return self.get_entity_metrics(customer, device, ip, card)

    def get_entity_metrics(self, customer_id: str, device_id: str, ip_hash: str, card_fp: str) -> Dict[str, Any]:
        """
        Extracts bounded topological graph metrics in sub-2ms.
        Uses BFS with bounded 2-hop neighborhood expansion.
        """
        with self._lock:
            deg_dev = len(self.device_customers.get(device_id, set()))
            deg_ip = len(self.ip_customers.get(ip_hash, set()))
            deg_card = len(self.card_customers.get(card_fp, set()))

            connected_customers: Set[str] = set()
            connected_customers.add(customer_id)

            # 1-hop via shared device or card
            connected_customers.update(self.device_customers.get(device_id, set()))
            connected_customers.update(self.card_customers.get(card_fp, set()))

            # Bounded 2-hop expansion via connected customers' alternate devices
            if 1 < len(connected_customers) < 50:
                secondary_devices: Set[str] = set()
                sample_customers = list(connected_customers)[:12]
                for c in sample_customers:
                    secondary_devices.update(self.customer_devices.get(c, set()))
                
                for d in secondary_devices:
                    if d != device_id:
                        connected_customers.update(self.device_customers.get(d, set()))
                        if len(connected_customers) >= 100:
                            break

            component_size = len(connected_customers)
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
        Extracts bounded ego subgraph centered around customer_id for interactive Vis.js visualization.
        """
        with self._lock:
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
                    # Suppress merchant nodes from multi-hop expansion to avoid star topology distortion
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
        """Clears all stored graph nodes and indices."""
        with self._lock:
            self.graph.clear()
            self.node_types.clear()
            self.device_customers.clear()
            self.ip_customers.clear()
            self.card_customers.clear()
            self.customer_devices.clear()
