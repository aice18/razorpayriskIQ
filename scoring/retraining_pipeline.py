"""
Automated Active Learning Retraining Pipeline with Shadow Promotion for Razorpay RiskIQ Sentinel.
Ingests analyst-corrected feedback samples with sample weights, trains a challenger model,
evaluates Brier calibration loss & PR-AUC on held-out slices, and promotes champion models safely.
"""

import time
import os
import json
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, brier_score_loss

from scoring.train_model import FEATURE_COLUMNS, MERCHANT_CATEGORIES, generate_training_dataset


class ActiveLearningRetrainer:
    """Automated retraining orchestrator using human analyst feedback buffers."""
    
    def __init__(self, model_dir: str = "scoring/models"):
        self.model_dir = model_dir
        self.retraining_history: List[Dict[str, Any]] = []

    def retrain_with_feedback(
        self,
        feedback_samples: List[Dict[str, Any]],
        base_samples_count: int = 4000
    ) -> Dict[str, Any]:
        """
        Fits candidate challenger model on baseline stream + weighted human corrections.
        """
        if not feedback_samples:
            return {"status": "skipped", "message": "No active learning feedback samples available."}

        print(f"Triggering Active Learning Retraining ({len(feedback_samples)} analyst overrides)...")
        start_t = time.time()

        # 1. Base dataset
        X_base, y_base, cats_base = generate_training_dataset(base_samples_count)
        
        # 2. Extract feedback dataset
        feedback_rows = []
        feedback_labels = []
        feedback_weights = []
        feedback_cats = []

        for item in feedback_samples:
            feat = item["features"]
            row = {
                "amount": float(feat.get("amount", 1000.0)),
                "velocity_1m": float(feat.get("velocity_1m", 1.0)),
                "velocity_5m": float(feat.get("velocity_5m", 1.0)),
                "velocity_1h": float(feat.get("velocity_1h", 1.0)),
                "device_velocity_5m": float(feat.get("device_velocity_5m", 1.0)),
                "amount_zscore_vs_customer": float(feat.get("amount_zscore_vs_customer", 0.0)),
                "amount_zscore_vs_merchant": float(feat.get("amount_zscore_vs_merchant", 0.0)),
                "is_new_device": 1.0 if feat.get("is_new_device") else 0.0,
                "is_new_ip": 1.0 if feat.get("is_new_ip") else 0.0,
                "is_new_card": 1.0 if feat.get("is_new_card") else 0.0,
                "geo_deviation": float(feat.get("geo_deviation", 0.0)),
                "vpa_handle_risk": float(feat.get("vpa_handle_risk", 0.0)),
                "is_qr_intent": 1.0 if feat.get("is_qr_intent") else 0.0,
                "device_sim_bound": float(feat.get("device_sim_bound", 1.0)),
                "entity_degree_device": float(feat.get("entity_degree_device", 1.0)),
                "entity_degree_ip": float(feat.get("entity_degree_ip", 1.0)),
                "entity_degree_card": float(feat.get("entity_degree_card", 1.0)),
                "component_size": float(feat.get("component_size", 1.0)),
                "ring_density_score": float(feat.get("ring_density_score", 0.0)),
                "is_ring_suspect": 1.0 if feat.get("is_ring_suspect") else 0.0
            }
            feedback_rows.append(row)
            feedback_labels.append(int(item.get("analyst_label", 0)))
            feedback_weights.append(float(item.get("sample_weight", 3.0)))
            feedback_cats.append(feat.get("merchant_category", "ECOMMERCE_RETAIL"))

        df_fb = pd.DataFrame(feedback_rows)[FEATURE_COLUMNS]
        y_fb = np.array(feedback_labels)
        weights_fb = np.array(feedback_weights)

        # Concatenate with base samples (base weight = 1.0)
        X_combined = pd.concat([X_base, df_fb], ignore_index=True)
        y_combined = np.concatenate([y_base, y_fb])
        weights_combined = np.concatenate([np.ones(len(y_base)), weights_fb])
        cats_combined = cats_base + feedback_cats

        # Train Challenger Model
        challenger_model = HistGradientBoostingClassifier(
            max_iter=200,
            learning_rate=0.07,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=1.2,
            random_state=1337
        )
        challenger_model.fit(X_combined.values, y_combined, sample_weight=weights_combined)

        # Fit Category Isotonic Calibrators on combined set
        calibrators = {}
        global_iso = IsotonicRegression(out_of_bounds="clip")
        raw_probs = challenger_model.predict_proba(X_combined.values)[:, 1]
        global_iso.fit(raw_probs, y_combined, sample_weight=weights_combined)
        calibrators["GLOBAL"] = global_iso

        cat_series = pd.Series(cats_combined)
        for cat in MERCHANT_CATEGORIES:
            mask = (cat_series == cat).values
            if np.sum(mask) >= 50 and len(np.unique(y_combined[mask])) > 1:
                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(raw_probs[mask], y_combined[mask], sample_weight=weights_combined[mask])
                calibrators[cat] = iso
            else:
                calibrators[cat] = global_iso

        # Evaluate Challenger on Validation Holdout (1,000 events)
        X_val, y_val, _ = generate_training_dataset(1000)
        val_probs_raw = challenger_model.predict_proba(X_val.values)[:, 1]
        val_probs_cal = global_iso.predict(val_probs_raw)
        
        roc_val = float(roc_auc_score(y_val, val_probs_cal))
        prec, rec, _ = precision_recall_curve(y_val, val_probs_cal)
        pr_val = float(auc(rec, prec))
        brier_val = float(brier_score_loss(y_val, val_probs_cal))

        # Safe Shadow Promotion Check: PR-AUC >= 0.95
        is_promoted = pr_val >= 0.95
        duration = round(time.time() - start_t, 2)

        if is_promoted:
            os.makedirs(self.model_dir, exist_ok=True)
            joblib.dump(challenger_model, os.path.join(self.model_dir, "risk_model.joblib"))
            joblib.dump(calibrators, os.path.join(self.model_dir, "calibrators.joblib"))

        summary = {
            "status": "success",
            "analyst_samples_ingested": len(feedback_samples),
            "total_training_samples": len(y_combined),
            "challenger_validation_roc_auc": round(roc_val, 4),
            "challenger_validation_pr_auc": round(pr_val, 4),
            "challenger_brier_score": round(brier_val, 5),
            "promoted_to_champion": is_promoted,
            "training_duration_seconds": duration,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        self.retraining_history.append(summary)
        return summary
