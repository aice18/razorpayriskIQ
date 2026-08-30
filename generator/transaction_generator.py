"""
Synthetic Transaction Stream Generator for RiskIQ Sentinel.
Generates realistic payment streams containing normal traffic, velocity fraud spikes,
coordinated abuse rings, and ambiguous/borderline cases with ground-truth labeling.
"""

import random
import time
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from generator.profiles import EntityPool

class TransactionGenerator:
    """Generates synthetic transaction streams with embedded fraud rings and velocity patterns."""
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.pool = EntityPool()
        self.rings: Dict[str, Dict[str, Any]] = self._generate_ring_definitions()

    def _generate_ring_definitions(self, num_rings: int = 5) -> Dict[str, Dict[str, Any]]:
        """Pre-define synthetic fraud rings sharing specific devices, IPs, and cards."""
        rings = {}
        for i in range(1, num_rings + 1):
            ring_id = f"ring_{i:03d}"
            # Ring shares 1-2 devices and 1-2 IPs across 10-25 synthetic customer accounts
            shared_device = random.choice(self.pool.devices)
            shared_ip = random.choice(self.pool.ips)
            shared_card = random.choice(self.pool.cards)
            member_customers = random.sample(self.pool.customers, random.randint(10, 25))
            
            rings[ring_id] = {
                "ring_id": ring_id,
                "shared_device": shared_device,
                "shared_ip": shared_ip,
                "shared_card": shared_card,
                "members": member_customers
            }
        return rings

    def generate_event(
        self,
        event_index: int,
        timestamp: datetime,
        pattern_override: Optional[str] = None,
        is_holdout: bool = False
    ) -> Dict[str, Any]:
        """Generate a single transaction event dictionary."""
        
        # Decide pattern if not overridden
        if pattern_override:
            pattern = pattern_override
        else:
            r = random.random()
            if r < 0.78:
                pattern = "NORMAL"
            elif r < 0.88:
                pattern = "VELOCITY_FRAUD"
            elif r < 0.96:
                pattern = "RING_FRAUD"
            else:
                pattern = "AMBIGUOUS"

        txn_id = f"txn_{event_index:08d}"
        merchant_id = self.pool.get_random_merchant()
        avg_ticket = self.pool.merchant_avg_ticket[merchant_id]

        if pattern == "NORMAL":
            customer_id = self.pool.get_random_customer()
            device_id = self.pool.customer_primary_device[customer_id]
            ip_hash = f"ip_hash_norm_{customer_id}"
            card_fp = f"card_fp_norm_{customer_id}"
            geo = self.pool.customer_home_country[customer_id]
            amount = round(random.gauss(avg_ticket, avg_ticket * 0.25), 2)
            amount = max(10.0, amount)
            is_fraud = False
            ring_id = None

        elif pattern == "VELOCITY_FRAUD":
            # Single customer rapidly hitting high amounts from new IP/device
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_vel_{random.randint(1, 50)}"
            ip_hash = f"ip_hash_vel_{random.randint(1, 30)}"
            card_fp = f"card_fp_vel_{customer_id}"
            geo = "IN"
            amount = round(avg_ticket * random.uniform(8.0, 20.0), 2)
            is_fraud = True
            ring_id = None

        elif pattern == "RING_FRAUD":
            # Pick one of the synthetic rings
            ring_key = random.choice(list(self.rings.keys()))
            ring_info = self.rings[ring_key]
            customer_id = random.choice(ring_info["members"])
            device_id = ring_info["shared_device"]
            ip_hash = ring_info["shared_ip"]
            card_fp = ring_info["shared_card"] if random.random() < 0.6 else f"card_fp_{customer_id}"
            geo = random.choice(["SG", "AE", "US", "IN"])
            amount = round(avg_ticket * random.uniform(5.0, 15.0), 2)
            is_fraud = True
            ring_id = ring_key

        else:  # AMBIGUOUS (e.g. legitimate shared family device or legitimate travel)
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_shared_family_{random.randint(1, 3)}"  # 2-3 customers share this legitimately
            ip_hash = "ip_hash_family_home"
            card_fp = f"card_fp_fam_{customer_id}"
            geo = "US"  # Travel geo deviation
            amount = round(avg_ticket * random.uniform(2.0, 3.5), 2)
            is_fraud = False
            ring_id = None


        home_country = self.pool.customer_home_country.get(customer_id, "IN")

        return {
            "transaction_id": txn_id,
            "timestamp": timestamp.isoformat(),
            "amount": amount,
            "currency": "INR",
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "device_id": device_id,
            "ip_address_hash": ip_hash,
            "card_fingerprint": card_fp,
            "geo_country": geo,
            "customer_home_country": home_country,
            "label_is_fraud": is_fraud,
            "label_ring_id": ring_id,
            "is_holdout": is_holdout
        }

    def generate_batch(
        self,
        count: int = 1000,
        start_time: Optional[datetime] = None,
        holdout_ratio: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Generate a sequential batch of transactions across time."""
        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(hours=6)

        events = []
        train_count = int(count * (1.0 - holdout_ratio))
        curr_time = start_time

        for i in range(1, count + 1):
            curr_time += timedelta(seconds=random.randint(2, 15))
            is_holdout = i > train_count
            event = self.generate_event(i, curr_time, is_holdout=is_holdout)
            events.append(event)

        return events

if __name__ == "__main__":
    gen = TransactionGenerator(seed=42)
    sample_batch = gen.generate_batch(count=10)
    print(f"Generated {len(sample_batch)} sample transactions.")
    print("Sample event:", sample_batch[0])
