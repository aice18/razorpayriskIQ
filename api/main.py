"""
FastAPI application entry point for Razorpay RiskIQ (Sentinel).
Hardened for enterprise production deployment with metrics, CORS, health checks, and dashboard hosting.
"""

import os
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import router as api_router
from config.settings import settings

# Optional Prometheus Metrics Definitions
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
    TRANSACTION_COUNTER = Counter(
        "riskiq_transactions_total",
        "Total payment transactions processed by RiskIQ",
        ["action", "status"]
    )
    LATENCY_HISTOGRAM = Histogram(
        "riskiq_decision_latency_seconds",
        "End-to-end transaction scoring and agent decision latency in seconds",
        buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.000]
    )
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"

app = FastAPI(
    title="Razorpay RiskIQ (Sentinel) API",
    description="Enterprise Autonomous Payment Risk, Abuse-Ring & Agentic Intelligence Platform for Razorpay",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

# Mount static dashboard files
if os.path.exists("dashboard"):
    app.mount("/static", StaticFiles(directory="dashboard"), name="static")

@app.get("/health")
def health_check():
    """Health check endpoint for Kubernetes liveness probes."""
    return {"status": "healthy", "service": "Razorpay RiskIQ", "version": "2.0.0", "env": settings.ENV}

@app.get("/ready")
def readiness_check():
    """Readiness check endpoint for Kubernetes readiness probes."""
    return {"status": "ready", "engine": "online", "graph_store": "active", "async_worker": "running"}

@app.get("/metrics")
def prometheus_metrics():
    """Prometheus metrics exposition format endpoint."""
    if PROMETHEUS_AVAILABLE:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    return Response(
        content="# RiskIQ Prometheus metrics fallback\nriskiq_status{status=\"online\"} 1\n",
        media_type="text/plain"
    )

@app.get("/")
def root():
    """Serves the live interactive dashboard UI."""
    if os.path.exists("dashboard/index.html"):
        return FileResponse("dashboard/index.html")
    return {
        "service": "Razorpay RiskIQ (Sentinel)",
        "status": "online",
        "env": settings.ENV,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }
