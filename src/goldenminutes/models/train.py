"""Training pipeline for GoldenMinutes model variants (B, C, D).

Trains LightGBM (Variants B & C), Isolation Forest anomaly detector, isotonic
probability calibrators, and logistic fusion stacker. Removes held-out typology
from train and validation splits, and chooses operating thresholds on validation only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yaml

from goldenminutes.common.config import get_settings
from goldenminutes.features.specs import (
    ALL_FEATURE_NAMES,
    NON_GRAPH_FEATURE_NAMES,
    VARIANT_E_FEATURE_NAMES,
)
from goldenminutes.models.anomaly import AnomalyIsolationForest
from goldenminutes.models.calibration import IsotonicCalibrator
from goldenminutes.models.fusion import FusionModel
from goldenminutes.models.registry import ModelRegistry
from goldenminutes.models.risk_lgbm import RiskLGBM
from goldenminutes.rules.baseline import RulesBaseline

logger = logging.getLogger("goldenminutes.models.train")


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def train_pipeline(profile: str = "full", version: Optional[str] = None) -> Dict[str, Any]:
    """Train all model variants and register the model version."""
    repo_root = Path(__file__).resolve().parents[3]
    raw_dir = repo_root / "data" / "raw" / profile
    processed_dir = repo_root / "data" / "processed" / profile
    features_path = processed_dir / "features.parquet"
    labels_path = raw_dir / "labels.parquet"
    config_path = repo_root / "configs" / "models.yaml"

    settings = get_settings()
    seed = settings.gm_seed

    if version is None:
        version = f"m-1.0.0-{profile}"

    logger.info(f"Starting model training pipeline for version {version} (profile: {profile}, seed: {seed})...")

    # 1. Load data
    logger.info(f"Loading features from {features_path}")
    features_df = pd.read_parquet(features_path)
    logger.info(f"Loading labels from {labels_path}")
    labels_df = pd.read_parquet(labels_path)

    merged = pd.merge(features_df, labels_df[["txn_id", "is_fraud", "typology"]], on="txn_id", how="inner")

    # 2. Partition by split
    train_mask = (merged["split"] == "train")
    val_mask = (merged["split"] == "val")
    test_mask = (merged["split"] == "test")

    # 3. Enforce Held-out Typology Contract:
    # Remove agent_collusion fraud rows from train and validation. Keep in test only.
    held_out_typology = "agent_collusion"
    train_clean_mask = train_mask & ~((merged["typology"] == held_out_typology) & (merged["is_fraud"] == 1))
    val_clean_mask = val_mask & ~((merged["typology"] == held_out_typology) & (merged["is_fraud"] == 1))

    train_df = merged[train_clean_mask].copy().reset_index(drop=True)
    val_df = merged[val_clean_mask].copy().reset_index(drop=True)
    test_df = merged[test_mask].copy().reset_index(drop=True)

    logger.info(f"Train split: {len(train_df):,} rows ({train_df['is_fraud'].sum()} fraud, {held_out_typology} excluded).")
    logger.info(f"Val split:   {len(val_df):,} rows ({val_df['is_fraud'].sum()} fraud, {held_out_typology} excluded).")
    logger.info(f"Test split:  {len(test_df):,} rows ({test_df['is_fraud'].sum()} fraud, ALL typologies included).")

    y_train = train_df["is_fraud"].values.astype(int)
    y_val = val_df["is_fraud"].values.astype(int)

    # Load model hyperparams
    with open(config_path, "r", encoding="utf-8") as f:
        models_cfg = yaml.safe_load(f)

    lgbm_params = models_cfg.get("risk_lgbm", {})
    anomaly_params = models_cfg.get("anomaly_iforest", {})
    fusion_cfg = models_cfg.get("fusion", {})
    config_hash = compute_file_hash(config_path)

    model_dir = repo_root / "models" / version
    model_dir.mkdir(parents=True, exist_ok=True)

    # 4. Train Variant B: LightGBM without graph features
    logger.info("--- Training Variant B: LightGBM (no graph) ---")
    model_b = RiskLGBM(feature_names=NON_GRAPH_FEATURE_NAMES, params=lgbm_params, random_state=seed)
    model_b.fit(train_df, y_train, val_df, y_val)
    val_preds_b_raw = model_b.predict_proba(val_df)

    calibrator_b = IsotonicCalibrator()
    calibrator_b.fit(val_preds_b_raw, y_val)
    val_preds_b = calibrator_b.predict(val_preds_b_raw)

    model_b.save(model_dir / "variant_b_lgbm.joblib")
    calibrator_b.save(model_dir / "variant_b_calibrator.joblib")

    # 5. Train Variant C: LightGBM with graph features
    logger.info("--- Training Variant C: LightGBM + Graph ---")
    model_c = RiskLGBM(feature_names=ALL_FEATURE_NAMES, params=lgbm_params, random_state=seed)
    model_c.fit(train_df, y_train, val_df, y_val)
    val_preds_c_raw = model_c.predict_proba(val_df)

    calibrator_c = IsotonicCalibrator()
    calibrator_c.fit(val_preds_c_raw, y_val)
    val_preds_c = calibrator_c.predict(val_preds_c_raw)

    model_c.save(model_dir / "variant_c_lgbm.joblib")
    calibrator_c.save(model_dir / "variant_c_calibrator.joblib")

    # 6. Train Variant E: LightGBM with Graph + GNN Features
    logger.info("--- Training Variant E: LightGBM + Graph + GNN ---")
    model_e = RiskLGBM(feature_names=VARIANT_E_FEATURE_NAMES, params=lgbm_params, random_state=seed)
    model_e.fit(train_df, y_train, val_df, y_val)
    val_preds_e_raw = model_e.predict_proba(val_df)

    calibrator_e = IsotonicCalibrator()
    calibrator_e.fit(val_preds_e_raw, y_val)
    val_preds_e = calibrator_e.predict(val_preds_e_raw)

    model_e.save(model_dir / "variant_e_lgbm.joblib")
    calibrator_e.save(model_dir / "variant_e_calibrator.joblib")

    # 7. Train Anomaly Model: Isolation Forest on legitimate training rows
    logger.info("--- Training Isolation Forest Anomaly Model ---")
    anomaly_model = AnomalyIsolationForest(feature_names=ALL_FEATURE_NAMES, params=anomaly_params, random_state=seed)
    train_legit_df = train_df[y_train == 0]
    anomaly_model.fit(train_legit_df)
    val_anom_scores = anomaly_model.predict_anomaly_score(val_df)

    anomaly_model.save(model_dir / "anomaly_iforest.joblib")

    # 8. Train Fusion Models (Variant D baseline and Variant E Champion)
    logger.info("--- Training Fusion Models ---")
    rules_engine = RulesBaseline()
    val_rules_res = rules_engine.evaluate_batch(val_df)
    val_rules_hit_counts = val_rules_res["rules_hit_count"].values.astype(float)

    # Variant D: baseline fusion on Variant C
    fusion_model_d = FusionModel(regularization_c=fusion_cfg.get("regularization_c", 1.0), random_state=seed)
    fusion_model_d.fit(val_preds_c, val_anom_scores, val_rules_hit_counts, y_val)
    val_preds_d = fusion_model_d.predict_risk(val_preds_c, val_anom_scores, val_rules_hit_counts)
    fusion_model_d.save(model_dir / "fusion_model_d.joblib")

    # Variant E Champion: fusion on Variant E
    fusion_model = FusionModel(regularization_c=fusion_cfg.get("regularization_c", 1.0), random_state=seed)
    fusion_model.fit(val_preds_e, val_anom_scores, val_rules_hit_counts, y_val)
    val_preds_e_fusion = fusion_model.predict_risk(val_preds_e, val_anom_scores, val_rules_hit_counts)
    fusion_model.save(model_dir / "fusion_model.joblib")

    # 9. Copy / register GNN embeddings
    gnn_processed = processed_dir / "gnn_embeddings.parquet"
    if gnn_processed.exists():
        import shutil
        shutil.copy(gnn_processed, model_dir / "gnn_embeddings.parquet")

    # 10. Choose Operating Thresholds on Validation Split strictly
    # Target: 1.0% False Friction Rate cap on legitimate validation traffic
    logger.info("Choosing operating thresholds on validation set (target: <= 1.0% FFR)...")
    val_legit_mask = (y_val == 0)

    thresholds: Dict[str, float] = {}
    variants_to_eval = [
        ("B", val_preds_b),
        ("C", val_preds_c),
        ("D", val_preds_d),
        ("E", val_preds_e),
        ("E_fusion", val_preds_e_fusion),
    ]
    for name, v_scores in variants_to_eval:
        legit_scores = np.sort(v_scores[val_legit_mask])
        idx = int(np.ceil(0.99 * len(legit_scores)))
        if idx >= len(legit_scores):
            idx = len(legit_scores) - 1
        th_1pct = float(legit_scores[idx])
        if th_1pct <= 0.05:
            th_1pct = 0.50
        thresholds[f"threshold_1pct_ffr_variant_{name.lower()}"] = th_1pct
        actual_val_ffr = float(np.mean(legit_scores >= th_1pct))
        logger.info(f"  Variant {name}: threshold={th_1pct:.4f} -> validation FFR={actual_val_ffr:.2%}")

    # Active Champion Thresholds
    thresholds["hold_threshold"] = thresholds["threshold_1pct_ffr_variant_e_fusion"]
    thresholds["verify_threshold"] = float(thresholds["hold_threshold"] * 0.75)
    thresholds["warn_threshold"] = float(thresholds["hold_threshold"] * 0.50)

    with open(model_dir / "thresholds.json", "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2)

    # 11. Register Model Version
    artifacts_map = {
        "variant_b_lgbm": str(model_dir / "variant_b_lgbm.joblib"),
        "variant_b_calibrator": str(model_dir / "variant_b_calibrator.joblib"),
        "variant_c_lgbm": str(model_dir / "variant_c_lgbm.joblib"),
        "variant_c_calibrator": str(model_dir / "variant_c_calibrator.joblib"),
        "variant_e_lgbm": str(model_dir / "variant_e_lgbm.joblib"),
        "variant_e_calibrator": str(model_dir / "variant_e_calibrator.joblib"),
        "anomaly_iforest": str(model_dir / "anomaly_iforest.joblib"),
        "fusion_model": str(model_dir / "fusion_model.joblib"),
        "fusion_model_d": str(model_dir / "fusion_model_d.joblib"),
        "thresholds": str(model_dir / "thresholds.json"),
    }
    if (model_dir / "gnn_embeddings.parquet").exists():
        artifacts_map["gnn_embeddings"] = str(model_dir / "gnn_embeddings.parquet")

    metadata = {
        "version": version,
        "profile": profile,
        "seed": seed,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": config_hash,
        "held_out_typology": held_out_typology,
        "training_rows": len(train_df),
        "validation_rows": len(val_df),
        "test_rows": len(test_df),
        "features_count": len(ALL_FEATURE_NAMES),
        "artifacts": artifacts_map,
        "thresholds": thresholds,
    }

    registry = ModelRegistry()
    registry.register_version(version=version, metadata=metadata, set_active=True)

    logger.info(f"Model training pipeline completed successfully for {version}!")
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Train GoldenMinutes model variants B, C, D.")
    parser.add_argument("--profile", choices=["small", "full"], default="small", help="Dataset profile.")
    parser.add_argument("--version", type=str, default=None, help="Optional model version string.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    train_pipeline(profile=args.profile, version=args.version)


if __name__ == "__main__":
    main()
