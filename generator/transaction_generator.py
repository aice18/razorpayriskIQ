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
        elif is_holdout:
            # Enriched fraud density for evaluation test harness
            r = random.random()
            if r < 0.72:
                pattern = "NORMAL"
            elif r < 0.78:
                pattern = "CARD_TESTING_BOT"
            elif r < 0.83:
                pattern = "ACCOUNT_TAKEOVER_ATO"
            elif r < 0.88:
                pattern = "SYNTHETIC_RING"
            elif r < 0.92:
                pattern = "CROSS_BORDER_NON_3DS_FRAUD"
            elif r < 0.96:
                pattern = "SERVICE_CHARGEBACK_FRIENDLY_FRAUD"
            elif r < 0.98:
                pattern = "LOCALITY_SUBURB_BURST"
            else:
                pattern = "AMBIGUOUS"
        else:
            # Realistic production distribution: 98.2% nominal clean traffic
            r = random.random()
            if r < 0.982:
                pattern = "NORMAL"
            elif r < 0.988:
                pattern = "CARD_TESTING_BOT"
            elif r < 0.992:
                pattern = "ACCOUNT_TAKEOVER_ATO"
            elif r < 0.995:
                pattern = "SYNTHETIC_RING"
            elif r < 0.997:
                pattern = "CROSS_BORDER_NON_3DS_FRAUD"
            elif r < 0.999:
                pattern = "SERVICE_CHARGEBACK_FRIENDLY_FRAUD"
            else:
                pattern = "LOCALITY_SUBURB_BURST"

        txn_id = f"pay_{event_index:08d}"
        merchant_id = self.pool.get_random_merchant()
        merchant_cat = MERCHANT_CATEGORIES.get(merchant_id, "ECOMMERCE_RETAIL")
        avg_ticket = self.pool.merchant_avg_ticket[merchant_id]

        # Defaults
        auth_mode = "3DS_AUTHENTICATED"
        chargeback_risk_type = "NONE"
        locality = random.choice(self.pool.customer_locality.get("cust_0001", "IN-BLR-Koramangala") if hasattr(self.pool, "customer_locality") else "IN-BLR-Koramangala")
        delivery_days_est = random.randint(2, 5)

        if pattern == "NORMAL":
            customer_id = self.pool.get_random_customer()
            device_id = self.pool.customer_primary_device[customer_id]
            ip_hash = f"ip_norm_{customer_id}"
            card_fp = f"card_norm_{customer_id}"
            geo = self.pool.customer_home_country[customer_id]
            locality = self.pool.customer_locality.get(customer_id, "IN-BLR-Koramangala")
            payment_method = random.choices(PAYMENT_METHODS, weights=[0.45, 0.25, 0.15, 0.10, 0.05])[0]
            auth_mode = "3DS_AUTHENTICATED" if geo == "IN" else random.choice(["3DS_AUTHENTICATED", "NON_3DS_FRICTIONLESS"])
            amount = max(15.0, round(random.gauss(avg_ticket, avg_ticket * 0.30), 2))
            is_fraud = False
            ring_id = None
            attack_vector = "ORGANIC"
            chargeback_risk_type = "NONE"

        elif pattern == "CROSS_BORDER_NON_3DS_FRAUD":
            # US/Global buyer checkout without 3DS - high merchant liability fraud
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_xb_{random.randint(100, 999)}"
            ip_hash = f"ip_xb_{random.randint(100, 999)}"
            card_fp = f"card_xb_stolen_{random.randint(1000, 9999)}"
            geo = random.choice(["US", "GB", "CA", "AU"])
            locality = "US-NYC-Manhattan" if geo == "US" else "GB-LON-Westminster"
            payment_method = "CARD_CREDIT"
            auth_mode = "NON_3DS_FRICTIONLESS"
            amount = round(random.uniform(180.0, 950.0), 2)  # USD/EUR cross border ticket
            is_fraud = True
            ring_id = None
            attack_vector = "CROSS_BORDER_NON_3DS_FRAUD"
            chargeback_risk_type = "FRAUD_CHARGEBACK"

        elif pattern == "SERVICE_CHARGEBACK_FRIENDLY_FRAUD":
            # 3DS passes, but buyer files "Package Not Received" or INR currency confusion chargeback
            customer_id = self.pool.get_random_customer()
            device_id = self.pool.customer_primary_device[customer_id]
            ip_hash = f"ip_friendly_{customer_id}"
            card_fp = f"card_norm_{customer_id}"
            geo = random.choice(["US", "GB", "AE", "SG"])
            locality = "US-SFO-BayArea" if geo == "US" else "AE-DXB-Downtown"
            payment_method = "CARD_CREDIT"
            auth_mode = "3DS_AUTHENTICATED"  # Passed 3DS, yet service chargeback risk is high!
            amount = round(random.uniform(350.0, 1800.0), 2)
            is_fraud = True  # Exploitative friendly fraud
            ring_id = None
            attack_vector = "SERVICE_CHARGEBACK_FRIENDLY_FRAUD"
            chargeback_risk_type = "SERVICE_CHARGEBACK"
            delivery_days_est = random.randint(18, 35)  # Transit time exceeds buyer patience

        elif pattern == "LOCALITY_SUBURB_BURST":
            # Rapid synchronized burst from a specific cell tower / geographic locality
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_loc_burst_{random.randint(1, 5)}"
            ip_hash = f"ip_subnet_burst_{random.randint(1, 3)}"
            card_fp = f"card_loc_{random.randint(1000, 9999)}"
            geo = random.choice(["IN", "NG", "US"])
            locality = "NG-LOS-Ikeja" if geo == "NG" else ("IN-MUM-Bandra" if geo == "IN" else "US-NYC-Manhattan")
            payment_method = "CARD_CREDIT" if geo != "IN" else "UPI_INTENT"
            auth_mode = "NON_3DS_FRICTIONLESS" if geo != "IN" else "3DS_AUTHENTICATED"
            amount = round(random.uniform(400.0, 2200.0), 2)
            is_fraud = True
            ring_id = "ring_locality_burst"
            attack_vector = "LOCALITY_SUBURB_BURST"
            chargeback_risk_type = "FRAUD_CHARGEBACK"

        elif pattern == "CARD_TESTING_BOT":
            # High frequency micro transactions with rotating cards
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_bot_{random.randint(1, 10)}"
            ip_hash = f"ip_bot_{random.randint(1, 10)}"
            card_fp = f"card_testing_{random.randint(1000, 9999)}"
            geo = "IN"
            locality = "IN-DEL-Connaught"
            payment_method = "CARD_CREDIT"
            auth_mode = "NON_3DS_FRICTIONLESS"
            amount = round(random.uniform(2.0, 49.0), 2)  # Micro-charge card testing
            is_fraud = True
            ring_id = None
            attack_vector = "CARD_TESTING_BOT"
            chargeback_risk_type = "FRAUD_CHARGEBACK"

        elif pattern == "ACCOUNT_TAKEOVER_ATO":
            # Legitimate account accessed from foreign IP/device with massive ticket size
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_ato_{random.randint(1, 50)}"
            ip_hash = f"ip_ato_{random.randint(1, 30)}"
            card_fp = f"card_norm_{customer_id}"
            geo = random.choice(["US", "RU", "SG", "GB"])
            locality = "SG-Marina-Downtown" if geo == "SG" else "US-NYC-Manhattan"
            payment_method = random.choice(["NETBANKING", "CARD_CREDIT", "UPI_INTENT"])
            auth_mode = "NON_3DS_FRICTIONLESS" if geo == "US" else "3DS_AUTHENTICATED"
            amount = round(avg_ticket * random.uniform(6.0, 15.0), 2)
            is_fraud = True
            ring_id = None
            attack_vector = "ACCOUNT_TAKEOVER_ATO"
            chargeback_risk_type = "FRAUD_CHARGEBACK"

        elif pattern == "SYNTHETIC_RING":
            ring_key = random.choice(list(self.rings.keys()))
            ring_info = self.rings[ring_key]
            customer_id = random.choice(ring_info["members"])
            device_id = ring_info["shared_device"]
            ip_hash = ring_info["shared_ip"]
            card_fp = ring_info["shared_card"] if random.random() < 0.65 else f"card_fp_{customer_id}"
            geo = random.choice(["IN", "AE", "SG", "US"])
            locality = "AE-DXB-Downtown" if geo == "AE" else "IN-BLR-Koramangala"
            payment_method = random.choice(["CARD_CREDIT", "UPI_VPA"])
            auth_mode = "NON_3DS_FRICTIONLESS" if geo == "US" else "3DS_AUTHENTICATED"
            amount = round(avg_ticket * random.uniform(4.0, 12.0), 2)
            is_fraud = True
            ring_id = ring_key
            attack_vector = "SYNTHETIC_ID_RING"
            chargeback_risk_type = "FRAUD_CHARGEBACK"

        else:  # AMBIGUOUS (e.g. flash sale surge or family device sharing)
            customer_id = self.pool.get_random_customer()
            device_id = f"dev_shared_family_{random.randint(1, 4)}"
            ip_hash = "ip_family_home"
            card_fp = f"card_norm_{customer_id}"
            geo = "IN"
            locality = "IN-BLR-Koramangala"
            payment_method = "UPI_INTENT"
            auth_mode = "3DS_AUTHENTICATED"
            amount = round(avg_ticket * random.uniform(2.0, 4.0), 2)
            is_fraud = False
            ring_id = None
            attack_vector = "LEGITIMATE_SPIKE"
            chargeback_risk_type = "NONE"

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

        # Multi-currency support (Razorpay Global Payments)
        geo_currency_map = {
            "IN": "INR", "US": "USD", "SG": "SGD", "GB": "GBP", "AE": "AED", "MY": "MYR", "NG": "USD", "CA": "CAD", "AU": "AUD"
        }
        currency = geo_currency_map.get(geo, "INR")
        if geo == "IN" and random.random() < 0.12:
            currency = random.choice(["USD", "EUR", "SGD", "GBP", "AED"])

        is_cross_border = (geo != "IN") or (home_country != "IN") or (currency != "INR")

        return {
            "transaction_id": txn_id,
            "timestamp": timestamp.isoformat(),
            "amount": amount,
            "currency": currency,
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "merchant_category": merchant_cat,
            "payment_method": payment_method,
            "auth_mode": auth_mode,
            "is_cross_border": is_cross_border,
            "locality": locality,
            "delivery_days_est": delivery_days_est,
            "chargeback_risk_type": chargeback_risk_type,
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
