"""Feature specifications for GoldenMinutes.

Single source of truth for all feature names, groups, data types, time windows,
and definitions according to ARCHITECTURE.md Section 8.
"""

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional


@dataclass(frozen=True)
class FeatureSpec:
    """Specification of a single feature."""

    name: str
    group: Literal["sender", "pair", "device_auth", "recipient", "graph", "gnn"]
    dtype: str
    window: Optional[str]
    description: str
    default_value: float = 0.0


FEATURE_SPECS: List[FeatureSpec] = [
    # --- Sender Features ---
    FeatureSpec(
        name="amount_to_median_ratio",
        group="sender",
        dtype="float64",
        window="30d",
        description="Ratio of current amount to sender's 30-day median transaction amount (1.0 if no history).",
        default_value=1.0,
    ),
    FeatureSpec(
        name="sender_txn_count_1h",
        group="sender",
        dtype="int64",
        window="1h",
        description="Number of transactions sent by this wallet in the preceding 1 hour.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="sender_txn_count_24h",
        group="sender",
        dtype="int64",
        window="24h",
        description="Number of transactions sent by this wallet in the preceding 24 hours.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="sender_amount_sum_24h",
        group="sender",
        dtype="float64",
        window="24h",
        description="Total amount sent by this wallet in the preceding 24 hours in BDT.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="sender_tenure_days",
        group="sender",
        dtype="float64",
        window=None,
        description="Age of sender wallet in days at time of transaction.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="balance_drain_ratio",
        group="sender",
        dtype="float64",
        window=None,
        description="Ratio of amount_bdt to balance_before (clamped to [0.0, 1.0]).",
        default_value=0.0,
    ),
    FeatureSpec(
        name="hour_of_day",
        group="sender",
        dtype="int64",
        window=None,
        description="Local hour of day (0-23 in Asia/Dhaka).",
        default_value=0.0,
    ),
    FeatureSpec(
        name="is_night",
        group="sender",
        dtype="int64",
        window=None,
        description="Binary indicator (1 if transaction occurred between 23:00 and 06:00, else 0).",
        default_value=0.0,
    ),
    # --- Pair Features ---
    FeatureSpec(
        name="is_first_time_pair",
        group="pair",
        dtype="int64",
        window=None,
        description="Binary indicator (1 if sender has never sent to recipient prior to ts, else 0).",
        default_value=1.0,
    ),
    FeatureSpec(
        name="pair_history_count",
        group="pair",
        dtype="int64",
        window=None,
        description="Number of prior transactions from sender to recipient strictly before ts.",
        default_value=0.0,
    ),
    # --- Device & Auth Features ---
    FeatureSpec(
        name="new_device_flag",
        group="device_auth",
        dtype="int64",
        window=None,
        description="Binary indicator (1 if device_id was not previously associated with sender wallet, else 0).",
        default_value=0.0,
    ),
    FeatureSpec(
        name="minutes_since_pin_reset",
        group="device_auth",
        dtype="float64",
        window=None,
        description="Minutes elapsed since most recent pin_reset event for sender wallet (capped at 43200 mins / 30d).",
        default_value=43200.0,
    ),
    FeatureSpec(
        name="minutes_since_sim_change",
        group="device_auth",
        dtype="float64",
        window=None,
        description="Minutes elapsed since most recent sim_change event for sender wallet (capped at 43200 mins / 30d).",
        default_value=43200.0,
    ),
    FeatureSpec(
        name="session_seconds",
        group="device_auth",
        dtype="float64",
        window=None,
        description="Transaction session duration in seconds.",
        default_value=60.0,
    ),
    # --- Recipient Features ---
    FeatureSpec(
        name="recipient_age_days",
        group="recipient",
        dtype="float64",
        window=None,
        description="Age of recipient wallet in days at time of transaction.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_owner_type_code",
        group="recipient",
        dtype="int64",
        window=None,
        description="Numeric encoding of recipient owner type: 0=customer, 1=agent, 2=merchant.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_unique_senders_1h",
        group="recipient",
        dtype="int64",
        window="1h",
        description="Number of distinct sender wallets transferring to recipient in preceding 1 hour.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_unique_senders_24h",
        group="recipient",
        dtype="int64",
        window="24h",
        description="Number of distinct sender wallets transferring to recipient in preceding 24 hours.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_first_time_sender_share_24h",
        group="recipient",
        dtype="float64",
        window="24h",
        description="Fraction of unique senders in last 24h that were sending to recipient for the first time.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_inflow_24h",
        group="recipient",
        dtype="float64",
        window="24h",
        description="Total incoming funds received by recipient wallet in preceding 24 hours in BDT.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_outflow_24h",
        group="recipient",
        dtype="float64",
        window="24h",
        description="Total outgoing funds (cash-out or transfer) disbursed by recipient in preceding 24 hours in BDT.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_pass_through_ratio_24h",
        group="recipient",
        dtype="float64",
        window="24h",
        description="Ratio of recipient outflow to inflow in last 24 hours (recipient_outflow_24h / (recipient_inflow_24h + 1)).",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_median_receipt_to_out_minutes",
        group="recipient",
        dtype="float64",
        window="7d",
        description="Median elapsed minutes between receiving funds and cashing out or forwarding in the last 7 days.",
        default_value=1440.0,  # default 24h if no cash-out history
    ),
    # --- Graph Features (7-day window & daily snapshots) ---
    FeatureSpec(
        name="recipient_fan_in_7d",
        group="graph",
        dtype="int64",
        window="7d",
        description="Unique incoming transaction counter-parties to recipient in preceding 7 days.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="recipient_fan_out_7d",
        group="graph",
        dtype="int64",
        window="7d",
        description="Unique outgoing transaction counter-parties from recipient in preceding 7 days.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="shared_device_wallet_count",
        group="graph",
        dtype="int64",
        window="7d",
        description="Count of distinct wallets associated with the transaction device in the last 7 days.",
        default_value=1.0,
    ),
    FeatureSpec(
        name="component_size_7d",
        group="graph",
        dtype="int64",
        window="7d",
        description="Connected component size in the suspicious transaction subgraph from previous day's daily snapshot.",
        default_value=1.0,
    ),
    FeatureSpec(
        name="two_hop_confirmed_mule_share",
        group="graph",
        dtype="float64",
        window="7d",
        description="Share of 2-hop graph neighbors of recipient that are confirmed mules in confirmations table (confirmed_at <= ts). Never reads labels.",
        default_value=0.0,
    ),
]

