"""Ablation study generator for GoldenMinutes (Variants A, B, C, D).

Evaluates all four variants side by side on the held-out test split,
computes PR-AUC, value-weighted recall at FFR cap, precision at K,
held-out typology recall, calibration, and latency, and writes reports/ablation.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from goldenminutes.eval.fairness import (
    compute_fairness_slices,
    generate_fairness_report_markdown,
    generate_sensitivity_report_markdown,
)
from goldenminutes.eval.metrics import (
    compute_brier_score,
    compute_expected_calibration_error,
    compute_expected_intercepted_value,
    compute_false_friction_rate,
    compute_precision_at_k,
    compute_value_weighted_recall,
)
from goldenminutes.models.anomaly import AnomalyIsolationForest
from goldenminutes.models.calibration import IsotonicCalibrator
from goldenminutes.models.fusion import FusionModel
from goldenminutes.models.registry import ModelRegistry
from goldenminutes.models.risk_lgbm import RiskLGBM
from goldenminutes.policy.engine import PolicyEngine
from goldenminutes.rules.baseline import RulesBaseline

logger = logging.getLogger("goldenminutes.eval.ablation")


def run_ablation(profile: str = "full") -> Dict[str, Any]:
    """Run full ablation across Variants A, B, C, D on the held-out test split."""
    repo_root = Path(__file__).resolve().parents[3]
    raw_dir = repo_root / "data" / "raw" / profile
    processed_dir = repo_root / "data" / "processed" / profile
    features_path = processed_dir / "features.parquet"
    labels_path = raw_dir / "labels.parquet"
    wallets_path = raw_dir / "wallets.parquet"
    customers_path = raw_dir / "customers.parquet"

    # 1. Load active model metadata from registry
    registry = ModelRegistry()
    active_meta = registry.get_active_metadata()
    if active_meta is None or "artifacts" not in active_meta:
        raise RuntimeError("No active trained model found in registry. Run `make train` first.")

    artifacts = active_meta["artifacts"]

    logger.info(f"Loaded active model version {active_meta['version']} for ablation.")

    # 2. Load model artifacts
    model_b = RiskLGBM.load(artifacts["variant_b_lgbm"])
    calibrator_b = IsotonicCalibrator.load(artifacts["variant_b_calibrator"])

    model_c = RiskLGBM.load(artifacts["variant_c_lgbm"])
    calibrator_c = IsotonicCalibrator.load(artifacts["variant_c_calibrator"])

    anomaly_model = AnomalyIsolationForest.load(artifacts["anomaly_iforest"])
    fusion_model = FusionModel.load(artifacts["fusion_model"])

    # 3. Load dataset and test split
    features_df = pd.read_parquet(features_path)
    labels_df = pd.read_parquet(labels_path)

    merged = pd.merge(features_df, labels_df[["txn_id", "is_fraud", "typology"]], on="txn_id", how="inner")

    # Demographic data for fairness
    wallets_df = pd.read_parquet(wallets_path)
    customers_df = pd.read_parquet(customers_path)
    customer_demo = pd.merge(
        wallets_df[["wallet_id", "customer_id"]],
        customers_df[["customer_id", "age_band", "region_type", "persona"]],
        on="customer_id",
        how="inner",
    )
    merged = pd.merge(merged, customer_demo.rename(columns={"wallet_id": "sender_wallet_id"}), on="sender_wallet_id", how="left")

    tenure_days = merged["sender_tenure_days"].values
    merged["tenure_bucket"] = np.where(tenure_days < 7, "<1w", np.where(tenure_days < 30, "1w-1m", "1m+"))

    test_df = merged[merged["split"] == "test"].copy().reset_index(drop=True)
    n_test = len(test_df)
    y_test = test_df["is_fraud"].values.astype(int)
    amounts = test_df["amount_bdt"].values
    typologies = test_df["typology"].fillna("none").values

    logger.info(f"Evaluating {n_test:,} test split transactions ({y_test.sum()} fraud, including held-out typology)...")

    policy_engine = PolicyEngine()

    # --- Variant A: Rules Baseline ---
    logger.info("Evaluating Variant A: Rules Baseline...")
    rules_engine = RulesBaseline()
    rules_res = rules_engine.evaluate_batch(test_df)
    scores_a = rules_res["risk_score"].values
    actions_a = rules_res["action"].values
    rules_hit_counts = rules_res["rules_hit_count"].values.astype(float)

    # --- Variant B: LightGBM (No Graph) ---
    logger.info("Evaluating Variant B: LightGBM (no graph)...")
    raw_b = model_b.predict_proba(test_df)
    scores_b = calibrator_b.predict(raw_b)
    actions_b = policy_engine.evaluate_batch(amounts, scores_b)

    # --- Variant C: LightGBM + Graph ---
    logger.info("Evaluating Variant C: LightGBM + Graph...")
    raw_c = model_c.predict_proba(test_df)
    scores_c = calibrator_c.predict(raw_c)
    actions_c = policy_engine.evaluate_batch(amounts, scores_c)

    # --- Variant D: Full Fusion + Anomaly ---
    logger.info("Evaluating Variant D: Full Fusion + Anomaly...")
    anom_test = anomaly_model.predict_anomaly_score(test_df)
    scores_d = fusion_model.predict_risk(scores_c, anom_test, rules_hit_counts)
    actions_d = policy_engine.evaluate_batch(amounts, scores_d)

    # Measure per-sample latency distribution on a sample
    sample_size = min(300, n_test)
    sample_df = test_df.iloc[:sample_size].copy()

    def _measure_latencies(fn: Any) -> Tuple[float, float]:
        lats: List[float] = []
        for i in range(sample_size):
            row_df = sample_df.iloc[[i]]
            t0 = time.perf_counter()
            fn(row_df)
            lats.append((time.perf_counter() - t0) * 1000.0)
        return float(np.median(lats)), float(np.percentile(lats, 95))

    p50_a, p95_a = _measure_latencies(lambda r: rules_engine.evaluate_batch(r))
    p50_b, p95_b = _measure_latencies(lambda r: calibrator_b.predict(model_b.predict_proba(r)))
    p50_c, p95_c = _measure_latencies(lambda r: calibrator_c.predict(model_c.predict_proba(r)))
    p50_d, p95_d = _measure_latencies(
        lambda r: fusion_model.predict_risk(
            calibrator_c.predict(model_c.predict_proba(r)),
            anomaly_model.predict_anomaly_score(r),
            rules_engine.evaluate_batch(r)["rules_hit_count"].values.astype(float),
        )
    )

    variants_data = [
        ("A", "Rules baseline", scores_a, actions_a, p50_a, p95_a),
        ("B", "LightGBM (no graph)", scores_b, actions_b, p50_b, p95_b),
        ("C", "LightGBM + Graph", scores_c, actions_c, p50_c, p95_c),
        ("D", "Fused (C + Anomaly)", scores_d, actions_d, p50_d, p95_d),
    ]

    ablation_results: List[Dict[str, Any]] = []

    for code, name, scores, acts, p50_lat, p95_lat in variants_data:
        pr_auc = float(average_precision_score(y_test, scores))
        roc_auc = float(roc_auc_score(y_test, scores))
        ffr = compute_false_friction_rate(y_test, acts)
        vw_recall = compute_value_weighted_recall(y_test, acts, amounts, target_actions=("verify", "hold"))
        prec_50 = compute_precision_at_k(y_test, scores, k=min(50, n_test))
        brier = compute_brier_score(y_test, scores)
        ece = compute_expected_calibration_error(y_test, scores)

        # Typology breakdown
        typ_recalls: Dict[str, float] = {}
        for typ in np.unique(typologies):
            if typ in ["none", ""]:
                continue
            m = (typologies == typ)
            tot = np.sum(m)
            if tot > 0:
                intercepted = np.sum(m & np.isin(acts, ["verify", "hold"]))
                typ_recalls[typ] = float(intercepted / tot)

        held_out_rec = typ_recalls.get("agent_collusion", 0.0)

        ablation_results.append({
            "variant": code,
            "name": name,
            "status": "evaluated",
            "pr_auc": round(pr_auc, 4),
            "roc_auc": round(roc_auc, 4),
            "ffr": round(ffr, 4),
            "value_weighted_recall": round(vw_recall, 4),
            "held_out_recall": round(held_out_rec, 4),
            "precision_at_50": round(prec_50, 4),
            "brier_score": round(brier, 4),
            "ece": round(ece, 4),
            "p50_latency_ms": round(p50_lat, 2),
            "p95_latency_ms": round(p95_lat, 2),
            "typology_recalls": typ_recalls,
        })

    # Fairness slices for Variant D (champion)
    fairness_d = compute_fairness_slices(test_df, y_test, actions_d, attributes=["age_band", "region_type", "tenure_bucket"])

    # Sensitivity grid for Variant D driven by configs/policy.yaml
    sensitivity_cfg = policy_engine.sensitivity or {
        "conservative": {
            "effectiveness": {"hold": 0.75, "verify": 0.40, "warn": 0.15, "allow": 0.0},
            "friction_cost_bdt": {"hold": 350, "verify": 60, "warn": 10, "allow": 0},
        },
        "baseline": {
            "effectiveness": policy_engine.effectiveness,
            "friction_cost_bdt": policy_engine.friction_cost_bdt,
        },
        "optimistic": {
            "effectiveness": {"hold": 0.98, "verify": 0.70, "warn": 0.40, "allow": 0.0},
            "friction_cost_bdt": {"hold": 100, "verify": 15, "warn": 2, "allow": 0},
        },
    }

    sensitivity_d: List[Dict[str, Any]] = []
    for scen_name, scen_params in sensitivity_cfg.items():
        eff = scen_params.get("effectiveness", policy_engine.effectiveness)
        fric = scen_params.get("friction_cost_bdt", policy_engine.friction_cost_bdt)
        acts_scen = policy_engine.evaluate_batch(amounts, scores_d, effectiveness_override=eff, friction_override=fric)
        val = compute_expected_intercepted_value(y_test, acts_scen, amounts, effectiveness=eff)
        sensitivity_d.append({
            "effectiveness_scenario": scen_name,
            "hold_eff": float(eff.get("hold", 0.90)),
            "verify_eff": float(eff.get("verify", 0.55)),
            "intercepted_bdt": float(val),
        })

    intercepted_val_d = compute_expected_intercepted_value(y_test, actions_d, amounts, effectiveness=policy_engine.effectiveness)

    summary = {
        "ablation_table": ablation_results,
        "champion_variant": "D",
        "held_out_typology": "agent_collusion",
        "held_out_recall_champion": ablation_results[-1]["held_out_recall"],
        "evaluated_at": active_meta["trained_at"],
        "profile": profile,
        "test_transactions": n_test,
        "test_fraud": int(y_test.sum()),
    }

    # Save reports/ablation.json
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ablation_file = reports_dir / "ablation.json"
    with open(ablation_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Saved ablation report to {ablation_file}")

    # Latency percentiles: read from reports/latency.json if present
    latency_file = reports_dir / "latency.json"
    if latency_file.exists():
        try:
            with open(latency_file, "r", encoding="utf-8") as lf:
                lat_data = json.load(lf)
            median_lat = float(lat_data.get("p50_latency_ms", p50_d))
            p95_lat = float(lat_data.get("p95_latency_ms", p95_d))
        except Exception:
            median_lat = float(p50_d)
            p95_lat = float(p95_d)
    else:
        median_lat = float(p50_d)
        p95_lat = float(p95_d)

    total_alerts_d = int(np.sum(np.isin(actions_d, ["verify", "hold"])))
    metrics_summary = {
        "fraud_value_intercepted_bdt": float(intercepted_val_d),
        "false_friction_rate": float(ablation_results[-1]["ffr"]),
        "median_decision_time_ms": round(median_lat, 2),
        "p95_decision_time_ms": round(p95_lat, 2),
        "ablation_table": ablation_results,
        "held_out_typology_recall": float(ablation_results[-1]["held_out_recall"]),
        "typology_recalls": ablation_results[-1]["typology_recalls"],
        "fairness_slices": fairness_d,
        "sensitivity_grid": sensitivity_d,
        "total_scored": n_test,
        "total_alerts": total_alerts_d,
    }
    metrics_file = reports_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_summary, f, indent=2)
    logger.info(f"Updated live system metrics in {metrics_file}")

    # Generate reports/fairness_report.md
    fairness_md = generate_fairness_report_markdown(
        fairness_slices=fairness_d,
        total_txns=n_test,
        total_fraud=int(y_test.sum()),
        evaluated_at=str(active_meta.get("trained_at", "2026-10-04")),
    )
    with open(reports_dir / "fairness_report.md", "w", encoding="utf-8") as f:
        f.write(fairness_md)
    logger.info("Updated reports/fairness_report.md")

    # Generate reports/sensitivity_report.md
    with open(repo_root / "configs" / "policy.yaml", "r", encoding="utf-8") as pf:
        import yaml
        policy_raw_cfg = yaml.safe_load(pf)
    sensitivity_md = generate_sensitivity_report_markdown(
        sensitivity_grid=sensitivity_d,
        policy_cfg=policy_raw_cfg,
        total_txns=n_test,
        total_fraud=int(y_test.sum()),
    )
    with open(reports_dir / "sensitivity_report.md", "w", encoding="utf-8") as f:
        f.write(sensitivity_md)
    logger.info("Updated reports/sensitivity_report.md")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Run GoldenMinutes ablation study.")
    parser.add_argument("--profile", choices=["small", "full"], default="small", help="Dataset profile.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_ablation(profile=args.profile)


if __name__ == "__main__":
    main()
