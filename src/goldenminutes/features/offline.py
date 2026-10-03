"""Offline feature builder for GoldenMinutes.

Vectorized batch feature extractor that constructs point-in-time correct features
from raw canonical tables without reading labels or hidden_truth.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Set

import networkx as nx
import numpy as np
import pandas as pd

from goldenminutes.features.specs import FEATURE_MAP, FEATURE_NAMES

logger = logging.getLogger("goldenminutes.features.offline")


class OfflineFeatureBuilder:
    """Vectorized offline feature generation pipeline."""

    def __init__(self, raw_dir: Path | str):
        self.raw_dir = Path(raw_dir)
        self.transactions: Optional[pd.DataFrame] = None
        self.wallets: Optional[pd.DataFrame] = None
        self.customers: Optional[pd.DataFrame] = None
        self.auth_events: Optional[pd.DataFrame] = None
        self.confirmations: Optional[pd.DataFrame] = None
        self.device_links: Optional[pd.DataFrame] = None

    def load_raw_data(self) -> None:
        """Load canonical input tables. Never loads labels or hidden_truth."""
        logger.info(f"Loading canonical raw data from {self.raw_dir}")
        self.transactions = pd.read_parquet(self.raw_dir / "transactions.parquet")
        self.wallets = pd.read_parquet(self.raw_dir / "wallets.parquet")
        self.customers = pd.read_parquet(self.raw_dir / "customers.parquet")
        self.auth_events = pd.read_parquet(self.raw_dir / "auth_events.parquet")
        self.confirmations = pd.read_parquet(self.raw_dir / "confirmations.parquet")
        self.device_links = pd.read_parquet(self.raw_dir / "device_links.parquet")

        # Ensure datetime64[ns, UTC]
        for df in [self.transactions, self.auth_events, self.confirmations, self.wallets]:
            for col in ["ts", "opened_at", "confirmed_at", "registered_at"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True)

        self.transactions = self.transactions.sort_values(["ts", "txn_id"]).reset_index(drop=True)

    def compute_features(self) -> pd.DataFrame:
        """Compute all features in a point-in-time correct, vectorized manner."""
        if self.transactions is None:
            self.load_raw_data()

        txns = self.transactions.copy()
        n_rows = len(txns)
        logger.info(f"Computing offline features for {n_rows:,} transactions...")

        # 1. Base time and split columns
        ts = txns["ts"]
        min_ts = ts.min()
        day_offset = (ts - min_ts).dt.total_seconds() / 86400.0
        total_days = day_offset.max()

        if total_days <= 35:  # small profile (30 days)
            splits = np.where(day_offset <= 20.0, "train", np.where(day_offset <= 25.0, "val", "test"))
        else:  # full profile (90 days)
            splits = np.where(day_offset <= 60.0, "train", np.where(day_offset <= 75.0, "val", "test"))
        txns["split"] = splits

        # 2. Time of day features
        hour_of_day = ts.dt.hour.values
        is_night = ((hour_of_day >= 23) | (hour_of_day <= 5)).astype(np.int64)

        # 3. Balance drain ratio
        bal_before = txns["balance_before"].values
        amt = txns["amount_bdt"].values
        safe_bal = np.maximum(bal_before, 1e-6)
        balance_drain_ratio = np.where(bal_before > 0, np.clip(amt / safe_bal, 0.0, 1.0), 0.0)

        # 4. Wallet tenures
        wallet_opened_map = dict(zip(self.wallets["wallet_id"], self.wallets["opened_at"], strict=False))
        wallet_owner_map = dict(zip(self.wallets["wallet_id"], self.wallets["owner_type"], strict=False))

        sender_opened = pd.Series(txns["sender_wallet_id"].map(wallet_opened_map))
        recipient_opened = pd.Series(txns["recipient_wallet_id"].map(wallet_opened_map))

        sender_tenure_days = np.maximum(0.0, (ts - sender_opened).dt.total_seconds().values / 86400.0)
        sender_tenure_days = np.nan_to_num(sender_tenure_days, nan=0.0)

        recipient_age_days = np.maximum(0.0, (ts - recipient_opened).dt.total_seconds().values / 86400.0)
        recipient_age_days = np.nan_to_num(recipient_age_days, nan=0.0)

        owner_type_series = txns["recipient_wallet_id"].map(wallet_owner_map).fillna("customer")
        owner_type_code_map = {"customer": 0, "agent": 1, "merchant": 2}
        recipient_owner_type_code = owner_type_series.map(owner_type_code_map).values.astype(np.int64)

        # 5. Pair features (instant vectorized cumcount)
        pair_key = txns["sender_wallet_id"] + "_" + txns["recipient_wallet_id"].fillna("")
        pair_history_count = txns.groupby(pair_key, observed=True).cumcount().values.astype(np.int64)
        is_first_time_pair = (pair_history_count == 0).astype(np.int64)

        # 6. Sender rolling features (30d median, 1h count, 24h count, 24h sum)
        logger.info("Computing sender rolling statistics...")
        ts_ns = ts.values.astype("datetime64[ns]").view("int64")
        one_hour_ns = int(3600 * 1e9)
        twenty_four_hours_ns = int(86400 * 1e9)
        thirty_days_ns = int(30 * 86400 * 1e9)

        sender_txn_count_1h = np.zeros(n_rows, dtype=np.int64)
        sender_txn_count_24h = np.zeros(n_rows, dtype=np.int64)
        sender_amount_sum_24h = np.zeros(n_rows, dtype=np.float64)
        amount_to_median_ratio = np.ones(n_rows, dtype=np.float64)

        # Vectorized sender grouping with searchsorted
        sender_groups = txns.groupby("sender_wallet_id", observed=True).indices
        for _, indices in sender_groups.items():
            if len(indices) == 0:
                continue
            s_ts = ts_ns[indices]
            s_amt = amt[indices]

            # 1h window
            idx_1h = np.searchsorted(s_ts, s_ts - one_hour_ns, side="left")
            # 24h window
            idx_24h = np.searchsorted(s_ts, s_ts - twenty_four_hours_ns, side="left")
            # 30d window
            idx_30d = np.searchsorted(s_ts, s_ts - thirty_days_ns, side="left")

            counts_1h = (np.arange(len(indices)) - idx_1h).astype(np.int64)
            counts_24h = (np.arange(len(indices)) - idx_24h).astype(np.int64)

            # Cumulative sum for fast range sum
            prefix_amt = np.empty(len(s_amt) + 1, dtype=np.float64)
            prefix_amt[0] = 0.0
            np.cumsum(s_amt, out=prefix_amt[1:])
            sums_24h = prefix_amt[np.arange(len(indices))] - prefix_amt[idx_24h]

            sender_txn_count_1h[indices] = counts_1h
            sender_txn_count_24h[indices] = counts_24h
            sender_amount_sum_24h[indices] = sums_24h

            # 30d median
            for pos in range(len(indices)):
                start = idx_30d[pos]
                if pos > start:
                    hist_median = float(np.median(s_amt[start:pos]))
                    if hist_median > 0:
                        amount_to_median_ratio[indices[pos]] = s_amt[pos] / hist_median

        # 7. Device and Auth Features
        logger.info("Computing device and auth features...")
        session_seconds = txns["session_seconds"].values.astype(np.float64)

        # Device seen previously for this sender wallet
        sender_dev_key = txns["sender_wallet_id"] + "_" + txns["device_id"]
        sender_dev_cumcount = txns.groupby(sender_dev_key, observed=True).cumcount().values
        new_device_flag = (sender_dev_cumcount == 0).astype(np.int64)

        # Minutes since auth events via merge_asof
        pin_resets = self.auth_events[self.auth_events["event_type"] == "pin_reset"].sort_values("ts")
        sim_changes = self.auth_events[self.auth_events["event_type"] == "sim_change"].sort_values("ts")

        txns_for_join = txns[["ts", "sender_wallet_id"]].copy()

        # Join PIN resets
        if len(pin_resets) > 0:
            m_pin = pd.merge_asof(
                txns_for_join,
                pin_resets[["ts", "wallet_id"]].rename(columns={"ts": "pin_ts"}),
                left_on="ts",
                right_on="pin_ts",
                left_by="sender_wallet_id",
                right_by="wallet_id",
                direction="backward",
                allow_exact_matches=False,
            )
            delta_pin_min = (m_pin["ts"] - m_pin["pin_ts"]).dt.total_seconds().values / 60.0
            minutes_since_pin_reset = np.clip(np.nan_to_num(delta_pin_min, nan=43200.0), 0.0, 43200.0)
        else:
            minutes_since_pin_reset = np.full(n_rows, 43200.0)

        # Join SIM changes
        if len(sim_changes) > 0:
            m_sim = pd.merge_asof(
                txns_for_join,
                sim_changes[["ts", "wallet_id"]].rename(columns={"ts": "sim_ts"}),
                left_on="ts",
                right_on="sim_ts",
                left_by="sender_wallet_id",
                right_by="wallet_id",
                direction="backward",
                allow_exact_matches=False,
            )
            delta_sim_min = (m_sim["ts"] - m_sim["sim_ts"]).dt.total_seconds().values / 60.0
            minutes_since_sim_change = np.clip(np.nan_to_num(delta_sim_min, nan=43200.0), 0.0, 43200.0)
        else:
            minutes_since_sim_change = np.full(n_rows, 43200.0)

        # 8. Recipient behavior & Fan-in Features
        logger.info("Computing recipient dynamics and inflow/outflow...")
        recipient_unique_senders_1h = np.zeros(n_rows, dtype=np.int64)
        recipient_unique_senders_24h = np.zeros(n_rows, dtype=np.int64)
        recipient_first_time_sender_share_24h = np.zeros(n_rows, dtype=np.float64)
        recipient_inflow_24h = np.zeros(n_rows, dtype=np.float64)
        recipient_fan_in_7d = np.zeros(n_rows, dtype=np.int64)

        seven_days_ns = int(7 * 86400 * 1e9)

        # Group by recipient_wallet_id
        valid_rec_mask = txns["recipient_wallet_id"].notna().values
        rec_indices = np.where(valid_rec_mask)[0]

        # Fast sender categoricals
        sender_codes = pd.Categorical(txns["sender_wallet_id"]).codes

        rec_groups = txns.iloc[rec_indices].groupby("recipient_wallet_id", observed=True).indices
        for _, local_idx in rec_groups.items():
            if len(local_idx) == 0:
                continue
            orig_idx = rec_indices[local_idx]
            r_ts = ts_ns[orig_idx]
            r_amt = amt[orig_idx]
            r_senders = sender_codes[orig_idx]
            r_is_first = is_first_time_pair[orig_idx]

            idx_1h = np.searchsorted(r_ts, r_ts - one_hour_ns, side="left")
            idx_24h = np.searchsorted(r_ts, r_ts - twenty_four_hours_ns, side="left")
            idx_7d = np.searchsorted(r_ts, r_ts - seven_days_ns, side="left")

            prefix_r_amt = np.empty(len(r_amt) + 1, dtype=np.float64)
            prefix_r_amt[0] = 0.0
            np.cumsum(r_amt, out=prefix_r_amt[1:])

            for pos in range(len(orig_idx)):
                i_row = orig_idx[pos]

                # 1h unique senders
                st_1h = idx_1h[pos]
                if pos > st_1h:
                    recipient_unique_senders_1h[i_row] = len(np.unique(r_senders[st_1h:pos]))

                # 24h unique senders & first-time share & inflow
                st_24h = idx_24h[pos]
                if pos > st_24h:
                    w_senders = r_senders[st_24h:pos]
                    recipient_unique_senders_24h[i_row] = len(np.unique(w_senders))
                    recipient_first_time_sender_share_24h[i_row] = float(np.mean(r_is_first[st_24h:pos]))
                    recipient_inflow_24h[i_row] = prefix_r_amt[pos] - prefix_r_amt[st_24h]

                # 7d fan-in
                st_7d = idx_7d[pos]
                if pos > st_7d:
                    recipient_fan_in_7d[i_row] = len(np.unique(r_senders[st_7d:pos]))

        # 9. Recipient outflow, pass-through, and median cash-out delay
        logger.info("Computing recipient outflow and cash-out delay...")
        recipient_outflow_24h = np.zeros(n_rows, dtype=np.float64)
        recipient_pass_through_ratio_24h = np.zeros(n_rows, dtype=np.float64)
        recipient_median_receipt_to_out_minutes = np.full(n_rows, 1440.0, dtype=np.float64)
        recipient_fan_out_7d = np.zeros(n_rows, dtype=np.int64)

        # Index outflows: transactions where sender disbursed funds
        outflows_df = txns[txns["type"].isin(["cash_out", "send_money"])][
            ["ts", "sender_wallet_id", "amount_bdt", "recipient_wallet_id"]
        ].copy()
        outflows_df["out_ts_ns"] = outflows_df["ts"].values.astype("datetime64[ns]").view("int64")

        rec_codes = pd.Categorical(outflows_df["recipient_wallet_id"].fillna("")).codes
        outflows_df["rec_code"] = rec_codes

        outflow_groups = outflows_df.groupby("sender_wallet_id", observed=True).indices

        for rec_id, local_idx in rec_groups.items():
            if rec_id not in outflow_groups:
                continue
            orig_idx = rec_indices[local_idx]
            r_ts = ts_ns[orig_idx]

            out_indices = outflow_groups[rec_id]
            o_ts = outflows_df["out_ts_ns"].values[out_indices]
            o_amt = outflows_df["amount_bdt"].values[out_indices]
            o_rec_codes = outflows_df["rec_code"].values[out_indices]

            prefix_o_amt = np.empty(len(o_amt) + 1, dtype=np.float64)
            prefix_o_amt[0] = 0.0
            np.cumsum(o_amt, out=prefix_o_amt[1:])

            for pos in range(len(orig_idx)):
                i_row = orig_idx[pos]
                curr_t = r_ts[pos]

                # Outflow in preceding 24h
                left_24 = np.searchsorted(o_ts, curr_t - twenty_four_hours_ns, side="left")
                right_24 = np.searchsorted(o_ts, curr_t, side="left")
                if right_24 > left_24:
                    outflow = prefix_o_amt[right_24] - prefix_o_amt[left_24]
                    recipient_outflow_24h[i_row] = outflow
                    inflow = recipient_inflow_24h[i_row]
                    recipient_pass_through_ratio_24h[i_row] = outflow / (inflow + 1.0)

                # Fan-out in 7d
                left_7d = np.searchsorted(o_ts, curr_t - seven_days_ns, side="left")
                if right_24 > left_7d:
                    recipient_fan_out_7d[i_row] = len(np.unique(o_rec_codes[left_7d:right_24]))

                # Median delay between receipt and outflow in last 7d
                if right_24 > left_7d:
                    delays = []
                    for o_idx in range(left_7d, right_24):
                        out_t = o_ts[o_idx]
                        # Prior receipt before out_t
                        p_rec_idx = np.searchsorted(r_ts, out_t, side="left") - 1
                        if p_rec_idx >= 0:
                            delay_min = max(0.1, (out_t - r_ts[p_rec_idx]) / (60 * 1e9))
                            delays.append(delay_min)
                    if delays:
                        recipient_median_receipt_to_out_minutes[i_row] = float(np.median(delays))

        # 10. Device sharing (7-day window)
        logger.info("Computing shared device counts...")
        shared_device_wallet_count = np.ones(n_rows, dtype=np.int64)
        dev_groups = txns.groupby("device_id", observed=True).indices
        for _, indices in dev_groups.items():
            if len(indices) <= 1:
                continue
            d_ts = ts_ns[indices]
            d_senders = sender_codes[indices]
            idx_7d = np.searchsorted(d_ts, d_ts - seven_days_ns, side="left")
            for pos in range(len(indices)):
                st = idx_7d[pos]
                if pos > st:
                    shared_device_wallet_count[indices[pos]] = max(1, len(np.unique(d_senders[st:pos])))

        # 11. Daily Snapshot Graph & Component Features & 2-hop Confirmed Mule Share
        logger.info("Building daily graph snapshots and 2-hop confirmed mule share...")
        component_size_7d = np.ones(n_rows, dtype=np.int64)
        two_hop_confirmed_mule_share = np.zeros(n_rows, dtype=np.float64)

        # Day bucket
        txns_day = ((ts - min_ts).dt.total_seconds() / 86400.0).astype(int).values
        unique_days = np.unique(txns_day)

        # Parse confirmations strictly
        conf_df = self.confirmations.copy()
        conf_df["conf_ts_ns"] = conf_df["confirmed_at"].values.astype("datetime64[ns]").view("int64")

        # Precompute daily graph snapshots using day D-1
        daily_graphs: Dict[int, nx.Graph] = {}
        daily_comp_sizes: Dict[int, Dict[str, int]] = {}
        daily_2hop_neighbors: Dict[int, Dict[str, Set[str]]] = {}

        # Edges candidate: transfers and cash-outs
        edge_txns = txns[txns["recipient_wallet_id"].notna()][
            ["sender_wallet_id", "recipient_wallet_id", "ts"]
        ].copy()
        edge_txns["day"] = ((edge_txns["ts"] - min_ts).dt.total_seconds() / 86400.0).astype(int).values

        for day in unique_days:
            # Previous day's snapshot covers [day - 7, day - 1]
            snap_start = max(0, day - 7)
            snap_end = day - 1
            if snap_end < 0:
                daily_graphs[day] = nx.Graph()
                daily_comp_sizes[day] = {}
                daily_2hop_neighbors[day] = {}
                continue

            sub_edges = edge_txns[(edge_txns["day"] >= snap_start) & (edge_txns["day"] <= snap_end)]
            G = nx.Graph()
            for u, v in zip(sub_edges["sender_wallet_id"], sub_edges["recipient_wallet_id"], strict=False):
                G.add_edge(u, v)

            daily_graphs[day] = G
            comps = list(nx.connected_components(G))
            c_map = {}
            for c in comps:
                sz = len(c)
                for node in c:
                    c_map[node] = sz
            daily_comp_sizes[day] = c_map

            # 2-hop neighbors mapping
            two_hop_map = {}
            for node in G.nodes():
                neighbors_1 = set(G.neighbors(node))
                neighbors_2 = set()
                for n1 in neighbors_1:
                    neighbors_2.update(G.neighbors(n1))
                neighbors_2.discard(node)
                two_hop_map[node] = neighbors_2
            daily_2hop_neighbors[day] = two_hop_map

        # Assign component sizes and 2-hop mule share
        for day in unique_days:
            day_mask = (txns_day == day)
            day_indices = np.where(day_mask)[0]
            c_map = daily_comp_sizes.get(day, {})
            two_hop_map = daily_2hop_neighbors.get(day, {})

            # Active confirmations as of day start
            day_start_ns = int(min_ts.value + day * 86400 * 1e9)
            active_confs = set(conf_df[conf_df["conf_ts_ns"] <= day_start_ns]["wallet_id"].values)

            # Precompute mule share for all nodes in this day's graph
            day_mule_shares = {}
            for node, neighbors in two_hop_map.items():
                if neighbors:
                    day_mule_shares[node] = len(neighbors.intersection(active_confs)) / len(neighbors)

            for idx in day_indices:
                r_id = txns["recipient_wallet_id"].iloc[idx]
                if pd.notna(r_id):
                    if r_id in c_map:
                        component_size_7d[idx] = c_map[r_id]
                    if r_id in day_mule_shares:
                        two_hop_confirmed_mule_share[idx] = day_mule_shares[r_id]

        # Assemble final features dataframe
        features_dict = {
            "amount_to_median_ratio": amount_to_median_ratio,
            "sender_txn_count_1h": sender_txn_count_1h,
            "sender_txn_count_24h": sender_txn_count_24h,
            "sender_amount_sum_24h": sender_amount_sum_24h,
            "sender_tenure_days": sender_tenure_days,
            "balance_drain_ratio": balance_drain_ratio,
            "hour_of_day": hour_of_day,
            "is_night": is_night,
            "is_first_time_pair": is_first_time_pair,
            "pair_history_count": pair_history_count,
            "new_device_flag": new_device_flag,
            "minutes_since_pin_reset": minutes_since_pin_reset,
            "minutes_since_sim_change": minutes_since_sim_change,
            "session_seconds": session_seconds,
            "recipient_age_days": recipient_age_days,
            "recipient_owner_type_code": recipient_owner_type_code,
            "recipient_unique_senders_1h": recipient_unique_senders_1h,
            "recipient_unique_senders_24h": recipient_unique_senders_24h,
            "recipient_first_time_sender_share_24h": recipient_first_time_sender_share_24h,
            "recipient_inflow_24h": recipient_inflow_24h,
            "recipient_outflow_24h": recipient_outflow_24h,
            "recipient_pass_through_ratio_24h": recipient_pass_through_ratio_24h,
            "recipient_median_receipt_to_out_minutes": recipient_median_receipt_to_out_minutes,
            "recipient_fan_in_7d": recipient_fan_in_7d,
            "recipient_fan_out_7d": recipient_fan_out_7d,
            "shared_device_wallet_count": shared_device_wallet_count,
            "component_size_7d": component_size_7d,
            "two_hop_confirmed_mule_share": two_hop_confirmed_mule_share,
        }

        # Validate against FEATURE_SPECS
        for name in FEATURE_NAMES:
            spec = FEATURE_MAP[name]
            features_dict[name] = features_dict[name].astype(spec.dtype)

        # Meta identification columns
        meta_df = txns[
            ["txn_id", "ts", "sender_wallet_id", "recipient_wallet_id", "amount_bdt", "channel", "type", "split"]
        ].copy()

        features_df = pd.concat([meta_df, pd.DataFrame(features_dict, index=txns.index)], axis=1)
        logger.info(f"Offline feature computation complete. Shape: {features_df.shape}")
        return features_df

    def build_and_save(self, output_path: Path | str) -> Path:
        """Run feature extraction and save partitioned Parquet."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        features_df = self.compute_features()
        features_df.to_parquet(out, index=False)
        logger.info(f"Saved features to {out}")
        return out


def main():
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Build offline features for GoldenMinutes.")
    parser.add_argument("--profile", choices=["small", "full"], default="small", help="Dataset profile to process.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    repo_root = Path(__file__).resolve().parents[3]
    raw_dir = repo_root / "data" / "raw" / args.profile
    processed_dir = repo_root / "data" / "processed" / args.profile
    out_file = processed_dir / "features.parquet"

    t0 = time.time()
    builder = OfflineFeatureBuilder(raw_dir=raw_dir)
    builder.build_and_save(out_file)
    elapsed = time.time() - t0
    logger.info(f"Offline feature generation for {args.profile} finished in {elapsed:.2f}s.")


if __name__ == "__main__":
    main()
