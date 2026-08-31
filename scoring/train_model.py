"""
Production ML Model Training Pipeline for Razorpay RiskIQ Sentinel.
Trains a high-performance HistGradientBoostingClassifier on tabular, behavioral, UPI, and graph features.
Fits multi-tenant Isotonic Regression calibrators per merchant risk profile, performs 5-Fold Stratified CV,
and saves model artifacts, calibrators, and baseline feature attribution parameters.
"""

import os
import joblib
import json
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List, Any
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    roc_auc_score,
    precision_recall_curve,
    auc,
    precision_score,
    recall_score,
    f1_score,
    brier_score_loss
)
from sklearn.inspection import permutation_importance

from generator.transaction_generator import TransactionGenerator
from streaming.feature_store import FeatureStore
from graph.entity_graph import EntityGraph

FEATURE_COLUMNS = [
    "amount",
    "velocity_1m",
    "velocity_5m",
    "velocity_1h",
    "device_velocity_5m",
    "amount_zscore_vs_customer",
    "amount_zscore_vs_merchant",
    "is_new_device",
    "is_new_ip",
    "is_new_card",
    "geo_deviation",
    "vpa_handle_risk",
    "is_qr_intent",
    "device_sim_bound",
    "entity_degree_device",
    "entity_degree_ip",
    "entity_degree_card",
    "component_size",
    "ring_density_score",
    "is_ring_suspect"
]

MERCHANT_CATEGORIES = [
    "GAMING_CRYPTO",
    "LUXURY_JEWELRY",
    "ECOMMERCE_RETAIL",
    "FOOD_GROCERY",
    "UTILITY_BILLPAY"
]


def generate_training_dataset(n_samples: int = 6000) -> Tuple[pd.DataFrame, np.ndarray, List[str]]:
    """Generates a diverse training stream and extracts full feature matrices with merchant categories."""
    generator = TransactionGenerator(seed=1337)
    events = generator.generate_batch(count=n_samples, holdout_ratio=0.0)

    feature_store = FeatureStore()
    graph = EntityGraph()

    records = []
    labels = []
    categories = []

    for event in events:
        feat = feature_store.compute_and_update(event)
        g_feat = graph.add_transaction(event)
        
        row = {
            "amount": float(event["amount"]),
            "velocity_1m": float(feat["velocity_1m"]),
            "velocity_5m": float(feat["velocity_5m"]),
            "velocity_1h": float(feat["velocity_1h"]),
            "device_velocity_5m": float(feat["device_velocity_5m"]),
            "amount_zscore_vs_customer": float(feat["amount_zscore_vs_customer"]),
            "amount_zscore_vs_merchant": float(feat["amount_zscore_vs_merchant"]),
            "is_new_device": 1.0 if feat["is_new_device"] else 0.0,
            "is_new_ip": 1.0 if feat["is_new_ip"] else 0.0,
            "is_new_card": 1.0 if feat["is_new_card"] else 0.0,
            "geo_deviation": float(feat["geo_deviation"]),
            "vpa_handle_risk": float(feat.get("vpa_handle_risk", 0.0)),
            "is_qr_intent": float(feat.get("is_qr_intent", 0.0)),
            "device_sim_bound": float(feat.get("device_sim_bound", 1.0)),
            "entity_degree_device": float(g_feat["entity_degree_device"]),
            "entity_degree_ip": float(g_feat["entity_degree_ip"]),
            "entity_degree_card": float(g_feat["entity_degree_card"]),
            "component_size": float(g_feat["component_size"]),
            "ring_density_score": float(g_feat["ring_density_score"]),
            "is_ring_suspect": 1.0 if g_feat["is_ring_suspect"] else 0.0
        }
        records.append(row)
        labels.append(1 if event["label_is_fraud"] else 0)
        categories.append(event["merchant_category"])

    df = pd.DataFrame(records)[FEATURE_COLUMNS]
    y = np.array(labels)
    return df, y, categories


