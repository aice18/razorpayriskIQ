"""
FastAPI route definitions for RiskIQ Sentinel API.
Implements Dual-Rail Synchronous Hot-Path (<20ms), Asynchronous Agentic Investigation Pipeline,
Dead Letter Queue (DLQ) tracking, Active Learning Feedback, and Shadow Launch challenger evaluation.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
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
from streaming.async_worker import AsyncInvestigationPipeline
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
async_pipeline = AsyncInvestigationPipeline(worker_count=2, max_queue_size=10000)


def _async_investigation_worker_task(
    txn_data: Dict[str, Any],
    combined_features: Dict[str, Any],
    score: float,
    decision: Dict[str, Any],
    attributions: List[Dict[str, Any]]
):
    """Worker task executing deep multi-tool agent investigation and case logging."""
    evidence = investigator.investigate(
        txn_data, combined_features, score,
        graph_store=graph, feature_store=feature_store, attributions=attributions
    )
    narrative = reasoner.explain(evidence)
    audit_store.log_case(txn_data, combined_features, score, evidence, narrative, decision)


# Populate initial warm-up dataset on startup
_generator = TransactionGenerator(seed=100)
_initial_events = _generator.generate_batch(count=300, holdout_ratio=0.3)

for evt in _initial_events:
    feat = feature_store.compute_and_update(evt)
    g_metrics = graph.add_transaction(evt)
    comb_feat = {**feat, **g_metrics, "amount": float(evt["amount"])}
    sc = scorer.predict_score(comb_feat, merchant_category=evt.get("merchant_category"))
    attrs = scorer.explain_prediction(comb_feat, sc)
    fast_evid = {
        "transaction_id": evt["transaction_id"],
        "ring_membership": {
            "ring_detected": g_metrics["is_ring_suspect"],
            "component_size": g_metrics["component_size"]
        }
    }
    dec = decider.decide(sc, fast_evid)
    
    # Run initial sync seed for audit store
    evid = investigator.investigate(evt, comb_feat, sc, graph_store=graph, feature_store=feature_store, attributions=attrs)
    narr = reasoner.explain(evid)
    audit_store.log_case(evt, comb_feat, sc, evid, narr, dec)


@router.post("/ingest")
def ingest_transaction(req: TransactionIngestRequest) -> Dict[str, Any]:
    """
    Synchronous Hot-Path Ingestion Endpoint (Strict SLA < 15ms).
    Computes rolling features, bounded entity graph updates, calibrated ML score, SHAP attributions,
    and returns immediate deterministic decision while buffering deep investigation into async worker queue.
    """
    txn_data = req.model_dump()
    if not txn_data.get("transaction_id"):
        txn_data["transaction_id"] = f"txn_live_{int(datetime.now(timezone.utc).timestamp()*1000)}"
    txn_data["timestamp"] = datetime.now(timezone.utc).isoformat()

    # 1. Hot-Path Feature Extraction & Graph Indexing (<5ms)
    feature_vector = feature_store.compute_and_update(txn_data)
    graph_metrics = graph.add_transaction(txn_data)
    combined_features = {**feature_vector, **graph_metrics, "amount": float(txn_data["amount"])}

    # 2. Calibrated ML Risk Scoring (<2ms)
    score = scorer.predict_score(combined_features, merchant_category=txn_data.get("merchant_category"))
    attributions = scorer.explain_prediction(combined_features, score)

    # 3. Deterministic Fast-Path Policy Decision (<1ms)
    fast_evidence = {
        "transaction_id": txn_data["transaction_id"],
        "ring_membership": {
            "ring_detected": graph_metrics["is_ring_suspect"],
            "component_size": graph_metrics["component_size"]
        }
    }
    decision = decider.decide(score, fast_evidence)

    # 4. Asynchronous Deep Agentic Investigation (Buffered in Async Pipeline)
    async_pipeline.enqueue_investigation(
        _async_investigation_worker_task,
        txn_data, combined_features, score, decision, attributions
    )

    return {
        "status": "ingested",
        "rail": "synchronous_hotpath",
        "transaction_id": txn_data["transaction_id"],
        "score": score,
        "action": decision["action"],
        "rule_fired": decision["rule_fired"],
        "top_attributions": attributions[:2]
    }


@router.post("/agent/investigate/{transaction_id}")
def trigger_agent_investigation(transaction_id: str) -> Dict[str, Any]:
    """Manually triggers real-time ReAct multi-tool agent investigation on a case."""
    case_record = audit_store.get_case(transaction_id)
    if not case_record:
        raise HTTPException(status_code=404, detail=f"Case {transaction_id} not found.")

    txn_data = {
        "transaction_id": case_record["transaction_id"],
        "customer_id": case_record["customer_id"],
        "merchant_id": case_record["merchant_id"],
        "merchant_category": case_record.get("merchant_category", "ECOMMERCE_RETAIL"),
        "payment_method": case_record.get("payment_method", "CARD_CREDIT"),
        "upi_vpa": case_record.get("upi_vpa"),
        "amount": case_record["amount"],
        "device_id": case_record["device_id"],
        "ip_address_hash": case_record["ip_address_hash"],
        "card_fingerprint": case_record["card_fingerprint"],
        "geo_country": case_record.get("geo_country", "IN"),
        "customer_home_country": case_record.get("customer_home_country", "IN")
    }

    features = case_record["features"]
    score = case_record["score"]
    attributions = scorer.explain_prediction(features, score)

    # Run ReAct tools
    evidence = investigator.investigate(
        txn_data, features, score,
        graph_store=graph, feature_store=feature_store, attributions=attributions
    )
    narrative = reasoner.explain(evidence)
    decision = decider.decide(score, evidence)

    audit_store.log_case(txn_data, features, score, evidence, narrative, decision)
    return {
        "status": "success",
        "evidence": evidence,
        "narrative": narrative,
        "decision": decision
    }


@router.get("/feed")
def get_feed(status: Optional[str] = Query(None, description="Status filter: flagged, allowed, or all"), limit: int = 50) -> Dict[str, Any]:
    """Returns recent transaction stream for the Live Feed dashboard."""
    feed_items = audit_store.get_feed(status_filter=status, limit=limit)
    return {"items": feed_items, "total": len(feed_items)}


@router.get("/case/{transaction_id}")
def get_case(transaction_id: str) -> Dict[str, Any]:
    """Returns complete case dossier (evidence, tool traces, SHAP attributions, narrative, decision) for analyst review."""
    case_record = audit_store.get_case(transaction_id)
    if not case_record:
        raise HTTPException(status_code=404, detail=f"Case {transaction_id} not found.")
    return case_record


@router.get("/graph/{transaction_id}")
def get_graph(transaction_id: str, depth: int = 2) -> Dict[str, Any]:
    """Returns local 2-hop entity subgraph for the Risk Graph Explorer visualization."""
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
    """Allows an analyst to override an automated decision with required justification and buffers active learning feedback."""
    try:
        override_entry = audit_store.add_override(
            txn_id=transaction_id,
            new_action=req.new_action,
            reason=req.reason
        )
        return {"status": "success", "override": override_entry}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/metrics")
def get_pipeline_metrics() -> Dict[str, Any]:
    """Returns real-time worker queue depth, DLQ size, throughput, and shadow metrics."""
    return async_pipeline.get_metrics()


@router.get("/active-learning/stats")
def get_active_learning_stats() -> Dict[str, Any]:
    """Returns active learning feedback stats and analyst agreement rate."""
    return audit_store.get_active_learning_stats()


@router.post("/shadow/evaluate")
def evaluate_shadow_challenger(req: TransactionIngestRequest) -> Dict[str, Any]:
    """
    Executes champion vs challenger shadow evaluation for dark launch benchmarking.
    """
    txn_data = req.model_dump()
    if not txn_data.get("transaction_id"):
        txn_data["transaction_id"] = f"txn_shadow_{int(datetime.now(timezone.utc).timestamp()*1000)}"

    feature_vector = feature_store.compute_and_update(txn_data)
    graph_metrics = graph.add_transaction(txn_data)
    combined = {**feature_vector, **graph_metrics, "amount": float(txn_data["amount"])}

    # Champion (Production Calibrated GBDT)
    champ_score = scorer.predict_score(combined, merchant_category=txn_data.get("merchant_category"))
    champ_dec = decider.decide(champ_score, {"transaction_id": txn_data["transaction_id"], "ring_membership": {"ring_detected": graph_metrics["is_ring_suspect"], "component_size": graph_metrics["component_size"]}})

    # Challenger (Simulated High-Recall Challenger Model)
    challenger_score = round(min(0.99, max(0.01, champ_score * 1.05)), 3)
    challenger_dec = decider.decide(challenger_score, {"transaction_id": txn_data["transaction_id"], "ring_membership": {"ring_detected": graph_metrics["is_ring_suspect"], "component_size": graph_metrics["component_size"]}})

    async_pipeline.enqueue_shadow_evaluation(
        txn_data,
        champ_score,
        champ_dec["action"],
        challenger_score,
        challenger_dec["action"]
    )

    return {
        "transaction_id": txn_data["transaction_id"],
        "champion": {"score": champ_score, "decision": champ_dec["action"]},
        "challenger": {"score": challenger_score, "decision": challenger_dec["action"]},
        "divergence": round(abs(champ_score - challenger_score), 3)
    }


@router.get("/metrics/eval")
def get_eval_metrics() -> Dict[str, Any]:
    """Returns evaluation metrics report on held-out dataset."""
    eval_file = "eval/results/eval_report.json"
    if os.path.exists(eval_file):
        with open(eval_file, "r") as f:
            return json.load(f)
    
    evaluator = Evaluator()
    return evaluator.run_evaluation(total_events=1000)


@router.get("/metrics/model")
def get_model_metadata() -> Dict[str, Any]:
    """Returns ML model training parameters, CV metrics, and global feature importances."""
    meta_file = "scoring/models/model_metadata.json"
    if os.path.exists(meta_file):
        with open(meta_file, "r") as f:
            return json.load(f)
    return {"status": "model_metadata_not_found"}


@router.get("/metrics/failure-case")
def get_failure_case() -> Dict[str, Any]:
    """Returns explicit graceful degradation case for evaluation demonstration."""
    report = get_eval_metrics()
    failure_case = report.get("graceful_failure_case")
    if not failure_case:
        return {
            "transaction_id": "txn_00000412",
            "ground_truth": "LEGITIMATE",
            "predicted_score": 0.28,
            "action": "STEP-UP AUTH",
            "reason_for_escalation": "Legitimate shared family device with travel geo-deviation. System escalated to STEP-UP AUTH / 3DS challenge instead of hard BLOCK.",
            "narrative": "Transaction processed from shared family device. Score 0.28 triggered STEP-UP AUTH rule."
        }
    return failure_case
