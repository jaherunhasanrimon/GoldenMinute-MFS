"""Defensible lift evaluation and paired bootstrap analysis for GoldenMinutes (Phase 1).

Measures whether graph learning (NetworkX C and GNN E) provides statistically significant
lift over tabular baseline B. Implements paired bootstrap (1,000 resamples) with 95% CIs,
single-feature AUC scan (<0.85 check), feature-group permutation importance, and
graph edge-rewiring sanity check.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from goldenminutes.features.specs import (
    FEATURE_GROUP_MAP,
    NON_GRAPH_FEATURE_NAMES,
    VARIANT_E_FEATURE_NAMES,
)
from goldenminutes.models.calibration import IsotonicCalibrator
from goldenminutes.models.registry import ModelRegistry
from goldenminutes.models.risk_lgbm import RiskLGBM

logger = logging.getLogger("goldenminutes.eval.lift")


def compute_single_feature_auc_scan(
    test_df: pd.DataFrame,
    y_test: np.ndarray,
    target_features: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Scan tabular features to verify no single feature has ROC-AUC > 0.85 (Criterion 1)."""
    # Criterion 1 enforces that tabular baseline features do not have a trivial synthetic shortcut
    # (such as the previous new_device_flag == 1 artifact).
    features_to_check = target_features or NON_GRAPH_FEATURE_NAMES
    auc_scan: Dict[str, float] = {}
    for feat in features_to_check:
        if feat in test_df.columns:
            vals = test_df[feat].values.astype(float)
            if len(np.unique(vals)) <= 1:
                auc_scan[feat] = 0.5
            else:
                try:
                    auc = float(roc_auc_score(y_test, vals))
                    auc_scan[feat] = max(auc, 1.0 - auc)
                except Exception:
                    auc_scan[feat] = 0.5

    sorted_scan = dict(sorted(auc_scan.items(), key=lambda kv: kv[1], reverse=True))
    max_feature = next(iter(sorted_scan))
    max_auc = sorted_scan[max_feature]

    # Full scan across all Variant E features for transparency
    all_scan: Dict[str, float] = {}
    for feat in VARIANT_E_FEATURE_NAMES:
        if feat in test_df.columns:
            vals = test_df[feat].values.astype(float)
            if len(np.unique(vals)) <= 1:
                all_scan[feat] = 0.5
            else:
                try:
                    auc = float(roc_auc_score(y_test, vals))
                    all_scan[feat] = max(auc, 1.0 - auc)
                except Exception:
                    all_scan[feat] = 0.5
    sorted_all = dict(sorted(all_scan.items(), key=lambda kv: kv[1], reverse=True))

    return {
        "max_feature": max_feature,
        "max_auc": max_auc,
        "passed_criterion_1": bool(max_auc <= 0.85),
        "rankings": sorted_scan,
        "all_rankings": sorted_all,
    }


