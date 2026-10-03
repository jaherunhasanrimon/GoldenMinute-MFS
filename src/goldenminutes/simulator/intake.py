"""Dataset intake and normalization layer.

Discovers supplied synthetic dataset, preserves raw files in data/raw_source/,
and normalizes records into canonical schemas (ARCHITECTURE.md Section 6).
"""

import logging
import shutil
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.common.config import PROJECT_ROOT

logger = logging.getLogger("goldenminutes.simulator.intake")

RAW_SOURCE_DIR = PROJECT_ROOT / "data" / "raw_source"
BOOTSTRAP_SOURCE_DIR = PROJECT_ROOT / "goldentimes_synthetic_dataset"

# District to region_type mapping
URBAN_DISTRICTS = {"Dhaka", "Chittagong", "Chattogram", "Gazipur", "Narayanganj"}
SEMI_URBAN_DISTRICTS = {
    "Sylhet", "Rajshahi", "Khulna", "Barisal", "Comilla", "Cumilla",
    "Mymensingh", "Brahmanbaria", "Bogra", "Bogura", "Jessore", "Dinajpur"
}


def map_district_to_region(district: Optional[str]) -> str:
    if not district or pd.isna(district):
        return "semi_urban"
    d = str(district).strip()
    if d in URBAN_DISTRICTS:
        return "urban"
    elif d in SEMI_URBAN_DISTRICTS:
        return "semi_urban"
    return "rural"


def map_age_to_band(age: Optional[float]) -> str:
    if age is None or pd.isna(age):
        return "middle"
    age = float(age)
    if age < 25:
        return "young"
    elif age <= 50:
        return "middle"
    return "senior"


def map_typology_name(raw_type: str) -> str:
    mapping = {
        "relative_emergency_scam": "impersonation_scam",
        "account_takeover": "sim_swap_takeover",
        "mule_account": "impersonation_scam",
        "mule_ring": "mule_ring",
        "card_to_wallet_burst": "card_to_wallet_burst",
        "agent_collusion": "agent_collusion",
        "none": "none",
    }
    return mapping.get(str(raw_type).strip(), str(raw_type).strip())


def discover_and_preserve_source(source_dir: Optional[Path] = None) -> Path:
    """Discover raw source dataset and copy to data/raw_source/ without modifying source."""
    src = source_dir or BOOTSTRAP_SOURCE_DIR
    if not src.exists():
        raise FileNotFoundError(f"Bootstrap dataset not found at {src}")

    RAW_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    csv_files = list(src.glob("*.csv")) + list(src.glob("*.json"))
    for file in csv_files:
        dest = RAW_SOURCE_DIR / file.name
        if not dest.exists():
            shutil.copy2(file, dest)

    logger.info("Preserved %d source files in %s", len(csv_files), RAW_SOURCE_DIR)
    return RAW_SOURCE_DIR


