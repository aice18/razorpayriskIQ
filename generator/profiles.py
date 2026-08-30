"""
Profile definitions for synthetic transaction stream generation.
"""

from typing import Dict, List, Any
import random
import hashlib

class EntityPool:
    """Pool of synthetic entity IDs for generating organic vs coordinated traffic."""
    
    def __init__(self, num_customers: int = 500, num_merchants: int = 20, num_devices: int = 400, num_ips: int = 300):
        self.customers = [f"cust_{i:04d}" for i in range(1, num_customers + 1)]
        self.merchants = [f"merch_{i:03d}" for i in range(1, num_merchants + 1)]
        self.devices = [f"dev_{hashlib.md5(str(i).encode()).hexdigest()[:6]}" for i in range(1, num_customers * 3)]
        self.ips = [f"ip_hash_{hashlib.md5(f'10.0.{i//250}.{i%250}'.encode()).hexdigest()[:6]}" for i in range(1, num_customers * 3)]
        self.cards = [f"card_fp_{hashlib.md5(f'411111{i:06d}'.encode()).hexdigest()[:6]}" for i in range(1, num_customers * 3)]

        
        # Pre-assign baseline customer home countries
        self.customer_home_country: Dict[str, str] = {
            c: "IN" if random.random() < 0.85 else random.choice(["US", "SG", "AE", "GB"])
            for c in self.customers
        }
        
        # Pre-assign customer primary devices
        self.customer_primary_device: Dict[str, str] = {
            c: random.choice(self.devices) for c in self.customers
        }
        
        # Pre-assign merchant average ticket sizes (in INR paise or rupees - let's use rupees integer)
        self.merchant_avg_ticket: Dict[str, float] = {
            m: random.choice([250.0, 500.0, 1200.0, 4500.0, 15000.0, 50000.0])
            for m in self.merchants
        }

    def get_random_customer(self) -> str:
        return random.choice(self.customers)

    def get_random_merchant(self) -> str:
        return random.choice(self.merchants)
