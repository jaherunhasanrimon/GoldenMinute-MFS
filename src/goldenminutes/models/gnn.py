"""GraphSAGE neural network for mule account detection and graph embedding extraction.

Implements a 2-layer GraphSAGE architecture (Hamilton et al., 2017) in pure PyTorch
with mean aggregation over heterogeneous relations (P2P transfer and shared device).
Trained semi-supervised strictly on `confirmations` (confirmed_at <= snapshot_end)
without touching fraud labels or hidden truth (ARCHITECTURE.md Section 8 & Phase 1).
"""

from __future__ import annotations

import logging

# Cap torch's inter-op and intra-op parallelism to 1 thread.
# macOS Accelerate BLAS crashes when run concurrently with another BLAS-backed
# library (LightGBM / OpenBLAS) in the same process.  Single-threaded torch is
# safe and sufficient for the small GNN we use here.
import os as _os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# LightGBM must initialise its OpenMP runtime before torch does; on macOS the
# reverse order segfaults the first time LightGBM predicts in the same process.
import lightgbm  # noqa: F401, I001
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

from goldenminutes.features.graph import build_p2p_snapshot_graph
from goldenminutes.models.embedding_store import InMemoryEmbeddingStore

_os.environ.setdefault("OMP_NUM_THREADS", "1")
_os.environ.setdefault("MKL_NUM_THREADS", "1")
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

logger = logging.getLogger("goldenminutes.models.gnn")

NODE_FEATURE_NAMES = [
    "tenure_days",
    "inflow_count_7d",
    "inflow_amount_7d",
    "outflow_count_7d",
    "outflow_amount_7d",
    "pass_through_ratio",
    "device_count_7d",
    "two_hop_confirmed_share",
]


