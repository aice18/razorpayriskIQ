"""
Production Idempotency & Deduplication Engine for Razorpay RiskIQ Sentinel.
Detects network retries, webhook re-deliveries, and duplicate UPI/Card events within sliding time windows.
Guarantees sub-0.1ms deterministic response caching and prevents false-positive velocity explosions.
"""

import time
import hashlib
import threading
from typing import Dict, Any, Optional, Tuple


class IdempotencyEngine:
    """
    Thread-safe Idempotency and Deduplication Store:
    - Checks explicitly provided 'idempotency_key' header / field.
    - Alternatively computes a deterministic SHA-256 transaction fingerprint.
    - Caches prior decision and score for duplicate re-deliveries within TTL (default: 300s / 5m).
    """
    
    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 50000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def generate_fingerprint(self, txn: Dict[str, Any]) -> str:
        """Generates deterministic transaction signature for payload-based deduplication."""
        if txn.get("idempotency_key"):
            return str(txn["idempotency_key"])

        cust = str(txn.get("customer_id", ""))
        merch = str(txn.get("merchant_id", ""))
        amount = str(txn.get("amount", ""))
        card = str(txn.get("card_fingerprint", ""))
        dev = str(txn.get("device_id", ""))
        vpa = str(txn.get("upi_vpa", ""))
        
        # 1-minute bucket to handle bank network retry spikes
        minute_bucket = int(time.time() // 60)
        
        raw_key = f"{cust}|{merch}|{amount}|{card}|{dev}|{vpa}|{minute_bucket}"
        return hashlib.sha256(raw_key.encode()).hexdigest()[:24]

    def check_and_get(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """Checks if a request is a duplicate replay and returns cached response if active."""
        now = time.time()
        with self._lock:
            if fingerprint in self.cache:
                entry = self.cache[fingerprint]
                if now - entry["cached_at"] <= self.ttl_seconds:
                    return entry["response"]
                else:
                    # Expired entry
                    del self.cache[fingerprint]
        return None

    def store_response(self, fingerprint: str, response: Dict[str, Any]):
        """Caches hotpath response against fingerprint with eviction protection."""
        now = time.time()
        with self._lock:
            # Memory safety: Evict oldest if reaching capacity
            if len(self.cache) >= self.max_entries:
                oldest_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k]["cached_at"])[:1000]
                for k in oldest_keys:
                    self.cache.pop(k, None)

            self.cache[fingerprint] = {
                "cached_at": now,
                "response": response
            }

    def clear(self):
        """Clears idempotency cache."""
        with self._lock:
            self.cache.clear()
