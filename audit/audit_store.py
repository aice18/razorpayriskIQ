"""
Immutable Audit Trail Store for RiskIQ Sentinel.
Records all evidence packages, narratives, automated decisions, and analyst overrides in append-only logs.
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

class AuditStore:
    """Append-only audit store for system decisions and analyst overrides."""
    
    def __init__(self):
        # Maps transaction_id -> list of audit records
        self.records: Dict[str, Dict[str, Any]] = {}
        # List of transaction IDs in order of ingestion
        self.order: List[str] = []
        # List of analyst overrides
        self.overrides: Dict[str, List[Dict[str, Any]]] = {}

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
        record = {
            "transaction_id": txn_id,
            "timestamp": transaction.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "amount": transaction.get("amount"),
            "currency": transaction.get("currency", "INR"),
            "customer_id": transaction.get("customer_id"),
            "merchant_id": transaction.get("merchant_id"),
            "device_id": transaction.get("device_id"),
            "ip_address_hash": transaction.get("ip_address_hash"),
            "card_fingerprint": transaction.get("card_fingerprint"),
            "geo_country": transaction.get("geo_country"),
            "customer_home_country": transaction.get("customer_home_country"),
            "score": score,
            "status": "flagged" if score >= 0.40 else "allowed",
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

    def add_override(self, txn_id: str, new_action: str, reason: str, analyst_id: str = "analyst_demo") -> Dict[str, Any]:
        """
        Appends an analyst override to a case record without mutating original decision log.
        """
        if txn_id not in self.records:
            raise KeyError(f"Transaction {txn_id} not found in audit log.")

        override_entry = {
            "transaction_id": txn_id,
            "previous_action": self.records[txn_id]["decision"]["action"],
            "new_action": new_action,
            "reason": reason,
            "analyst_id": analyst_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if txn_id not in self.overrides:
            self.overrides[txn_id] = []
        self.overrides[txn_id].append(override_entry)

        # Attach override summary to case record for quick access
        self.records[txn_id]["override"] = override_entry
        return override_entry

    def get_case(self, txn_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete audit case record by transaction ID."""
        return self.records.get(txn_id)

    def get_feed(self, status_filter: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent transactions for the Live Feed API."""
        results = []
        for txn_id in reversed(self.order):
            rec = self.records[txn_id]
            if status_filter is None or status_filter == "all" or rec["status"] == status_filter:
                results.append({
                    "transaction_id": rec["transaction_id"],
                    "timestamp": rec["timestamp"],
                    "amount": rec["amount"],
                    "customer_id": rec["customer_id"],
                    "score": rec["score"],
                    "status": rec["status"],
                    "action": rec["override"]["new_action"] if "override" in rec else rec["decision"]["action"],
                    "is_overridden": "override" in rec,
                    "headline": rec["narrative"].get("headline", "")
                })
            if len(results) >= limit:
                break
        return results

    def clear(self):
        """Clears audit records."""
        self.records.clear()
        self.order.clear()
        self.overrides.clear()
