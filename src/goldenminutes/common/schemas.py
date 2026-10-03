"""Pydantic schemas for the GoldenMinutes API contract (ARCHITECTURE.md Section 13)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# --- Error Schemas ---


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# --- Common Sub-Models ---


class ReasonCode(BaseModel):
    code: str
    weight: float


class CustomerMessage(BaseModel):
    bn: str
    en: str


# --- Health ---


class HealthResponse(BaseModel):
    status: str = "ok"
    model_version: str = "m-0.1.0-stub"
    policy_version: str = "0.1"
    environment: str = "dev"


# --- POST /v1/score ---


class ScoreRequest(BaseModel):
    txn_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str = "send_money"
    sender_wallet_id: str
    recipient_wallet_id: str
    amount_bdt: float = Field(gt=0)
    channel: Literal["app", "ussd", "agent"] = "app"
    device_id: str
    balance_before: float = Field(ge=0)
    session_seconds: Optional[int] = Field(default=60, ge=0)
    reference: Optional[str] = Field(default=None, max_length=140)


class ScoreResponse(BaseModel):
    txn_id: str
    risk_score: float = Field(ge=0.0, le=1.0)
    action: Literal["allow", "warn", "verify", "hold"]
    reason_codes: List[ReasonCode] = Field(default_factory=list)
    customer_message: CustomerMessage
    alert_id: Optional[str] = None
    model_version: str = "m-0.1.0-stub"
    policy_version: str = "0.1"
    latency_ms: float = 0.0


# --- Alerts Schemas ---


class AlertSummary(BaseModel):
    alert_id: str
    decision_id: str
    txn_id: str
    status: Literal["open", "in_review", "resolved", "late"] = "open"
    priority: float
    money_at_risk: float
    deadline_ts: datetime
    created_at: datetime
    sender_wallet_id: str
    recipient_wallet_id: str
    amount_bdt: float


class AlertListResponse(BaseModel):
    alerts: List[AlertSummary]
    total: int


class AlertDetailResponse(BaseModel):
    alert_id: str
    decision_id: str
    txn_id: str
    status: Literal["open", "in_review", "resolved", "late"]
    priority: float
    money_at_risk: float
    deadline_ts: datetime
    created_at: datetime
    risk_score: float
    action: Literal["allow", "warn", "verify", "hold"]
    reason_codes: List[ReasonCode]
    sender_wallet_id: str
    recipient_wallet_id: str
    amount_bdt: float
    customer_message: Optional[CustomerMessage] = None
    narrative: Optional[Dict[str, str]] = None
    evidence: Optional[Dict[str, Any]] = None
    actions_taken: List[Dict[str, Any]] = Field(default_factory=list)


class AlertDecisionRequest(BaseModel):
    action: Literal["approve", "release", "escalate"]
    note: Optional[str] = None


class AlertDecisionResponse(BaseModel):
    alert_id: str
    status: Literal["open", "in_review", "resolved", "late"]
    action_taken: Literal["approve", "release", "escalate"]
    analyst_id: str = "analyst_demo"
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: Optional[str] = None


# --- Feedback ---


class FeedbackRequest(BaseModel):
    decision_id: str
    source: Literal["customer", "analyst"]
    label: Literal["this_was_me", "not_me", "fraud", "legit"]


class FeedbackResponse(BaseModel):
    feedback_id: str
    status: str = "recorded"


# --- Graph ---


class GraphNode(BaseModel):
    id: str
    label: str
    type: Literal["customer", "wallet", "agent", "merchant", "device"]
    risk_score: Optional[float] = None
    is_mule: Optional[bool] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    amount_bdt: float = 0.0
    ts: Optional[datetime] = None
    txn_count: int = 1


class GraphResponse(BaseModel):
    wallet_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]


# --- Metrics ---


class MetricsResponse(BaseModel):
    fraud_value_intercepted_bdt: float
    false_friction_rate: float
    median_decision_time_ms: float
    p95_decision_time_ms: float
    ablation_table: List[Dict[str, Any]]
    held_out_typology_recall: Optional[float] = None
    fairness_slices: Optional[Dict[str, Any]] = None
    sensitivity_grid: Optional[List[Dict[str, Any]]] = None
    hold_resolution_minutes: Optional[float] = None
    total_scored: int = 0
    total_alerts: int = 0


# --- Simulation & Demo ---


class SimulateAttackRequest(BaseModel):
    scenario_id: Optional[str] = "impersonation_scam_01"
    speed_factor: Optional[float] = 1.0


class SimulateAttackResponse(BaseModel):
    status: str = "started"
    scenario_id: str
    message: str
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class SimulateResetResponse(BaseModel):
    status: str = "reset_completed"
    message: str = "Demo simulation state reset to baseline"


class DemoAccount(BaseModel):
    wallet_id: str
    customer_id: str
    name: str
    balance_bdt: float
    persona: str
    description: str


class DemoAccountsResponse(BaseModel):
    senders: List[DemoAccount]
    recipients: List[DemoAccount]
