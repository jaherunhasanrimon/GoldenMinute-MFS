"""Synthetic legitimate transaction generator incorporating personas and confounders."""

from typing import Dict, List, Tuple

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
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate normal transactions, cash-outs, and confounders over profile duration."""
    rng = np.random.default_rng(seed)
    start_date = pd.Timestamp("2026-01-01", tz="UTC")
    total_days = profile.days

    customer_wallets = wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist()
    merchant_wallets = wallets[wallets["owner_type"] == "merchant"]["wallet_id"].tolist()
    agent_ids = agents["agent_id"].tolist()

    # Device lookup
    device_map = dict(zip(device_links["wallet_id"], device_links["device_id"], strict=False))

    # Persona lookup
    cust_persona_map = dict(zip(customers["customer_id"], customers["persona"], strict=False))
    wallet_to_cust = dict(zip(wallets["wallet_id"], wallets["customer_id"], strict=False))

    txns: List[Dict] = []
    auth_events: List[Dict] = []

    # Persona characteristics
    persona_params = {
        "salaried": {"mean_amt": 5500, "std_amt": 4500, "freq_scale": 1.0},
        "student": {"mean_amt": 1800, "std_amt": 1500, "freq_scale": 0.8},
        "small_trader": {"mean_amt": 16500, "std_amt": 9500, "freq_scale": 3.0},
        "remittance_receiver": {"mean_amt": 22000, "std_amt": 8500, "freq_scale": 0.6},
    }

    n_base_events = int(len(customer_wallets) * total_days * 0.4)

    for i in range(n_base_events):
        sender = customer_wallets[i % len(customer_wallets)]
        cid = wallet_to_cust.get(sender)
        persona = cust_persona_map.get(cid, "salaried")
        params = persona_params.get(persona, persona_params["salaried"])

        # Timestamp
        day_offset = rng.integers(0, total_days)
        # Hourly cycle: higher between 8 AM and 10 PM
        hour_p = np.array([
            0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.03, 0.05,
            0.07, 0.07, 0.06, 0.06, 0.07, 0.06, 0.06, 0.06,
            0.07, 0.08, 0.07, 0.06, 0.04, 0.03, 0.02, 0.01
        ])
        hour_p = hour_p / hour_p.sum()
        hour = int(rng.choice(list(range(24)), p=hour_p))
        minute = rng.integers(0, 60)
        second = rng.integers(0, 60)
        ts = start_date + pd.to_timedelta(day_offset, unit="D") + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m") + pd.to_timedelta(second, unit="s")

        # Type of transaction
        txn_type_roll = rng.random()
        if txn_type_roll < 0.50:
            txn_type = "send_money"
            # 70% regular peer, 30% new recipient
            if rng.random() < 0.30:
                # Confounder: legitimate transfer to a new recipient
                recipient = customer_wallets[rng.integers(0, len(customer_wallets))]
                # Sometimes a legitimate large amount (rent/tuition)
                if rng.random() < 0.15:
                    amount = float(rng.integers(15000, 32000))
                else:
                    amount = max(100.0, float(rng.normal(params["mean_amt"], params["std_amt"])))
            else:
                recipient = customer_wallets[(i + 7) % len(customer_wallets)]
                amount = max(50.0, float(rng.normal(params["mean_amt"], params["std_amt"])))
            agent_id = None
        elif txn_type_roll < 0.75:
            # Merchant payment / High fan-in merchant confounder
            txn_type = "merchant_pay"
            recipient = merchant_wallets[rng.integers(0, len(merchant_wallets))]
            amount = max(50.0, float(rng.normal(params["mean_amt"] * 0.4, 300)))
            agent_id = None
        elif txn_type_roll < 0.90:
            # Cash out
            txn_type = "cash_out"
            recipient = None
            amount = max(200.0, float(rng.normal(params["mean_amt"] * 0.8, params["std_amt"] * 0.5)))
            agent_id = agent_ids[rng.integers(0, len(agent_ids))]
        else:
            # Cash in
            txn_type = "cash_in"
            recipient = sender
            sender = customer_wallets[(i + 3) % len(customer_wallets)]
            amount = max(500.0, float(rng.normal(params["mean_amt"] * 1.2, params["std_amt"])))
            agent_id = agent_ids[rng.integers(0, len(agent_ids))]

        dev_id = device_map.get(sender, f"DEV{rng.integers(1, 1000):06d}")
        session_sec = int(rng.integers(15, 180))
        bal_before = amount * float(rng.uniform(1.2, 5.0))

        txns.append({
            "txn_id": f"TXN{len(txns)+1:08d}",
            "ts": ts,
            "type": txn_type,
            "sender_wallet_id": sender,
            "recipient_wallet_id": recipient,
            "agent_id": agent_id,
            "amount_bdt": round(amount, 2),
            "channel": "app" if rng.random() > 0.15 else "ussd",
            "device_id": dev_id,
            "session_seconds": session_sec,
            "balance_before": round(bal_before, 2),
        })

    txns_df = pd.DataFrame(txns)
    txns_df = txns_df.sort_values("ts").reset_index(drop=True)

    # Re-index txn_id sequentially
    txns_df["txn_id"] = [f"TXN{i+1:08d}" for i in range(len(txns_df))]

    # Generate background auth events
    auth_events = []
    sampled_users = rng.choice(customer_wallets, size=min(1500, len(customer_wallets)), replace=False)
    for idx, wid in enumerate(sampled_users):
        event_time = start_date + pd.to_timedelta(rng.integers(1, total_days), unit="D")
        auth_events.append({
            "event_id": f"AUTH_NORM_{idx+1:06d}",
            "wallet_id": wid,
            "ts": event_time,
            "event_type": rng.choice(["new_device_login", "pin_reset"]),
            "device_id": device_map.get(wid, "DEV000001"),
        })

    auth_df = pd.DataFrame(auth_events).sort_values("ts").reset_index(drop=True)
    return txns_df, auth_df
