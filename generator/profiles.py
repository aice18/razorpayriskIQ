"""
Profile definitions and Indian payment ecosystem constants for RiskIQ Sentinel.
"""

from typing import Dict, List, Any
import random
import hashlib

PAYMENT_METHODS = ["UPI_VPA", "UPI_INTENT", "CARD_CREDIT", "CARD_DEBIT", "NETBANKING"]
UPI_HANDLES = ["@okhdfcbank", "@oksbi", "@okicici", "@okaxis", "@paytm", "@ybl", "@ibl"]
DISPOSABLE_UPI_HANDLES = ["@tempupi", "@freecharge_bot", "@disposable_pay", "@burner_vpa"]

MERCHANT_CATEGORIES = {
    "merch_gaming_01": "GAMING_CRYPTO",
    "merch_crypto_02": "GAMING_CRYPTO",
    "merch_luxury_03": "LUXURY_JEWELRY",
    "merch_ecom_04": "ECOMMERCE_RETAIL",
    "merch_ecom_05": "ECOMMERCE_RETAIL",
    "merch_grocery_06": "FOOD_GROCERY",
    "merch_food_07": "FOOD_GROCERY",
    "merch_utility_08": "UTILITY_BILLPAY",
    "merch_utility_09": "UTILITY_BILLPAY"
}


class EntityPool:
    """Pool of synthetic entity IDs and behavioral baseline profiles."""
    
    def __init__(self, num_customers: int = 500, num_devices: int = 400, num_ips: int = 300):
        self.customers = [f"cust_{i:04d}" for i in range(1, num_customers + 1)]
        self.merchants = list(MERCHANT_CATEGORIES.keys())
        self.devices = [f"dev_{hashlib.md5(str(i).encode()).hexdigest()[:8]}" for i in range(1, num_customers * 3)]
        self.ips = [f"ip_hash_{hashlib.md5(f'10.0.{i//250}.{i%250}'.encode()).hexdigest()[:8]}" for i in range(1, num_customers * 3)]
        self.cards = [f"card_fp_{hashlib.md5(f'411111{i:06d}'.encode()).hexdigest()[:8]}" for i in range(1, num_customers * 3)]

        self.customer_home_country: Dict[str, str] = {
            c: "IN" if random.random() < 0.92 else random.choice(["US", "SG", "AE", "GB"])
            for c in self.customers
        }
        
        self.customer_primary_device: Dict[str, str] = {
            c: random.choice(self.devices) for c in self.customers
        }

        self.customer_upi_handle: Dict[str, str] = {
            c: f"{c}{random.choice(UPI_HANDLES)}" for c in self.customers
        }
        
        self.merchant_avg_ticket: Dict[str, float] = {
            "merch_gaming_01": 2500.0,
            "merch_crypto_02": 15000.0,
            "merch_luxury_03": 45000.0,
            "merch_ecom_04": 2200.0,
            "merch_ecom_05": 1400.0,
            "merch_grocery_06": 650.0,
            "merch_food_07": 380.0,
            "merch_utility_08": 1800.0,
            "merch_utility_09": 950.0
        }

    def get_random_customer(self) -> str:
        return random.choice(self.customers)

    def get_random_merchant(self) -> str:
        return random.choice(self.merchants)
