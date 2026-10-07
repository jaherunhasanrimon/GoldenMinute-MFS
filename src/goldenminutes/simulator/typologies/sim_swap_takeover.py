"""SIM swap and account takeover typology generator (Phase 1 realism).

Pattern: Account takeover preceded by a SIM change or PIN reset event.
- 70% of cases use an attacker device, 30% use remote access on the victim's existing device.
- Transfer drains balance to a network mule wallet.
- The mule forwards or cashes out at an agent counter.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.simulator.networks import FraudContext, _label, _txn


def inject_sim_swap_takeovers(
    legit_txns: pd.DataFrame,
    wallets: pd.DataFrame,
    auth_events: pd.DataFrame,
    n_cases: int = 50,
    seed: int = 42,
    ctx: Optional[FraudContext] = None,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    rng = ctx.rng if ctx is not None else np.random.default_rng(seed)
    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()

    fraud_txns: List[Dict] = []
    fraud_labels: List[Dict] = []
    injected_auth: List[Dict] = []

    attacker_dev_prob = float(ctx.realism.get("takeover_attacker_device_prob", 0.7)) if ctx is not None else 0.7

    for case_idx in range(n_cases):
        case_id = f"CASE_TAKEOVER_{case_idx+1:05d}"

        if ctx is not None:
            net = ctx.pick_network()
            base_time = ctx.case_time(net)
            mule = ctx.pick_mule(net, base_time)
            # Pick a victim not in network
            avail = [w for w in customer_wallets if w not in ctx.reserved_wallets and w != mule]
            victim = avail[int(rng.integers(0, len(avail)))]
            victim_own_dev = ctx.own_device.get(victim, f"DEV{rng.integers(1, 1000):06d}")
            channel = ctx.channel()
        else:
            net = None
            base_time = legit_txns["ts"].sample(n=1, random_state=int(seed + case_idx)).iloc[0]
            victim = customer_wallets[int(rng.integers(0, len(customer_wallets)))]
            mule = customer_wallets[(case_idx + 11) % len(customer_wallets)]
            victim_own_dev = f"DEV{rng.integers(1, 1000):06d}"
            channel = "app"

        # Attacker device: 70% new device, 30% existing device
        if rng.random() < attacker_dev_prob:
            attacker_dev = f"DEV_TAKEOVER_{case_idx+1:04d}"
        else:
            attacker_dev = victim_own_dev

        # 1. Recent SIM change or PIN reset
        auth_time = base_time - pd.to_timedelta(int(rng.integers(15, 55)), unit="m")
        injected_auth.append({
            "event_id": f"AUTH_SWAP_{case_idx+1:05d}",
            "wallet_id": victim,
            "ts": auth_time,
            "event_type": "sim_change" if rng.random() > 0.4 else "pin_reset",
            "device_id": attacker_dev,
        })

        # 2. Balance drain transaction to mule (attacker drains variable share of victim balance)
        drain_amount = float(rng.integers(5500, 24000))
        txn_id = f"TXN_TAKEOVER_{case_idx+1:05d}"
        bal_before = round(drain_amount * float(rng.uniform(1.05, 2.20)), 2)

        fraud_txns.append(_txn(
            txn_id=txn_id,
            ts=base_time,
            txn_type="send_money",
            sender=victim,
            recipient=mule,
            agent_id=None,
            amount=drain_amount,
            channel=channel,
            device_id=attacker_dev,
            session_seconds=int(rng.integers(25, 110)),
            balance_before=bal_before,
        ))
        fraud_labels.append(_label(
            txn_id=txn_id,
            typology="sim_swap_takeover",
            case_id=case_id,
            is_mule_recipient=1,
        ))

        # 3. Mule moves funds out
        if ctx is not None and net is not None:
            co_txns, co_lbls = ctx.move_out(
                net=net,
                mule=mule,
                received_at=base_time,
                amount=drain_amount,
                case_id=case_id,
                typology="sim_swap_takeover",
            )
            fraud_txns.extend(co_txns)
            fraud_labels.extend(co_lbls)

    return fraud_txns, fraud_labels, injected_auth
