"""Impersonation scam typology generator.

Pattern: Victim sends an unusually large amount to a new recipient after a short session.
The recipient receives from several victims and cashes out within minutes.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def inject_impersonation_scams(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    n_cases: int = 60,
    seed: int = 42,
) -> Tuple[List[Dict], List[Dict]]:
    rng = np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    fraud_txns = []
    fraud_labels = []

    mule_recipients = rng.choice(customer_wallets, size=n_cases, replace=False)

    for case_idx, mule in enumerate(mule_recipients):
        case_id = f"CASE_SCAM_{case_idx+1:05d}"
        n_victims = rng.integers(2, 5)
        base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]

        for v_idx in range(n_victims):
            victim = customer_wallets[rng.integers(0, len(customer_wallets))]
            if victim == mule:
                continue

            send_time = base_time + pd.to_timedelta(rng.integers(5, 45) * v_idx, unit="m")
            amt = float(rng.integers(4500, 24000))
            txn_id = f"TXN_SCAM_{case_idx+1:04d}_{v_idx+1}"

            fraud_txns.append({
                "txn_id": txn_id,
                "ts": send_time,
                "type": "send_money",
                "sender_wallet_id": victim,
                "recipient_wallet_id": mule,
                "agent_id": None,
                "amount_bdt": amt,
                "channel": "app",
                "device_id": f"DEV_V_{victim[-6:]}",
                "session_seconds": int(rng.integers(20, 140)),  # Variable rushed and guided sessions
                "balance_before": round(amt * rng.uniform(1.05, 1.4), 2),
            })

            fraud_labels.append({
                "txn_id": txn_id,
                "is_fraud": 1,
                "typology": "impersonation_scam",
                "case_id": case_id,
                "is_mule_recipient": 1,
            })

        # Rapid cash-out after receiving funds
        cashout_time = base_time + pd.to_timedelta(rng.integers(8, 25), unit="m")
        co_txn_id = f"TXN_SCAM_CO_{case_idx+1:04d}"
        co_amount = float(rng.integers(9000, 32000))
        fraud_txns.append({
            "txn_id": co_txn_id,
            "ts": cashout_time,
            "type": "cash_out",
            "sender_wallet_id": mule,
            "recipient_wallet_id": None,
            "agent_id": agent_ids[rng.integers(0, len(agent_ids))],
            "amount_bdt": co_amount,
            "channel": "agent",
            "device_id": f"DEV_M_{mule[-6:]}",
            "session_seconds": int(rng.integers(30, 90)),
            "balance_before": round(co_amount * 1.05, 2),
        })

        fraud_labels.append({
            "txn_id": co_txn_id,
            "is_fraud": 1,
            "typology": "impersonation_scam",
            "case_id": case_id,
            "is_mule_recipient": 1,
        })

    return fraud_txns, fraud_labels