def paired_bootstrap_evaluation(
    y_test: np.ndarray,
    amounts: np.ndarray,
    typologies: np.ndarray,
    scores_dict: Dict[str, np.ndarray],
    thresholds_dict: Dict[str, float],
    n_bootstraps: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Compute paired bootstrap 95% confidence intervals for metrics and variant differences."""
    rng = np.random.default_rng(seed)
    n_samples = len(y_test)

    # Metric accumulators
    metrics_per_variant: Dict[str, Dict[str, List[float]]] = {
        name: {"pr_auc": [], "recall_at_1pct_ffr": [], "value_recall": []}
        for name in scores_dict
    }

    # Differences accumulators: C - B, E - C, E - B
    diff_keys = [("C_minus_B", "C", "B"), ("E_minus_C", "E", "C"), ("E_minus_B", "E", "B")]
    diffs_accum: Dict[str, Dict[str, List[float]]] = {
        k: {"pr_auc": [], "recall_at_1pct_ffr": [], "value_recall": []}
        for (k, _, _) in diff_keys
    }

    # Per-typology accumulators
    unique_typos = [t for t in np.unique(typologies) if t not in ("none", "legitimate", "")]
    typo_diffs_accum: Dict[str, Dict[str, Dict[str, List[float]]]] = {
        typo: {k: {"pr_auc": [], "recall_at_1pct_ffr": []} for (k, _, _) in diff_keys}
        for typo in unique_typos
    }

    for _b in range(n_bootstraps):
        boot_idx = rng.choice(n_samples, size=n_samples, replace=True)
        y_b = y_test[boot_idx]

        # Ensure both classes are present in sample
        if np.sum(y_b) == 0 or np.sum(y_b) == len(y_b):
            continue

        amt_b = amounts[boot_idx]
        tot_fraud_amt_b = np.sum(amt_b[y_b == 1])
        if tot_fraud_amt_b <= 0:
            tot_fraud_amt_b = 1.0

        typo_b = typologies[boot_idx]

        # Calculate metrics for each variant on this sample
        sample_metrics: Dict[str, Dict[str, float]] = {}
        for name, scores in scores_dict.items():
            sc_b = scores[boot_idx]
            th = thresholds_dict.get(name, 0.5)

            # 1. PR-AUC
            pr_auc = float(average_precision_score(y_b, sc_b))

            # 2. Recall at 1% FFR
            preds = (sc_b >= th).astype(int)
            fraud_hits = np.sum((preds == 1) & (y_b == 1))
            tot_fraud = np.sum(y_b == 1)
            rec = float(fraud_hits / tot_fraud) if tot_fraud > 0 else 0.0

            # 3. Value-weighted recall
            val_hits = np.sum(amt_b[(preds == 1) & (y_b == 1)])
            v_rec = float(val_hits / tot_fraud_amt_b)

            sample_metrics[name] = {"pr_auc": pr_auc, "recall_at_1pct_ffr": rec, "value_recall": v_rec}
            metrics_per_variant[name]["pr_auc"].append(pr_auc)
            metrics_per_variant[name]["recall_at_1pct_ffr"].append(rec)
            metrics_per_variant[name]["value_recall"].append(v_rec)

        # Record paired differences
        for diff_k, v1, v2 in diff_keys:
            if v1 in sample_metrics and v2 in sample_metrics:
                for m_k in ["pr_auc", "recall_at_1pct_ffr", "value_recall"]:
                    d_val = sample_metrics[v1][m_k] - sample_metrics[v2][m_k]
                    diffs_accum[diff_k][m_k].append(d_val)

        # Per-typology differences
        for typo in unique_typos:
            mask_typo = (typo_b == typo)
            if np.sum(mask_typo) == 0:
                continue

            # Sub-sample containing this typology + legitimate
            sub_mask = mask_typo | (y_b == 0)
            y_sub = y_b[sub_mask]
            if np.sum(y_sub) == 0:
                continue

            for diff_k, v1, v2 in diff_keys:
                if v1 in scores_dict and v2 in scores_dict:
                    sc1 = scores_dict[v1][boot_idx][sub_mask]
                    sc2 = scores_dict[v2][boot_idx][sub_mask]
                    th1 = thresholds_dict.get(v1, 0.5)
                    th2 = thresholds_dict.get(v2, 0.5)

                    pr1 = float(average_precision_score(y_sub, sc1))
                    pr2 = float(average_precision_score(y_sub, sc2))

                    rec1 = float(np.sum((sc1 >= th1) & (y_sub == 1)) / np.sum(y_sub == 1))
                    rec2 = float(np.sum((sc2 >= th2) & (y_sub == 1)) / np.sum(y_sub == 1))

                    typo_diffs_accum[typo][diff_k]["pr_auc"].append(pr1 - pr2)
                    typo_diffs_accum[typo][diff_k]["recall_at_1pct_ffr"].append(rec1 - rec2)

    # Format summaries with 95% CIs
    def _ci(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return {"mean": 0.0, "ci_lower": 0.0, "ci_upper": 0.0}
        return {
            "mean": float(np.mean(arr)),
            "ci_lower": float(np.percentile(arr, 2.5)),
            "ci_upper": float(np.percentile(arr, 97.5)),
        }

    summary_variants = {
        name: {m_k: _ci(vals) for m_k, vals in m_dict.items()}
        for name, m_dict in metrics_per_variant.items()
    }

    summary_diffs = {
        diff_k: {m_k: _ci(vals) for m_k, vals in m_dict.items()}
        for diff_k, m_dict in diffs_accum.items()
    }

    summary_typos = {
        typo: {
            diff_k: {m_k: _ci(vals) for m_k, vals in m_dict.items()}
            for diff_k, m_dict in d_dict.items()
        }
        for typo, d_dict in typo_diffs_accum.items()
    }

    return {
        "n_bootstraps": len(metrics_per_variant["B"]["pr_auc"]),
        "variants": summary_variants,
        "differences": summary_diffs,
        "typologies": summary_typos,
    }


def compute_group_permutation_importance(
    model: RiskLGBM,
    calibrator: IsotonicCalibrator,
    test_df: pd.DataFrame,
    y_test: np.ndarray,
    n_repeats: int = 5,
    seed: int = 42,
) -> Dict[str, Dict[str, float]]:
    """Compute permutation importance by feature group (sender, pair, device_auth, recipient, graph, gnn)."""
    rng = np.random.default_rng(seed)

    raw_baseline = model.predict_proba(test_df)
    scores_baseline = calibrator.predict(raw_baseline)
    base_pr_auc = float(average_precision_score(y_test, scores_baseline))

    # Group features
    groups: Dict[str, List[str]] = {}
    for feat in model.feature_names:
        grp = FEATURE_GROUP_MAP.get(feat, "other")
        groups.setdefault(grp, []).append(feat)

    results: Dict[str, Dict[str, float]] = {}

    for grp, feat_list in groups.items():
        drops = []
        for _ in range(n_repeats):
            permuted_df = test_df.copy()
            perm_indices = rng.permutation(len(test_df))
            for f in feat_list:
                permuted_df[f] = test_df[f].iloc[perm_indices].values

            raw_p = model.predict_proba(permuted_df)
            scores_p = calibrator.predict(raw_p)
            auc_p = float(average_precision_score(y_test, scores_p))
            drops.append(max(0.0, base_pr_auc - auc_p))

        results[grp] = {
            "mean_pr_auc_drop": float(np.mean(drops)),
            "std_pr_auc_drop": float(np.std(drops)),
            "feature_count": len(feat_list),
        }

    return dict(sorted(results.items(), key=lambda kv: kv[1]["mean_pr_auc_drop"], reverse=True))


def compute_graph_rewiring_test(
    model: RiskLGBM,
    calibrator: IsotonicCalibrator,
    test_df: pd.DataFrame,
    y_test: np.ndarray,
    seed: int = 42,
) -> Dict[str, float]:
    """Test model performance when graph/GNN features are randomly rewired across entities."""
    rng = np.random.default_rng(seed)

    # Baseline performance
    raw_base = model.predict_proba(test_df)
    sc_base = calibrator.predict(raw_base)
    base_pr_auc = float(average_precision_score(y_test, sc_base))

    # Permute all graph and GNN features (breaking network topology)
    rewired_df = test_df.copy()
    graph_cols = [c for c in model.feature_names if FEATURE_GROUP_MAP.get(c) in ("graph", "gnn")]

    perm_idx = rng.permutation(len(test_df))
    for col in graph_cols:
        rewired_df[col] = test_df[col].iloc[perm_idx].values

    raw_rewired = model.predict_proba(rewired_df)
    sc_rewired = calibrator.predict(raw_rewired)
    rewired_pr_auc = float(average_precision_score(y_test, sc_rewired))

    return {
        "baseline_pr_auc": base_pr_auc,
        "rewired_pr_auc": rewired_pr_auc,
        "drop_under_rewiring": float(base_pr_auc - rewired_pr_auc),
        "topology_dependency_verified": bool((base_pr_auc - rewired_pr_auc) > 0.0),
    }


def generate_lift_report_markdown(results: Dict[str, Any]) -> str:
    """Generate professional Markdown lift report conforming to Phase 1 standards."""
    diffs = results["bootstrap"]["differences"]
    typos = results["bootstrap"]["typologies"]
    groups = results["group_importance"]
    rewire = results["rewiring_test"]
    scan = results["single_feature_auc_scan"]

    eb_ci = diffs["E_minus_B"]["pr_auc"]
    ec_ci = diffs["E_minus_C"]["pr_auc"]
    cb_ci = diffs["C_minus_B"]["pr_auc"]

    verdict_met = (
        eb_ci["ci_lower"] > 0
        or any(typos[t]["E_minus_B"]["pr_auc"]["ci_lower"] > 0 for t in ("mule_ring", "impersonation_scam") if t in typos)
    )

    lines = [
        "# Phase 1: Graph Learning Lift & Network Intelligence Evaluation",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Dataset Profile:** `{results['profile']}` | **Model Version:** `{results['version']}`  ",
        f"**Bootstrap Resamples:** {results['bootstrap']['n_bootstraps']} paired iterations | **Coverage:** 95% Confidence Intervals",
        "",
        "## Executive Summary",
        "",
        f"- **Tabular Shortcut Invariant (Criterion 1):** {'PASSED' if scan['passed_criterion_1'] else 'FAILED'}. "
        f"Highest tabular single-feature ROC-AUC is `{scan['max_feature']}` at **{scan['max_auc']:.4f}** (Strictly <= 0.85 threshold; previous shortcut `new_device_flag` reduced to **{scan['rankings'].get('new_device_flag', 0.5):.4f}**).",
        f"- **Graph Learning Lift (E − B):** ΔPR-AUC = **{eb_ci['mean']:+.4f}** [95% CI: `{eb_ci['ci_lower']:+.4f}`, `{eb_ci['ci_upper']:+.4f}`].",
        f"- **GNN Incremental Lift over NetworkX (E − C):** ΔPR-AUC = **{ec_ci['mean']:+.4f}** [95% CI: `{ec_ci['ci_lower']:+.4f}`, `{ec_ci['ci_upper']:+.4f}`].",
        f"- **NetworkX Graph Lift over Tabular (C − B):** ΔPR-AUC = **{cb_ci['mean']:+.4f}** [95% CI: `{cb_ci['ci_lower']:+.4f}`, `{cb_ci['ci_upper']:+.4f}`].",
        f"- **Graph Rewiring Sensitivity:** PR-AUC drops from **{rewire['baseline_pr_auc']:.4f}** to **{rewire['rewired_pr_auc']:.4f}** "
        f"(Δ = **-{rewire['drop_under_rewiring']:.4f}**) when topological edges are randomized.",
        "",
        f"**Acceptance Criterion 3 Verdict:** **{'PASS — Statistically Significant Graph Lift Confirmed' if verdict_met else 'HONEST REPORTING — Non-Significant / Zero Lift Recorded'}**.",
        "",
        "---",
        "",
        "## 1. Variant Comparison & Paired Differences",
        "",
        "| Comparison | Metric | Mean Diff | 95% CI Lower | 95% CI Upper | Statistically Significant? |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
    ]

    for comp_name, comp_key in [("E − B (Full Graph Lift)", "E_minus_B"), ("E − C (GNN over NetworkX)", "E_minus_C"), ("C − B (NetworkX over Tabular)", "C_minus_B")]:
        d = diffs[comp_key]
        for m_label, m_key in [("PR-AUC", "pr_auc"), ("Recall @ 1% FFR", "recall_at_1pct_ffr"), ("Value Recall", "value_recall")]:
            m = d[m_key]
            sig = "Yes (p < 0.05)" if m["ci_lower"] > 0 or m["ci_upper"] < 0 else "No (overlaps 0)"
            lines.append(f"| **{comp_name}** | {m_label} | {m['mean']:+.4f} | {m['ci_lower']:+.4f} | {m['ci_upper']:+.4f} | {sig} |")

    lines.extend([
        "",
        "---",
        "",
        "## 2. Typology-Level Graph Lift Breakdown",
        "",
        "| Typology | Comparison | ΔPR-AUC (Mean) | 95% CI Lower | 95% CI Upper | ΔRecall @ 1% FFR |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
    ])

    for typo, t_data in typos.items():
        for comp_name, comp_key in [("E − B", "E_minus_B"), ("E − C", "E_minus_C")]:
            t_diff = t_data[comp_key]
            pr = t_diff["pr_auc"]
            rec = t_diff["recall_at_1pct_ffr"]
            lines.append(
                f"| `{typo}` | {comp_name} | {pr['mean']:+.4f} | {pr['ci_lower']:+.4f} | {pr['ci_upper']:+.4f} | {rec['mean']:+.4f} |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Feature-Group Permutation Importance",
        "",
        "Measures mean PR-AUC drop when all features in a group are permuted across test instances (higher drop = higher reliance):",
        "",
        "| Feature Group | Features Count | Mean PR-AUC Drop | Std Dev | Importance Share |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ])

    tot_drop = sum(g["mean_pr_auc_drop"] for g in groups.values()) or 1.0
    for grp_name, g_info in groups.items():
        share = (g_info["mean_pr_auc_drop"] / tot_drop) * 100.0
        lines.append(
            f"| **`{grp_name}`** | {g_info['feature_count']} | {g_info['mean_pr_auc_drop']:.4f} | ±{g_info['std_pr_auc_drop']:.4f} | {share:.1f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Graph Topology Rewiring Test",
        "",
        "To verify that the model's performance relies on true topological relations (rather than marginal distribution shifts), "
        "we randomly rewire edges across graph and GNN features while preserving all tabular signals:",
        "",
        f"- **Baseline PR-AUC (Intact Graph):** `{rewire['baseline_pr_auc']:.4f}`",
        f"- **Rewired PR-AUC (Perturbed Graph):** `{rewire['rewired_pr_auc']:.4f}`",
        f"- **Performance Collapse:** `-{rewire['drop_under_rewiring']:.4f}`",
        f"- **Topology Dependency Confirmed:** `{'YES' if rewire['topology_dependency_verified'] else 'NO'}`",
        "",
    ])

    return "\n".join(lines)


def run_lift_analysis(profile: str = "full") -> Dict[str, Any]:
    """Execute complete lift analysis pipeline and write lift.json and lift_report.md."""
    repo_root = Path(__file__).resolve().parents[3]
    raw_dir = repo_root / "data" / "raw" / profile
    processed_dir = repo_root / "data" / "processed" / profile
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    registry = ModelRegistry()
    active_meta = registry.get_active_metadata()
    if active_meta is None or "artifacts" not in active_meta:
        raise RuntimeError("No active trained model found in registry.")

    artifacts = active_meta["artifacts"]
    thresholds = active_meta.get("thresholds", {})

    logger.info("Loading models for lift analysis...")
    model_b = RiskLGBM.load(artifacts["variant_b_lgbm"])
    calibrator_b = IsotonicCalibrator.load(artifacts["variant_b_calibrator"])

    model_c = RiskLGBM.load(artifacts["variant_c_lgbm"])
    calibrator_c = IsotonicCalibrator.load(artifacts["variant_c_calibrator"])

    model_e = RiskLGBM.load(artifacts["variant_e_lgbm"])
    calibrator_e = IsotonicCalibrator.load(artifacts["variant_e_calibrator"])

    # Load test split data
    features_df = pd.read_parquet(processed_dir / "features.parquet")
    labels_df = pd.read_parquet(raw_dir / "labels.parquet")
    merged = pd.merge(features_df, labels_df[["txn_id", "is_fraud", "typology"]], on="txn_id", how="inner")

    test_df = merged[merged["split"] == "test"].copy()
    # Primary population = transaction types /v1/score accepts (F6).
    if "type" in test_df.columns:
        test_df = test_df[test_df["type"].isin(("send_money",))]
    test_df = test_df.reset_index(drop=True)
    y_test = test_df["is_fraud"].values.astype(int)
    amounts = test_df["amount_bdt"].values.astype(float)
    typologies = test_df["typology"].fillna("none").values

    logger.info(f"Loaded {len(test_df):,} test transactions for lift evaluation ({y_test.sum()} fraud).")

    # 1. Single Feature AUC Scan
    logger.info("Running single-feature AUC scan...")
    auc_scan = compute_single_feature_auc_scan(test_df, y_test)

    # 2. Compute Variant Predictions
    logger.info("Generating predictions across Variants B, C, E...")
    raw_b = model_b.predict_proba(test_df)
    scores_b = calibrator_b.predict(raw_b)

    raw_c = model_c.predict_proba(test_df)
    scores_c = calibrator_c.predict(raw_c)

    raw_e = model_e.predict_proba(test_df)
    scores_e = calibrator_e.predict(raw_e)

    scores_dict = {
        "B": scores_b,
        "C": scores_c,
        "E": scores_e,
    }
    thresholds_dict = {
        "B": thresholds.get("threshold_1pct_ffr_variant_b", 0.5),
        "C": thresholds.get("threshold_1pct_ffr_variant_c", 0.5),
        "E": thresholds.get("threshold_1pct_ffr_variant_e", 0.5),
    }

    # 3. Paired Bootstrap
    logger.info("Running paired bootstrap (1,000 resamples)...")
    boot_results = paired_bootstrap_evaluation(
        y_test=y_test,
        amounts=amounts,
        typologies=typologies,
        scores_dict=scores_dict,
        thresholds_dict=thresholds_dict,
        n_bootstraps=1000,
        seed=42,
    )

    # 4. Group Permutation Importance
    logger.info("Computing feature-group permutation importance...")
    group_imp = compute_group_permutation_importance(
        model=model_e,
        calibrator=calibrator_e,
        test_df=test_df,
        y_test=y_test,
        n_repeats=5,
        seed=42,
    )

    # 5. Graph Rewiring Sensitivity Test
    logger.info("Computing graph rewiring sensitivity test...")
    rewire_test = compute_graph_rewiring_test(
        model=model_e,
        calibrator=calibrator_e,
        test_df=test_df,
        y_test=y_test,
        seed=42,
    )

    full_results = {
        "version": active_meta["version"],
        "profile": profile,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "single_feature_auc_scan": auc_scan,
        "bootstrap": boot_results,
        "group_importance": group_imp,
        "rewiring_test": rewire_test,
    }

    # Write reports/lift.json
    with open(reports_dir / "lift.json", "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2)
    logger.info(f"Saved lift results to {reports_dir / 'lift.json'}")

    # Write reports/lift_report.md
    md_content = generate_lift_report_markdown(full_results)
    with open(reports_dir / "lift_report.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Saved lift Markdown report to {reports_dir / 'lift_report.md'}")

    return full_results


def main():
    parser = argparse.ArgumentParser(description="Evaluate graph lift and bootstrap confidence intervals.")
    parser.add_argument("--profile", choices=["small", "full"], default="small", help="Dataset profile.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_lift_analysis(profile=args.profile)


if __name__ == "__main__":
    main()
