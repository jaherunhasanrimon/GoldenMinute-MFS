"""Validation tests for the GoldenMinutes synthetic data simulator.

Checks referential integrity, monotone timestamps, deterministic generation,
leakage separation, legitimate confounders, and raw feature AUC bounds.
"""

import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from goldenminutes.common.config import PROJECT_ROOT
from goldenminutes.simulator.generate import generate_dataset


@pytest.fixture(scope="module")
def small_dataset():
    """Ensure small dataset is generated once for the test module."""
    raw_dir = PROJECT_ROOT / "data" / "raw" / "small"
    if not (raw_dir / "transactions.parquet").exists():
        generate_dataset(profile_name="small", seed=42)

    return {
        "customers": pd.read_parquet(raw_dir / "customers.parquet"),
        "wallets": pd.read_parquet(raw_dir / "wallets.parquet"),
        "agents": pd.read_parquet(raw_dir / "agents.parquet"),
        "device_links": pd.read_parquet(raw_dir / "device_links.parquet"),
        "auth_events": pd.read_parquet(raw_dir / "auth_events.parquet"),
        "transactions": pd.read_parquet(raw_dir / "transactions.parquet"),
        "labels": pd.read_parquet(raw_dir / "labels.parquet"),
        "hidden_truth": pd.read_parquet(raw_dir / "hidden_truth.parquet"),
        "confirmations": pd.read_parquet(raw_dir / "confirmations.parquet"),
    }


def test_schema_compatibility(small_dataset):
    txns = small_dataset["transactions"]
    expected_cols = [
        "txn_id", "ts", "type", "sender_wallet_id", "recipient_wallet_id",
        "agent_id", "amount_bdt", "channel", "device_id", "session_seconds",
        "balance_before"
    ]
    for col in expected_cols:
        assert col in txns.columns, f"Missing canonical transaction column: {col}"

    labels = small_dataset["labels"]
    for col in ["txn_id", "is_fraud", "typology", "case_id", "is_mule_recipient"]:
        assert col in labels.columns, f"Missing canonical label column: {col}"

    confirmations = small_dataset["confirmations"]
    for col in ["wallet_id", "confirmed_at", "source"]:
        assert col in confirmations.columns, f"Missing confirmation column: {col}"


def test_leakage_separation(small_dataset):
    txns = small_dataset["transactions"]
    # Model features must not contain ground-truth flags
    forbidden = ["is_fraud", "typology", "fraud_type", "mule_account", "is_mule", "is_mule_recipient"]
    for col in forbidden:
        assert col not in txns.columns, f"Data leakage detected! '{col}' present in transactions"


def test_held_out_typology_not_in_confirmations(small_dataset):
    labels = small_dataset["labels"]
    txns = small_dataset["transactions"]
    confirmations = small_dataset["confirmations"]

    # Wallets solely associated with agent_collusion must NEVER appear in confirmations
    merged = labels.merge(txns[["txn_id", "recipient_wallet_id"]], on="txn_id")
    collusion_wallets = set(merged[merged["typology"] == "agent_collusion"]["recipient_wallet_id"].dropna())
    other_fraud_wallets = set(merged[(merged["is_fraud"] == 1) & (merged["typology"] != "agent_collusion")]["recipient_wallet_id"].dropna())

    only_collusion_wallets = collusion_wallets - other_fraud_wallets
    confirmed_wallets = set(confirmations["wallet_id"])

    assert len(only_collusion_wallets.intersection(confirmed_wallets)) == 0, \
        "Held-out typology wallets were leaked into confirmations!"


def test_referential_integrity(small_dataset):
    txns = small_dataset["transactions"]
    wallets = set(small_dataset["wallets"]["wallet_id"])
    agents = set(small_dataset["agents"]["agent_id"])

    # All non-card sender wallets must exist in wallets table
    customer_senders = txns[~txns["sender_wallet_id"].str.startswith("CARD_")]["sender_wallet_id"]
    missing_senders = set(customer_senders) - wallets
    assert len(missing_senders) == 0, f"Foreign key violation: missing sender wallets: {len(missing_senders)}"

    # All recipient wallets must exist in wallets table
    recipients = txns["recipient_wallet_id"].dropna()
    missing_recipients = set(recipients) - wallets
    assert len(missing_recipients) == 0, f"Foreign key violation: missing recipient wallets: {len(missing_recipients)}"

    # Non-null agent IDs must exist in agents table
    txn_agents = txns["agent_id"].dropna()
    missing_agents = set(txn_agents) - agents
    assert len(missing_agents) == 0, f"Foreign key violation: missing agents: {len(missing_agents)}"


