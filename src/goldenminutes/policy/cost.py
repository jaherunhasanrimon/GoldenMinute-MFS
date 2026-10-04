"""Expected cost evaluation for GoldenMinutes policy actions.

Implements ARCHITECTURE.md Section 11 expected-cost optimization:
expected_cost(a) = p * amount * (1 - effectiveness[a]) + (1 - p) * friction_cost[a]
"""

from __future__ import annotations

from typing import Dict, Tuple


def expected_cost(
    action: str,
    p: float,
    amount_bdt: float,
    effectiveness: float,
    friction_cost: float,
) -> float:
    """Calculate the expected financial + customer friction cost for an intervention action."""
    cost_fraud = p * amount_bdt * (1.0 - effectiveness)
    cost_friction = (1.0 - p) * friction_cost
    return float(cost_fraud + cost_friction)


def evaluate_action_costs(
    p: float,
    amount_bdt: float,
    effectiveness: Dict[str, float],
    friction_costs: Dict[str, float],
) -> Dict[str, float]:
    """Calculate expected cost for all configured actions."""
    costs: Dict[str, float] = {}
    for act, eff in effectiveness.items():
        fric = friction_costs.get(act, 0.0)
        costs[act] = expected_cost(act, p, amount_bdt, eff, fric)
    return costs


def select_optimal_action(
    action_costs: Dict[str, float],
    priority_order: Tuple[str, ...] = ("allow", "warn", "verify", "hold"),
) -> str:
    """Pick the action with lowest expected cost, breaking ties towards lowest friction."""
    # Find minimum cost
    min_cost = min(action_costs.values())
    eps = 1e-4

    # Break ties in order of increasing friction
    for act in priority_order:
        if act in action_costs and abs(action_costs[act] - min_cost) < eps:
            return act

    # Fallback
    return min(action_costs.items(), key=lambda kv: kv[1])[0]
