"""Synthetic population generator: customers, wallets, agents, devices."""

from typing import Tuple

import numpy as np
import pandas as pd

from goldenminutes.common.config import SimulatorProfile


def generate_population(
    profile: SimulatorProfile,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate synthetic customers, wallets, agents, and device links deterministically."""
    rng = np.random.default_rng(seed)
    base_date = pd.Timestamp("2026-01-01", tz="UTC")

    # 1. Customers
    n_cust = profile.customers
    cust_ids = [f"CUST{i+1:06d}" for i in range(n_cust)]
    ages = rng.integers(18, 72, size=n_cust)
    age_bands = [
        "young" if a < 25 else "middle" if a <= 50 else "senior"
        for a in ages
    ]

    region_choices = ["urban", "semi_urban", "rural"]
    region_probs = [0.45, 0.35, 0.20]
    regions = rng.choice(region_choices, size=n_cust, p=region_probs)

    persona_choices = ["salaried", "student", "small_trader", "remittance_receiver"]
    persona_probs = [0.40, 0.25, 0.20, 0.15]
    personas = rng.choice(persona_choices, size=n_cust, p=persona_probs)

    reg_days_ago = rng.integers(30, 1500, size=n_cust)
    reg_dates = [base_date - pd.to_timedelta(int(d), unit="D") for d in reg_days_ago]
    kyc_levels = ["full" if d > 180 else "basic" for d in reg_days_ago]

    customers_df = pd.DataFrame({
        "customer_id": cust_ids,
        "age_band": age_bands,
        "region_type": regions,
        "persona": personas,
        "registered_at": reg_dates,
        "kyc_level": kyc_levels,
    })

    # 2. Agents
    n_agents = profile.agents
    agent_ids = [f"AGT{i+1:05d}" for i in range(n_agents)]
    agent_regions = rng.choice(region_choices, size=n_agents, p=region_probs)
    agent_days_ago = rng.integers(180, 1800, size=n_agents)
    agent_dates = [base_date - pd.to_timedelta(int(d), unit="D") for d in agent_days_ago]

    agents_df = pd.DataFrame({
        "agent_id": agent_ids,
        "region_type": agent_regions,
        "opened_at": agent_dates,
    })

    # 3. Wallets (customer + agent + merchant)
    wallets = []
    # Customer wallets
    for idx, cid in enumerate(cust_ids):
        wid = f"WAL{idx+1:06d}"
        assigned_agent = agent_ids[idx % n_agents]
        opened_at = reg_dates[idx] + pd.to_timedelta(rng.integers(0, 5), unit="D")
        wallets.append({
            "wallet_id": wid,
            "customer_id": cid,
            "owner_type": "customer",
            "opened_at": opened_at,
            "opened_via_agent_id": assigned_agent,
            "status": "active",
        })

    # Agent wallets
    for idx, aid in enumerate(agent_ids):
        wid = f"WAL_AGT_{aid}"
        wallets.append({
            "wallet_id": wid,
            "customer_id": None,
            "owner_type": "agent",
            "opened_at": agent_dates[idx],
            "opened_via_agent_id": None,
            "status": "active",
        })

    # Merchant wallets
    n_merch = profile.merchants
    for idx in range(n_merch):
        wid = f"WAL_MERCH_{idx+1:05d}"
        opened = base_date - pd.to_timedelta(rng.integers(60, 1200), unit="D")
        wallets.append({
            "wallet_id": wid,
            "customer_id": None,
            "owner_type": "merchant",
            "opened_at": opened,
            "opened_via_agent_id": agent_ids[idx % n_agents],
            "status": "active",
        })

    wallets_df = pd.DataFrame(wallets)

    # 4. Device Links
    devices = []
    n_devices = max(int(n_cust * 0.8), 100)
    device_pool = [f"DEV{i+1:06d}" for i in range(n_devices)]

    for idx, wid in enumerate(wallets_df[wallets_df["owner_type"] == "customer"]["wallet_id"]):
        primary_dev = device_pool[idx % n_devices]
        first_seen = base_date - pd.to_timedelta(rng.integers(30, 365), unit="D")
        last_seen = base_date + pd.to_timedelta(profile.days, unit="D")
        devices.append({
            "wallet_id": wid,
            "device_id": primary_dev,
            "first_seen_at": first_seen,
            "last_seen_at": last_seen,
        })

    device_links_df = pd.DataFrame(devices)

    return customers_df, wallets_df, agents_df, device_links_df
