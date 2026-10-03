"""Isolation Forest Anomaly Model for GoldenMinutes.

Trained strictly on legitimate transactions (y == 0) from the training split,
outputting an anomaly score as an empirical percentile rank in [0.0, 1.0].
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger("goldenminutes.models.anomaly")


class AnomalyIsolationForest:
    """Isolation Forest anomaly detector with percentile rank calibration."""

    def __init__(
        self,
        feature_names: List[str],
        params: Optional[Dict[str, Any]] = None,
        random_state: int = 42,
    ):
        self.feature_names = list(feature_names)
        self.random_state = random_state

        default_params: Dict[str, Any] = {
            "n_estimators": 150,
            "contamination": 0.01,
            "random_state": self.random_state,
            "n_jobs": -1,
        }
        if params:
            default_params.update(params)
        self.params = default_params

        self.model: Optional[IsolationForest] = None
        self.sorted_train_scores: Optional[np.ndarray] = None

    def fit(self, X_train_legit: pd.DataFrame) -> "AnomalyIsolationForest":
        """Fit Isolation Forest strictly on legitimate training rows."""
        X_sub = X_train_legit[self.feature_names]
        logger.info(f"Fitting Isolation Forest on {len(X_sub):,} legitimate transactions...")

        self.model = IsolationForest(**self.params)
        self.model.fit(X_sub)

        # Invert decision function so higher = more anomalous
        raw_train_scores = -self.model.decision_function(X_sub)
        self.sorted_train_scores = np.sort(raw_train_scores)
        logger.info("Isolation Forest fitted and training score distribution calibrated.")
        return self

    def predict_anomaly_score(self, X: pd.DataFrame) -> np.ndarray:
        """Compute percentile rank anomaly score in [0.0, 1.0]."""
        if self.model is None or self.sorted_train_scores is None:
            raise RuntimeError("Anomaly model is not fitted.")

        X_sub = X[self.feature_names]
        raw_scores = -self.model.decision_function(X_sub)

        # Compute empirical percentile rank
        ranks = np.searchsorted(self.sorted_train_scores, raw_scores, side="right")
        percentile_scores = np.clip(ranks / len(self.sorted_train_scores), 0.0, 1.0)
        return percentile_scores

    def save(self, path: Path | str) -> None:
        """Persist anomaly model and calibration array."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "feature_names": self.feature_names,
                "params": self.params,
                "random_state": self.random_state,
                "sorted_train_scores": self.sorted_train_scores,
            },
            p,
        )
        logger.info(f"Saved AnomalyIsolationForest to {p}")

    @classmethod
    def load(cls, path: Path | str) -> "AnomalyIsolationForest":
        """Load persisted anomaly model and calibration array."""
        p = Path(path)
        data = joblib.load(p)
        instance = cls(
            feature_names=data["feature_names"],
            params=data["params"],
            random_state=data["random_state"],
        )
        instance.model = data["model"]
        instance.sorted_train_scores = data["sorted_train_scores"]
        return instance
