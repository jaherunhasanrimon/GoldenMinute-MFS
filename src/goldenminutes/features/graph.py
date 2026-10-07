"""Graph feature extractor and snapshot builder for GoldenMinutes (ARCHITECTURE.md Section 8).

Constructs the P2P transfer subgraph (strictly excluding merchant and agent hubs to prevent
giant-component collapse) and heterogeneous relations (wallet-device, wallet-agent).
Computes point-in-time component sizes and 2-hop confirmed mule shares using only
events strictly before the query timestamp and confirmations prior to snapshot start.
Shared implementation used by both features/offline.py and features/online.py.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger("goldenminutes.features.graph")


class DailyGraphSnapshot:
    """Represents a point-in-time graph snapshot over days [day-7, day-1]."""

    def __init__(
        self,
        day: int,
        component_sizes: Dict[str, int],
        two_hop_mule_shares: Dict[str, float],
        graph: Optional[nx.Graph] = None,
    ):
        self.day = day
        self.component_sizes = component_sizes
        self.two_hop_mule_shares = two_hop_mule_shares
        self.graph = graph or nx.Graph()

    def get_component_size(self, wallet_id: str) -> int:
        return self.component_sizes.get(wallet_id, 1)

    def get_two_hop_mule_share(self, wallet_id: str) -> float:
        return self.two_hop_mule_shares.get(wallet_id, 0.0)


def build_p2p_snapshot_graph(
    edges: List[Tuple[str, str]],
    device_edges: Optional[List[Tuple[str, str]]] = None,
    agent_edges: Optional[List[Tuple[str, str]]] = None,
    active_confirmations: Optional[Set[str]] = None,
) -> Tuple[Dict[str, int], Dict[str, float], nx.Graph]:
    """Build a P2P transfer graph and compute connected component sizes and 2-hop confirmed mule shares.

    Args:
        edges: List of (sender_wallet, recipient_wallet) for P2P transfers.
        device_edges: Optional list of (wallet_id, device_id).
        agent_edges: Optional list of (wallet_id, agent_id).
        active_confirmations: Set of confirmed mule wallet_ids as of snapshot boundary.

    Returns:
        (component_sizes, two_hop_mule_shares, networkx_graph)
    """
    G = nx.Graph()
    active_confs = active_confirmations or set()

    for u, v in edges:
        if u and v and u != v:
            G.add_edge(u, v, rel="p2p_transfer")

    # Connected components on P2P transfer graph
    comp_sizes: Dict[str, int] = {}
    for c in nx.connected_components(G):
        sz = len(c)
        for node in c:
            comp_sizes[node] = sz

    # Add device and agent bipartite edges for 2-hop neighborhood expansion
    # Shared device connects two wallets through a device node: W1 <-> DEV <-> W2
    if device_edges:
        for w, d in device_edges:
            if w and d:
                G.add_edge(w, f"DEV::{d}", rel="wallet_device")

    if agent_edges:
        for w, a in agent_edges:
            if w and a:
                G.add_edge(w, f"AGT::{a}", rel="wallet_agent")

    # 2-hop neighbors mapping for wallets (filtering out non-wallet nodes)
    mule_shares: Dict[str, float] = {}
    wallet_nodes = [n for n in G.nodes() if not str(n).startswith(("DEV::", "AGT::"))]

    for node in wallet_nodes:
        n1 = set(G.neighbors(node))
        n2: Set[str] = set()
        for neighbor in n1:
            n2.update(G.neighbors(neighbor))
        n2.discard(node)
        # Filter 2-hop neighbors to wallet nodes only
        n2_wallets = {w for w in n2 if not str(w).startswith(("DEV::", "AGT::"))}
        if n2_wallets:
            mule_shares[node] = len(n2_wallets.intersection(active_confs)) / len(n2_wallets)
        else:
            mule_shares[node] = 0.0

    return comp_sizes, mule_shares, G
