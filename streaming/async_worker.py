"""
Resilient Asynchronous Worker & Queue Pipeline for Razorpay RiskIQ Sentinel.
Provides bounded concurrent task buffering, worker threadpool execution,
exponential backoff retries, Dead Letter Queue (DLQ), and Shadow Mode comparator.
"""

import time
import queue
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone

logger = logging.getLogger("RiskIQ.AsyncWorker")


class AsyncInvestigationPipeline:
    """
    Production Asynchronous Worker Pipeline:
    - Bounded in-memory concurrent queue (decoupled from HTTP request cycle)
    - Background worker threadpool with retry backoff
    - Dead Letter Queue (DLQ) for unrecoverable errors
    - Shadow Mode Challenger evaluation
    """
    
    def __init__(
        self,
        worker_count: int = 2,
        max_queue_size: int = 10000,
        max_retries: int = 3,
        backoff_factor: float = 0.5
    ):
        self.max_queue_size = max_queue_size
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.task_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self.dlq: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        
        self.processed_count: int = 0
        self.failed_count: int = 0
        self.total_latency_ms: float = 0.0
        
        # Shadow launch stats
        self.shadow_comparisons: List[Dict[str, Any]] = []
        
        self._running = True
        self.workers: List[threading.Thread] = []
        
        for i in range(worker_count):
            t = threading.Thread(target=self._worker_loop, name=f"RiskIQ-Worker-{i+1}", daemon=True)
            t.start()
            self.workers.append(t)

    def enqueue_investigation(
        self,
        handler: Callable[..., Any],
        *args,
        priority: int = 0,
        **kwargs
    ) -> bool:
        """Enqueues an investigation task to the bounded worker queue."""
        if not self._running:
            return False

        task = {
            "handler": handler,
            "args": args,
            "kwargs": kwargs,
            "enqueued_at": time.time(),
            "retries": 0,
            "priority": priority
        }

        try:
            self.task_queue.put_nowait(task)
            return True
        except queue.Full:
            # DLQ overflow protection
            with self._lock:
                self.dlq.append({
                    "task": "investigation",
                    "error": "QUEUE_OVERFLOW_SHED_LOAD",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            return False

    def enqueue_shadow_evaluation(
        self,
        txn_data: Dict[str, Any],
        champion_score: float,
        champion_decision: str,
        challenger_score: float,
        challenger_decision: str
    ):
        """Records shadow-mode challenger evaluation alongside live champion decision."""
        with self._lock:
            divergence = abs(champion_score - challenger_score)
            self.shadow_comparisons.append({
                "transaction_id": txn_data.get("transaction_id"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "champion_score": champion_score,
                "champion_decision": champion_decision,
                "challenger_score": challenger_score,
                "challenger_decision": challenger_decision,
                "score_divergence": round(divergence, 3),
                "decision_match": (champion_decision == challenger_decision)
            })
            if len(self.shadow_comparisons) > 500:
                self.shadow_comparisons.pop(0)

    def _worker_loop(self):
        """Worker thread loop processing queued investigation jobs."""
        while self._running:
            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            start_t = time.time()
            handler = task["handler"]
            args = task["args"]
            kwargs = task["kwargs"]

            success = False
            while task["retries"] <= self.max_retries and not success:
                try:
                    handler(*args, **kwargs)
                    success = True
                    duration_ms = (time.time() - start_t) * 1000.0
                    with self._lock:
                        self.processed_count += 1
                        self.total_latency_ms += duration_ms
                except Exception as e:
                    task["retries"] += 1
                    if task["retries"] <= self.max_retries:
                        time.sleep(self.backoff_factor * (2 ** (task["retries"] - 1)))
                    else:
                        with self._lock:
                            self.failed_count += 1
                            self.dlq.append({
                                "error": str(e),
                                "retries": task["retries"],
                                "enqueued_at": task["enqueued_at"],
                                "failed_at": datetime.now(timezone.utc).isoformat()
                            })
                            if len(self.dlq) > 200:
                                self.dlq.pop(0)

            self.task_queue.task_done()

    def get_metrics(self) -> Dict[str, Any]:
        """Returns operational worker queue and pipeline metrics."""
        with self._lock:
            avg_lat = (self.total_latency_ms / self.processed_count) if self.processed_count > 0 else 0.0
            return {
                "queue_size": self.task_queue.qsize(),
                "processed_count": self.processed_count,
                "failed_count": self.failed_count,
                "dlq_size": len(self.dlq),
                "avg_processing_latency_ms": round(avg_lat, 2),
                "shadow_evaluations_count": len(self.shadow_comparisons),
                "shadow_concordance_rate": (
                    round(sum(1 for s in self.shadow_comparisons if s["decision_match"]) / len(self.shadow_comparisons), 3)
                    if self.shadow_comparisons else 1.0
                )
            }

    def shutdown(self):
        """Gracefully shuts down worker pipeline."""
        self._running = False
        for t in self.workers:
            t.join(timeout=1.0)
