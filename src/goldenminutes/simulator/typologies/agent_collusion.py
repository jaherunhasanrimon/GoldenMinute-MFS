"""Agent collusion typology generator (HELD-OUT typology, Phase 1 realism).

Pattern: An agent with abnormal cash-out volume for linked wallets,
with amounts structured just under the 25,000 BDT regulatory reporting limit.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.simulator.networks import FraudContext, _label, _txn


def inject_agent_collusion(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    n_cases: int = 50,
    seed: int = 42,
    ctx: Optional[FraudContext] = None,
) -> Tuple[List[Dict], List[Dict]]:
    rng = ctx.rng if ctx is not None else np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    fraud_txns: List[Dict] = []
    fraud_labels: List[Dict] = []

    # Pick 2-4 collusive agents
    n_collusive_agents = max(2, int(len(agent_ids) * 0.05))
    collusive_agents = list(rng.choice(agent_ids, size=min(n_collusive_agents, len(agent_ids)), replace=False))

    device_map = ctx.own_device if ctx is not None else {}

    for case_idx in range(n_cases):
        chosen_agent = collusive_agents[case_idx % len(collusive_agents)]
        linked_wallets = list(rng.choice(customer_wallets, size=int(rng.integers(2, 5)), replace=False))
        case_id = f"CASE_COLLUSION_{case_idx+1:05d}"
        base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]

        for w_idx, wallet in enumerate(linked_wallets):
            co_time = base_time + pd.to_timedelta(int(rng.integers(10, 45) * (w_idx + 1)), unit="m")
            # Structured amount just under 25,000 BDT threshold
            structured_amt = float(rng.integers(24500, 24950))
            txn_id = f"TXN_COLLUSION_{case_idx+1:04d}_{w_idx+1}"

            dev_id = device_map.get(wallet, f"DEV{rng.integers(1, 1000):06d}")

            fraud_txns.append(_txn(
                txn_id=txn_id,
                ts=co_time,
                txn_type="cash_out",
                sender=wallet,
                recipient=None,
                agent_id=chosen_agent,
                amount=structured_amt,
                channel="agent",
                device_id=dev_id,
                session_seconds=int(rng.integers(30, 120)),
                balance_before=round(structured_amt * float(rng.uniform(1.01, 1.08)), 2),
            ))
            fraud_labels.append(_label(
                txn_id=txn_id,
                typology="agent_collusion",
                case_id=case_id,
                is_mule_recipient=1,
            ))

    return fraud_txns, fraud_labels
