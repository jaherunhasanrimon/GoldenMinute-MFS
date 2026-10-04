"""Evaluation metrics for GoldenMinutes.

Calculates FFR, value-weighted recall, precision at K, per-typology recall,
Brier score, ECE, bootstrap confidence intervals, and fairness slices
according to ARCHITECTURE.md Section 15.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from goldenminutes.eval.fairness import compute_fairness_slices


def compute_false_friction_rate(y_true: np.ndarray, actions: np.ndarray) -> float:
    """Calculate False-Friction Rate (FFR):

    Share of legitimate transactions (y_true == 0) receiving friction ('warn', 'verify', 'hold').
    """
    legit_mask = (y_true == 0)
    if not np.any(legit_mask):
        return 0.0
    friction_mask = np.isin(actions, ["warn", "verify", "hold"])
    return float(np.mean(friction_mask[legit_mask]))


def compute_value_weighted_recall(
    y_true: np.ndarray,
    actions: np.ndarray,
    amounts: np.ndarray,
    target_actions: Tuple[str, ...] = ("verify", "hold"),
) -> float:
    """Calculate Value-Weighted Recall:

    Share of fraud amount receiving target actions (default: 'verify' or 'hold').
    """
    fraud_mask = (y_true == 1)
    total_fraud_value = np.sum(amounts[fraud_mask])
    if total_fraud_value <= 0:
        return 0.0
    intercepted_mask = fraud_mask & np.isin(actions, target_actions)
    intercepted_fraud_value = np.sum(amounts[intercepted_mask])
    return float(intercepted_fraud_value / total_fraud_value)


def compute_expected_intercepted_value(
    y_true: np.ndarray,
    actions: np.ndarray,
    amounts: np.ndarray,
    effectiveness: Optional[Dict[str, float]] = None,
) -> float:
    """Calculate Expected Intercepted Value:

    Sum of amount * effectiveness[action] over fraud transactions.
    """
    if effectiveness is None:
        effectiveness = {"hold": 0.90, "verify": 0.55, "warn": 0.25, "allow": 0.0}

    fraud_mask = (y_true == 1)
    eff_weights = np.array([effectiveness.get(act, 0.0) for act in actions])
    return float(np.sum(amounts[fraud_mask] * eff_weights[fraud_mask]))


def compute_precision_at_k(y_true: np.ndarray, scores: np.ndarray, k: int) -> float:
    """Precision among the top K highest scoring transactions."""
    if len(scores) == 0 or k <= 0:
        return 0.0
    k = min(k, len(scores))
    top_indices = np.argsort(scores)[::-1][:k]
    return float(np.mean(y_true[top_indices]))


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Brier score: mean squared difference between probabilities and true binary labels."""
    if len(y_true) == 0:
        return 0.0
    return float(np.mean((y_prob - y_true) ** 2))


def compute_expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE) with equal-width probability bins."""
    if len(y_true) == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    ece = 0.0
    n = len(y_true)
    for b in range(n_bins):
        in_bin = (bin_indices == b)
        if np.any(in_bin):
            bin_size = np.sum(in_bin)
            bin_acc = np.mean(y_true[in_bin])
            bin_conf = np.mean(y_prob[in_bin])
            ece += (bin_size / n) * abs(bin_acc - bin_conf)

    return float(ece)


def compute_bootstrap_ci(
    y_true: np.ndarray,
    y_pred_or_actions: np.ndarray,
    metric_fn: Any,
    n_bootstraps: int = 200,
    alpha: float = 0.05,
    seed: int = 42,
    **kwargs: Any,
) -> Tuple[float, float, float]:
    """Compute point estimate and bootstrap confidence intervals [low, high]."""
    point_est = metric_fn(y_true, y_pred_or_actions, **kwargs)
    n = len(y_true)
    if n <= 1:
        return point_est, point_est, point_est

    rng = np.random.default_rng(seed)
    boot_estimates = []
    for _ in range(n_bootstraps):
        boot_idx = rng.integers(0, n, size=n)
        est = metric_fn(y_true[boot_idx], y_pred_or_actions[boot_idx], **kwargs)
        boot_estimates.append(est)

    low = float(np.percentile(boot_estimates, 100 * (alpha / 2.0)))
    high = float(np.percentile(boot_estimates, 100 * (1.0 - alpha / 2.0)))
    return point_est, low, high


__all__ = [
    "compute_false_friction_rate",
    "compute_value_weighted_recall",
    "compute_expected_intercepted_value",
    "compute_precision_at_k",
    "compute_brier_score",
    "compute_expected_calibration_error",
    "compute_bootstrap_ci",
    "compute_fairness_slices",
]

