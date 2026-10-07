"""Mule ring typology generator (Phase 1 realism).

Pattern: A coordinated network of 5-15 mule wallets organized by herders.
- Inflow is funnelled into entry mules, passed through chains to aggregator/collector wallets,
  and disbursed at agent counters.
- Herder devices are shared across multiple mule wallets in the ring, creating genuine
  device sharing and graph connectivity.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.simulator.networks import FraudContext, _label, _txn


def inject_mule_rings(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    n_rings: int = 15,
    seed: int = 42,
    ctx: Optional[FraudContext] = None,
) -> Tuple[List[Dict], List[Dict]]:
    rng = ctx.rng if ctx is not None else np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    fraud_txns: List[Dict] = []
    fraud_labels: List[Dict] = []

    for ring_idx in range(n_rings):
        case_id = f"CASE_RING_{ring_idx+1:05d}"

        if ctx is not None:
            net = ctx.pick_network()
            base_time = ctx.case_time(net)
            ring_size = min(len(net.mules), int(rng.integers(4, 9)))
            ring_wallets = list(rng.choice(net.mules, size=ring_size, replace=False))
            collector = net.collectors[int(rng.integers(0, len(net.collectors)))]
            ring_agents = net.agents

            def device_fn(wid: str, current_net=net) -> str:
                return ctx.mule_device(current_net, wid)

            channel = ctx.channel()
        else:
            net = None
            base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + ring_idx)).iloc[0]
            ring_size = int(rng.integers(5, 10))
            ring_wallets = list(rng.choice(customer_wallets, size=ring_size, replace=False))
            collector = ring_wallets[-1]
            ring_agents = list(rng.choice(agent_ids, size=min(2, len(agent_ids)), replace=False))
            shared_dev = f"DEV_RING_{ring_idx+1:04d}"

            def device_fn(wid: str, dev=shared_dev) -> str:
                return dev

            channel = "app"

        # Step 1: Sequential / tree fan-in and pass-through chain
        running_amt = 0.0
        step_time = base_time

        for step in range(len(ring_wallets) - 1):
            source = ring_wallets[step]
            target = ring_wallets[step + 1]
            step_time = base_time + pd.to_timedelta(int(rng.integers(10, 40) * (step + 1)), unit="m")
            amt = float(rng.integers(3500, 18000))
            running_amt = amt
            txn_id = f"TXN_RING_{ring_idx+1:03d}_{step+1}"

            fraud_txns.append(_txn(
                txn_id=txn_id,
                ts=step_time,
                txn_type="send_money",
                sender=source,
                recipient=target,
                agent_id=None,
                amount=amt,
                channel=channel,
                device_id=device_fn(source),
                session_seconds=int(rng.integers(40, 120)),
                balance_before=round(amt * float(rng.uniform(1.02, 1.20)), 2),
            ))
            fraud_labels.append(_label(
                txn_id=txn_id,
                typology="mule_ring",
                case_id=case_id,
                is_mule_recipient=1,
            ))

        # Step 2: Forward final chain output to collector
        final_wallet = ring_wallets[-1]
        fwd_time = step_time + pd.to_timedelta(int(rng.integers(15, 45)), unit="m")
        fwd_txn_id = f"TXN_RING_FWD_{ring_idx+1:03d}"
        fwd_amt = round(max(3000.0, running_amt * float(rng.uniform(0.90, 0.98))), 2)

        fraud_txns.append(_txn(
            txn_id=fwd_txn_id,
            ts=fwd_time,
            txn_type="send_money",
            sender=final_wallet,
            recipient=collector,
            agent_id=None,
            amount=fwd_amt,
            channel=channel,
            device_id=device_fn(final_wallet),
            session_seconds=int(rng.integers(35, 100)),
            balance_before=round(fwd_amt * 1.05, 2),
        ))
        fraud_labels.append(_label(
            txn_id=fwd_txn_id,
            typology="mule_ring",
            case_id=case_id,
            is_mule_recipient=1,
        ))

        # Step 3: Final cash-out by collector at collusive/compromised agent
        co_time = fwd_time + pd.to_timedelta(int(rng.integers(30, 120)), unit="m")
        co_txn_id = f"TXN_RING_CO_{ring_idx+1:03d}"
        co_amt = round(fwd_amt * float(rng.uniform(0.92, 0.99)), 2)

        fraud_txns.append(_txn(
            txn_id=co_txn_id,
            ts=co_time,
            txn_type="cash_out",
            sender=collector,
            recipient=None,
            agent_id=ring_agents[0],
            amount=co_amt,
            channel="agent",
            device_id=device_fn(collector),
            session_seconds=int(rng.integers(45, 120)),
            balance_before=round(co_amt * 1.05, 2),
        ))
        fraud_labels.append(_label(
            txn_id=co_txn_id,
            typology="mule_ring",
            case_id=case_id,
            is_mule_recipient=0,
        ))

    return fraud_txns, fraud_labels