def train_and_evaluate_model():
    """Trains the risk model with cross-validation, isotonic calibration, and threshold optimization."""
    print("Generating synthetic training data stream (6,000 events)...")
    X, y, categories = generate_training_dataset(6000)
    print(f"Dataset generated. Shape: {X.shape}, Fraud prevalence: {np.mean(y)*100:.2f}%")

    # 5-Fold Stratified Cross-Validation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_raw_predictions = np.zeros(len(y))
    cv_roc_aucs = []
    cv_pr_aucs = []

    print("\nRunning 5-Fold Stratified Cross-Validation...")
    for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        X_train, y_train = X.iloc[train_idx], y[train_idx]
        X_val, y_val = X.iloc[val_idx], y[val_idx]

        model = HistGradientBoostingClassifier(
            max_iter=180,
            learning_rate=0.07,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=1.2,
            random_state=42 + fold
        )
        model.fit(X_train, y_train)
        val_probs = model.predict_proba(X_val)[:, 1]
        oof_raw_predictions[val_idx] = val_probs

        roc_auc = roc_auc_score(y_val, val_probs)
        prec, rec, _ = precision_recall_curve(y_val, val_probs)
        pr_auc_val = auc(rec, prec)

        cv_roc_aucs.append(roc_auc)
        cv_pr_aucs.append(pr_auc_val)
        print(f"  Fold {fold+1}: ROC-AUC = {roc_auc:.4f}, PR-AUC = {pr_auc_val:.4f}")

    print(f"\nMean CV ROC-AUC: {np.mean(cv_roc_aucs):.4f} +/- {np.std(cv_roc_aucs):.4f}")
    print(f"Mean CV PR-AUC:  {np.mean(cv_pr_aucs):.4f} +/- {np.std(cv_pr_aucs):.4f}")

    # Train Global and Multi-Tenant Isotonic Calibrators
    print("\nFitting Multi-Tenant Isotonic Calibrators per Merchant Category...")
    calibrators = {}
    
    # Global calibrator
    global_iso = IsotonicRegression(out_of_bounds="clip")
    global_iso.fit(oof_raw_predictions, y)
    calibrators["GLOBAL"] = global_iso

    cat_series = pd.Series(categories)
    for cat in MERCHANT_CATEGORIES:
        mask = (cat_series == cat).values
        if np.sum(mask) >= 100 and len(np.unique(y[mask])) > 1:
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(oof_raw_predictions[mask], y[mask])
            calibrators[cat] = iso
            brier_before = brier_score_loss(y[mask], oof_raw_predictions[mask])
            brier_after = brier_score_loss(y[mask], iso.predict(oof_raw_predictions[mask]))
            print(f"  {cat:20s}: Samples={np.sum(mask):4d} | Brier: {brier_before:.4f} -> {brier_after:.4f}")
        else:
            calibrators[cat] = global_iso

    # Calculate calibrated OOF predictions
    oof_calibrated = np.zeros(len(y))
    for i, cat in enumerate(categories):
        calibrator = calibrators.get(cat, global_iso)
        oof_calibrated[i] = calibrator.predict([oof_raw_predictions[i]])[0]

    # Optimize Decision Threshold for Payment Risk (Target: FPR < 1.5%, Recall >= 90%)
    precisions, recalls, thresholds = precision_recall_curve(y, oof_calibrated)
    best_threshold = 0.45
    best_f1 = 0.0

    for p, r, t in zip(precisions[:-1], recalls[:-1], thresholds):
        if p + r > 0:
            f1 = 2 * (p * r) / (p + r)
            if f1 > best_f1 and r >= 0.88:
                best_f1 = f1
                best_threshold = float(t)

    preds_binary = (oof_calibrated >= best_threshold).astype(int)
    final_prec = precision_score(y, preds_binary)
    final_rec = recall_score(y, preds_binary)
    final_f1 = f1_score(y, preds_binary)
    tn = np.sum((y == 0) & (preds_binary == 0))
    fp = np.sum((y == 0) & (preds_binary == 1))
    final_fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    print("\n--- Optimized Operating Point ---")
    print(f"Decision Threshold: {best_threshold:.4f}")
    print(f"Precision:          {final_prec*100:.2f}%")
    print(f"Recall:             {final_rec*100:.2f}%")
    print(f"F1 Score:           {final_f1:.4f}")
    print(f"False Positive Rate:{final_fpr*100:.2f}%")

    # Fit final production model on full dataset
    print("\nFitting final production model on full dataset...")
    final_model = HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.07,
        max_leaf_nodes=31,
        min_samples_leaf=20,
        l2_regularization=1.2,
        random_state=42
    )
    final_model.fit(X.values, y)

    # Compute Feature Importances via Permutation Importance
    perm_imp = permutation_importance(final_model, X.values, y, n_repeats=5, random_state=42)
    importance_dict = {
        col: round(float(imp), 4)
        for col, imp in zip(FEATURE_COLUMNS, perm_imp.importances_mean)
    }

    # Save artifacts
    model_dir = "scoring/models"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "risk_model.joblib")
    calibrator_path = os.path.join(model_dir, "calibrators.joblib")
    joblib.dump(final_model, model_path)
    joblib.dump(calibrators, calibrator_path)

    # Baseline statistics for dynamic feature attribution
    feature_means = X.mean().to_dict()
    feature_stds = X.std().replace(0, 1.0).to_dict()

    metadata = {
        "model_type": "HistGradientBoostingClassifier",
        "feature_columns": FEATURE_COLUMNS,
        "optimal_threshold": round(best_threshold, 3),
        "cv_roc_auc_mean": round(float(np.mean(cv_roc_aucs)), 4),
        "cv_pr_auc_mean": round(float(np.mean(cv_pr_aucs)), 4),
        "oof_precision": round(final_prec, 4),
        "oof_recall": round(final_rec, 4),
        "oof_f1": round(final_f1, 4),
        "oof_fpr": round(final_fpr, 4),
        "feature_importances": importance_dict,
        "feature_means": feature_means,
        "feature_stds": feature_stds
    }

    meta_path = os.path.join(model_dir, "model_metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Model saved successfully to {model_path}")
    print(f"Calibrators saved to {calibrator_path}")
    print(f"Metadata saved to {meta_path}")
    return metadata


if __name__ == "__main__":
    train_and_evaluate_model()
