"""Card to wallet burst typology generator (Phase 1 realism).

Pattern: Rapid sequence of stolen card add-money events into a mule wallet,
followed by fast disbursement via cash-out or forwarding.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.simulator.networks import FraudContext, _label, _txn


def inject_card_to_wallet_bursts(
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

    for case_idx in range(n_cases):
        case_id = f"CASE_BURST_{case_idx+1:05d}"

        if ctx is not None:
            net = ctx.pick_network()
            base_time = ctx.case_time(net)
            mule = ctx.pick_mule(net, base_time)
            mule_dev = ctx.mule_device(net, mule)
            channel = ctx.channel()
        else:
            net = None
            base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]
            mule = customer_wallets[int(rng.integers(0, len(customer_wallets)))]
            mule_dev = f"DEV_BURST_{case_idx+1:04d}"
            channel = "app"

        # 1. 3-6 small add_money_card events in rapid succession
        n_bursts = int(rng.integers(3, 7))
        total_inflow = 0.0
        last_b_time = base_time

        for b_idx in range(n_bursts):
            b_time = base_time + pd.to_timedelta(int(rng.integers(1, 6) * (b_idx + 1)), unit="m")
            last_b_time = b_time
            b_amt = float(rng.integers(3000, 7500))
            total_inflow += b_amt
            txn_id = f"TXN_BURST_IN_{case_idx+1:04d}_{b_idx+1}"

            fraud_txns.append(_txn(
                txn_id=txn_id,
                ts=b_time,
                txn_type="add_money_card",
                sender=f"CARD_{rng.integers(1000, 9999)}",
                recipient=mule,
                agent_id=None,
                amount=b_amt,
                channel=channel,
                device_id=mule_dev,
                session_seconds=int(rng.integers(20, 100)),
                balance_before=round(total_inflow - b_amt, 2),
            ))
            fraud_labels.append(_label(
                txn_id=txn_id,
                typology="card_to_wallet_burst",
                case_id=case_id,
                is_mule_recipient=1,
            ))

        # 2. Fast disbursement of accumulated funds
        if ctx is not None and net is not None:
            co_txns, co_lbls = ctx.move_out(
                net=net,
                mule=mule,
                received_at=last_b_time,
                amount=total_inflow,
                case_id=case_id,
                typology="card_to_wallet_burst",
            )
            fraud_txns.extend(co_txns)
            fraud_labels.extend(co_lbls)
        else:
            drain_time = last_b_time + pd.to_timedelta(int(rng.integers(15, 35)), unit="m")
            drain_txn_id = f"TXN_BURST_DRAIN_{case_idx+1:04d}"
            co_amt = round(total_inflow * 0.95, 2)
            fraud_txns.append(_txn(
                txn_id=drain_txn_id,
                ts=drain_time,
                txn_type="cash_out",
                sender=mule,
                recipient=None,
                agent_id=agent_ids[int(rng.integers(0, len(agent_ids)))],
                amount=co_amt,
                channel="agent",
                device_id=mule_dev,
                session_seconds=45,
                balance_before=round(total_inflow, 2),
            ))
            fraud_labels.append(_label(
                txn_id=drain_txn_id,
                typology="card_to_wallet_burst",
                case_id=case_id,
                is_mule_recipient=0,
            ))

    return fraud_txns, fraud_labels
