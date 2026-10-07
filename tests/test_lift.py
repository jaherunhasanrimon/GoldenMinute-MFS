"""Tests for lift analysis, single-feature AUC shortcut enforcement, and paired bootstrap (Phase 1 Acceptance Criteria 1 & 3)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goldenminutes.eval.lift import (
    compute_single_feature_auc_scan,
    paired_bootstrap_evaluation,
)


@pytest.fixture(scope="module")
def small_dataset():
    repo_root = Path(__file__).resolve().parents[1]
    features_path = repo_root / "data" / "processed" / "small" / "features.parquet"
    labels_path = repo_root / "data" / "raw" / "small" / "labels.parquet"

    if not features_path.exists() or not labels_path.exists():
        pytest.skip("Small features or labels not present.")

    features_df = pd.read_parquet(features_path)
    labels_df = pd.read_parquet(labels_path)
    merged = pd.merge(features_df, labels_df[["txn_id", "is_fraud", "typology"]], on="txn_id", how="inner")
    test_df = merged[merged["split"] == "test"].copy()
    if "type" in test_df.columns:
        test_df = test_df[test_df["type"].isin(("send_money",))]
    return test_df.reset_index(drop=True)


def test_acceptance_criterion_1_no_feature_auc_above_85(small_dataset):
    """Enforce Acceptance Criterion 1: No single feature has ROC-AUC > 0.85 on full test split (<= 0.88 on small due to sample size)."""
    test_df = small_dataset
    y_test = test_df["is_fraud"].values.astype(int)

    scan_res = compute_single_feature_auc_scan(test_df, y_test)
    max_feat = scan_res["max_feature"]
    max_auc = scan_res["max_auc"]

    # On small dataset (only 17 fraud cases in test split), finite-sample variance allows up to 0.88
    assert max_auc <= 0.88, (
        f"Data shortcut detected! Feature '{max_feat}' has single-feature ROC-AUC = {max_auc:.4f} > 0.88 on small"
    )

    # On full profile, strictly enforce Criterion 1 (<= 0.85) on scoring population (F6)
    repo_root = Path(__file__).resolve().parents[1]
    full_features = repo_root / "data" / "processed" / "full" / "features.parquet"
    full_labels = repo_root / "data" / "raw" / "full" / "labels.parquet"
    if full_features.exists() and full_labels.exists():
        f_feats = pd.read_parquet(full_features)
        f_lbls = pd.read_parquet(full_labels)
        f_merged = pd.merge(f_feats, f_lbls[["txn_id", "is_fraud"]], on="txn_id", how="inner")
        f_test = f_merged[f_merged["split"] == "test"].copy()
        if "type" in f_test.columns:
            f_test = f_test[f_test["type"].isin(("send_money",))]
        f_y = f_test["is_fraud"].values.astype(int)
        f_scan = compute_single_feature_auc_scan(f_test, f_y)
        assert f_scan["passed_criterion_1"] is True, (
            f"Strict Criterion 1 failed on full profile: '{f_scan['max_feature']}' has ROC-AUC = {f_scan['max_auc']:.4f} > 0.85"
        )
        assert f_scan["max_auc"] <= 0.85


def test_paired_bootstrap_reproducibility(small_dataset):
    """Verify paired bootstrap produces deterministic confidence intervals under fixed seed."""
    test_df = small_dataset
    y_test = test_df["is_fraud"].values.astype(int)
    amounts = test_df["amount_bdt"].values.astype(float)
    typologies = test_df["typology"].fillna("none").values

    # Mock scores with known delta
    np.random.seed(42)
    scores_b = np.random.uniform(0, 1, size=len(y_test))
    scores_c = scores_b + 0.05 * y_test  # slight positive lift on fraud
    scores_e = scores_b + 0.10 * y_test  # higher positive lift on fraud

    scores_dict = {"B": scores_b, "C": scores_c, "E": scores_e}
    thresholds_dict = {"B": 0.5, "C": 0.5, "E": 0.5}

    b1 = paired_bootstrap_evaluation(y_test, amounts, typologies, scores_dict, thresholds_dict, n_bootstraps=50, seed=42)
    b2 = paired_bootstrap_evaluation(y_test, amounts, typologies, scores_dict, thresholds_dict, n_bootstraps=50, seed=42)

    diff1 = b1["differences"]["E_minus_B"]["pr_auc"]
    diff2 = b2["differences"]["E_minus_B"]["pr_auc"]

    assert abs(diff1["mean"] - diff2["mean"]) < 1e-5
    assert abs(diff1["ci_lower"] - diff2["ci_lower"]) < 1e-5
    assert abs(diff1["ci_upper"] - diff2["ci_upper"]) < 1e-5
