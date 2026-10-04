"""Policy Engine for GoldenMinutes.

Implements ARCHITECTURE.md Section 11:
- Config-driven deterministic policy (configs/policy.yaml)
- Hard rules (e.g. recipient_blocklisted -> hold)
- Minimum amount threshold (amount < 300 BDT -> allow)
- Expected cost optimization across actions: [allow, warn, verify, hold]
- Tie-breaking in favor of lower friction
- Hold capacity fallback (fallback to verify when hourly capacity is exceeded)
- Never returns 'deny'
- Priority & golden window deadline calculations
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from goldenminutes.policy.cost import evaluate_action_costs, select_optimal_action


@dataclass
class PolicyDecision:
    """Result of policy engine evaluation."""
    action: str
    risk_score: float
    amount_bdt: float
    expected_costs: Dict[str, float]
    chosen_raw_action: str
    capacity_exceeded: bool = False
    hard_rule_fired: Optional[str] = None
    rule_reason: Optional[str] = None
    priority: Optional[float] = None
    urgency: Optional[float] = None
    time_left_minutes: Optional[float] = None
    alert_status: Optional[str] = None
    deadline_ts: Optional[datetime] = None


class PolicyEngine:
    """Config-driven policy engine for proportional intervention."""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        if config_path is None:
            # Look relative to repo root
            repo_root = Path(__file__).resolve().parents[3]
            config_path = repo_root / "configs" / "policy.yaml"

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.version: str = str(cfg.get("version", "0.1"))
        self.actions: List[str] = list(cfg.get("actions", ["allow", "warn", "verify", "hold"]))
        self.effectiveness: Dict[str, float] = {
            k: float(v) for k, v in cfg.get("effectiveness", {}).items()
        }
        self.friction_cost_bdt: Dict[str, float] = {
            k: float(v) for k, v in cfg.get("friction_cost_bdt", {}).items()
        }
        self.min_amount_bdt: float = float(cfg.get("min_amount_bdt_for_intervention", 300.0))
        self.hold_capacity_per_hour: int = int(cfg.get("hold_capacity_per_hour", 20))
        self.golden_window_minutes: float = float(cfg.get("golden_window_minutes", 30.0))
        self.hard_rules: List[str] = list(cfg.get("hard_rules", ["recipient_blocklisted"]))

        self.sensitivity: Dict[str, Any] = cfg.get("sensitivity", {})

        # Hold timestamps for capacity tracking: sliding 1-hour window
        self._hold_history: deque[datetime] = deque()

    def reset(self) -> None:
        """Reset internal hold capacity tracking."""
        self._hold_history.clear()

    def evaluate_batch(
        self,
        amounts_bdt: Any,
        risk_scores: Any,
        effectiveness_override: Optional[Dict[str, float]] = None,
        friction_override: Optional[Dict[str, float]] = None,
    ) -> np.ndarray:
        """Vectorized cost-based action selection for batch evaluation."""
        eff_dict = effectiveness_override or self.effectiveness
        fric_dict = friction_override or self.friction_cost_bdt

        act_names = ["allow", "warn", "verify", "hold"]
        eff = np.array([eff_dict.get(a, 0.0) for a in act_names])
        fric = np.array([fric_dict.get(a, 0.0) for a in act_names])

        scores = np.asarray(risk_scores, dtype=float)
        amounts = np.asarray(amounts_bdt, dtype=float)

        p = scores[:, None]
        amt = amounts[:, None]
        costs = p * amt * (1.0 - eff) + (1.0 - p) * fric

        best_idx = np.argmin(costs, axis=1)
        actions = np.array(act_names)[best_idx]
        actions[amounts < self.min_amount_bdt] = "allow"
        return actions

    def _prune_holds(self, current_ts: datetime) -> None:
        """Prune hold events older than 1 hour relative to current_ts."""
        cutoff = current_ts - timedelta(hours=1)
        while self._hold_history and self._hold_history[0] < cutoff:
            self._hold_history.popleft()

    def get_hold_count_last_hour(self, current_ts: Optional[datetime] = None) -> int:
        """Count holds in the past hour."""
        if current_ts is None:
            current_ts = datetime.now(timezone.utc)
        self._prune_holds(current_ts)
        return len(self._hold_history)

    def calculate_priority(
        self,
        risk_score: float,
        amount_bdt: float,
        minutes_since_first_inflow: float = 0.0,
        cashed_out: bool = False,
        current_ts: Optional[datetime] = None,
    ) -> Tuple[float, float, float, str, Optional[datetime]]:
        """Calculate alert priority and golden window urgency.

        Returns: (priority, urgency, time_left, status, deadline_ts)
        priority = p * amount * (1 + urgency)
        urgency = clip(1 - time_left / golden_window_minutes, 0, 1)
        time_left = golden_window_minutes - minutes_since_recipient_first_inflow
        """
        if current_ts is None:
            current_ts = datetime.now(timezone.utc)

        time_left = max(0.0, self.golden_window_minutes - minutes_since_first_inflow)
        urgency = min(1.0, max(0.0, 1.0 - (time_left / self.golden_window_minutes)))
        priority = risk_score * amount_bdt * (1.0 + urgency)

        if cashed_out or time_left <= 0:
            status = "late"
            deadline_ts = current_ts
        else:
            status = "open"
            deadline_ts = current_ts + timedelta(minutes=time_left)

        return priority, urgency, time_left, status, deadline_ts

    def evaluate(
        self,
        amount_bdt: float,
        risk_score: float,
        context: Optional[Dict[str, Any]] = None,
        current_ts: Optional[datetime] = None,
        hold_count_override: Optional[int] = None,
    ) -> PolicyDecision:
        """Evaluate policy for a transaction and return the chosen action."""
        if current_ts is None:
            current_ts = datetime.now(timezone.utc)

        ctx = context or {}

        # 1. Hard rules check
        for rule in self.hard_rules:
            if ctx.get(rule):
                # Hard rule fired -> hold
                prio, urg, t_left, status, deadline = self.calculate_priority(
                    risk_score=max(risk_score, 0.95),
                    amount_bdt=amount_bdt,
                    minutes_since_first_inflow=ctx.get("minutes_since_first_inflow", 0.0),
                    cashed_out=ctx.get("cashed_out", False),
                    current_ts=current_ts,
                )
                self._hold_history.append(current_ts)
                return PolicyDecision(
                    action="hold",
                    risk_score=risk_score,
                    amount_bdt=amount_bdt,
                    expected_costs={a: 0.0 for a in self.actions},
                    chosen_raw_action="hold",
                    capacity_exceeded=False,
                    hard_rule_fired=rule,
                    rule_reason=f"Hard rule triggered: {rule}",
                    priority=prio,
                    urgency=urg,
                    time_left_minutes=t_left,
                    alert_status=status,
                    deadline_ts=deadline,
                )

        # 2. Minimum amount threshold check
        if amount_bdt < self.min_amount_bdt:
            costs = evaluate_action_costs(
                p=risk_score,
                amount_bdt=amount_bdt,
                effectiveness=self.effectiveness,
                friction_costs=self.friction_cost_bdt,
            )
            return PolicyDecision(
                action="allow",
                risk_score=risk_score,
                amount_bdt=amount_bdt,
                expected_costs=costs,
                chosen_raw_action="allow",
                capacity_exceeded=False,
                hard_rule_fired=None,
                rule_reason=f"Amount ({amount_bdt:.1f} BDT) below intervention threshold ({self.min_amount_bdt:.1f} BDT)",
                priority=None,
                urgency=None,
                time_left_minutes=None,
                alert_status=None,
                deadline_ts=None,
            )

        # 3. Expected cost optimization
        costs = evaluate_action_costs(
            p=risk_score,
            amount_bdt=amount_bdt,
            effectiveness=self.effectiveness,
            friction_costs=self.friction_cost_bdt,
        )
        optimal_action = select_optimal_action(
            action_costs=costs,
            priority_order=("allow", "warn", "verify", "hold"),
        )

        chosen_action = optimal_action
        capacity_exceeded = False

        # 4. Hold capacity fallback check
        if optimal_action == "hold":
            hold_count = (
                hold_count_override
                if hold_count_override is not None
                else self.get_hold_count_last_hour(current_ts)
            )
            if hold_count >= self.hold_capacity_per_hour:
                chosen_action = "verify"
                capacity_exceeded = True
            else:
                self._hold_history.append(current_ts)

        # 5. Alert priority and deadline (for hold or verify interventions)
        prio, urg, t_left, status, deadline = None, None, None, None, None
        if chosen_action in ["hold", "verify"]:
            prio, urg, t_left, status, deadline = self.calculate_priority(
                risk_score=risk_score,
                amount_bdt=amount_bdt,
                minutes_since_first_inflow=ctx.get("minutes_since_first_inflow", 0.0),
                cashed_out=ctx.get("cashed_out", False),
                current_ts=current_ts,
            )

        # 6. Never return 'deny' (guaranteed as 'deny' is not in actions)
        assert chosen_action in ["allow", "warn", "verify", "hold"]

        return PolicyDecision(
            action=chosen_action,
            risk_score=risk_score,
            amount_bdt=amount_bdt,
            expected_costs=costs,
            chosen_raw_action=optimal_action,
            capacity_exceeded=capacity_exceeded,
            hard_rule_fired=None,
            rule_reason=None if not capacity_exceeded else "Hold capacity exceeded; fallback to verify",
            priority=prio,
            urgency=urg,
            time_left_minutes=t_left,
            alert_status=status,
            deadline_ts=deadline,
        )
