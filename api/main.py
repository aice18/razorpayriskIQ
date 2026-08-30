"""
FastAPI application entry point for Razorpay RiskIQ (Sentinel).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from api.routes import router as api_router

app = FastAPI(
    title="Razorpay RiskIQ (Sentinel) API",
    description="Autonomous Abuse-Ring & Fraud-Spike AI Agent Intelligence Platform",
    version="1.0.0"
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
def root():
    return {
        "service": "Razorpay RiskIQ (Sentinel)",
        "status": "online",
        "docs": "/docs",
        "endpoints": [
            "/api/feed",
            "/api/case/{txn_id}",
            "/api/graph/{txn_id}",
            "/api/metrics/eval",
            "/api/metrics/failure-case"
        ]
    }
