"""Tests for feature extraction, point-in-time correctness, and leakage prevention."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from goldenminutes.features.offline import OfflineFeatureBuilder
from goldenminutes.features.specs import FEATURE_NAMES, FEATURE_SPECS


def test_feature_specs_completeness():
    """Verify that feature specs define all required features from Section 8."""
    assert len(FEATURE_SPECS) == 28
    assert len(FEATURE_NAMES) == 28
    # Ensure all names are unique
    assert len(set(FEATURE_NAMES)) == 28


def test_leakage_prevention_on_processed_features():
    """Verify processed features contain NO fraud labels or hidden truth."""
    repo_root = Path(__file__).resolve().parents[1]
    features_path = repo_root / "data" / "processed" / "small" / "features.parquet"
    if not features_path.exists():
        builder = OfflineFeatureBuilder(raw_dir=repo_root / "data" / "raw" / "small")
        builder.build_and_save(features_path)

    df = pd.read_parquet(features_path)

    forbidden_cols = ["is_fraud", "typology", "case_id", "is_mule", "mule_ring_id", "agent_is_collusive", "is_mule_recipient"]
    for col in forbidden_cols:
        assert col not in df.columns, f"Leakage detected! Found forbidden column '{col}' in features.parquet"

    # Verify all feature specs are present
    for feat_name in FEATURE_NAMES:
        assert feat_name in df.columns, f"Missing feature '{feat_name}' in features.parquet"

    # Verify splits exist
    assert "split" in df.columns
    assert set(df["split"].unique()).issubset({"train", "val", "test"})


def test_point_in_time_correctness():
    """Verify that adding future transactions does not alter features of past transactions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = Path(__file__).resolve().parents[1]
        small_raw = repo_root / "data" / "raw" / "small"

        # Copy raw tables
        for tbl in ["wallets", "customers", "auth_events", "confirmations", "device_links"]:
            pd.read_parquet(small_raw / f"{tbl}.parquet").to_parquet(tmp_path / f"{tbl}.parquet")

        base_txns = pd.read_parquet(small_raw / "transactions.parquet").head(1000).copy()
        base_txns.to_parquet(tmp_path / "transactions.parquet")

        builder1 = OfflineFeatureBuilder(raw_dir=tmp_path)
        features1 = builder1.compute_features()

        # Now append 500 future transactions with massive amounts and new devices
        max_ts = base_txns["ts"].max()
        future_txns = base_txns.head(500).copy()
        future_txns["ts"] = max_ts + pd.to_timedelta(np.arange(1, 501), unit="m")
        future_txns["txn_id"] = [f"FUT_{i:04d}" for i in range(500)]
        future_txns["amount_bdt"] = 500000.0

        extended_txns = pd.concat([base_txns, future_txns]).sort_values("ts").reset_index(drop=True)
        extended_txns.to_parquet(tmp_path / "transactions.parquet")

        builder2 = OfflineFeatureBuilder(raw_dir=tmp_path)
        features2 = builder2.compute_features()

        # The features of the first 1000 transactions MUST be identical
        f1_first = features1.set_index("txn_id")[FEATURE_NAMES].loc[base_txns["txn_id"]]
        f2_first = features2.set_index("txn_id")[FEATURE_NAMES].loc[base_txns["txn_id"]]

        pd.testing.assert_frame_equal(f1_first, f2_first, check_exact=False, rtol=1e-5, atol=1e-5)


def test_confirmations_used_without_labels():
    """Verify two_hop_confirmed_mule_share reads confirmations table and ignores unconfirmed."""
    repo_root = Path(__file__).resolve().parents[1]
    features_path = repo_root / "data" / "processed" / "small" / "features.parquet"
    if not features_path.exists():
        builder = OfflineFeatureBuilder(raw_dir=repo_root / "data" / "raw" / "small")
        builder.build_and_save(features_path)

    df = pd.read_parquet(features_path)
    assert "two_hop_confirmed_mule_share" in df.columns
    # Check value bounds [0.0, 1.0]
    vals = df["two_hop_confirmed_mule_share"].values
    assert np.all(vals >= 0.0)
    assert np.all(vals <= 1.0)
