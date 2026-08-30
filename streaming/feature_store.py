"""
In-memory feature store for calculating rolling window features, velocities,
z-scores, and entity first-seen flags (simulating Redis/Flink stream processing).
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import numpy as np

class FeatureStore:
    """Manages low-latency rolling feature computations per entity."""
    
    def __init__(self):
        # Maps customer_id -> list of (timestamp_dt, amount)
        self.customer_history: Dict[str, List[tuple]] = {}
        # Maps device_id -> list of timestamp_dt
        self.device_history: Dict[str, List[datetime]] = {}
        # Sets for first-seen tracking
        self.seen_devices: set = set()
        self.seen_ips: set = set()
        self.seen_cards: set = set()
        # Merchant amount accumulators for baseline computation
        self.merchant_amounts: Dict[str, List[float]] = {}

    def compute_and_update(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests a transaction, updates rolling windows, and returns the enriched feature vector.
        """
        cust = txn["customer_id"]
        dev = txn["device_id"]
        ip = txn["ip_address_hash"]
        card = txn["card_fingerprint"]
        merch = txn["merchant_id"]
        amount = float(txn["amount"])
        
        # Parse timestamp
        if isinstance(txn["timestamp"], str):
            ts = datetime.fromisoformat(txn["timestamp"].replace("Z", "+00:00"))
        else:
            ts = txn["timestamp"]

        # First-seen booleans
        is_new_device = dev not in self.seen_devices
        is_new_ip = ip not in self.seen_ips
        is_new_card = card not in self.seen_cards

        self.seen_devices.add(dev)
        self.seen_ips.add(ip)
        self.seen_cards.add(card)

        # Update customer history
        if cust not in self.customer_history:
            self.customer_history[cust] = []
        self.customer_history[cust].append((ts, amount))

        # Update device history
        if dev not in self.device_history:
            self.device_history[dev] = []
        self.device_history[dev].append(ts)

        # Update merchant history
        if merch not in self.merchant_amounts:
            self.merchant_amounts[merch] = []
        self.merchant_amounts[merch].append(amount)

        # Compute velocity features
        velocity_1m = sum(1 for (t, _) in self.customer_history[cust] if ts - t <= timedelta(minutes=1))
        velocity_5m = sum(1 for (t, _) in self.customer_history[cust] if ts - t <= timedelta(minutes=5))
        velocity_1h = sum(1 for (t, _) in self.customer_history[cust] if ts - t <= timedelta(hours=1))
        
        device_velocity_5m = sum(1 for t in self.device_history[dev] if ts - t <= timedelta(minutes=5))

        # Compute amount z-score vs customer history
        cust_amounts = [a for (_, a) in self.customer_history[cust][:-1]]  # prior amounts
        if len(cust_amounts) >= 2:
            mean_c = np.mean(cust_amounts)
            std_c = np.std(cust_amounts) + 1e-5
            amount_zscore_vs_customer = float((amount - mean_c) / std_c)
        else:
            amount_zscore_vs_customer = 0.0


        # Compute amount z-score vs merchant average
        merch_past = self.merchant_amounts[merch][:-1]
        if len(merch_past) >= 2:
            mean_m = np.mean(merch_past)
            std_m = np.std(merch_past) + 1e-5
            amount_zscore_vs_merchant = float((amount - mean_m) / std_m)
        else:
            amount_zscore_vs_merchant = 0.0

        # Geo country mismatch indicator
        geo_country = txn.get("geo_country", "IN")
        home_country = txn.get("customer_home_country", "IN")
        geo_deviation = 1.0 if geo_country != home_country else 0.0

        return {
            "velocity_1m": velocity_1m,
            "velocity_5m": velocity_5m,
            "velocity_1h": velocity_1h,
            "device_velocity_5m": device_velocity_5m,
            "amount_zscore_vs_customer": round(amount_zscore_vs_customer, 3),
            "amount_zscore_vs_merchant": round(amount_zscore_vs_merchant, 3),
            "is_new_device": is_new_device,
            "is_new_ip": is_new_ip,
            "is_new_card": is_new_card,
            "geo_deviation": geo_deviation
        }

    def clear(self):
        """Clears all stored history."""
        self.customer_history.clear()
        self.device_history.clear()
        self.seen_devices.clear()
        self.seen_ips.clear()
        self.seen_cards.clear()
        self.merchant_amounts.clear()
