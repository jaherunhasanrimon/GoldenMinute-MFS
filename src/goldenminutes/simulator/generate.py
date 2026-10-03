"""GoldenMinutes synthetic dataset generator and canonical Parquet builder."""

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from goldenminutes.common.config import PROJECT_ROOT, get_simulator_config
from goldenminutes.simulator.behavior import generate_legitimate_behavior
from goldenminutes.simulator.intake import (
    discover_and_preserve_source,
    generate_auth_events,
    generate_confirmations,
    normalize_agents,
    normalize_customers,
    normalize_device_links,
    normalize_hidden_truth,
    normalize_transactions_and_labels,
    normalize_wallets,
)
from goldenminutes.simulator.population import generate_population
from goldenminutes.simulator.typologies.agent_collusion import inject_agent_collusion
from goldenminutes.simulator.typologies.card_to_wallet_burst import inject_card_to_wallet_bursts
from goldenminutes.simulator.typologies.impersonation_scam import inject_impersonation_scams
from goldenminutes.simulator.typologies.mule_ring import inject_mule_rings
from goldenminutes.simulator.typologies.sim_swap_takeover import inject_sim_swap_takeovers

logger = logging.getLogger("goldenminutes.simulator.generate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def compute_file_hash(path: Path) -> str:
    """Compute sha256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_dataset(
    profile_name: str = "small",
    source_mode: str = "generate",
    seed: Optional[int] = None,
) -> Dict:
    """Generate or normalize canonical synthetic Parquet dataset under data/raw/<profile>/."""
    start_time = time.perf_counter()
    config = get_simulator_config()
    run_seed = seed if seed is not None else config.seed

    if profile_name not in config.profiles:
        raise ValueError(f"Unknown profile: {profile_name}. Available: {list(config.profiles.keys())}")

    profile = config.profiles[profile_name]
    output_dir = PROJECT_ROOT / "data" / "raw" / profile_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Discover and preserve raw source if bootstrap directory exists
    try:
        discover_and_preserve_source()
    except Exception as e:
        logger.info("Raw source discovery skipped or already preserved: %s", e)

    if source_mode == "bootstrap" and (PROJECT_ROOT / "data" / "raw_source").exists():
        logger.info("Using normalized bootstrap dataset from raw_source...")
        raw_src = PROJECT_ROOT / "data" / "raw_source"
        customers_df = normalize_customers(raw_src)
        wallets_df = normalize_wallets(raw_src)
        agents_df = normalize_agents(raw_src)
        device_links_df = normalize_device_links(raw_src)
        txns_df, labels_df = normalize_transactions_and_labels(
            raw_src,
            target_fraud_rate=profile.target_fraud_rate,
            seed=run_seed,
        )
        auth_events_df = generate_auth_events(txns_df, labels_df, seed=run_seed)
        hidden_truth_df = normalize_hidden_truth(raw_src)
        confirmations_df = generate_confirmations(
            labels_df,
            txns_df,
            confirmation_lag_hours=config.confirmation_lag_hours,
            detection_rate=config.detection_rate,
            seed=run_seed,
        )
    else:
        logger.info("Generating canonical synthetic dataset with profile: %s, seed: %d", profile_name, run_seed)
        # 1. Population
        customers_df, wallets_df, agents_df, device_links_df = generate_population(profile, seed=run_seed)

        # 2. Legitimate behavior
        legit_txns, auth_events_df = generate_legitimate_behavior(
            customers_df, wallets_df, agents_df, device_links_df, profile, seed=run_seed
        )

        # Scale injection cases according to profile target
        min_pos = profile.min_typology_positives

        # 3. Inject 5 typologies with guaranteed positive counts (>= 30 on small, >= 300 on full)
        n_scam_cases = max(15, int(min_pos / 2.5))
        n_ring_cases = max(6, int(min_pos / 7))
        n_swap_cases = max(35, int(min_pos * 1.05))
        n_burst_cases = max(10, int(min_pos / 4.5))
        n_collude_cases = max(15, int(min_pos / 2.5))

        f_txns_1, f_labels_1 = inject_impersonation_scams(legit_txns, wallets_df, agents_df, n_cases=n_scam_cases, seed=run_seed + 1)
        f_txns_2, f_labels_2 = inject_mule_rings(legit_txns, wallets_df, agents_df, n_rings=n_ring_cases, seed=run_seed + 2)
        f_txns_3, f_labels_3, extra_auth = inject_sim_swap_takeovers(legit_txns, wallets_df, auth_events_df, n_cases=n_swap_cases, seed=run_seed + 3)
        f_txns_4, f_labels_4 = inject_card_to_wallet_bursts(legit_txns, wallets_df, agents_df, n_cases=n_burst_cases, seed=run_seed + 4)
        f_txns_5, f_labels_5 = inject_agent_collusion(legit_txns, wallets_df, agents_df, n_cases=n_collude_cases, seed=run_seed + 5)

        # Append extra auth events from takeovers
        if extra_auth:
            extra_auth_df = pd.DataFrame(extra_auth)
            auth_events_df = pd.concat([auth_events_df, extra_auth_df], ignore_index=True).sort_values("ts").reset_index(drop=True)

        all_fraud_txns = f_txns_1 + f_txns_2 + f_txns_3 + f_txns_4 + f_txns_5
        all_fraud_labels = f_labels_1 + f_labels_2 + f_labels_3 + f_labels_4 + f_labels_5

        fraud_txns_df = pd.DataFrame(all_fraud_txns)
        labels_df = pd.DataFrame(all_fraud_labels)

        # Build legitimate labels (is_fraud=0, typology="none")
        legit_labels_df = pd.DataFrame({
            "txn_id": legit_txns["txn_id"],
            "is_fraud": 0,
            "typology": "none",
            "case_id": "NONE",
            "is_mule_recipient": 0,
        })

        # Combine transactions and labels
        txns_df = pd.concat([legit_txns, fraud_txns_df], ignore_index=True)
        labels_df = pd.concat([legit_labels_df, labels_df], ignore_index=True)

        # Enforce monotone timestamps
        txns_df = txns_df.sort_values("ts").reset_index(drop=True)
        # Ensure labels index matches txns
        labels_df = labels_df.set_index("txn_id").loc[txns_df["txn_id"]].reset_index()

        # Build hidden truth
        all_wallets = wallets_df["wallet_id"].tolist()
        mule_wids = set(labels_df[labels_df["is_mule_recipient"] == 1]["txn_id"].map(
            dict(zip(txns_df["txn_id"], txns_df["recipient_wallet_id"], strict=False))
        ).dropna())

        hidden_truth_df = pd.DataFrame({
            "wallet_id": all_wallets,
            "is_mule": [1 if w in mule_wids else 0 for w in all_wallets],
            "mule_ring_id": ["" for _ in all_wallets],
            "agent_is_collusive": [0 for _ in all_wallets],
        })

        # Confirmations table (Never emitted for agent_collusion)
        confirmations_df = generate_confirmations(
            labels_df,
            txns_df,
            confirmation_lag_hours=config.confirmation_lag_hours,
            detection_rate=config.detection_rate,
            seed=run_seed,
        )

    # STRICT ARCHITECTURAL CONTRACT:
    # Model input transactions must NEVER have is_fraud or typology!
    for forbidden in ["is_fraud", "typology", "fraud_type", "mule_account"]:
        if forbidden in txns_df.columns:
            txns_df = txns_df.drop(columns=[forbidden])

    # Save to Parquet
    customers_df.to_parquet(output_dir / "customers.parquet", index=False)
    wallets_df.to_parquet(output_dir / "wallets.parquet", index=False)
    agents_df.to_parquet(output_dir / "agents.parquet", index=False)
    device_links_df.to_parquet(output_dir / "device_links.parquet", index=False)
    auth_events_df.to_parquet(output_dir / "auth_events.parquet", index=False)
    txns_df.to_parquet(output_dir / "transactions.parquet", index=False)
    labels_df.to_parquet(output_dir / "labels.parquet", index=False)
    hidden_truth_df.to_parquet(output_dir / "hidden_truth.parquet", index=False)
    confirmations_df.to_parquet(output_dir / "confirmations.parquet", index=False)

    duration = time.perf_counter() - start_time

    # Calculate statistics
    total_txns = len(txns_df)
    total_fraud = int(labels_df["is_fraud"].sum())
    fraud_rate = float(total_fraud / total_txns) if total_txns > 0 else 0.0
    typology_counts = labels_df[labels_df["is_fraud"] == 1]["typology"].value_counts().to_dict()

    # Calculate hashes
    hashes = {
        p.name: compute_file_hash(p)
        for p in output_dir.glob("*.parquet")
    }

    summary = {
        "profile": profile_name,
        "seed": run_seed,
        "customers_count": len(customers_df),
        "wallets_count": len(wallets_df),
        "agents_count": len(agents_df),
        "total_transactions": total_txns,
        "total_fraud_transactions": total_fraud,
        "fraud_rate": fraud_rate,
        "typology_counts": typology_counts,
        "confirmations_count": len(confirmations_df),
        "duration_seconds": round(duration, 3),
        "hashes": hashes,
    }

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    with open(reports_dir / "sim_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Successfully generated %s profile in %.2fs: %d txns, %d fraud (%.3f%%)",
                profile_name, duration, total_txns, total_fraud, fraud_rate * 100)
    return summary


def main():
    parser = argparse.ArgumentParser(description="GoldenMinutes Dataset Generator")
    parser.add_argument("--profile", choices=["small", "full"], default="small")
    parser.add_argument("--source", choices=["bootstrap", "generate"], default="generate")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    summary = generate_dataset(
        profile_name=args.profile,
        source_mode=args.source,
        seed=args.seed,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
