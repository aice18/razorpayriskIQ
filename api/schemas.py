"""
Pydantic data schemas for RiskIQ Sentinel REST API.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class TransactionIngestRequest(BaseModel):
    transaction_id: Optional[str] = None
    amount: float
    currency: str = "INR"
    customer_id: str
    merchant_id: str
    merchant_category: Optional[str] = "ECOMMERCE_RETAIL"
    payment_method: Optional[str] = "CARD_CREDIT"
    auth_mode: Optional[str] = "3DS_AUTHENTICATED"
    is_cross_border: Optional[bool] = False
    locality: Optional[str] = "IN-BLR-Koramangala"
    delivery_days_est: Optional[float] = 3.0
    chargeback_risk_type: Optional[str] = "NONE"
    upi_vpa: Optional[str] = None
    vpa_handle_risk: Optional[float] = 0.0
    is_qr_intent: Optional[bool] = False
    device_sim_bound: Optional[bool] = True
    device_id: str
    ip_address_hash: str
    card_fingerprint: str
    geo_country: str = "IN"
    customer_home_country: str = "IN"
    idempotency_key: Optional[str] = None

    model_config = {"extra": "allow"}

class QuarantineRequest(BaseModel):
    node_id: str = Field(..., description="Entity ID to seed quarantine (customer, device, card, ip, or locality)")
    reason: str = Field("MANUAL_ANALYST_QUARANTINE", description="Investigation rationale for quarantine")
    max_hops: int = Field(2, description="Bounded graph traversal radius (1 or 2 hops)")

class OverrideRequest(BaseModel):
    new_action: str = Field(..., description="Action to set: ALLOW, STEP-UP AUTH, REVIEW, BLOCK")
    reason: str = Field(..., description="Mandatory analyst rationale for override")

class FeedItem(BaseModel):
    transaction_id: str
    timestamp: str
    amount: float
    currency: Optional[str] = "INR"
    customer_id: str
    payment_method: Optional[str] = "CARD_CREDIT"
    auth_mode: Optional[str] = "3DS_AUTHENTICATED"
    is_cross_border: Optional[bool] = False
    locality: Optional[str] = "IN-BLR-Koramangala"
    score: float
    status: str
    action: str
    is_overridden: bool = False
    is_preemptively_quarantined: Optional[bool] = False
    headline: Optional[str] = None

class FeedResponse(BaseModel):
    items: List[FeedItem]
    total: int

class OverrideResponse(BaseModel):
    status: str = "success"
    override: Dict[str, Any]
