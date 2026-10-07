"""Online feature store for GoldenMinutes.

Maintains rolling event-time state per wallet, device, and pair.
Computes point-in-time features for single transactions matching offline features (C9).
Supports warming from historical canonical datasets up to GM_WARMUP_CUTOFF.
"""

from __future__ import annotations

import logging
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from goldenminutes.features.graph import build_p2p_snapshot_graph
from goldenminutes.models.embedding_store import EmbeddingStore

logger = logging.getLogger("goldenminutes.features.online")


def _to_utc_dt(ts: Any) -> datetime:
    """Convert various timestamp types to timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    if isinstance(ts, (np.datetime64, pd.Timestamp)):
        p_ts = pd.to_datetime(ts)
        if p_ts.tzinfo is None:
            return p_ts.tz_localize("UTC").to_pydatetime()
        return p_ts.tz_convert("UTC").to_pydatetime()
    if isinstance(ts, (int, float)):
        # Assume seconds or nanoseconds
        if ts > 1e11:  # ns
            return datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    # Parse string
    dt = pd.to_datetime(ts)
    if dt.tzinfo is None:
        return dt.tz_localize("UTC").to_pydatetime()
    return dt.tz_convert("UTC").to_pydatetime()


class OnlineFeatureStore:
    """Stateful event-time feature store providing sub-millisecond feature extraction."""

    def __init__(self) -> None:
        self.min_ts: Optional[datetime] = None

        # Static wallet metadata: wallet_id -> (opened_at, owner_type)
        self.wallet_meta: Dict[str, Tuple[datetime, str]] = {}

        # Auth events: wallet_id -> {"pin_reset": dt, "sim_change": dt}
        # Stores sorted list of timestamps: [(dt, event_type)]
        self.auth_events: Dict[str, Dict[str, List[datetime]]] = defaultdict(lambda: defaultdict(list))

        # Confirmations: list of (confirmed_at, wallet_id)
        self.confirmations: List[Tuple[datetime, str]] = []

        # Sender history: sender_wallet_id -> sorted lists of (ts, amount)
        self.sender_history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)

        # Pair history: (sender_wallet_id, recipient_wallet_id) -> count of prior txns
        self.pair_history: Dict[Tuple[str, str], int] = defaultdict(int)

        # Sender devices: sender_wallet_id -> set of device_ids seen
        self.sender_devices: Dict[str, Set[str]] = defaultdict(set)

        # Device history: device_id -> sorted list of (ts, sender_wallet_id)
        self.device_history: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)

        # Recipient inflows: recipient_wallet_id -> sorted list of (ts, sender_wallet_id, amount, is_first_time)
        self.recipient_inflows: Dict[str, List[Tuple[datetime, str, float, bool]]] = defaultdict(list)

        # Wallet outflows: wallet_id -> sorted list of (ts, recipient_wallet_id, amount)
        self.wallet_outflows: Dict[str, List[Tuple[datetime, Optional[str], float]]] = defaultdict(list)

        # Graph edge history by day: day_int -> list of (sender, recipient)
        self.edges_by_day: Dict[int, List[Tuple[str, str]]] = defaultdict(list)
        self.dev_edges_by_day: Dict[int, List[Tuple[str, str]]] = defaultdict(list)

        # Precomputed/cached daily snapshots: day_int -> (comp_sizes_dict, mule_shares_dict)
        self._daily_snapshot_cache: Dict[int, Tuple[Dict[str, int], Dict[str, float]]] = {}

        # GNN embedding store
        self.embedding_store: Optional[EmbeddingStore] = None

    def set_embedding_store(self, store: Optional[EmbeddingStore]) -> None:
        """Attach an embedding store for point-in-time GNN feature lookups."""
        self.embedding_store = store

    def reset(self) -> None:
        """Clear all in-memory rolling state."""
        self.min_ts = None
        self.wallet_meta.clear()
        self.auth_events.clear()
        self.confirmations.clear()
        self.sender_history.clear()
        self.pair_history.clear()
        self.sender_devices.clear()
        self.device_history.clear()
        self.recipient_inflows.clear()
        self.wallet_outflows.clear()
        self.edges_by_day.clear()
        self.dev_edges_by_day.clear()
        self._daily_snapshot_cache.clear()

    def register_wallet(self, wallet_id: str, opened_at: Any, owner_type: str) -> None:
        """Register wallet creation metadata."""
        dt = _to_utc_dt(opened_at)
        self.wallet_meta[wallet_id] = (dt, owner_type)

    def register_auth_event(self, wallet_id: str, event_type: str, ts: Any) -> None:
        """Register PIN reset or SIM change event."""
        dt = _to_utc_dt(ts)
        self.auth_events[wallet_id][event_type].append(dt)

    def register_confirmation(self, wallet_id: str, confirmed_at: Any) -> None:
        """Register ground truth / confirmed mule report."""
        dt = _to_utc_dt(confirmed_at)
        self.confirmations.append((dt, wallet_id))

    def _get_day_offset(self, ts: datetime) -> int:
        """Get integer day offset relative to min_ts."""
        if self.min_ts is None:
            self.min_ts = ts
        return int((ts - self.min_ts).total_seconds() / 86400.0)

    def _get_or_build_snapshot(self, day: int) -> Tuple[Dict[str, int], Dict[str, float]]:
        """Get or compute previous day's daily graph snapshot (days [day-7, day-1])."""
        if day in self._daily_snapshot_cache:
            return self._daily_snapshot_cache[day]

        snap_start = max(0, day - 7)
        snap_end = day - 1

        if snap_end < 0:
            res: Tuple[Dict[str, int], Dict[str, float]] = ({}, {})
            self._daily_snapshot_cache[day] = res
            return res

        edges: List[Tuple[str, str]] = []
        for d in range(snap_start, snap_end + 1):
            if d in self.edges_by_day:
                edges.extend(self.edges_by_day[d])

        dev_edges: List[Tuple[str, str]] = []
        for d in range(snap_start, snap_end + 1):
            if d in self.dev_edges_by_day:
                dev_edges.extend(self.dev_edges_by_day[d])

        # Active confirmations as of day start
        if self.min_ts is not None:
            day_start = self.min_ts + timedelta(days=day)
            active_confs = {w for c_ts, w in self.confirmations if c_ts <= day_start}
        else:
            active_confs = set()

        c_map, mule_shares, _ = build_p2p_snapshot_graph(
            edges=edges,
            device_edges=dev_edges,
            active_confirmations=active_confs,
        )
        res = (c_map, mule_shares)
        self._daily_snapshot_cache[day] = res
        return res

    def features(self, txn: Dict[str, Any] | pd.Series) -> Dict[str, float]:
        """Compute all 28 point-in-time features strictly before txn timestamp."""
        ts = _to_utc_dt(txn.get("ts") if isinstance(txn, dict) else txn["ts"])
        sender_id = str(txn.get("sender_wallet_id") if isinstance(txn, dict) else txn["sender_wallet_id"])
        recipient_id = txn.get("recipient_wallet_id") if isinstance(txn, dict) else txn.get("recipient_wallet_id")
        recipient_id = str(recipient_id) if recipient_id is not None and pd.notna(recipient_id) and recipient_id != "" else None
        amount_bdt = float(txn.get("amount_bdt") if isinstance(txn, dict) else txn["amount_bdt"])
        balance_before = float(txn.get("balance_before") if isinstance(txn, dict) else txn.get("balance_before", 0.0))
        device_id = str(txn.get("device_id") if isinstance(txn, dict) else txn.get("device_id", "default_device"))
        session_seconds = float(txn.get("session_seconds") if isinstance(txn, dict) else txn.get("session_seconds", 60.0))

        if self.min_ts is None or ts < self.min_ts:
            self.min_ts = ts

        # 1. Base time features
        hour_of_day = ts.hour
        is_night = 1 if (hour_of_day >= 23 or hour_of_day <= 5) else 0

        # 2. Balance drain ratio
        safe_bal = max(balance_before, 1e-6)
        balance_drain_ratio = min(1.0, max(0.0, amount_bdt / safe_bal)) if balance_before > 0 else 0.0

        # 3. Wallet tenures
        sender_opened, _ = self.wallet_meta.get(sender_id, (ts, "customer"))
        sender_tenure_days = max(0.0, (ts - sender_opened).total_seconds() / 86400.0)

        if recipient_id and recipient_id in self.wallet_meta:
            rec_opened, rec_owner_type = self.wallet_meta[recipient_id]
            recipient_age_days = max(0.0, (ts - rec_opened).total_seconds() / 86400.0)
            owner_code_map = {"customer": 0, "agent": 1, "merchant": 2}
            recipient_owner_type_code = owner_code_map.get(rec_owner_type, 0)
        else:
            recipient_age_days = 0.0
            recipient_owner_type_code = 0

        # 4. Pair features
        pair_key = (sender_id, recipient_id) if recipient_id else (sender_id, "")
        pair_history_count = self.pair_history.get(pair_key, 0)
        is_first_time_pair = 1 if pair_history_count == 0 else 0

        # 5. Sender rolling features (30d median, 1h count, 24h count, 24h sum)
        s_hist = self.sender_history.get(sender_id, [])
        s_ts_list = [entry[0] for entry in s_hist]
        right_idx = bisect_right(s_ts_list, ts)

        t_1h_cutoff = ts - timedelta(hours=1)
        t_24h_cutoff = ts - timedelta(hours=24)
        t_30d_cutoff = ts - timedelta(days=30)

        left_1h = bisect_left(s_ts_list, t_1h_cutoff, 0, right_idx)
        left_24h = bisect_left(s_ts_list, t_24h_cutoff, 0, right_idx)
        left_30d = bisect_left(s_ts_list, t_30d_cutoff, 0, right_idx)

        sender_txn_count_1h = right_idx - left_1h
        sender_txn_count_24h = right_idx - left_24h

        sender_amount_sum_24h = 0.0
        for i in range(left_24h, right_idx):
            sender_amount_sum_24h += s_hist[i][1]

        if right_idx > left_30d:
            past_amts = [s_hist[i][1] for i in range(left_30d, right_idx)]
            hist_median = float(np.median(past_amts))
            amount_to_median_ratio = float(amount_bdt / hist_median) if hist_median > 0 else 1.0
        else:
            amount_to_median_ratio = 1.0

        # 6. Device and Auth features
        new_device_flag = 0 if device_id in self.sender_devices.get(sender_id, set()) else 1

        # PIN reset
        pin_list = self.auth_events.get(sender_id, {}).get("pin_reset", [])
        pin_right = bisect_left(pin_list, ts)
        if pin_right > 0:
            last_pin_ts = pin_list[pin_right - 1]
            minutes_since_pin_reset = min(43200.0, max(0.0, (ts - last_pin_ts).total_seconds() / 60.0))
        else:
            minutes_since_pin_reset = 43200.0

        # SIM change
        sim_list = self.auth_events.get(sender_id, {}).get("sim_change", [])
        sim_right = bisect_left(sim_list, ts)
        if sim_right > 0:
            last_sim_ts = sim_list[sim_right - 1]
            minutes_since_sim_change = min(43200.0, max(0.0, (ts - last_sim_ts).total_seconds() / 60.0))
        else:
            minutes_since_sim_change = 43200.0

        # 7. Recipient dynamic features
        recipient_unique_senders_1h = 0
        recipient_unique_senders_24h = 0
        recipient_first_time_sender_share_24h = 0.0
        recipient_inflow_24h = 0.0
        recipient_fan_in_7d = 0
        recipient_outflow_24h = 0.0
        recipient_pass_through_ratio_24h = 0.0
        recipient_median_receipt_to_out_minutes = 1440.0
        recipient_fan_out_7d = 0

        if recipient_id:
            r_in = self.recipient_inflows.get(recipient_id, [])
            r_in_ts = [entry[0] for entry in r_in]
            r_in_right = bisect_right(r_in_ts, ts)

            t_7d_cutoff = ts - timedelta(days=7)

            r_in_left_1h = bisect_left(r_in_ts, t_1h_cutoff, 0, r_in_right)
            r_in_left_24h = bisect_left(r_in_ts, t_24h_cutoff, 0, r_in_right)
            r_in_left_7d = bisect_left(r_in_ts, t_7d_cutoff, 0, r_in_right)

            # 1h unique senders
            if r_in_right > r_in_left_1h:
                senders_1h = {r_in[i][1] for i in range(r_in_left_1h, r_in_right)}
                recipient_unique_senders_1h = len(senders_1h)

            # 24h stats
            if r_in_right > r_in_left_24h:
                senders_24h = {r_in[i][1] for i in range(r_in_left_24h, r_in_right)}
                recipient_unique_senders_24h = len(senders_24h)

                is_first_flags = [1 if r_in[i][3] else 0 for i in range(r_in_left_24h, r_in_right)]
                recipient_first_time_sender_share_24h = float(np.mean(is_first_flags)) if is_first_flags else 0.0

                recipient_inflow_24h = float(sum(r_in[i][2] for i in range(r_in_left_24h, r_in_right)))

            # 7d fan-in
            if r_in_right > r_in_left_7d:
                senders_7d = {r_in[i][1] for i in range(r_in_left_7d, r_in_right)}
                recipient_fan_in_7d = len(senders_7d)

            # Outflows for recipient
            r_out = self.wallet_outflows.get(recipient_id, [])
            r_out_ts = [entry[0] for entry in r_out]
            r_out_right = bisect_right(r_out_ts, ts)
            r_out_left_24h = bisect_left(r_out_ts, t_24h_cutoff, 0, r_out_right)
            r_out_left_7d = bisect_left(r_out_ts, t_7d_cutoff, 0, r_out_right)

            if r_out_right > r_out_left_24h:
                recipient_outflow_24h = float(sum(r_out[i][2] for i in range(r_out_left_24h, r_out_right)))
                recipient_pass_through_ratio_24h = recipient_outflow_24h / (recipient_inflow_24h + 1.0)

            if r_out_right > r_out_left_7d:
                out_recipients = {r_out[i][1] or "" for i in range(r_out_left_7d, r_out_right)}
                recipient_fan_out_7d = len(out_recipients)

                # Delay calculation
                delays = []
                for i in range(r_out_left_7d, r_out_right):
                    out_t = r_out[i][0]
                    # Find prior receipt strictly before out_t
                    p_idx = bisect_left(r_in_ts, out_t) - 1
                    if p_idx >= 0:
                        delay_min = max(0.1, (out_t - r_in_ts[p_idx]).total_seconds() / 60.0)
                        delays.append(delay_min)
                if delays:
                    recipient_median_receipt_to_out_minutes = float(np.median(delays))

        # 8. Shared device wallet count (preceding 7d)
        d_hist = self.device_history.get(device_id, [])
        d_ts_list = [entry[0] for entry in d_hist]
        d_right = bisect_right(d_ts_list, ts)
        t_7d_cutoff = ts - timedelta(days=7)
        d_left = bisect_left(d_ts_list, t_7d_cutoff, 0, d_right)

        if d_right > d_left:
            unique_dev_senders = {d_hist[i][1] for i in range(d_left, d_right)}
            shared_device_wallet_count = max(1, len(unique_dev_senders))
        else:
            shared_device_wallet_count = 1

        # 9. Graph features: daily snapshot
        day = self._get_day_offset(ts)
        c_map, mule_share_map = self._get_or_build_snapshot(day)

        if recipient_id:
            component_size_7d = c_map.get(recipient_id, 1)
            two_hop_confirmed_mule_share = mule_share_map.get(recipient_id, 0.0)
        else:
            component_size_7d = 1
            two_hop_confirmed_mule_share = 0.0

        features = {
            "amount_to_median_ratio": float(amount_to_median_ratio),
            "sender_txn_count_1h": int(sender_txn_count_1h),
            "sender_txn_count_24h": int(sender_txn_count_24h),
            "sender_amount_sum_24h": float(sender_amount_sum_24h),
            "sender_tenure_days": float(sender_tenure_days),
            "balance_drain_ratio": float(balance_drain_ratio),
            "hour_of_day": int(hour_of_day),
            "is_night": int(is_night),
            "is_first_time_pair": int(is_first_time_pair),
            "pair_history_count": int(pair_history_count),
            "new_device_flag": int(new_device_flag),
            "minutes_since_pin_reset": float(minutes_since_pin_reset),
            "minutes_since_sim_change": float(minutes_since_sim_change),
            "session_seconds": float(session_seconds),
            "recipient_age_days": float(recipient_age_days),
            "recipient_owner_type_code": int(recipient_owner_type_code),
            "recipient_unique_senders_1h": int(recipient_unique_senders_1h),
            "recipient_unique_senders_24h": int(recipient_unique_senders_24h),
            "recipient_first_time_sender_share_24h": float(recipient_first_time_sender_share_24h),
            "recipient_inflow_24h": float(recipient_inflow_24h),
            "recipient_outflow_24h": float(recipient_outflow_24h),
            "recipient_pass_through_ratio_24h": float(recipient_pass_through_ratio_24h),
            "recipient_median_receipt_to_out_minutes": float(recipient_median_receipt_to_out_minutes),
            "recipient_fan_in_7d": int(recipient_fan_in_7d),
            "recipient_fan_out_7d": int(recipient_fan_out_7d),
            "shared_device_wallet_count": int(shared_device_wallet_count),
            "component_size_7d": int(component_size_7d),
            "two_hop_confirmed_mule_share": float(two_hop_confirmed_mule_share),
        }

        # 10. GNN features
        if self.embedding_store is not None:
            gnn_f = self.embedding_store.get_transaction_gnn_features(day, recipient_id, sender_id)
        else:
            gnn_f = {
                "gnn_recipient_mule_score": 0.0,
                "gnn_sender_mule_score": 0.0,
                "gnn_recipient_emb_0": 0.0,
                "gnn_recipient_emb_1": 0.0,
                "gnn_recipient_emb_2": 0.0,
                "gnn_recipient_emb_3": 0.0,
            }
        features.update(gnn_f)
        return features

    def update(self, event: Dict[str, Any] | pd.Series) -> None:
        """Update rolling state with a completed transaction or event."""
        event_type = event.get("event_type") if isinstance(event, dict) else event.get("event_type")

        # Check if auth event
        if event_type in ["pin_reset", "sim_change"]:
            w_id = str(event.get("wallet_id") if isinstance(event, dict) else event["wallet_id"])
            ts = _to_utc_dt(event.get("ts") if isinstance(event, dict) else event["ts"])
            self.register_auth_event(w_id, event_type, ts)
            return

        # Transaction event
        ts = _to_utc_dt(event.get("ts") if isinstance(event, dict) else event["ts"])
        sender_id = str(event.get("sender_wallet_id") if isinstance(event, dict) else event["sender_wallet_id"])
        recipient_id = event.get("recipient_wallet_id") if isinstance(event, dict) else event.get("recipient_wallet_id")
        recipient_id = str(recipient_id) if recipient_id is not None and pd.notna(recipient_id) and recipient_id != "" else None
        amount_bdt = float(event.get("amount_bdt") if isinstance(event, dict) else event["amount_bdt"])
        device_id = str(event.get("device_id") if isinstance(event, dict) else event.get("device_id", "default_device"))
        txn_type = str(event.get("type") if isinstance(event, dict) else event.get("type", "send_money"))

        if self.min_ts is None or ts < self.min_ts:
            self.min_ts = ts

        # 1. Update sender history
        self.sender_history[sender_id].append((ts, amount_bdt))

        # 2. Check if first time pair before incrementing
        pair_key = (sender_id, recipient_id) if recipient_id else (sender_id, "")
        is_first = (self.pair_history[pair_key] == 0)
        self.pair_history[pair_key] += 1

        # 3. Update device tracking
        self.sender_devices[sender_id].add(device_id)
        self.device_history[device_id].append((ts, sender_id))

        # 4. Update recipient inflows
        if recipient_id:
            self.recipient_inflows[recipient_id].append((ts, sender_id, amount_bdt, is_first))

        # 5. Update outflows
        if txn_type in ["cash_out", "send_money"]:
            self.wallet_outflows[sender_id].append((ts, recipient_id, amount_bdt))

        # 6. Update graph edge history (customer-to-customer P2P send_money, and customer-device)
        sender_owner = self.wallet_meta.get(sender_id, (ts, "customer"))[1]
        rec_owner = self.wallet_meta.get(recipient_id, (ts, "customer"))[1] if recipient_id else None

        day = self._get_day_offset(ts)
        if txn_type == "send_money" and recipient_id and sender_owner == "customer" and rec_owner == "customer":
            self.edges_by_day[day].append((sender_id, recipient_id))

        if sender_owner == "customer" and device_id:
            self.dev_edges_by_day[day].append((sender_id, device_id))

    def recipient_first_inflow_minutes(self, recipient_id: Optional[str], ts: Any, window_hours: float = 24.0) -> float:
        """Minutes since the recipient's first inflow in the trailing window, strictly before ts.

        Feeds `time_left = golden_window_minutes - minutes_since_recipient_first_inflow`
        (ARCHITECTURE.md Section 11). Returns 0.0 when the recipient has no recent inflow.
        """
        if not recipient_id:
            return 0.0
        now = _to_utc_dt(ts)
        earliest = None
        for inflow_ts, _sender, _amt, _first in self.recipient_inflows.get(recipient_id, []):
            if inflow_ts < now and (now - inflow_ts).total_seconds() <= window_hours * 3600.0:
                if earliest is None or inflow_ts < earliest:
                    earliest = inflow_ts
        if earliest is None:
            return 0.0
        return max(0.0, (now - earliest).total_seconds() / 60.0)

    def recipient_cashed_out(self, recipient_id: Optional[str], ts: Any, window_hours: float = 24.0) -> bool:
        """True if the recipient already moved money out in the trailing window before ts."""
        if not recipient_id:
            return False
        now = _to_utc_dt(ts)
        return any(
            out_ts < now and (now - out_ts).total_seconds() <= window_hours * 3600.0
            for out_ts, _dest, _amt in self.wallet_outflows.get(recipient_id, [])
        )

    def warm_from_history(self, raw_dir: Path | str, cutoff_ts: Optional[Any] = None) -> int:
        """Warm online feature store from historical raw data up to cutoff_ts."""
        r_dir = Path(raw_dir)
        logger.info("Warming online feature store from %s (cutoff: %s)", r_dir, cutoff_ts)

        cutoff_dt = _to_utc_dt(cutoff_ts) if cutoff_ts is not None else None

        # 1. Wallets
        wallets_df = pd.read_parquet(r_dir / "wallets.parquet")
        for _, row in wallets_df.iterrows():
            self.register_wallet(row["wallet_id"], row["opened_at"], row["owner_type"])

        # 2. Auth events
        auth_df = pd.read_parquet(r_dir / "auth_events.parquet")
        for _, row in auth_df.iterrows():
            event_dt = _to_utc_dt(row["ts"])
            if cutoff_dt is None or event_dt < cutoff_dt:
                self.register_auth_event(row["wallet_id"], row["event_type"], event_dt)

        # 3. Confirmations
        conf_df = pd.read_parquet(r_dir / "confirmations.parquet")
        for _, row in conf_df.iterrows():
            self.register_confirmation(row["wallet_id"], row["confirmed_at"])

        # 4. Transactions
        txns_df = pd.read_parquet(r_dir / "transactions.parquet").sort_values(["ts", "txn_id"]).reset_index(drop=True)
        if len(txns_df) > 0:
            self.min_ts = _to_utc_dt(txns_df["ts"].min())

        count = 0
        for _, row in txns_df.iterrows():
            row_dt = _to_utc_dt(row["ts"])
            if cutoff_dt is not None and row_dt >= cutoff_dt:
                break
            self.update(row)
            count += 1

        logger.info("Online feature store warmed with %d historical transactions", count)
        return count
