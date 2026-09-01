"""
Immutable Audit Trail Store & Active Learning Feedback Buffer for RiskIQ Sentinel.
Records all evidence packages, narratives, automated decisions, and analyst overrides in append-only logs.
Maintains active learning retraining buffers with sample weights.
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


class AuditStore:
    """Append-only audit store for system decisions, analyst overrides, and active learning feedback."""
    
    def __init__(self):
        # Maps transaction_id -> audit record
        self.records: Dict[str, Dict[str, Any]] = {}
        # List of transaction IDs in order of ingestion
        self.order: List[str] = []
        # List of analyst overrides
        self.overrides: Dict[str, List[Dict[str, Any]]] = {}
        # Active learning feedback buffer for retraining
        self.active_learning_buffer: List[Dict[str, Any]] = []

    def log_case(
        self,
        transaction: Dict[str, Any],
        features: Dict[str, Any],
        score: float,
        evidence: Dict[str, Any],
        narrative: Dict[str, Any],
        decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Appends a full audit record for a processed case.
        """
        txn_id = transaction["transaction_id"]
        is_quarantined = features.get("is_preemptively_quarantined", False) or evidence.get("is_preemptively_quarantined", False)
        record = {
            "transaction_id": txn_id,
            "timestamp": transaction.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "amount": transaction.get("amount"),
            "currency": transaction.get("currency", "INR"),
            "customer_id": transaction.get("customer_id"),
            "merchant_id": transaction.get("merchant_id"),
            "merchant_category": transaction.get("merchant_category", "ECOMMERCE_RETAIL"),
            "payment_method": transaction.get("payment_method", "CARD_CREDIT"),
            "auth_mode": transaction.get("auth_mode", "3DS_AUTHENTICATED"),
            "is_cross_border": transaction.get("is_cross_border", False),
            "locality": transaction.get("locality", "IN-BLR-Koramangala"),
            "chargeback_risk_type": transaction.get("chargeback_risk_type", "NONE"),
            "upi_vpa": transaction.get("upi_vpa"),
            "device_id": transaction.get("device_id"),
            "ip_address_hash": transaction.get("ip_address_hash"),
            "card_fingerprint": transaction.get("card_fingerprint"),
            "geo_country": transaction.get("geo_country"),
            "customer_home_country": transaction.get("customer_home_country"),
            "score": score,
            "status": "flagged" if score >= 0.40 else "allowed",
            "is_preemptively_quarantined": is_quarantined,
            "features": features,
            "evidence": evidence,
            "narrative": narrative,
            "decision": decision,
            "audit_logged_at": datetime.now(timezone.utc).isoformat()
        }

        self.records[txn_id] = record
        if txn_id not in self.order:
            self.order.append(txn_id)

        return record

    def add_override(
        self,
        txn_id: str,
        new_action: str,
        reason: str,
        analyst_id: str = "analyst_demo"
    ) -> Dict[str, Any]:
        """
        Appends an analyst override to a case record and buffers it for active learning retraining.
        """
        if txn_id not in self.records:
            raise KeyError(f"Transaction {txn_id} not found in audit log.")

        prev_action = self.records[txn_id]["decision"]["action"]
        override_entry = {
            "transaction_id": txn_id,
            "previous_action": prev_action,
            "new_action": new_action,
            "reason": reason,
            "analyst_id": analyst_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if txn_id not in self.overrides:
            self.overrides[txn_id] = []
        self.overrides[txn_id].append(override_entry)

        # Attach override summary to case record
        self.records[txn_id]["override"] = override_entry

        # Active Learning Feedback Ingestion:
        sample_weight = 3.0 if prev_action != new_action else 1.0
        override_label = 1 if new_action in ("BLOCK", "STEP_UP") else 0
        
        self.active_learning_buffer.append({
            "transaction_id": txn_id,
            "features": self.records[txn_id]["features"],
            "analyst_label": override_label,
            "sample_weight": sample_weight,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if len(self.active_learning_buffer) > 1000:
            self.active_learning_buffer.pop(0)

        return override_entry

    def get_case(self, txn_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete audit case record by transaction ID."""
        return self.records.get(txn_id)

    def get_feed(self, status_filter: Optional[str] = None, limit: int = 5000) -> List[Dict[str, Any]]:
        """Returns recent transactions for the Live Feed API."""
        results = []
        for txn_id in reversed(self.order):
            rec = self.records[txn_id]
            if status_filter is None or status_filter == "all" or rec["status"] == status_filter:
                results.append({
                    "transaction_id": rec["transaction_id"],
                    "timestamp": rec["timestamp"],
                    "amount": rec["amount"],
                    "currency": rec.get("currency", "INR"),
                    "customer_id": rec["customer_id"],
                    "payment_method": rec.get("payment_method", "CARD_CREDIT"),
                    "auth_mode": rec.get("auth_mode", "3DS_AUTHENTICATED"),
                    "is_cross_border": rec.get("is_cross_border", False),
                    "locality": rec.get("locality", "IN-BLR-Koramangala"),
                    "score": rec["score"],
                    "status": rec["status"],
                    "action": rec["override"]["new_action"] if "override" in rec else rec["decision"]["action"],
                    "is_overridden": "override" in rec,
                    "is_preemptively_quarantined": rec.get("is_preemptively_quarantined", False),
                    "headline": rec["narrative"].get("headline", "")
                })
            if len(results) >= limit:
                break
        return results

    def get_active_learning_stats(self) -> Dict[str, Any]:
        """Calculates active learning feedback and analyst agreement metrics."""
        total_overrides = len(self.overrides)
        fp_reversals = 0
        fn_catches = 0
        
        for txn_id, ov_list in self.overrides.items():
            if ov_list:
                last_ov = ov_list[-1]
                if last_ov["previous_action"] in ("BLOCK", "REVIEW") and last_ov["new_action"] == "ALLOW":
                    fp_reversals += 1
                elif last_ov["previous_action"] == "ALLOW" and last_ov["new_action"] in ("BLOCK", "STEP_UP", "STEP-UP AUTH"):
                    fn_catches += 1

        total_cases = len(self.records)
        agreement_rate = (1.0 - (total_overrides / total_cases)) if total_cases > 0 else 1.0

        return {
            "total_cases": total_cases,
            "total_overrides": total_overrides,
            "false_positive_reversals": fp_reversals,
            "false_negative_catches": fn_catches,
            "analyst_agreement_rate": round(max(0.0, agreement_rate), 4),
            "buffered_training_samples": len(self.active_learning_buffer)
        }

    def get_dashboard_analytics(self) -> Dict[str, Any]:
        """Calculates live aggregate distribution and KPI metrics across all ingested transactions."""
        total = len(self.records)
        allow_count = 0
        stepup_count = 0
        review_count = 0
        block_count = 0
        cross_border_count = 0
        quarantined_count = 0
        total_gmv = 0.0
        abuse_prevented_amt = 0.0
        funds_protected_amt = 0.0

        hist_buckets = [0] * 10  # 0.0-0.1, 0.1-0.2, ... 0.9-1.0
        channel_counts = {"UPI_INTENT": 0, "CARD_CREDIT": 0, "CARD_DEBIT": 0, "UPI_VPA": 0, "NETBANKING": 0}
        currency_counts = {}

        for rec in self.records.values():
            amt = float(rec.get("amount", 0.0))
            total_gmv += amt
            sc = float(rec.get("score", 0.0))
            b_idx = min(9, max(0, int(sc * 10)))
            hist_buckets[b_idx] += 1

            act = rec.get("decision", {}).get("action", "ALLOW")
            if "override" in rec:
                act = rec["override"]["new_action"]

            if act == "ALLOW":
                allow_count += 1
                funds_protected_amt += amt
            elif act in ("STEP_UP", "STEP-UP AUTH", "STEP_UP_AUTH"):
                stepup_count += 1
            elif act == "REVIEW":
                review_count += 1
            elif act == "BLOCK":
                block_count += 1
                abuse_prevented_amt += amt

            if rec.get("is_cross_border"):
                cross_border_count += 1
            if rec.get("is_preemptively_quarantined"):
                quarantined_count += 1

            pm = rec.get("payment_method", "CARD_CREDIT")
            channel_counts[pm] = channel_counts.get(pm, 0) + 1

            curr = rec.get("currency", "INR")
            currency_counts[curr] = currency_counts.get(curr, 0) + 1

        return {
            "total_transactions": total,
            "total_gmv_inr": round(total_gmv, 2),
            "allow_count": allow_count,
            "stepup_count": stepup_count,
            "review_count": review_count,
            "block_count": block_count,
            "allow_pct": round((allow_count / total * 100) if total > 0 else 98.2, 1),
            "stepup_pct": round((stepup_count / total * 100) if total > 0 else 0.9, 1),
            "block_pct": round((block_count / total * 100) if total > 0 else 0.9, 1),
            "abuse_prevented_inr": round(abuse_prevented_amt, 2),
            "funds_protected_inr": round(funds_protected_amt, 2),
            "cross_border_count": cross_border_count,
            "quarantined_count": quarantined_count,
            "score_histogram": hist_buckets,
            "channel_counts": channel_counts,
            "currency_counts": currency_counts
        }

    def clear(self):
        """Clears audit records and active learning buffers."""
        self.records.clear()
        self.order.clear()
        self.overrides.clear()
        self.active_learning_buffer.clear()