def test_monotone_timestamps(small_dataset):
    txns = small_dataset["transactions"]
    # Overall dataframe must be ordered by timestamp
    assert txns["ts"].is_monotonic_increasing, "Transactions are not globally monotonically ordered by ts!"


def test_deterministic_generation():
    # Run small with seed 99 twice and compare sha256
    res1 = generate_dataset(profile_name="small", seed=99)
    res2 = generate_dataset(profile_name="small", seed=99)
    assert res1["hashes"] == res2["hashes"], "Deterministic generation failed: file hashes differed for identical seed!"


def test_fraud_share_and_typologies_on_small(small_dataset):
    labels = small_dataset["labels"]
    fraud_rate = labels["is_fraud"].mean()
    # Required: roughly 0.2 - 1.0% on small
    assert 0.002 <= fraud_rate <= 0.012, f"Fraud rate {fraud_rate:.4f} outside expected range [0.002, 0.012]"

    # Each typology must have at least 30 positive transactions on small
    counts = labels[labels["is_fraud"] == 1]["typology"].value_counts().to_dict()
    for typ in ["impersonation_scam", "mule_ring", "sim_swap_takeover", "card_to_wallet_burst", "agent_collusion"]:
        assert typ in counts, f"Missing typology: {typ}"
        assert counts[typ] >= 30, f"Typology {typ} has only {counts[typ]} positives (required >= 30)"


def test_legitimate_confounders_present(small_dataset):
    txns = small_dataset["transactions"]
    labels = small_dataset["labels"]
    merged = txns.merge(labels[["txn_id", "is_fraud"]], on="txn_id")

    # 1. Legitimate large sends (> 15,000 BDT) must exist
    legit_large = merged[(merged["is_fraud"] == 0) & (merged["amount_bdt"] >= 15000)]
    assert len(legit_large) > 10, "Confounder missing: not enough legitimate large sends (>15,000 BDT)"

    # 2. Legitimate merchant payments exist
    merch_txns = merged[(merged["is_fraud"] == 0) & (merged["type"] == "merchant_pay")]
    assert len(merch_txns) > 50, "Confounder missing: high fan-in merchant payments missing"


def test_no_single_raw_column_auc_over_85(small_dataset):
    txns = small_dataset["transactions"]
    labels = small_dataset["labels"]
    merged = txns.merge(labels[["txn_id", "is_fraud"]], on="txn_id")

    y_true = merged["is_fraud"].values

    # Test amount
    auc_amount = roc_auc_score(y_true, merged["amount_bdt"].values)
    auc_amount = max(auc_amount, 1.0 - auc_amount)
    assert auc_amount <= 0.85, f"Pitfall! amount_bdt has trivial separation AUC: {auc_amount:.3f} > 0.85"

    # Test session seconds
    auc_session = roc_auc_score(y_true, merged["session_seconds"].values)
    auc_session = max(auc_session, 1.0 - auc_session)
    assert auc_session <= 0.85, f"Pitfall! session_seconds has trivial separation AUC: {auc_session:.3f} > 0.85"

    # Test balance before
    auc_balance = roc_auc_score(y_true, merged["balance_before"].values)
    auc_balance = max(auc_balance, 1.0 - auc_balance)
    assert auc_balance <= 0.85, f"Pitfall! balance_before has trivial separation AUC: {auc_balance:.3f} > 0.85"

    # Test hour of day
    hours = merged["ts"].dt.hour.values
    auc_hour = roc_auc_score(y_true, hours)
    auc_hour = max(auc_hour, 1.0 - auc_hour)
    assert auc_hour <= 0.85, f"Pitfall! hour has trivial separation AUC: {auc_hour:.3f} > 0.85"
