"""SIM swap and account takeover typology generator.

Pattern: Recent SIM change or PIN reset, then a new device,
then a drain of most of the balance to a new recipient.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def inject_sim_swap_takeovers(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    auth_events: pd.DataFrame,
    n_cases: int = 50,
    seed: int = 42,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    rng = np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()

    fraud_txns = []
    fraud_labels = []
    injected_auth = []

    for case_idx in range(n_cases):
        victim = customer_wallets[rng.integers(0, len(customer_wallets))]
        mule = customer_wallets[(rng.integers(0, len(customer_wallets)) + 11) % len(customer_wallets)]
        case_id = f"CASE_TAKEOVER_{case_idx+1:05d}"

        base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]

        # 1. Recent SIM change or PIN reset
        auth_time = base_time - pd.to_timedelta(rng.integers(15, 55), unit="m")
        new_attacker_dev = f"DEV_HACK_{case_idx+1:04d}"

        injected_auth.append({
            "event_id": f"AUTH_SWAP_{case_idx+1:05d}",
            "wallet_id": victim,
            "ts": auth_time,
            "event_type": "sim_change" if rng.random() > 0.4 else "pin_reset",
            "device_id": new_attacker_dev,
        })

        # 2. Balance drain transaction
        drain_amount = float(rng.integers(5500, 24000))
        txn_id = f"TXN_TAKEOVER_{case_idx+1:05d}"

        fraud_txns.append({
            "txn_id": txn_id,
            "ts": base_time,
            "type": "send_money",
            "sender_wallet_id": victim,
            "recipient_wallet_id": mule,
            "agent_id": None,
            "amount_bdt": drain_amount,
            "channel": "app",
            "device_id": new_attacker_dev,  # Unseen new device
            "session_seconds": int(rng.integers(25, 140)),
            "balance_before": round(drain_amount * rng.uniform(1.02, 1.10), 2),  # >90% drain
        })

        fraud_labels.append({
            "txn_id": txn_id,
            "is_fraud": 1,
            "typology": "sim_swap_takeover",
            "case_id": case_id,
            "is_mule_recipient": 1,
        })

    return fraud_txns, fraud_labels, injected_auth
