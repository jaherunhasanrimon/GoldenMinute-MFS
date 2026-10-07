"""Point-in-time online vs offline feature parity tests (C9).

Verifies that OnlineFeatureStore produces identical feature values to OfflineFeatureBuilder
on at least 5,000 sampled transactions, including first-ever transactions and wallets with no prior history.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goldenminutes.features.online import OnlineFeatureStore
from goldenminutes.features.specs import FEATURE_NAMES, VARIANT_E_FEATURE_NAMES
from goldenminutes.models.embedding_store import InMemoryEmbeddingStore


@pytest.fixture(scope="module")
def dataset_paths():
    """Locate available raw and processed datasets (prefer small for fast test execution, fallback to full)."""
    repo_root = Path(__file__).resolve().parents[1]
    raw_small = repo_root / "data" / "raw" / "small"
    proc_small = repo_root / "data" / "processed" / "small" / "features.parquet"

    raw_full = repo_root / "data" / "raw" / "full"
    proc_full = repo_root / "data" / "processed" / "full" / "features.parquet"

    if raw_small.exists() and proc_small.exists():
        return raw_small, proc_small
    elif raw_full.exists() and proc_full.exists():
        return raw_full, proc_full
    pytest.skip("Neither small nor full processed dataset available for parity test.")


def test_online_offline_feature_parity_5000(dataset_paths):
    """Test parity across 5,000+ sampled transactions."""
    raw_dir, proc_path = dataset_paths

    wallets = pd.read_parquet(raw_dir / "wallets.parquet")
    auth_events = pd.read_parquet(raw_dir / "auth_events.parquet")
    confirmations = pd.read_parquet(raw_dir / "confirmations.parquet")
    txns = pd.read_parquet(raw_dir / "transactions.parquet").sort_values(["ts", "txn_id"]).reset_index(drop=True)
    off_feats = pd.read_parquet(proc_path)

    store = OnlineFeatureStore()
    gnn_store_path = proc_path.parent / "gnn_embeddings.parquet"
    if gnn_store_path.exists():
        store.set_embedding_store(InMemoryEmbeddingStore.load(gnn_store_path))

    for _, r in wallets.iterrows():
        store.register_wallet(r["wallet_id"], r["opened_at"], r["owner_type"])
    for _, r in auth_events.iterrows():
        store.register_auth_event(r["wallet_id"], r["event_type"], r["ts"])
    for _, r in confirmations.iterrows():
        store.register_confirmation(r["wallet_id"], r["confirmed_at"])

    n_txns = len(txns)
    sample_size = min(5000, n_txns)

    np.random.seed(42)
    # Always include the very first 500 transactions (first-ever txns, zero history)
    sample_indices = set(range(min(500, n_txns)))
    # Randomly sample remaining
    remaining = min(n_txns, 8000)
    sample_indices.update(np.random.choice(remaining, size=min(sample_size, remaining), replace=False))
    sample_set = set(sample_indices)
    max_idx = max(sample_set)

    mismatches = 0
    checked_count = 0

    features_to_check = VARIANT_E_FEATURE_NAMES if gnn_store_path.exists() else FEATURE_NAMES

    for idx in range(max_idx + 1):
        row = txns.iloc[idx]
        if idx in sample_set:
            on_f = store.features(row)
            off_row = off_feats.iloc[idx]
            checked_count += 1

            for fn in features_to_check:
                ov = float(off_row[fn])
                nv = float(on_f[fn])
                diff = abs(ov - nv)
                if diff > 1e-4:
                    mismatches += 1
                    assert diff <= 1e-4, f"Mismatch at idx {idx} for feature '{fn}': offline={ov}, online={nv}"

        store.update(row)

    assert checked_count >= min(5000, n_txns), f"Expected at least 5000 sampled transactions, checked {checked_count}"
    assert mismatches == 0, f"Found {mismatches} feature mismatches between online and offline extractors"


def test_online_features_brand_new_wallet():
    """Verify that a transaction with a brand new, unseen sender and recipient does not crash and produces defaults."""
    store = OnlineFeatureStore()
    txn = {
        "txn_id": "T_NEW_001",
        "ts": "2026-03-01T12:00:00+00:00",
        "sender_wallet_id": "W_UNSEEN_SENDER",
        "recipient_wallet_id": "W_UNSEEN_RECIPIENT",
        "amount_bdt": 1500.0,
        "balance_before": 2000.0,
        "device_id": "DEV_NEW",
        "session_seconds": 45,
    }

    feats = store.features(txn)
    assert len(feats) == len(VARIANT_E_FEATURE_NAMES)
    assert feats["is_first_time_pair"] == 1
    assert feats["pair_history_count"] == 0
    assert feats["new_device_flag"] == 1
    assert feats["amount_to_median_ratio"] == 1.0
    assert feats["sender_txn_count_1h"] == 0
    assert feats["sender_txn_count_24h"] == 0
    assert feats["recipient_unique_senders_1h"] == 0
    assert feats["component_size_7d"] == 1
    assert feats["two_hop_confirmed_mule_share"] == 0.0
    assert feats["gnn_recipient_mule_score"] == 0.0
    assert feats["gnn_sender_mule_score"] == 0.0
    assert feats["gnn_recipient_emb_0"] == 0.0
