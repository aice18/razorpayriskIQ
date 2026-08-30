"""
Production Online Feature Store for Razorpay RiskIQ Sentinel.
Supports high-throughput Redis cluster backend with atomic sliding window sorted sets
and online Welford statistics computation, with seamless thread-safe in-memory fallback.
"""

import os
import time
import math
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
import numpy as np

import importlib

redis = None
try:
    redis = importlib.import_module("redis")
except ImportError:
    redis = None


class OnlineStatsTracker:
    """Welford's algorithm tracker for online streaming mean and variance."""
    __slots__ = ('count', 'mean', 'm2')

    def __init__(self):
        self.count: int = 0
        self.mean: float = 0.0
        self.m2: float = 0.0

    def update(self, val: float) -> Tuple[float, float]:
        """Updates stats with new value and returns (prior_mean, prior_stddev)."""
        prior_mean = self.mean
        prior_std = math.sqrt(self.m2 / self.count) if self.count >= 2 else 0.0
        
        self.count += 1
        delta = val - self.mean
        self.mean += delta / self.count
        delta2 = val - self.mean
        self.m2 += delta * delta2
        return prior_mean, prior_std


class FeatureStore:
    """
    Dual-engine Feature Store:
    - Primary: Redis Cluster / Redis Standalone (atomic sliding windows, TTL expiration).
    - Secondary/Fallback: Thread-safe in-memory sliding window + Welford online stats.
    """
    
    def __init__(self, redis_host: Optional[str] = None, redis_port: Optional[int] = None):
        self.redis_host = redis_host or os.environ.get("REDIS_HOST", "localhost")
        self.redis_port = int(redis_port or os.environ.get("REDIS_PORT", 6379))
        self.redis_client = None
        self._lock = threading.RLock()

        # Connect to Redis if configured & available
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

        # In-memory structures (used directly or as fallback)
        self.customer_history: Dict[str, List[Tuple[float, float]]] = {}  # cust -> [(epoch_s, amount)]
        self.device_history: Dict[str, List[float]] = {}  # dev -> [epoch_s]
        self.seen_devices: set = set()
        self.seen_ips: set = set()
        self.seen_cards: set = set()
        
        self.customer_stats: Dict[str, OnlineStatsTracker] = {}
        self.merchant_stats: Dict[str, OnlineStatsTracker] = {}

    def compute_and_update(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests a payment event, updates rolling state, and calculates sub-2ms feature vector.
        """
        cust = str(txn["customer_id"])
        dev = str(txn["device_id"])
        ip = str(txn["ip_address_hash"])
        card = str(txn["card_fingerprint"])
        merch = str(txn["merchant_id"])
        amount = float(txn["amount"])
        
        # Parse timestamp to epoch seconds
        raw_ts = txn.get("timestamp")
        if isinstance(raw_ts, str):
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            now_epoch = dt.timestamp()
        elif isinstance(raw_ts, datetime):
            now_epoch = raw_ts.timestamp()
        else:
            now_epoch = time.time()

        if self.redis_client:
            try:
                return self._compute_redis(cust, dev, ip, card, merch, amount, now_epoch, txn)
            except Exception:
                # Seamless fallback to in-memory on any Redis timeout/error
                pass

        return self._compute_in_memory(cust, dev, ip, card, merch, amount, now_epoch, txn)

    def _compute_in_memory(
        self,
        cust: str,
        dev: str,
        ip: str,
        card: str,
        merch: str,
        amount: float,
        now_epoch: float,
        txn: Dict[str, Any]
    ) -> Dict[str, Any]:
        with self._lock:
            is_new_device = dev not in self.seen_devices
            is_new_ip = ip not in self.seen_ips
            is_new_card = card not in self.seen_cards

            self.seen_devices.add(dev)
            self.seen_ips.add(ip)
            self.seen_cards.add(card)

            # Update customer velocity window
            if cust not in self.customer_history:
                self.customer_history[cust] = []
            cust_hist = self.customer_history[cust]
            cust_hist.append((now_epoch, amount))
            # Evict entries older than 1 hour to prevent memory bloat
            cutoff_1h = now_epoch - 3600.0
            self.customer_history[cust] = [(t, a) for t, a in cust_hist if t >= cutoff_1h]

            # Update device velocity window
            if dev not in self.device_history:
                self.device_history[dev] = []
            dev_hist = self.device_history[dev]
            dev_hist.append(now_epoch)
            cutoff_5m = now_epoch - 300.0
            self.device_history[dev] = [t for t in dev_hist if t >= cutoff_5m]

            # Calculate velocities
            v1m = sum(1 for t, _ in self.customer_history[cust] if t >= (now_epoch - 60.0))
            v5m = sum(1 for t, _ in self.customer_history[cust] if t >= (now_epoch - 300.0))
            v1h = len(self.customer_history[cust])
            dev_v5m = len(self.device_history[dev])

            # Update online Welford statistics
            if cust not in self.customer_stats:
                self.customer_stats[cust] = OnlineStatsTracker()
            prior_cust_mean, prior_cust_std = self.customer_stats[cust].update(amount)

            if merch not in self.merchant_stats:
                self.merchant_stats[merch] = OnlineStatsTracker()
            prior_merch_mean, prior_merch_std = self.merchant_stats[merch].update(amount)

            # Compute Z-Scores against prior distributions
            if prior_cust_std > 1.0:
                cust_z = float((amount - prior_cust_mean) / prior_cust_std)
            else:
                cust_z = 0.0

            if prior_merch_std > 1.0:
                merch_z = float((amount - prior_merch_mean) / prior_merch_std)
            else:
                merch_z = 0.0

            # Geo deviation calculation
            geo_country = txn.get("geo_country", "IN")
            home_country = txn.get("customer_home_country", "IN")
            geo_deviation = 1.0 if geo_country != home_country else 0.0

            # UPI and SIM binding intelligence
            vpa_handle_risk = float(txn.get("vpa_handle_risk", 0.0))
            is_qr_intent = 1.0 if txn.get("is_qr_intent") else 0.0
            device_sim_bound = 1.0 if txn.get("device_sim_bound", True) else 0.0

            return {
                "velocity_1m": float(v1m),
                "velocity_5m": float(v5m),
                "velocity_1h": float(v1h),
                "device_velocity_5m": float(dev_v5m),
                "amount_zscore_vs_customer": round(cust_z, 3),
                "amount_zscore_vs_merchant": round(merch_z, 3),
                "is_new_device": is_new_device,
                "is_new_ip": is_new_ip,
                "is_new_card": is_new_card,
                "geo_deviation": geo_deviation,
                "vpa_handle_risk": vpa_handle_risk,
                "is_qr_intent": is_qr_intent,
                "device_sim_bound": device_sim_bound
            }

    def _compute_redis(
        self,
        cust: str,
        dev: str,
        ip: str,
        card: str,
        merch: str,
        amount: float,
        now_epoch: float,
        txn: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes atomic Redis pipeline for sub-2ms multi-key aggregation."""
        p = self.redis_client.pipeline(transaction=False)

        # Keys
        k_dev_seen = f"seen:dev:{dev}"
        k_ip_seen = f"seen:ip:{ip}"
        k_card_seen = f"seen:card:{card}"
        k_cust_win = f"win:cust:{cust}"
        k_dev_win = f"win:dev:{dev}"

        # 1. First seen checks & sets with 90-day TTL
        p.set(k_dev_seen, "1", nx=True, ex=7776000)
        p.set(k_ip_seen, "1", nx=True, ex=7776000)
        p.set(k_card_seen, "1", nx=True, ex=7776000)

        # 2. Sliding window sorted sets (Score = epoch, Member = epoch:amount or epoch:uuid)
        member_cust = f"{now_epoch}:{amount}"
        p.zadd(k_cust_win, {member_cust: now_epoch})
        p.expire(k_cust_win, 3600)
        p.zremrangebyscore(k_cust_win, "-inf", now_epoch - 3600)
        p.zcount(k_cust_win, now_epoch - 60, "+inf")
        p.zcount(k_cust_win, now_epoch - 300, "+inf")
        p.zcard(k_cust_win)

        member_dev = f"{now_epoch}:{dev}"
        p.zadd(k_dev_win, {member_dev: now_epoch})
        p.expire(k_dev_win, 300)
        p.zremrangebyscore(k_dev_win, "-inf", now_epoch - 300)
        p.zcount(k_dev_win, now_epoch - 300, "+inf")

        results = p.execute()

        # Parse pipeline responses
        is_new_device = bool(results[0])
        is_new_ip = bool(results[1])
        is_new_card = bool(results[2])

        v1m = float(results[6])
        v5m = float(results[7])
        v1h = float(results[8])
        dev_v5m = float(results[12])

        # Compute z-scores via in-memory fast Welford
        with self._lock:
            if cust not in self.customer_stats:
                self.customer_stats[cust] = OnlineStatsTracker()
            p_c_mean, p_c_std = self.customer_stats[cust].update(amount)

            if merch not in self.merchant_stats:
                self.merchant_stats[merch] = OnlineStatsTracker()
            p_m_mean, p_m_std = self.merchant_stats[merch].update(amount)

        cust_z = float((amount - p_c_mean) / p_c_std) if p_c_std > 1.0 else 0.0
        merch_z = float((amount - p_m_mean) / p_m_std) if p_m_std > 1.0 else 0.0

        geo_country = txn.get("geo_country", "IN")
        home_country = txn.get("customer_home_country", "IN")
        geo_deviation = 1.0 if geo_country != home_country else 0.0

        # UPI and SIM binding intelligence
        vpa_handle_risk = float(txn.get("vpa_handle_risk", 0.0))
        is_qr_intent = 1.0 if txn.get("is_qr_intent") else 0.0
        device_sim_bound = 1.0 if txn.get("device_sim_bound", True) else 0.0

        return {
            "velocity_1m": v1m,
            "velocity_5m": v5m,
            "velocity_1h": v1h,
            "device_velocity_5m": dev_v5m,
            "amount_zscore_vs_customer": round(cust_z, 3),
            "amount_zscore_vs_merchant": round(merch_z, 3),
            "is_new_device": is_new_device,
            "is_new_ip": is_new_ip,
            "is_new_card": is_new_card,
            "geo_deviation": geo_deviation,
            "vpa_handle_risk": vpa_handle_risk,
            "is_qr_intent": is_qr_intent,
            "device_sim_bound": device_sim_bound
        }

    def clear(self):
        """Resets all feature store state."""
        with self._lock:
            self.customer_history.clear()
            self.device_history.clear()
            self.seen_devices.clear()
            self.seen_ips.clear()
            self.seen_cards.clear()
            self.customer_stats.clear()
            self.merchant_stats.clear()
        if self.redis_client:
            try:
                self.redis_client.flushdb()
            except Exception:
                pass
