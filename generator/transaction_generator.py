"""
Synthetic Transaction Stream Generator for Razorpay RiskIQ Sentinel.
Simulates realistic Indian payment rails (UPI, RuPay/Cards, NetBanking)
with advanced attack vectors (Card Testing Bots, ATO, Synthetic ID Rings, Bust-out).
"""

import random
import time
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from generator.profiles import EntityPool, MERCHANT_CATEGORIES, PAYMENT_METHODS, DISPOSABLE_UPI_HANDLES


class TransactionGenerator:
    """Generates synthetic transaction streams with embedded payment abuse vectors."""
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.pool = EntityPool()
        self.rings: Dict[str, Dict[str, Any]] = self._generate_ring_definitions()

    def _generate_ring_definitions(self, num_rings: int = 6) -> Dict[str, Dict[str, Any]]:
        """Pre-defines coordinated fraud syndicates sharing devices, IPs, and cards."""
        rings = {}
        for i in range(1, num_rings + 1):
            ring_id = f"ring_{i:03d}"
            shared_device = random.choice(self.pool.devices)
            shared_ip = random.choice(self.pool.ips)
            shared_card = random.choice(self.pool.cards)
            member_customers = random.sample(self.pool.customers, random.randint(8, 20))
            
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
        """Generates a realistic transaction event with contextual payment features."""
        if pattern_override:
            pattern = pattern_override
        else:
            r = random.random()
            if r < 0.82:
                pattern = "NORMAL"
            elif r < 0.88:
                pattern = "CARD_TESTING_BOT"
            elif r < 0.93:
                pattern = "ACCOUNT_TAKEOVER_ATO"
            elif r < 0.97:
                pattern = "SYNTHETIC_RING"
            else:
                pattern = "AMBIGUOUS"

        txn_id = f"pay_{event_index:08d}"
        merchant_id = self.pool.get_random_merchant()
        merchant_cat = MERCHANT_CATEGORIES.get(merchant_id, "ECOMMERCE_RETAIL")
        avg_ticket = self.pool.merchant_avg_ticket[merchant_id]

        if pattern == "NORMAL":
            customer_id = self.pool.get_random_customer()
            device_id = self.pool.customer_primary_device[customer_id]
            ip_hash = f"ip_norm_{customer_id}"
            card_fp = f"card_norm_{customer_id}"
            geo = self.pool.customer_home_country[customer_id]
            payment_method = random.choices(PAYMENT_METHODS, weights=[0.45, 0.25, 0.15, 0.10, 0.05])[0]
            amount = max(15.0, round(random.gauss(avg_ticket, avg_ticket * 0.30), 2))
            is_fraud = False
            ring_id = None
            attack_vector = "ORGANIC"

        elif pattern == "CARD_TESTING_BOT":
            # High frequency micro transactions with rotating cards
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_bot_{random.randint(1, 10)}"
            ip_hash = f"ip_bot_{random.randint(1, 10)}"
            card_fp = f"card_testing_{random.randint(1000, 9999)}"
            geo = "IN"
            payment_method = "CARD_CREDIT"
            amount = round(random.uniform(2.0, 49.0), 2)  # Micro-charge card testing
            is_fraud = True
            ring_id = None
            attack_vector = "CARD_TESTING_BOT"

        elif pattern == "ACCOUNT_TAKEOVER_ATO":
            # Legitimate account accessed from foreign IP/device with massive ticket size
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_ato_{random.randint(1, 50)}"
            ip_hash = f"ip_ato_{random.randint(1, 30)}"
            card_fp = f"card_norm_{customer_id}"
            geo = random.choice(["US", "RU", "SG", "GB"])
            payment_method = random.choice(["NETBANKING", "CARD_CREDIT", "UPI_INTENT"])
            amount = round(avg_ticket * random.uniform(6.0, 15.0), 2)
            is_fraud = True
            ring_id = None
            attack_vector = "ACCOUNT_TAKEOVER_ATO"

        elif pattern == "SYNTHETIC_RING":
            ring_key = random.choice(list(self.rings.keys()))
            ring_info = self.rings[ring_key]
            customer_id = random.choice(ring_info["members"])
            device_id = ring_info["shared_device"]
            ip_hash = ring_info["shared_ip"]
            card_fp = ring_info["shared_card"] if random.random() < 0.65 else f"card_fp_{customer_id}"
            geo = random.choice(["IN", "AE", "SG"])
            payment_method = random.choice(["CARD_CREDIT", "UPI_VPA"])
            amount = round(avg_ticket * random.uniform(4.0, 12.0), 2)
            is_fraud = True
            ring_id = ring_key
            attack_vector = "SYNTHETIC_ID_RING"

        else:  # AMBIGUOUS (e.g. flash sale surge or family device sharing)
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_shared_family_{random.randint(1, 4)}"
            ip_hash = "ip_family_home"
            card_fp = f"card_norm_{customer_id}"
            geo = "IN"
            payment_method = "UPI_INTENT"
            amount = round(avg_ticket * random.uniform(2.0, 4.0), 2)
            is_fraud = False
            ring_id = None
            attack_vector = "LEGITIMATE_SPIKE"

        home_country = self.pool.customer_home_country.get(customer_id, "IN")
        
        # UPI deep profiling signals
        if "UPI" in payment_method:
            if pattern in ("CARD_TESTING_BOT", "SYNTHETIC_RING", "ACCOUNT_TAKEOVER_ATO") and random.random() < 0.6:
                upi_vpa = f"bot_{random.randint(100, 999)}{random.choice(DISPOSABLE_UPI_HANDLES)}"
                vpa_handle_risk = 0.85
                device_sim_bound = False
            else:
                upi_vpa = self.pool.customer_upi_handle.get(customer_id, f"{customer_id}@okhdfcbank")
                vpa_handle_risk = 0.05
                device_sim_bound = True
            is_qr_intent = (payment_method == "UPI_INTENT")
        else:
            upi_vpa = None
            vpa_handle_risk = 0.0
            device_sim_bound = True
            is_qr_intent = False

        return {
            "transaction_id": txn_id,
            "timestamp": timestamp.isoformat(),
            "amount": amount,
            "currency": "INR",
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "merchant_category": merchant_cat,
            "payment_method": payment_method,
            "upi_vpa": upi_vpa,
            "vpa_handle_risk": vpa_handle_risk,
            "is_qr_intent": is_qr_intent,
            "device_sim_bound": device_sim_bound,
            "device_id": device_id,
            "ip_address_hash": ip_hash,
            "card_fingerprint": card_fp,
            "geo_country": geo,
            "customer_home_country": home_country,
            "label_is_fraud": is_fraud,
            "label_ring_id": ring_id,
            "attack_vector": attack_vector,
            "is_holdout": is_holdout
        }

    def generate_batch(
        self,
        count: int = 1000,
        start_time: Optional[datetime] = None,
        holdout_ratio: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Generates a chronological stream of transactions."""
        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(hours=8)

        events = []
        train_count = int(count * (1.0 - holdout_ratio))
        curr_time = start_time

        for i in range(1, count + 1):
            curr_time += timedelta(seconds=random.randint(1, 10))
            is_holdout = i > train_count
            event = self.generate_event(i, curr_time, is_holdout=is_holdout)
            events.append(event)

        return events
