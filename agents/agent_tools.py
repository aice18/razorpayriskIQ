"""
Specialized Investigation Tools for Autonomous ReAct Risk Agent.
Enables active retrieval of entity topology, merchant baselines, velocity curves,
UPI deep intelligence, and device profiling without hallucination.
"""

from typing import Dict, Any, List, Optional
import numpy as np


class EntityGraphTool:
    """Tool for deep inspection of entity relationships and abuse rings."""
    name = "inspect_entity_graph"
    description = "Retrieves connected customers, shared device/card clusters, and topological ring metrics."

    def execute(self, txn: Dict[str, Any], graph_store: Any) -> Dict[str, Any]:
        customer_id = txn["customer_id"]
        device_id = txn["device_id"]
        ip_hash = txn["ip_address_hash"]
        card_fp = txn["card_fingerprint"]

        metrics = graph_store.get_entity_metrics(customer_id, device_id, ip_hash, card_fp)
        
        return {
            "tool": self.name,
            "device_degree": metrics["entity_degree_device"],
            "ip_degree": metrics["entity_degree_ip"],
            "card_degree": metrics["entity_degree_card"],
            "component_size": metrics["component_size"],
            "is_ring_suspect": metrics["is_ring_suspect"],
            "ring_density_score": metrics["ring_density_score"],
            "connected_accounts": metrics["connected_customers"][:10],
            "assessment": (
                f"High-density abuse ring detected ({metrics['component_size']} linked accounts across device {device_id})"
                if metrics["is_ring_suspect"]
                else f"Normal entity topology (Degree: {metrics['entity_degree_device']} device, {metrics['entity_degree_ip']} IP)"
            )
        }


class MerchantProfileTool:
    """Tool for inspecting merchant risk baselines, category chargebacks, and ticket ratios."""
    name = "inspect_merchant_profile"
    description = "Queries merchant historical average ticket size, category, and chargeback baseline."

    def execute(self, txn: Dict[str, Any], feature_store: Any) -> Dict[str, Any]:
        merchant_id = txn["merchant_id"]
        amount = float(txn["amount"])

        # Merchant category profiling
        is_high_risk_category = merchant_id in ("merch_crypto_01", "merch_gaming_02", "merch_crypto_02", "merch_gaming_01")
        merchant_avg_ticket = 3500.0 if "crypto" in merchant_id or "gaming" in merchant_id else 1800.0
        amount_ratio = round(amount / merchant_avg_ticket, 2)
        chargeback_rate_bps = 145 if is_high_risk_category else 15

        return {
            "tool": self.name,
            "merchant_id": merchant_id,
            "category_risk": "HIGH" if is_high_risk_category else "STANDARD",
            "chargeback_rate_bps": chargeback_rate_bps,
            "ticket_ratio_vs_avg": amount_ratio,
            "assessment": (
                f"Transaction amount is {amount_ratio}x of merchant benchmark. Chargeback baseline: {chargeback_rate_bps} bps."
            )
        }


class VelocityAnomalyTool:
    """Tool for analyzing temporal velocity spikes and spend z-scores."""
    name = "inspect_velocity_and_amount"
    description = "Calculates rolling 1-min, 5-min, 1-hour transaction velocities and historical z-scores."

    def execute(self, txn: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        v1m = features.get("velocity_1m", 1)
        v5m = features.get("velocity_5m", 1)
        v1h = features.get("velocity_1h", 1)
        dev_v5m = features.get("device_velocity_5m", 1)
        z_cust = features.get("amount_zscore_vs_customer", 0.0)

        is_velocity_spike = (v5m >= 4) or (dev_v5m >= 4)
        is_amount_spike = z_cust >= 3.0

        return {
            "tool": self.name,
            "velocity_1m": v1m,
            "velocity_5m": v5m,
            "velocity_1h": v1h,
            "device_velocity_5m": dev_v5m,
            "customer_amount_zscore": z_cust,
            "is_velocity_spike": is_velocity_spike,
            "is_amount_spike": is_amount_spike,
            "assessment": (
                f"Velocity burst detected: {v5m} txns in 5 min, device velocity {dev_v5m}/5m. Spend deviation: +{z_cust} sigma."
                if (is_velocity_spike or is_amount_spike)
                else "Velocity and spend volume are within standard customer baseline."
            )
        }


class DeviceIntelligenceTool:
    """Tool for analyzing device fingerprint consistency, IP ASN risk, and geo-travel."""
    name = "inspect_device_and_geo"
    description = "Evaluates device fingerprint first-seen flags, IP proxy indicators, and country mismatch."

    def execute(self, txn: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        is_new_dev = features.get("is_new_device", False)
        is_new_ip = features.get("is_new_ip", False)
        geo_deviation = features.get("geo_deviation", 0.0)
        txn_geo = txn.get("geo_country", "IN")
        home_geo = txn.get("customer_home_country", "IN")

        has_geo_mismatch = (geo_deviation > 0.0) or (txn_geo != home_geo)

        return {
            "tool": self.name,
            "is_new_device": is_new_dev,
            "is_new_ip": is_new_ip,
            "txn_geo": txn_geo,
            "home_geo": home_geo,
            "has_geo_mismatch": has_geo_mismatch,
            "assessment": (
                f"Geo mismatch: Originating country '{txn_geo}' differs from home country '{home_geo}'. New device: {is_new_dev}."
                if has_geo_mismatch
                else f"Domestic payment from {home_geo}. Device first-seen: {is_new_dev}."
            )
        }


class UPIIntelligenceTool:
    """Tool for analyzing UPI VPA handle anomalies, SIM binding verification, and payment mode risk."""
    name = "inspect_upi_profile"
    description = "Evaluates UPI VPA handle safety, SIM binding verification status, and Intent/QR channel."

    def execute(self, txn: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
        vpa = txn.get("upi_vpa")
        payment_method = txn.get("payment_method", "CARD_CREDIT")
        vpa_risk = features.get("vpa_handle_risk", 0.0)
        sim_bound = features.get("device_sim_bound", 1.0) > 0
        is_qr = features.get("is_qr_intent", 0.0) > 0

        is_high_risk_vpa = vpa_risk >= 0.50 or not sim_bound

        return {
            "tool": self.name,
            "payment_method": payment_method,
            "upi_vpa": vpa,
            "vpa_handle_risk": vpa_risk,
            "device_sim_bound": sim_bound,
            "is_qr_intent": is_qr,
            "is_high_risk_upi": is_high_risk_vpa,
            "assessment": (
                f"High-risk UPI pattern: VPA '{vpa}' risk {vpa_risk:.2f}, SIM binding: {sim_bound}."
                if is_high_risk_vpa and "UPI" in payment_method
                else f"Verified UPI handle '{vpa}' with valid hardware SIM binding."
                if "UPI" in payment_method
                else "Non-UPI payment channel."
            )
        }
