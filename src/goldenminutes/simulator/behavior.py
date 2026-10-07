"""Synthetic legitimate transaction generator incorporating personas and confounders.

Phase 1 realism enhancements:
- Confounders to eliminate artificial single-feature shortcuts (new_device_flag, balance_drain_ratio).
- Phone upgrades: ~5-6% of wallets switch phones mid-simulation (registered with new_device_login).
- Borrowed/family devices: ~3% of transactions use an alternate device.
- Legitimate wallet emptying: ~8% of transactions drain >= 80% balance (rent, fees, salary cash-outs).
- Legitimate add_money_card: ~2% of transactions are legitimate card top-ups.
- Somity (savings-group) hubs: legitimate high fan-in peer wallets that disburse/cash out funds.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.common.config import SimulatorProfile


def generate_legitimate_behavior(
    customers: pd.DataFrame,
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    device_links: pd.DataFrame,
    profile: SimulatorProfile,
    seed: int = 42,
    realism_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate normal transactions, cash-outs, and confounders over profile duration.

    Returns:
        (transactions_df, auth_events_df, updated_device_links_df)
    """
    rng = np.random.default_rng(seed)
    realism = realism_cfg or {}
    start_date = pd.Timestamp("2026-01-01", tz="UTC")
    total_days = profile.days

    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    merchant_wallets = wallets[wallets["owner_type"] == "merchant"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    # Base device map
    device_map = dict(zip(device_links["wallet_id"], device_links["device_id"], strict=False))
    all_devices_pool = list(device_links["device_id"].unique())

    # Phone upgrades: ~5-6% of customer wallets switch to a new phone mid-simulation
    upgrade_share = float(realism.get("phone_upgrade_wallet_share", 0.06))
    n_upgrades = int(len(customer_wallets) * upgrade_share)
    upgraded_wallets = set(rng.choice(customer_wallets, size=n_upgrades, replace=False))
    upgrade_info: Dict[str, Tuple[pd.Timestamp, str]] = {}
    new_device_links_rows = []

    for wid in upgraded_wallets:
        upg_day = int(rng.integers(5, max(6, total_days - 2)))
        upg_time = start_date + pd.to_timedelta(upg_day, unit="D") + pd.to_timedelta(int(rng.integers(9, 21)), unit="h")
        new_dev_id = f"DEV_UPG_{wid[-6:]}"
        upgrade_info[wid] = (upg_time, new_dev_id)
        new_device_links_rows.append({
            "wallet_id": wid,
            "device_id": new_dev_id,
            "first_seen_at": upg_time,
            "last_seen_at": start_date + pd.to_timedelta(total_days, unit="D"),
        })

    # Persona lookup
    cust_persona_map = dict(zip(customers["customer_id"], customers["persona"], strict=False))
    wallet_to_cust = dict(zip(wallets["wallet_id"], wallets["customer_id"], strict=False))

    txns: List[Dict] = []
    auth_events: List[Dict] = []

    # Record new_device_login auth events for phone upgrades
    for wid, (upg_time, new_dev_id) in upgrade_info.items():
        auth_events.append({
            "event_id": f"AUTH_UPG_{wid[-6:]}",
            "wallet_id": wid,
            "ts": upg_time,
            "event_type": "new_device_login",
            "device_id": new_dev_id,
        })

    # Persona characteristics
    persona_params = {
        "salaried": {"mean_amt": 5500, "std_amt": 4500, "freq_scale": 1.0},
        "student": {"mean_amt": 1800, "std_amt": 1500, "freq_scale": 0.8},
        "small_trader": {"mean_amt": 16500, "std_amt": 9500, "freq_scale": 3.0},
        "remittance_receiver": {"mean_amt": 22000, "std_amt": 8500, "freq_scale": 0.6},
    }

    # Somity (savings-group) hubs: legitimate high fan-in peer wallets
    somity_rate = float(realism.get("somity_groups_per_1000_customers", 2.5))
    n_somity = max(2, int(len(customer_wallets) / 1000.0 * somity_rate))
    somity_organizers = list(rng.choice(customer_wallets, size=n_somity, replace=False))
    somity_members: Dict[str, List[str]] = {}
    avail_customers = [w for w in customer_wallets if w not in set(somity_organizers)]
    for org in somity_organizers:
        mem_count = int(rng.integers(
            int(realism.get("somity_members_min", 8)),
            int(realism.get("somity_members_max", 20)) + 1
        ))
        somity_members[org] = list(rng.choice(avail_customers, size=min(mem_count, len(avail_customers)), replace=False))

    n_base_events = int(len(customer_wallets) * total_days * 0.4)

    # Rates
    borrowed_dev_rate = float(realism.get("borrowed_device_rate", 0.03))
    wallet_empty_rate = float(realism.get("wallet_emptying_rate", 0.08))
    legit_card_rate = float(realism.get("legit_card_topup_rate", 0.02))

    for i in range(n_base_events):
        sender = customer_wallets[i % len(customer_wallets)]
        cid = wallet_to_cust.get(sender)
        persona = cust_persona_map.get(cid, "salaried")
        params = persona_params.get(persona, persona_params["salaried"])

        # Timestamp
        day_offset = int(rng.integers(0, total_days))
        hour_p = np.array([
            0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.03, 0.05,
            0.07, 0.07, 0.06, 0.06, 0.07, 0.06, 0.06, 0.06,
            0.07, 0.08, 0.07, 0.06, 0.04, 0.03, 0.02, 0.01
        ])
        hour_p = hour_p / hour_p.sum()
        hour = int(rng.choice(list(range(24)), p=hour_p))
        minute = int(rng.integers(0, 60))
        second = int(rng.integers(0, 60))
        ts = start_date + pd.to_timedelta(day_offset, unit="D") + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m") + pd.to_timedelta(second, unit="s")

        # Determine device for sender at this timestamp
        if sender in upgrade_info and ts >= upgrade_info[sender][0]:
            dev_id = upgrade_info[sender][1]
        else:
            dev_id = device_map.get(sender, f"DEV{rng.integers(1, 1000):06d}")

        # Borrowed / family phone confounder
        if rng.random() < borrowed_dev_rate:
            dev_id = all_devices_pool[int(rng.integers(0, len(all_devices_pool)))]

        # Type of transaction
        txn_type_roll = rng.random()
        if txn_type_roll < legit_card_rate:
            # Legitimate card add-money event
            txn_type = "add_money_card"
            sender_id = f"CARD_{rng.integers(1000, 9999)}"
            recipient = sender
            amount = max(500.0, float(rng.normal(params["mean_amt"] * 0.7, 1000)))
            agent_id = None
            bal_before = amount * float(rng.uniform(0.1, 1.5))
        elif txn_type_roll < 0.50:
            txn_type = "send_money"
            sender_id = sender
            # 70% regular peer, 30% new recipient
            if rng.random() < 0.30:
                # Confounder: legitimate transfer to a new recipient
                recipient = customer_wallets[int(rng.integers(0, len(customer_wallets)))]
                if rng.random() < 0.15:
                    amount = float(rng.integers(15000, 32000))
                else:
                    amount = max(100.0, float(rng.normal(params["mean_amt"], params["std_amt"])))
            else:
                recipient = customer_wallets[(i + 7) % len(customer_wallets)]
                amount = max(50.0, float(rng.normal(params["mean_amt"], params["std_amt"])))
            agent_id = None
            # Balance drain confounder (e.g. paying high fees or rent)
            if rng.random() < wallet_empty_rate:
                bal_before = round(amount * float(rng.uniform(1.02, 1.15)), 2)
            else:
                bal_before = round(amount * float(rng.uniform(1.3, 5.0)), 2)
        elif txn_type_roll < 0.75:
            # Merchant payment / High fan-in merchant confounder
            txn_type = "merchant_pay"
            sender_id = sender
            recipient = merchant_wallets[int(rng.integers(0, len(merchant_wallets)))]
            amount = max(50.0, float(rng.normal(params["mean_amt"] * 0.4, 300)))
            agent_id = None
            bal_before = round(amount * float(rng.uniform(1.5, 6.0)), 2)
        elif txn_type_roll < 0.90:
            # Cash out
            txn_type = "cash_out"
            sender_id = sender
            recipient = None
            amount = max(200.0, float(rng.normal(params["mean_amt"] * 0.8, params["std_amt"] * 0.5)))
            agent_id = agent_ids[int(rng.integers(0, len(agent_ids)))]
            if rng.random() < wallet_empty_rate:
                bal_before = round(amount * float(rng.uniform(1.01, 1.10)), 2)
            else:
                bal_before = round(amount * float(rng.uniform(1.2, 4.0)), 2)
        else:
            # Cash in
            txn_type = "cash_in"
            recipient = sender
            sender_id = customer_wallets[(i + 3) % len(customer_wallets)]
            amount = max(500.0, float(rng.normal(params["mean_amt"] * 1.2, params["std_amt"])))
            agent_id = agent_ids[int(rng.integers(0, len(agent_ids)))]
            bal_before = round(amount * float(rng.uniform(0.5, 3.0)), 2)

        session_sec = int(rng.integers(15, 180))

        txns.append({
            "txn_id": f"TXN{len(txns)+1:08d}",
            "ts": ts,
            "type": txn_type,
            "sender_wallet_id": sender_id,
            "recipient_wallet_id": recipient,
            "agent_id": agent_id,
            "amount_bdt": round(amount, 2),
            "channel": "app" if rng.random() > 0.15 else "ussd",
            "device_id": dev_id,
            "session_seconds": session_sec,
            "balance_before": round(bal_before, 2),
        })

    # Generate Somity periodic pool deposits and cash-outs (creates legit high-fan-in + pass-through P2P)
    for org, members in somity_members.items():
        # Every ~15-30 days, members deposit
        n_rounds = max(1, total_days // 20)
        for r_idx in range(n_rounds):
            round_day = int(rng.integers(5 + r_idx * 20, min(total_days - 2, 25 + r_idx * 20)))
            round_time = start_date + pd.to_timedelta(round_day, unit="D") + pd.to_timedelta(int(rng.integers(10, 16)), unit="h")
            pool_total = 0.0
            for m_idx, mem in enumerate(members):
                mem_ts = round_time + pd.to_timedelta(int(rng.integers(5, 120) * (m_idx + 1)), unit="m")
                mem_amt = float(rng.integers(1000, 3500))
                pool_total += mem_amt
                mem_dev = device_map.get(mem, f"DEV{rng.integers(1, 1000):06d}")
                txns.append({
                    "txn_id": f"TXN_SOM_{len(txns)+1:08d}",
                    "ts": mem_ts,
                    "type": "send_money",
                    "sender_wallet_id": mem,
                    "recipient_wallet_id": org,
                    "agent_id": None,
                    "amount_bdt": mem_amt,
                    "channel": "app" if rng.random() > 0.2 else "ussd",
                    "device_id": mem_dev,
                    "session_seconds": int(rng.integers(30, 100)),
                    "balance_before": round(mem_amt * float(rng.uniform(1.5, 4.0)), 2),
                })
            # Organizer disburses or cashes out the pool
            co_time = round_time + pd.to_timedelta(int(rng.integers(3, 8)), unit="h")
            org_dev = device_map.get(org, f"DEV{rng.integers(1, 1000):06d}")
            txns.append({
                "txn_id": f"TXN_SOM_CO_{len(txns)+1:08d}",
                "ts": co_time,
                "type": "cash_out",
                "sender_wallet_id": org,
                "recipient_wallet_id": None,
                "agent_id": agent_ids[int(rng.integers(0, len(agent_ids)))],
                "amount_bdt": round(pool_total * 0.95, 2),
                "channel": "agent",
                "device_id": org_dev,
                "session_seconds": int(rng.integers(40, 120)),
                "balance_before": round(pool_total, 2),
            })

    txns_df = pd.DataFrame(txns)
    txns_df = txns_df.sort_values("ts").reset_index(drop=True)
    txns_df["txn_id"] = [f"TXN{i+1:08d}" for i in range(len(txns_df))]

    # Generate background auth events
    sampled_users = rng.choice(customer_wallets, size=min(1500, len(customer_wallets)), replace=False)
    for idx, wid in enumerate(sampled_users):
        event_time = start_date + pd.to_timedelta(int(rng.integers(1, total_days)), unit="D")
        auth_events.append({
            "event_id": f"AUTH_NORM_{idx+1:06d}",
            "wallet_id": wid,
            "ts": event_time,
            "event_type": rng.choice(["new_device_login", "pin_reset"]),
            "device_id": device_map.get(wid, "DEV000001"),
        })

    auth_df = pd.DataFrame(auth_events).sort_values("ts").reset_index(drop=True)

    # Updated device links
    updated_device_links = device_links.copy()
    if new_device_links_rows:
        upg_dl_df = pd.DataFrame(new_device_links_rows)
        updated_device_links = pd.concat([updated_device_links, upg_dl_df], ignore_index=True)

    return txns_df, auth_df, updated_device_links