class SAGEConv(nn.Module):
    """GraphSAGE convolution layer with mean neighborhood aggregation."""

    def __init__(self, in_features: int, out_features: int, bias: bool = True) -> None:
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.linear_self = nn.Linear(in_features, out_features, bias=False)
        self.linear_neigh = nn.Linear(in_features, out_features, bias=bias)

    def forward(self, x: torch.Tensor, adj_norm: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Node features of shape (N, in_features).
            adj_norm: Row-normalized sparse or dense adjacency matrix of shape (N, N).
        """
        if adj_norm.is_sparse:
            neigh_agg = torch.spmm(adj_norm, x)
        else:
            neigh_agg = torch.matmul(adj_norm, x)

        h_self = self.linear_self(x)
        h_neigh = self.linear_neigh(neigh_agg)
        return h_self + h_neigh


class MuleGraphSAGE(nn.Module):
    """2-layer GraphSAGE for node classification and low-dimensional graph embedding."""

    def __init__(self, in_dim: int = 8, hidden_dim: int = 32, emb_dim: int = 4) -> None:
        super().__init__()
        self.in_dim = in_dim
        self.hidden_dim = hidden_dim
        self.emb_dim = emb_dim

        self.conv1 = SAGEConv(in_dim, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, hidden_dim)
        self.proj_emb = nn.Linear(hidden_dim, emb_dim)
        self.classifier = nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor, adj_norm: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass returning logits, probabilities, and low-dim embeddings.

        Returns:
            (logits of shape (N,), probs of shape (N,), embeddings of shape (N, emb_dim))
        """
        h1 = F.relu(self.conv1(x, adj_norm))
        h2 = F.relu(self.conv2(h1, adj_norm))

        logits = self.classifier(h2).squeeze(-1)
        probs = torch.sigmoid(logits)
        embs = self.proj_emb(h2)

        return logits, probs, embs

    def save(self, path: Path | str) -> None:
        """Save model checkpoint."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.state_dict(),
                "in_dim": self.in_dim,
                "hidden_dim": self.hidden_dim,
                "emb_dim": self.emb_dim,
            },
            p,
        )

    @classmethod
    def load(cls, path: Path | str) -> MuleGraphSAGE:
        """Load model checkpoint."""
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        model = cls(
            in_dim=ckpt.get("in_dim", 8),
            hidden_dim=ckpt.get("hidden_dim", 32),
            emb_dim=ckpt.get("emb_dim", 4),
        )
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        return model


def build_snapshot_graph_data(
    wallets_df: pd.DataFrame,
    txns_window_df: pd.DataFrame,
    active_confirmations: Set[str],
    min_ts: pd.Timestamp,
    snap_end_ts: pd.Timestamp,
) -> Tuple[List[str], np.ndarray, torch.Tensor, Set[str]]:
    """Construct wallet nodes, node features, and normalized sparse adjacency for a snapshot window.

    Args:
        wallets_df: Wallets table containing wallet_id, opened_at, owner_type.
        txns_window_df: Transactions occurring in [snap_start, snap_end].
        active_confirmations: Wallets confirmed prior to snapshot boundary.
        min_ts: Global dataset start timestamp.
        snap_end_ts: Snapshot boundary timestamp.

    Returns:
        (node_ids, features_np, adj_sparse_tensor, positive_wallets)
    """
    # Customer wallets
    cust_mask = wallets_df["owner_type"] == "customer"
    cust_wallets = wallets_df[cust_mask].copy()
    wallet_opened_map = dict(zip(cust_wallets["wallet_id"], cust_wallets["opened_at"], strict=False))

    # Relevant wallets active or present in snapshot
    w_senders = set(txns_window_df["sender_wallet_id"].dropna().unique())
    w_recipients = set(txns_window_df["recipient_wallet_id"].dropna().unique())
    active_wallets_in_txns = (w_senders | w_recipients).intersection(wallet_opened_map.keys())

    # Include all confirmed wallets even if inactive in this window
    all_node_set = sorted(active_wallets_in_txns | active_confirmations.intersection(wallet_opened_map.keys()))
    if not all_node_set:
        all_node_set = sorted(list(wallet_opened_map.keys())[:100])

    node_ids = all_node_set
    node_to_idx = {w: i for i, w in enumerate(node_ids)}
    n_nodes = len(node_ids)

    # 1. Compute node features
    # Tenure in days
    tenures = np.zeros(n_nodes, dtype=np.float32)
    for i, w in enumerate(node_ids):
        op = pd.to_datetime(wallet_opened_map.get(w, min_ts), utc=True)
        tenures[i] = max(0.0, (snap_end_ts - op).total_seconds() / 86400.0)

    # Inflows and Outflows in window
    inflow_cnt = np.zeros(n_nodes, dtype=np.float32)
    inflow_amt = np.zeros(n_nodes, dtype=np.float32)
    outflow_cnt = np.zeros(n_nodes, dtype=np.float32)
    outflow_amt = np.zeros(n_nodes, dtype=np.float32)
    devices_per_wallet: Dict[str, Set[str]] = {w: set() for w in node_ids}

    # Aggregate window transactions
    p2p_mask = (txns_window_df["type"] == "send_money") & txns_window_df["recipient_wallet_id"].notna()
    p2p_txns = txns_window_df[p2p_mask]

    for _, r in p2p_txns.iterrows():
        s = r["sender_wallet_id"]
        rec = r["recipient_wallet_id"]
        amt = float(r["amount_bdt"])
        dev = r.get("device_id")

        if s in node_to_idx:
            outflow_cnt[node_to_idx[s]] += 1.0
            outflow_amt[node_to_idx[s]] += amt
            if dev and pd.notna(dev):
                devices_per_wallet[s].add(str(dev))

        if rec in node_to_idx:
            inflow_cnt[node_to_idx[rec]] += 1.0
            inflow_amt[node_to_idx[rec]] += amt

    # Outflows from cash_outs
    cashout_mask = txns_window_df["type"] == "cash_out"
    for _, r in txns_window_df[cashout_mask].iterrows():
        s = r["sender_wallet_id"]
        amt = float(r["amount_bdt"])
        dev = r.get("device_id")
        if s in node_to_idx:
            outflow_cnt[node_to_idx[s]] += 1.0
            outflow_amt[node_to_idx[s]] += amt
            if dev and pd.notna(dev):
                devices_per_wallet[s].add(str(dev))

    pass_through = outflow_amt / (inflow_amt + 1.0)
    device_cnt = np.array([len(devices_per_wallet[w]) for w in node_ids], dtype=np.float32)

    # NetworkX 2-hop mule share
    p2p_edges = [
        (r["sender_wallet_id"], r["recipient_wallet_id"])
        for _, r in p2p_txns.iterrows()
        if r["sender_wallet_id"] in node_to_idx and r["recipient_wallet_id"] in node_to_idx
    ]
    dev_edges = []
    for w in node_ids:
        for d in devices_per_wallet[w]:
            dev_edges.append((w, d))

    _, mule_shares, _ = build_p2p_snapshot_graph(
        edges=p2p_edges,
        device_edges=dev_edges,
        active_confirmations=active_confirmations,
    )
    two_hop_share = np.array([mule_shares.get(w, 0.0) for w in node_ids], dtype=np.float32)

    # Assemble and normalize node features
    feats = np.stack(
        [
            tenures,
            inflow_cnt,
            inflow_amt,
            outflow_cnt,
            outflow_amt,
            pass_through,
            device_cnt,
            two_hop_share,
        ],
        axis=1,
    )

    # 2. Build adjacency edges
    edge_src: List[int] = []
    edge_dst: List[int] = []

    # Self-loops for all nodes
    for i in range(n_nodes):
        edge_src.append(i)
        edge_dst.append(i)

    # P2P bidirectional edges
    for u, v in p2p_edges:
        if u != v:
            iu, iv = node_to_idx[u], node_to_idx[v]
            edge_src.extend([iu, iv])
            edge_dst.extend([iv, iu])

    # Shared device edges (two wallets sharing a device)
    dev_to_wallets: Dict[str, List[int]] = {}
    for w, d in dev_edges:
        dev_to_wallets.setdefault(d, []).append(node_to_idx[w])

    for _, w_indices in dev_to_wallets.items():
        if len(w_indices) > 1 and len(w_indices) < 20:  # avoid dense hubs
            for i_idx in range(len(w_indices)):
                for j_idx in range(i_idx + 1, len(w_indices)):
                    u_idx, v_idx = w_indices[i_idx], w_indices[j_idx]
                    edge_src.extend([u_idx, v_idx])
                    edge_dst.extend([v_idx, u_idx])

    # Row-normalized adjacency
    edge_src_arr = np.array(edge_src, dtype=np.int64)
    edge_dst_arr = np.array(edge_dst, dtype=np.int64)

    # Deduplicate edges
    edge_tuples = set(zip(edge_src_arr, edge_dst_arr, strict=False))
    if not edge_tuples:
        edge_tuples = {(i, i) for i in range(n_nodes)}

    src_list, dst_list = zip(*edge_tuples, strict=False)
    src_t = torch.tensor(src_list, dtype=torch.long)
    dst_t = torch.tensor(dst_list, dtype=torch.long)

    # Degree normalization: D^-1 * A
    # Compute in-degrees of destinations
    degrees = torch.zeros(n_nodes, dtype=torch.float32)
    degrees.index_add_(0, src_t, torch.ones_like(src_t, dtype=torch.float32))
    degrees = torch.clamp(degrees, min=1.0)
    norm_vals = 1.0 / degrees[src_t]

    indices = torch.stack([src_t, dst_t], dim=0)
    adj_sparse = torch.sparse_coo_tensor(indices, norm_vals, (n_nodes, n_nodes)).coalesce()

    pos_nodes = active_confirmations.intersection(node_ids)
    return node_ids, feats, adj_sparse, pos_nodes


def train_graphsage(
    wallets_df: pd.DataFrame,
    txns_df: pd.DataFrame,
    confirmations_df: pd.DataFrame,
    train_end_ts: pd.Timestamp,
    seed: int = 42,
    epochs: int = 60,
    lr: float = 0.01,
) -> Tuple[MuleGraphSAGE, np.ndarray, np.ndarray]:
    """Train MuleGraphSAGE on training split snapshot using confirmations only.

    Args:
        wallets_df: Wallets table.
        txns_df: Transactions table up to train split boundary.
        confirmations_df: Confirmations table.
        train_end_ts: Train split end boundary timestamp.
        seed: Random seed for reproducibility.
        epochs: Number of training epochs.
        lr: Learning rate.

    Returns:
        (trained_model, feature_mean, feature_std)
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    min_ts = pd.to_datetime(txns_df["ts"].min(), utc=True)
    snap_end_ts = pd.to_datetime(train_end_ts, utc=True)
    snap_start_ts = max(min_ts, snap_end_ts - pd.Timedelta(days=7))

    # Filter transactions to snapshot window
    txns_window = txns_df[(txns_df["ts"] >= snap_start_ts) & (txns_df["ts"] <= snap_end_ts)].copy()

    # Confirmations strictly before snapshot boundary
    conf_mask = pd.to_datetime(confirmations_df["confirmed_at"], utc=True) <= snap_end_ts
    active_confirmations = set(confirmations_df[conf_mask]["wallet_id"].values)

    node_ids, feats, adj_sparse, pos_nodes = build_snapshot_graph_data(
        wallets_df=wallets_df,
        txns_window_df=txns_window,
        active_confirmations=active_confirmations,
        min_ts=min_ts,
        snap_end_ts=snap_end_ts,
    )

    # Standardize features
    feat_mean = np.mean(feats, axis=0, keepdims=True)
    feat_std = np.std(feats, axis=0, keepdims=True) + 1e-5
    feats_norm = (feats - feat_mean) / feat_std

    x_tensor = torch.tensor(feats_norm, dtype=torch.float32)

    # Semi-supervised supervision: target labels
    n_nodes = len(node_ids)
    y_true = np.zeros(n_nodes, dtype=np.float32)
    for i, w in enumerate(node_ids):
        if w in pos_nodes:
            y_true[i] = 1.0

    n_pos = int(np.sum(y_true))
    pos_indices = np.where(y_true == 1.0)[0]
    neg_indices = np.where(y_true == 0.0)[0]

    # Sample balanced/semi-supervised mask (include all pos, sample up to 10x negatives)
    if n_pos > 0 and len(neg_indices) > 0:
        n_sample_neg = min(len(neg_indices), max(len(pos_indices) * 10, 50))
        sampled_neg = np.random.choice(neg_indices, size=n_sample_neg, replace=False)
        train_mask_idx = np.concatenate([pos_indices, sampled_neg])
        pos_weight_val = max(1.0, float(len(sampled_neg)) / max(1, n_pos))
    else:
        train_mask_idx = np.arange(n_nodes)
        pos_weight_val = 1.0

    train_mask = torch.tensor(train_mask_idx, dtype=torch.long)
    y_tensor = torch.tensor(y_true, dtype=torch.float32)
    pos_weight = torch.tensor([pos_weight_val], dtype=torch.float32)

    model = MuleGraphSAGE(in_dim=feats.shape[1], hidden_dim=32, emb_dim=4)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        logits, _, _ = model(x_tensor, adj_sparse)
        loss = criterion(logits[train_mask], y_tensor[train_mask])
        loss.backward()
        optimizer.step()

    model.eval()
    logger.info(
        f"Trained MuleGraphSAGE for {epochs} epochs on {n_nodes} nodes "
        f"({n_pos} positive confirmations, final loss: {loss.item():.4f})"
    )
    return model, feat_mean, feat_std


def build_and_populate_embedding_store(
    raw_dir: Path | str,
    output_store_path: Optional[Path | str] = None,
    seed: int = 42,
) -> InMemoryEmbeddingStore:
    """Inductively compute point-in-time GNN scores and embeddings across all daily snapshots.

    Args:
        raw_dir: Directory containing wallets, transactions, confirmations.
        output_store_path: Optional path to save Parquet embeddings table.
        seed: Random seed.

    Returns:
        Populated InMemoryEmbeddingStore.
    """
    r_dir = Path(raw_dir)
    wallets_df = pd.read_parquet(r_dir / "wallets.parquet")
    txns_df = pd.read_parquet(r_dir / "transactions.parquet").sort_values("ts").reset_index(drop=True)
    confirmations_df = pd.read_parquet(r_dir / "confirmations.parquet")

    min_ts = pd.to_datetime(txns_df["ts"].min(), utc=True)
    max_ts = pd.to_datetime(txns_df["ts"].max(), utc=True)
    total_days = (max_ts - min_ts).total_seconds() / 86400.0
    train_days = 20.0 if total_days <= 35.0 else 60.0
    train_end_ts = min_ts + pd.Timedelta(days=train_days)

    # Train inductive model on training period
    model, feat_mean, feat_std = train_graphsage(
        wallets_df=wallets_df,
        txns_df=txns_df,
        confirmations_df=confirmations_df,
        train_end_ts=train_end_ts,
        seed=seed,
    )

    store = InMemoryEmbeddingStore(emb_dim=4)
    min_ts = pd.to_datetime(txns_df["ts"].min(), utc=True)
    txns_df["day"] = ((pd.to_datetime(txns_df["ts"], utc=True) - min_ts).dt.total_seconds() / 86400.0).astype(int)
    unique_days = sorted(txns_df["day"].unique())

    logger.info(f"Computing inductive GNN embeddings for {len(unique_days)} daily snapshots...")
    model.eval()

    with torch.no_grad():
        for day in unique_days:
            snap_start = max(0, day - 7)
            snap_end = day - 1

            if snap_end < 0:
                continue

            day_start_ts = min_ts + pd.Timedelta(days=day)
            snap_end_ts = min_ts + pd.Timedelta(days=snap_end + 1)

            # Transctions in [snap_start, snap_end]
            sub_txns = txns_df[(txns_df["day"] >= snap_start) & (txns_df["day"] <= snap_end)].copy()
            if len(sub_txns) == 0:
                continue

            # Active confirmations strictly before day start
            conf_mask = pd.to_datetime(confirmations_df["confirmed_at"], utc=True) <= day_start_ts
            active_confs = set(confirmations_df[conf_mask]["wallet_id"].values)

            node_ids, feats, adj_sparse, _ = build_snapshot_graph_data(
                wallets_df=wallets_df,
                txns_window_df=sub_txns,
                active_confirmations=active_confs,
                min_ts=min_ts,
                snap_end_ts=snap_end_ts,
            )

            feats_norm = (feats - feat_mean) / feat_std
            x_tensor = torch.tensor(feats_norm, dtype=torch.float32)

            _, probs, embs = model(x_tensor, adj_sparse)
            probs_np = probs.cpu().numpy()
            embs_np = embs.cpu().numpy()

            for i, w_id in enumerate(node_ids):
                store.set_wallet_record(
                    day=day,
                    wallet_id=w_id,
                    score=float(probs_np[i]),
                    embedding=embs_np[i],
                )

    if output_store_path:
        store.save(output_store_path)

    return store
