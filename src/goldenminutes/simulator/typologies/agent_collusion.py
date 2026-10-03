"""Agent collusion typology generator (HELD-OUT typology).

Pattern: An agent with abnormal cash-out volume for linked wallets,
with amounts structured just under limits.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def inject_agent_collusion(
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

    # Pick 2-4 collusive agents
    n_collusive_agents = max(2, int(len(agent_ids) * 0.05))
    collusive_agents = rng.choice(agent_ids, size=n_collusive_agents, replace=False)

    for case_idx in range(n_cases):
        chosen_agent = collusive_agents[case_idx % len(collusive_agents)]
        linked_wallets = rng.choice(customer_wallets, size=rng.integers(2, 5), replace=False)
        case_id = f"CASE_COLLUSION_{case_idx+1:05d}"
        base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]

        for w_idx, wallet in enumerate(linked_wallets):
            co_time = base_time + pd.to_timedelta(rng.integers(10, 45) * (w_idx + 1), unit="m")
            # Structured amount just under 25,000 BDT threshold
            structured_amt = float(rng.integers(24500, 24950))
            txn_id = f"TXN_COLLUSION_{case_idx+1:04d}_{w_idx+1}"

            fraud_txns.append({
                "txn_id": txn_id,
                "ts": co_time,
                "type": "cash_out",
                "sender_wallet_id": wallet,
                "recipient_wallet_id": None,
                "agent_id": chosen_agent,
                "amount_bdt": structured_amt,
                "channel": "agent",
                "device_id": f"DEV_COLLUDE_{wallet[-6:]}",
                "session_seconds": int(rng.integers(30, 120)),
                "balance_before": round(structured_amt * 1.02, 2),
            })

            fraud_labels.append({
                "txn_id": txn_id,
                "is_fraud": 1,
                "typology": "agent_collusion",
                "case_id": case_id,
                "is_mule_recipient": 1,
            })

    return fraud_txns, fraud_labels
