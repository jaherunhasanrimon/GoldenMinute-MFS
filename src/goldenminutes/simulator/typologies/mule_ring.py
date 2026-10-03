"""Mule ring typology generator.

Pattern: 5–15 wallets, with fan-in followed by pass-through chains, shared devices,
and cash-out at a small set of agents.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def inject_mule_rings(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    n_rings: int = 15,
    seed: int = 42,
) -> Tuple[List[Dict], List[Dict]]:
    rng = np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    fraud_txns = []
    fraud_labels = []

    for ring_idx in range(n_rings):
        case_id = f"CASE_RING_{ring_idx+1:05d}"
        ring_size = rng.integers(5, 12)
        ring_wallets = rng.choice(customer_wallets, size=ring_size, replace=False)
        shared_dev = f"DEV_RING_{ring_idx+1:04d}"
        ring_agents = rng.choice(agent_ids, size=min(2, len(agent_ids)), replace=False)

        base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + ring_idx)).iloc[0]

        # Step 1: External fan-in into initial layer
        for step in range(ring_size - 1):
            source = ring_wallets[step]
            target = ring_wallets[step + 1]
            step_time = base_time + pd.to_timedelta(rng.integers(10, 40) * (step + 1), unit="m")
            amt = float(rng.integers(3500, 18000))
            txn_id = f"TXN_RING_{ring_idx+1:03d}_{step+1}"

            fraud_txns.append({
                "txn_id": txn_id,
                "ts": step_time,
                "type": "send_money",
                "sender_wallet_id": source,
                "recipient_wallet_id": target,
                "agent_id": None,
                "amount_bdt": amt,
                "channel": "app",
                "device_id": shared_dev if rng.random() > 0.3 else f"DEV_{source[-6:]}",
                "session_seconds": int(rng.integers(40, 120)),
                "balance_before": round(amt * 1.15, 2),
            })

            fraud_labels.append({
                "txn_id": txn_id,
                "is_fraud": 1,
                "typology": "mule_ring",
                "case_id": case_id,
                "is_mule_recipient": 1,
            })

        # Step 2: Final cash-out at collusive/compromised agent
        final_wallet = ring_wallets[-1]
        co_time = base_time + pd.to_timedelta(rng.integers(60, 180), unit="m")
        co_txn_id = f"TXN_RING_CO_{ring_idx+1:03d}"
        co_amt = float(rng.integers(12000, 32000))

        fraud_txns.append({
            "txn_id": co_txn_id,
            "ts": co_time,
            "type": "cash_out",
            "sender_wallet_id": final_wallet,
            "recipient_wallet_id": None,
            "agent_id": ring_agents[0],
            "amount_bdt": co_amt,
            "channel": "agent",
            "device_id": shared_dev,
            "session_seconds": 90,
            "balance_before": round(co_amt * 1.05, 2),
        })

        fraud_labels.append({
            "txn_id": co_txn_id,
            "is_fraud": 1,
            "typology": "mule_ring",
            "case_id": case_id,
            "is_mule_recipient": 1,
        })

    return fraud_txns, fraud_labels
