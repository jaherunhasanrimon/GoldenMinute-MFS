"""Card to wallet burst typology generator.

Pattern: Many small card add-money events into a fresh wallet,
then a fast send or cash-out.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def inject_card_to_wallet_bursts(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    n_cases: int = 50,
    seed: int = 42,
) -> Tuple[List[Dict], List[Dict]]:
    rng = np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    fraud_txns = []
    fraud_labels = []

    for case_idx in range(n_cases):
        mule = customer_wallets[rng.integers(0, len(customer_wallets))]
        case_id = f"CASE_BURST_{case_idx+1:05d}"
        base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]

        # 1. 3-6 small add_money_card events in rapid succession
        n_bursts = rng.integers(3, 7)
        total_inflow = 0.0

        for b_idx in range(n_bursts):
            b_time = base_time + pd.to_timedelta(rng.integers(1, 6) * (b_idx + 1), unit="m")
            b_amt = float(rng.integers(3000, 7500))
            total_inflow += b_amt
            txn_id = f"TXN_BURST_IN_{case_idx+1:04d}_{b_idx+1}"

            fraud_txns.append({
                "txn_id": txn_id,
                "ts": b_time,
                "type": "add_money_card",
                "sender_wallet_id": f"CARD_{rng.integers(1000, 9999)}",
                "recipient_wallet_id": mule,
                "agent_id": None,
                "amount_bdt": b_amt,
                "channel": "app",
                "device_id": f"DEV_BURST_{case_idx+1:04d}",
                "session_seconds": int(rng.integers(20, 120)),
                "balance_before": round(total_inflow - b_amt, 2),
            })

            fraud_labels.append({
                "txn_id": txn_id,
                "is_fraud": 1,
                "typology": "card_to_wallet_burst",
                "case_id": case_id,
                "is_mule_recipient": 1,
            })

        # 2. Fast send_money or cash_out draining the collected funds
        drain_time = base_time + pd.to_timedelta(rng.integers(25, 45), unit="m")
        drain_txn_id = f"TXN_BURST_DRAIN_{case_idx+1:04d}"

        fraud_txns.append({
            "txn_id": drain_txn_id,
            "ts": drain_time,
            "type": "cash_out" if rng.random() > 0.5 else "send_money",
            "sender_wallet_id": mule,
            "recipient_wallet_id": customer_wallets[(case_idx + 19) % len(customer_wallets)],
            "agent_id": agent_ids[rng.integers(0, len(agent_ids))],
            "amount_bdt": round(total_inflow * 0.96, 2),
            "channel": "app",
            "device_id": f"DEV_BURST_{case_idx+1:04d}",
            "session_seconds": 45,
            "balance_before": round(total_inflow, 2),
        })

        fraud_labels.append({
            "txn_id": drain_txn_id,
            "is_fraud": 1,
            "typology": "card_to_wallet_burst",
            "case_id": case_id,
            "is_mule_recipient": 1,
        })

    return fraud_txns, fraud_labels
