"""Mule-herding network infrastructure shared by fraud typologies (Phase 1 realism).

Real scam operations rarely use a mule wallet once and discard it. A herder runs a small
pool of recruited customer wallets, controls them from a few phones, forwards proceeds to
collector wallets, and cashes out at a handful of agents. This module models that
infrastructure so that wallet-link structure exists in the data at all. Without it there
is no graph signal for any model (rules, tabular, or GNN) to find.

Every parameter comes from ``configs/simulator.yaml -> networks`` and is recorded as an
assumption in ``docs/assumptions.md`` (A-P1-*).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class ScamNetwork:
    network_id: str
    mules: List[str]
    collectors: List[str]
    herder_devices: List[str]
    agents: List[str]
    start: pd.Timestamp
    end: pd.Timestamp
    onboard_ts: Dict[str, pd.Timestamp] = field(default_factory=dict)


@dataclass
class FraudContext:
    """Shared state handed to every typology generator."""

    rng: np.random.Generator
    networks: List[ScamNetwork]
    own_device: Dict[str, str]
    legit_ts: pd.Series
    realism: Dict[str, Any]
    net_cfg: Dict[str, Any]
    reserved_wallets: set = field(default_factory=set)
    aux_txns: List[Dict] = field(default_factory=list)  # non-loss infrastructure events (onboarding)
    _counter: int = 0

    def next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter:06d}"

    # ---- sampling helpers -------------------------------------------------
    def channel(self) -> str:
        return "ussd" if self.rng.random() < float(self.realism.get("fraud_ussd_rate", 0.15)) else "app"

    def victim_device(self, victim: str) -> str:
        """Coerced victims send from their own registered phone (occasionally a borrowed one)."""
        if self.rng.random() < float(self.realism.get("borrowed_device_rate", 0.03)):
            others = list(self.own_device.values())
            return others[int(self.rng.integers(0, len(others)))]
        return self.own_device.get(victim, f"DEV_UNREG_{victim}")

    def victim_balance(self, amount: float) -> float:
        lo = float(self.realism.get("victim_balance_multiplier_min", 1.05))
        hi = float(self.realism.get("victim_balance_multiplier_max", 3.0))
        return round(amount * float(self.rng.uniform(lo, hi)), 2)

    def pick_network(self) -> ScamNetwork:
        return self.networks[int(self.rng.integers(0, len(self.networks)))]

    def case_time(self, net: ScamNetwork) -> pd.Timestamp:
        """Sample a realistic (diurnal) timestamp inside the network's active window."""
        window = self.legit_ts[(self.legit_ts >= net.start) & (self.legit_ts <= net.end)]
        if len(window) == 0:
            window = self.legit_ts
        return window.iloc[int(self.rng.integers(0, len(window)))]

    def pick_mule(self, net: ScamNetwork, at: pd.Timestamp) -> str:
        """Pick a mule already onboarded before ``at`` (mules are reused until burnt)."""
        ready = [m for m in net.mules if net.onboard_ts[m] < at]
        pool = ready if ready else net.mules
        return pool[int(self.rng.integers(0, len(pool)))]

    def mule_device(self, net: ScamNetwork, mule: str) -> str:
        if self.rng.random() < float(self.net_cfg.get("herder_device_prob", 0.6)):
            return net.herder_devices[int(self.rng.integers(0, len(net.herder_devices)))]
        return self.own_device.get(mule, f"DEV_UNREG_{mule}")

    # ---- shared cash-out / forwarding behaviour ----------------------------
    def move_out(
        self,
        net: ScamNetwork,
        mule: str,
        received_at: pd.Timestamp,
        amount: float,
        case_id: str,
        typology: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        """Mule either forwards to a collector (who cashes out) or cashes out directly."""
        rng = self.rng
        txns: List[Dict] = []
        labels: List[Dict] = []
        if rng.random() < float(self.net_cfg.get("forward_to_collector_prob", 0.6)):
            collector = net.collectors[int(rng.integers(0, len(net.collectors)))]
            t_fwd = received_at + pd.to_timedelta(int(rng.integers(3, 40)), unit="m")
            fwd_amt = round(amount * float(rng.uniform(0.85, 0.98)), 2)
            tid = self.next_id("TXN_FWD")
            txns.append(_txn(tid, t_fwd, "send_money", mule, collector, None, fwd_amt,
                             self.channel(), self.mule_device(net, mule),
                             int(rng.integers(25, 120)), round(fwd_amt * float(rng.uniform(1.0, 1.15)), 2)))
            labels.append(_label(tid, typology, case_id, is_mule_recipient=1))
            # Collector cashes out at a network agent.
            t_co = t_fwd + pd.to_timedelta(int(rng.integers(10, 90)), unit="m")
            co_amt = round(fwd_amt * float(rng.uniform(0.9, 0.99)), 2)
            cid = self.next_id("TXN_COLL_CO")
            txns.append(_txn(cid, t_co, "cash_out", collector, None,
                             net.agents[int(rng.integers(0, len(net.agents)))], co_amt, "agent",
                             self.mule_device(net, collector), int(rng.integers(30, 120)),
                             round(co_amt * float(rng.uniform(1.0, 1.2)), 2)))
            labels.append(_label(cid, typology, case_id, is_mule_recipient=0))
        else:
            t_co = received_at + pd.to_timedelta(int(rng.integers(5, 40)), unit="m")
            co_amt = round(amount * float(rng.uniform(0.85, 0.99)), 2)
            cid = self.next_id("TXN_MULE_CO")
            txns.append(_txn(cid, t_co, "cash_out", mule, None,
                             net.agents[int(rng.integers(0, len(net.agents)))], co_amt, "agent",
                             self.mule_device(net, mule), int(rng.integers(30, 120)),
                             round(co_amt * float(rng.uniform(1.0, 1.2)), 2)))
            labels.append(_label(cid, typology, case_id, is_mule_recipient=0))
        return txns, labels


def _txn(
    txn_id: str,
    ts: pd.Timestamp,
    txn_type: str,
    sender: str,
    recipient: Optional[str],
    agent_id: Optional[str],
    amount: float,
    channel: str,
    device_id: str,
    session_seconds: int,
    balance_before: float,
) -> Dict:
    return {
        "txn_id": txn_id,
        "ts": ts,
        "type": txn_type,
        "sender_wallet_id": sender,
        "recipient_wallet_id": recipient,
        "agent_id": agent_id,
        "amount_bdt": float(amount),
        "channel": channel,
        "device_id": device_id,
        "session_seconds": int(session_seconds),
        "balance_before": float(balance_before),
    }


def _label(txn_id: str, typology: str, case_id: str, is_mule_recipient: int) -> Dict:
    return {
        "txn_id": txn_id,
        "is_fraud": 1,
        "typology": typology,
        "case_id": case_id,
        "is_mule_recipient": int(is_mule_recipient),
    }


def build_scam_networks(
    wallets: pd.DataFrame,
    agents: pd.DataFrame,
    device_links: pd.DataFrame,
    legit_ts: pd.Series,
    n_customers: int,
    total_days: int,
    net_cfg: Dict[str, Any],
    realism: Dict[str, Any],
    seed: int,
    exclude_wallets: Optional[set] = None,
) -> FraudContext:
    """Create mule-herding networks and the shared FraudContext."""
    rng = np.random.default_rng(seed)
    exclude = set(exclude_wallets or set())
    customer_wallets = [
        w for w in wallets[wallets["owner_type"] == "customer"]["wallet_id"].tolist() if w not in exclude
    ]
    agent_ids = agents["agent_id"].tolist()
    start_date = pd.Timestamp("2026-01-01", tz="UTC")

    n_networks = max(3, int(round(n_customers / 1000.0 * float(net_cfg.get("per_1000_customers", 1.25)))))
    perm = list(rng.permutation(customer_wallets))
    used = 0
    networks: List[ScamNetwork] = []

    for k in range(n_networks):
        n_mules = int(rng.integers(int(net_cfg.get("mules_min", 6)), int(net_cfg.get("mules_max", 14)) + 1))
        n_coll = int(rng.integers(int(net_cfg.get("collectors_min", 1)), int(net_cfg.get("collectors_max", 2)) + 1))
        members = perm[used: used + n_mules + n_coll]
        used += n_mules + n_coll
        mules, collectors = list(members[:n_mules]), list(members[n_mules:])

        n_dev = int(rng.integers(int(net_cfg.get("herder_devices_min", 1)), int(net_cfg.get("herder_devices_max", 3)) + 1))
        herder_devices = [f"DEV_HERDER_{k + 1:03d}_{d + 1}" for d in range(n_dev)]
        net_agents = list(rng.choice(agent_ids, size=min(int(net_cfg.get("cashout_agents", 3)), len(agent_ids)), replace=False))

        active = int(rng.integers(int(net_cfg.get("active_days_min", 18)), int(net_cfg.get("active_days_max", 40)) + 1))
        active = min(active, max(5, total_days - 2))
        start_day = int(rng.integers(1, max(2, total_days - active)))
        start = start_date + pd.to_timedelta(start_day, unit="D")
        end = start + pd.to_timedelta(active, unit="D")

        net = ScamNetwork(f"NET{k + 1:03d}", mules, collectors, herder_devices, net_agents, start, end)
        # Progressive onboarding: half the pool before launch, the rest during the first 60% of the window.
        for i, m in enumerate(mules):
            if i < max(1, n_mules // 2):
                lead = int(rng.integers(int(net_cfg.get("onboarding_days_before_min", 1)),
                                        int(net_cfg.get("onboarding_days_before_max", 6)) + 1))
                net.onboard_ts[m] = start - pd.to_timedelta(lead, unit="D") + pd.to_timedelta(int(rng.integers(8, 20)), unit="h")
            else:
                frac = float(rng.uniform(0.0, 0.6))
                net.onboard_ts[m] = start + pd.to_timedelta(frac * active, unit="D")
        networks.append(net)

    own_device = dict(zip(device_links["wallet_id"], device_links["device_id"], strict=False))
    ctx = FraudContext(
        rng=rng,
        networks=networks,
        own_device=own_device,
        legit_ts=legit_ts.sort_values().reset_index(drop=True),
        realism=realism,
        net_cfg=net_cfg,
        reserved_wallets=set(perm[:used]),
    )

    # Onboarding "test" transfers collector -> mule from a herder phone (non-loss infrastructure events).
    for net in networks:
        for m in net.mules:
            t = net.onboard_ts[m]
            collector = net.collectors[int(rng.integers(0, len(net.collectors)))]
            amt = float(rng.integers(50, 500))
            ctx.aux_txns.append(_txn(ctx.next_id("TXN_ONBOARD"), t, "send_money", collector, m, None, amt,
                                     ctx.channel(), net.herder_devices[0], int(rng.integers(20, 90)),
                                     round(amt * float(rng.uniform(2.0, 10.0)), 2)))
    return ctx


def networks_hidden_truth(ctx: FraudContext) -> pd.DataFrame:
    """Evaluation-only map wallet -> network id for mules and collectors."""
    rows = []
    for net in ctx.networks:
        for w in net.mules + net.collectors:
            rows.append({"wallet_id": w, "mule_ring_id": net.network_id})
    return pd.DataFrame(rows, columns=["wallet_id", "mule_ring_id"])