def normalize_customers(source_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(source_dir / "customers.csv")
    out = pd.DataFrame()
    out["customer_id"] = df["customer_id"].astype(str)
    out["age_band"] = df["age"].apply(map_age_to_band)
    out["region_type"] = df["district"].apply(map_district_to_region)

    # Map persona
    persona_map = {
        "low": "salaried",
        "medium": "small_trader",
        "high": "student",
        "very_high": "remittance_receiver",
    }
    out["persona"] = df["risk_profile"].map(persona_map).fillna("salaried")

    # Registered at
    reg_dates = pd.to_datetime(df["registration_date"], errors="coerce")
    fallback_date = pd.Timestamp("2022-01-01", tz="UTC")
    out["registered_at"] = reg_dates.dt.tz_localize("UTC").fillna(fallback_date)
    out["kyc_level"] = np.where(df["account_age_days"] > 365, "full", "basic")

    return out


def normalize_agents(source_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(source_dir / "agents.csv")
    out = pd.DataFrame()
    out["agent_id"] = df["agent_id"].astype(str)
    out["region_type"] = df["district"].apply(map_district_to_region)
    ref_date = pd.Timestamp("2026-06-30", tz="UTC")
    out["opened_at"] = ref_date - pd.to_timedelta(df["agent_age_days"].fillna(365), unit="D")
    return out


def normalize_wallets(source_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(source_dir / "wallets.csv")
    out = pd.DataFrame()
    out["wallet_id"] = df["wallet_id"].astype(str)
    out["customer_id"] = df["customer_id"].astype(str)
    out["owner_type"] = "customer"
    ref_date = pd.Timestamp("2026-06-30", tz="UTC")
    out["opened_at"] = ref_date - pd.to_timedelta(df["account_age_days"].fillna(180), unit="D")
    out["opened_via_agent_id"] = df["primary_agent_id"].astype(str)
    out["status"] = df["wallet_status"].astype(str)
    return out


def normalize_device_links(source_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(source_dir / "devices_wallets.csv")
    out = pd.DataFrame()
    out["wallet_id"] = df["wallet_id"].astype(str)
    out["device_id"] = df["device_id"].astype(str)
    out["first_seen_at"] = pd.to_datetime(df["first_seen"]).dt.tz_localize("UTC")
    out["last_seen_at"] = pd.to_datetime(df["last_seen"]).dt.tz_localize("UTC")
    return out


def normalize_transactions_and_labels(
    source_dir: Path,
    target_fraud_rate: Optional[float] = None,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Extract canonical transactions (sanitized) and isolated ground-truth labels."""
    df = pd.read_csv(source_dir / "transactions.csv")
    rng = np.random.default_rng(seed)

    # Standardize typologies
    df["typology"] = df["fraud_type"].apply(map_typology_name)

    # If target_fraud_rate is specified and lower than raw, downsample fraud rows to achieve target rate
    if target_fraud_rate and target_fraud_rate < df["is_fraud"].mean():
        total_legit = (df["is_fraud"] == 0).sum()
        desired_total_fraud = int(total_legit * (target_fraud_rate / (1.0 - target_fraud_rate)))
        # Stratified sample ensuring every typology retains >= min_positives
        selected_fraud_indices = []
        for _typ, group in df[df["is_fraud"] == 1].groupby("typology"):
            count = len(group)
            take = max(300, int(desired_total_fraud / 5))
            take = min(count, take)
            chosen = rng.choice(group.index, size=take, replace=False)
            selected_fraud_indices.extend(chosen)

        legit_indices = df[df["is_fraud"] == 0].index
        all_keep = np.sort(np.concatenate([legit_indices, selected_fraud_indices]))
        df = df.loc[all_keep].copy()

    # Sort strictly by timestamp for monotonicity
    df["ts"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
    df = df.sort_values("ts").reset_index(drop=True)

    # 1. Canonical transactions (STRICTLY WITHOUT FRAUD LABELS)
    txns = pd.DataFrame()
    txns["txn_id"] = df["transaction_id"].astype(str)
    txns["ts"] = df["ts"]
    txns["type"] = df["transaction_type"].astype(str)
    txns["sender_wallet_id"] = df["sender_wallet_id"].astype(str)
    txns["recipient_wallet_id"] = df["receiver_wallet_id"].astype(str)
    txns["agent_id"] = df["sender_agent_id"].fillna(df["receiver_agent_id"]).astype(str)
    txns["amount_bdt"] = df["amount"].astype(float)
    txns["channel"] = "app"
    txns["device_id"] = df["sender_device_id"].astype(str)
    # Session seconds: 20-300s normally
    txns["session_seconds"] = rng.integers(25, 240, size=len(txns))
    txns["balance_before"] = txns["amount_bdt"] * rng.uniform(1.2, 4.0, size=len(txns))

    # 2. Isolated ground-truth labels table
    labels = pd.DataFrame()
    labels["txn_id"] = df["transaction_id"].astype(str)
    labels["is_fraud"] = df["is_fraud"].astype(int)
    labels["typology"] = df["typology"].astype(str)
    labels["case_id"] = "CASE-" + labels["txn_id"].str.slice(-6)
    labels["is_mule_recipient"] = df["mule_account"].astype(int)

    return txns, labels


def normalize_hidden_truth(source_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(source_dir / "mule_ground_truth.csv")
    out = pd.DataFrame()
    out["wallet_id"] = df["wallet_id"].astype(str)
    out["is_mule"] = df["mule_label"].astype(int)
    out["mule_ring_id"] = df["mule_ring_id"].fillna("").astype(str)
    out["agent_is_collusive"] = 0
    return out


def generate_confirmations(
    labels: pd.DataFrame,
    transactions: pd.DataFrame,
    confirmation_lag_hours: int = 24,
    detection_rate: float = 0.8,
    seed: int = 42,
) -> pd.DataFrame:
    """Simulate analyst confirmations table with configured lag.

    Never emits confirmations for the held-out agent_collusion typology.
    """
    rng = np.random.default_rng(seed)
    merged = labels.merge(transactions[["txn_id", "ts", "recipient_wallet_id"]], on="txn_id")

    # Filter fraud rows, excluding held-out typology
    fraud_rows = merged[
        (merged["is_fraud"] == 1) & (merged["typology"] != "agent_collusion")
    ].copy()

    # Apply detection rate
    mask = rng.uniform(0, 1, size=len(fraud_rows)) < detection_rate
    detected = fraud_rows[mask].copy()

    # Add confirmation lag
    lag_delta = pd.to_timedelta(confirmation_lag_hours, unit="h")
    detected["confirmed_at"] = detected["ts"] + lag_delta

    confirmations = pd.DataFrame()
    confirmations["wallet_id"] = detected["recipient_wallet_id"].astype(str)
    confirmations["confirmed_at"] = detected["confirmed_at"]
    confirmations["source"] = "analyst_confirmation"

    # Deduplicate by wallet taking earliest confirmation
    confirmations = (
        confirmations.sort_values("confirmed_at")
        .groupby("wallet_id", as_index=False)
        .first()
    )
    return confirmations


def generate_auth_events(
    transactions: pd.DataFrame,
    labels: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate realistic auth events (pin_reset, sim_change, new_device_login)."""
    rng = np.random.default_rng(seed)
    events = []

    merged = labels.merge(transactions, on="txn_id")
    takeover_txns = merged[merged["typology"] == "sim_swap_takeover"]

    for idx, row in takeover_txns.iterrows():
        # Inject PIN reset or SIM change 20-45 minutes before transaction
        event_time = row["ts"] - pd.to_timedelta(rng.integers(15, 50), unit="m")
        events.append({
            "event_id": f"AUTH-TAKEOVER-{idx}",
            "wallet_id": row["sender_wallet_id"],
            "ts": event_time,
            "event_type": "sim_change" if rng.random() > 0.5 else "pin_reset",
            "device_id": row["device_id"],
        })

    # Add legitimate background auth events
    sample_senders = transactions.sample(n=min(2000, len(transactions)), random_state=seed)
    for idx, row in sample_senders.iterrows():
        if rng.random() < 0.15:
            event_time = row["ts"] - pd.to_timedelta(rng.integers(1, 240), unit="h")
            events.append({
                "event_id": f"AUTH-LEGIT-{idx}",
                "wallet_id": row["sender_wallet_id"],
                "ts": event_time,
                "event_type": rng.choice(["new_device_login", "pin_reset"]),
                "device_id": row["device_id"],
            })

    auth_df = pd.DataFrame(events)
    if not auth_df.empty:
        auth_df = auth_df.sort_values("ts").reset_index(drop=True)
    return auth_df
