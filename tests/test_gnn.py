"""Tests for MuleGraphSAGE, semi-supervised graph training, and leakage prevention (Phase 1 Acceptance Criterion 2)."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from goldenminutes.models.embedding_store import InMemoryEmbeddingStore
from goldenminutes.models.gnn import (
    build_and_populate_embedding_store,
    train_graphsage,
)


@pytest.fixture(scope="module")
def small_raw_dir():
    repo_root = Path(__file__).resolve().parents[1]
    raw_dir = repo_root / "data" / "raw" / "small"
    if not (raw_dir / "transactions.parquet").exists():
        pytest.skip("data/raw/small not generated.")
    return raw_dir


def test_gnn_seeded_determinism(small_raw_dir):
    """(a) Seeded determinism: Two runs with seed=42 produce identical model weights and scores."""
    wallets_df = pd.read_parquet(small_raw_dir / "wallets.parquet")
    txns_df = pd.read_parquet(small_raw_dir / "transactions.parquet")
    conf_df = pd.read_parquet(small_raw_dir / "confirmations.parquet")
    min_ts = pd.to_datetime(txns_df["ts"].min(), utc=True)
    train_end_ts = min_ts + pd.Timedelta(days=15)

    m1, mean1, std1 = train_graphsage(wallets_df, txns_df, conf_df, train_end_ts, seed=42, epochs=20)
    m2, mean2, std2 = train_graphsage(wallets_df, txns_df, conf_df, train_end_ts, seed=42, epochs=20)

    # Verify normalization stats
    np.testing.assert_allclose(mean1, mean2, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(std1, std2, rtol=1e-5, atol=1e-5)

    # Verify model parameters
    for p1, p2 in zip(m1.parameters(), m2.parameters(), strict=True):
        torch.testing.assert_close(p1, p2, rtol=1e-5, atol=1e-5)


def test_gnn_leakage_prevention(small_raw_dir):
    """(b) Leakage prevention: Training reads ONLY confirmations (confirmed_at <= snapshot_end).

    Never reads labels.parquet or hidden_truth.parquet.
    Altering future confirmations (after snapshot_end) produces zero change in snapshot embeddings.
    """
    wallets_df = pd.read_parquet(small_raw_dir / "wallets.parquet")
    txns_df = pd.read_parquet(small_raw_dir / "transactions.parquet")
    conf_df = pd.read_parquet(small_raw_dir / "confirmations.parquet")

    min_ts = pd.to_datetime(txns_df["ts"].min(), utc=True)
    snap_end_ts = min_ts + pd.Timedelta(days=10)

    # Run 1: Original confirmations
    m1, mean1, std1 = train_graphsage(wallets_df, txns_df, conf_df, snap_end_ts, seed=42, epochs=15)

    # Run 2: Confirmed mules added FAR IN THE FUTURE (day 25)
    future_conf = conf_df.copy()
    future_rows = pd.DataFrame(
        [
            {"wallet_id": "WAL000001", "confirmed_at": min_ts + pd.Timedelta(days=25)},
            {"wallet_id": "WAL000002", "confirmed_at": min_ts + pd.Timedelta(days=26)},
        ]
    )
    future_conf = pd.concat([future_conf, future_rows], ignore_index=True)

    m2, mean2, std2 = train_graphsage(wallets_df, txns_df, future_conf, snap_end_ts, seed=42, epochs=15)

    # Parameters must be strictly identical because future confirmations were ignored
    np.testing.assert_allclose(mean1, mean2, rtol=1e-5, atol=1e-5)
    for p1, p2 in zip(m1.parameters(), m2.parameters(), strict=True):
        torch.testing.assert_close(p1, p2, rtol=1e-5, atol=1e-5)


def test_gnn_point_in_time_future_edge_invariance(small_raw_dir):
    """(c) Point-in-time correctness: Appending future transactions/edges does not alter past embeddings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Copy tables
        for tbl in ["wallets", "customers", "auth_events", "confirmations", "device_links"]:
            pd.read_parquet(small_raw_dir / f"{tbl}.parquet").to_parquet(tmp_path / f"{tbl}.parquet")

        base_txns = pd.read_parquet(small_raw_dir / "transactions.parquet").head(2000).copy()
        base_txns.to_parquet(tmp_path / "transactions.parquet")

        store1 = build_and_populate_embedding_store(raw_dir=tmp_path, seed=42)

        # Pick day 5 records from store1
        day5_scores_1 = {w: store1.get_wallet_mule_score(5, w) for (_, w) in store1.scores if _ == 5}
        assert len(day5_scores_1) > 0

        # Now append future transactions at day 20
        max_ts = base_txns["ts"].max()
        future_txns = base_txns.head(500).copy()
        future_txns["ts"] = max_ts + pd.to_timedelta(np.arange(1, 501), unit="m")
        future_txns["txn_id"] = [f"FUT_{i:04d}" for i in range(500)]
        extended = pd.concat([base_txns, future_txns]).sort_values("ts").reset_index(drop=True)
        extended.to_parquet(tmp_path / "transactions.parquet")

        store2 = build_and_populate_embedding_store(raw_dir=tmp_path, seed=42)
        day5_scores_2 = {w: store2.get_wallet_mule_score(5, w) for w in day5_scores_1}

        # Scores on past day 5 must remain equal
        for w, s1 in day5_scores_1.items():
            s2 = day5_scores_2[w]
            assert abs(s1 - s2) <= 1e-4, f"Past score changed for wallet {w} on day 5: {s1} vs {s2}"


def test_gnn_online_offline_store_parity(small_raw_dir):
    """(d) Online/offline parity: Queries from InMemoryEmbeddingStore match saved Parquet store exactly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "test_store.parquet"
        store = build_and_populate_embedding_store(raw_dir=small_raw_dir, output_store_path=store_path, seed=42)

        loaded_store = InMemoryEmbeddingStore.load(store_path)

        assert len(store.scores) == len(loaded_store.scores)
        sample_keys = list(store.scores.keys())[:100]
        for day, w_id in sample_keys:
            s1 = store.get_wallet_mule_score(day, w_id)
            s2 = loaded_store.get_wallet_mule_score(day, w_id)
            assert s1 == s2

            e1 = store.get_wallet_embedding(day, w_id)
            e2 = loaded_store.get_wallet_embedding(day, w_id)
            np.testing.assert_array_equal(e1, e2)

        # Unseen wallet defaults match
        assert loaded_store.get_wallet_mule_score(99, "UNSEEN") == 0.0
        np.testing.assert_array_equal(loaded_store.get_wallet_embedding(99, "UNSEEN"), np.zeros(4, dtype=np.float32))
