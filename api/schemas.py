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
    device_id: str
    ip_address_hash: str
    card_fingerprint: str
    geo_country: str = "IN"
    customer_home_country: str = "IN"

class OverrideRequest(BaseModel):
    new_action: str = Field(..., description="Action to set: ALLOW, STEP-UP AUTH, REVIEW, BLOCK")
    reason: str = Field(..., description="Mandatory analyst rationale for override")

class FeedItem(BaseModel):
    transaction_id: str
    timestamp: str
    amount: float
    customer_id: str
    score: float
    status: str
    action: str
    is_overridden: bool = False
    headline: Optional[str] = None

class FeedResponse(BaseModel):
    items: List[FeedItem]
    total: int

class OverrideResponse(BaseModel):
    status: str = "success"
    override: Dict[str, Any]
