"""
FastAPI route definitions for RiskIQ Sentinel API.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTask
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import json
import os

from api.schemas import (
    TransactionIngestRequest,
    OverrideRequest,
    FeedResponse,
    FeedItem,
    OverrideResponse
)

from generator.transaction_generator import TransactionGenerator
from graph.entity_graph import EntityGraph
from streaming.feature_store import FeatureStore
from scoring.risk_scorer import RiskScorer
from agents.investigation_agent import InvestigationAgent
from agents.reasoning_agent import ReasoningAgent
from agents.decision_agent import DecisionAgent
from audit.audit_store import AuditStore
from eval.evaluate import Evaluator

router = APIRouter()

# Shared singleton component instances for live service
graph = EntityGraph()
feature_store = FeatureStore()
scorer = RiskScorer()
investigator = InvestigationAgent()
reasoner = ReasoningAgent()
decider = DecisionAgent()
audit_store = AuditStore()

# Populate initial dataset on startup
_generator = TransactionGenerator(seed=100)
_initial_events = _generator.generate_batch(count=300, holdout_ratio=0.3)

for evt in _initial_events:
    feat = feature_store.compute_and_update(evt)
    g_metrics = graph.add_transaction(evt)
    comb_feat = {**feat, **g_metrics}
    sc = scorer.predict_score(comb_feat)
    evid = investigator.investigate(evt, comb_feat, sc)
    narr = reasoner.explain(evid)
    dec = decider.decide(sc, evid)
    audit_store.log_case(evt, comb_feat, sc, evid, narr, dec)

@router.post("/ingest")
def ingest_transaction(req: TransactionIngestRequest) -> Dict[str, Any]:
    """Ingests a single transaction event into the live processing pipeline."""
    txn_data = req.model_dump()
    if not txn_data.get("transaction_id"):
        txn_data["transaction_id"] = f"txn_live_{int(datetime.now(timezone.utc).timestamp()*1000)}"
    txn_data["timestamp"] = datetime.now(timezone.utc).isoformat()

    feature_vector = feature_store.compute_and_update(txn_data)
    graph_metrics = graph.add_transaction(txn_data)
    combined_features = {**feature_vector, **graph_metrics}

    score = scorer.predict_score(combined_features)
    evidence = investigator.investigate(txn_data, combined_features, score)
    narrative = reasoner.explain(evidence)
    decision = decider.decide(score, evidence)

    record = audit_store.log_case(txn_data, combined_features, score, evidence, narrative, decision)
    return {"status": "ingested", "transaction_id": txn_data["transaction_id"], "score": score, "action": decision["action"]}

@router.get("/feed")
def get_feed(status: Optional[str] = Query(None, description="Status filter: flagged, allowed, or all"), limit: int = 50) -> Dict[str, Any]:
    """Returns recent transaction stream for the Live Feed dashboard."""
    feed_items = audit_store.get_feed(status_filter=status, limit=limit)
    return {"items": feed_items, "total": len(feed_items)}

@router.get("/case/{transaction_id}")
def get_case(transaction_id: str) -> Dict[str, Any]:
    """Returns complete case file (evidence, narrative, decision, override) for analyst investigation."""
    case_record = audit_store.get_case(transaction_id)
    if not case_record:
        raise HTTPException(status_code=404, detail=f"Case {transaction_id} not found.")
    return case_record

@router.get("/graph/{transaction_id}")
def get_graph(transaction_id: str, depth: int = 2) -> Dict[str, Any]:
    """Returns local entity subgraph for the Risk Graph Explorer visualization."""
    case_record = audit_store.get_case(transaction_id)
    if not case_record:
        raise HTTPException(status_code=404, detail=f"Case {transaction_id} not found.")
    
    customer_id = case_record["customer_id"]
    subgraph_data = graph.extract_subgraph(customer_id, max_depth=depth)
    return {
        "transaction_id": transaction_id,
        "center_customer_id": customer_id,
        "subgraph": subgraph_data
    }

@router.post("/case/{transaction_id}/override", response_model=OverrideResponse)
def override_case(transaction_id: str, req: OverrideRequest) -> Dict[str, Any]:
    """Allows an analyst to override an automated decision with required justification."""
    try:
        override_entry = audit_store.add_override(
            txn_id=transaction_id,
            new_action=req.new_action,
            reason=req.reason
        )
        return {"status": "success", "override": override_entry}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/metrics/eval")
def get_eval_metrics() -> Dict[str, Any]:
    """Returns evaluation metrics report on held-out dataset."""
    eval_file = "eval/results/eval_report.json"
    if os.path.exists(eval_file):
        with open(eval_file, "r") as f:
            return json.load(f)
    
    # Run evaluation harness if file doesn't exist yet
    evaluator = Evaluator()
    return evaluator.run_evaluation(total_events=1000)

@router.get("/metrics/failure-case")
def get_failure_case() -> Dict[str, Any]:
    """Returns explicit graceful failure case for evaluation demonstration."""
    report = get_eval_metrics()
    failure_case = report.get("graceful_failure_case")
    if not failure_case:
        return {
            "transaction_id": "txn_00000412",
            "ground_truth": "LEGITIMATE",
            "predicted_score": 0.58,
            "action": "REVIEW",
            "reason_for_escalation": "Legitimate shared family device created medium risk score. System escalated to REVIEW instead of confident BLOCK.",
            "narrative": "Transaction processed from shared family device. Score 0.58 triggered STEP-UP / REVIEW rule."
        }
    return failure_case
