"""Impersonation scam typology generator (Phase 1 realism).

Pattern: A phone scammer coerces a victim into sending money to a mule account.
- Victims use their OWN registered device (or occasionally borrowed family phone),
  not an invented synthetic device ID.
- Mules belong to the herder network and are reused across cases within their active window.
- The mule either forwards funds to a collector wallet or cashes out directly at a network agent.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.simulator.networks import FraudContext, _label, _txn


def inject_impersonation_scams(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    n_cases: int = 60,
    seed: int = 42,
    ctx: Optional[FraudContext] = None,
) -> Tuple[List[Dict], List[Dict]]:
    rng = ctx.rng if ctx is not None else np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    fraud_txns: List[Dict] = []
    fraud_labels: List[Dict] = []

    # If no FraudContext provided, fallback to non-network mode but using realistic devices
    device_map = ctx.own_device if ctx is not None else {}

    for case_idx in range(n_cases):
        case_id = f"CASE_SCAM_{case_idx+1:05d}"
        n_victims = int(rng.integers(2, 5))

        if ctx is not None:
            net = ctx.pick_network()
            base_time = ctx.case_time(net)
            mule = ctx.pick_mule(net, base_time)
        else:
            net = None
            base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]
            mule = customer_wallets[int(rng.integers(0, len(customer_wallets)))]

        total_scam_inflow = 0.0
        last_send_time = base_time

        for v_idx in range(n_victims):
            victim = customer_wallets[int(rng.integers(0, len(customer_wallets)))]
            if victim == mule or (ctx is not None and victim in ctx.reserved_wallets):
                continue

            send_time = base_time + pd.to_timedelta(int(rng.integers(5, 45) * v_idx), unit="m")
            last_send_time = send_time
            amt = float(rng.integers(4500, 24000))
            total_scam_inflow += amt
            txn_id = f"TXN_SCAM_{case_idx+1:04d}_{v_idx+1}"

            # Coerced victim sends from their own registered device
            if ctx is not None:
                victim_dev = ctx.victim_device(victim)
                bal_before = ctx.victim_balance(amt)
                channel = ctx.channel()
            else:
                victim_dev = device_map.get(victim, f"DEV{rng.integers(1, 1000):06d}")
                bal_before = round(amt * float(rng.uniform(1.1, 2.5)), 2)
                channel = "app"

            session_sec = int(rng.integers(30, 160))

            fraud_txns.append(_txn(
                txn_id=txn_id,
                ts=send_time,
                txn_type="send_money",
                sender=victim,
                recipient=mule,
                agent_id=None,
                amount=amt,
                channel=channel,
                device_id=victim_dev,
                session_seconds=session_sec,
                balance_before=bal_before,
            ))
            fraud_labels.append(_label(
                txn_id=txn_id,
                typology="impersonation_scam",
                case_id=case_id,
                is_mule_recipient=1,
            ))

        # Mule moves funds out (forwarding or cash-out)
        if total_scam_inflow > 0:
            if ctx is not None and net is not None:
                co_txns, co_lbls = ctx.move_out(
                    net=net,
                    mule=mule,
                    received_at=last_send_time,
                    amount=total_scam_inflow,
                    case_id=case_id,
                    typology="impersonation_scam",
                )
                fraud_txns.extend(co_txns)
                fraud_labels.extend(co_lbls)
            else:
                co_time = last_send_time + pd.to_timedelta(int(rng.integers(8, 25)), unit="m")
                co_txn_id = f"TXN_SCAM_CO_{case_idx+1:04d}"
                co_amount = round(total_scam_inflow * float(rng.uniform(0.85, 0.98)), 2)
                fraud_txns.append(_txn(
                    txn_id=co_txn_id,
                    ts=co_time,
                    txn_type="cash_out",
                    sender=mule,
                    recipient=None,
                    agent_id=agent_ids[int(rng.integers(0, len(agent_ids)))],
                    amount=co_amount,
                    channel="agent",
                    device_id=device_map.get(mule, f"DEV{rng.integers(1, 1000):06d}"),
                    session_seconds=int(rng.integers(30, 90)),
                    balance_before=round(co_amount * 1.05, 2),
                ))
                fraud_labels.append(_label(
                    txn_id=co_txn_id,
                    typology="impersonation_scam",
                    case_id=case_id,
                    is_mule_recipient=0,
                ))

    return fraud_txns, fraud_labels