FEATURE_NAMES: List[str] = [spec.name for spec in FEATURE_SPECS]
FEATURE_MAP: Dict[str, FeatureSpec] = {spec.name: spec for spec in FEATURE_SPECS}

# Model variants feature subsets
GRAPH_FEATURE_NAMES: List[str] = [
    spec.name for spec in FEATURE_SPECS if spec.group == "graph"
]

NON_GRAPH_FEATURE_NAMES: List[str] = [
    spec.name for spec in FEATURE_SPECS if spec.group != "graph"
]

ALL_FEATURE_NAMES: List[str] = [spec.name for spec in FEATURE_SPECS]

# --- Phase 1: GNN Learned Graph Representations ---
GNN_FEATURE_SPECS: List[FeatureSpec] = [
    FeatureSpec(
        name="gnn_recipient_mule_score",
        group="gnn",
        dtype="float64",
        window="7d",
        description="GraphSAGE predicted mule probability for recipient wallet from previous day's daily snapshot.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="gnn_sender_mule_score",
        group="gnn",
        dtype="float64",
        window="7d",
        description="GraphSAGE predicted mule probability for sender wallet from previous day's daily snapshot.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="gnn_recipient_emb_0",
        group="gnn",
        dtype="float64",
        window="7d",
        description="Dimension 0 of recipient wallet 4-dim GraphSAGE structural embedding.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="gnn_recipient_emb_1",
        group="gnn",
        dtype="float64",
        window="7d",
        description="Dimension 1 of recipient wallet 4-dim GraphSAGE structural embedding.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="gnn_recipient_emb_2",
        group="gnn",
        dtype="float64",
        window="7d",
        description="Dimension 2 of recipient wallet 4-dim GraphSAGE structural embedding.",
        default_value=0.0,
    ),
    FeatureSpec(
        name="gnn_recipient_emb_3",
        group="gnn",
        dtype="float64",
        window="7d",
        description="Dimension 3 of recipient wallet 4-dim GraphSAGE structural embedding.",
        default_value=0.0,
    ),
]

GNN_FEATURE_NAMES: List[str] = [spec.name for spec in GNN_FEATURE_SPECS]
VARIANT_E_FEATURE_NAMES: List[str] = ALL_FEATURE_NAMES + GNN_FEATURE_NAMES

ALL_SPECS_WITH_GNN: List[FeatureSpec] = FEATURE_SPECS + GNN_FEATURE_SPECS
FEATURE_GROUP_MAP: Dict[str, str] = {spec.name: spec.group for spec in ALL_SPECS_WITH_GNN}

