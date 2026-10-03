"""Model fusion stacker for GoldenMinutes (Variant D).

Combines LightGBM risk predictions, Isolation Forest anomaly scores, and rules-hit
counts using a transparent logistic regression stacker fitted on validation split predictions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger("goldenminutes.models.fusion")


class FusionModel:
    """Logistic regression fusion stacker for Variant D."""

    def __init__(self, regularization_c: float = 1.0, random_state: int = 42):
        self.regularization_c = regularization_c
        self.random_state = random_state
        self.model: Optional[LogisticRegression] = None

    @staticmethod
    def transform_features(
        p_lgbm: np.ndarray,
        anomaly_scores: np.ndarray,
        rules_hit_counts: np.ndarray,
    ) -> np.ndarray:
        """Construct feature matrix [logit(p_lgbm), anomaly_score, rules_hit_count]."""
        eps = 1e-5
        p_safe = np.clip(p_lgbm, eps, 1.0 - eps)
        logit_p = np.log(p_safe / (1.0 - p_safe))
        logit_p = np.clip(logit_p, -10.0, 10.0)

        anom = np.clip(anomaly_scores, 0.0, 1.0)
        rules = np.clip(rules_hit_counts, 0.0, 10.0)

        return np.column_stack([logit_p, anom, rules])

    def fit(
        self,
        p_lgbm_val: np.ndarray,
        anomaly_val: np.ndarray,
        rules_val: np.ndarray,
        y_val: np.ndarray,
    ) -> "FusionModel":
        """Fit logistic regression stacker strictly on validation predictions."""
        logger.info(f"Fitting FusionModel on {len(y_val):,} validation instances...")
        X_val_fused = self.transform_features(p_lgbm_val, anomaly_val, rules_val)

        self.model = LogisticRegression(
            C=self.regularization_c,
            class_weight="balanced",
            random_state=self.random_state,
            max_iter=1000,
        )
        self.model.fit(X_val_fused, y_val)

        logger.info(
            f"FusionModel fitted. Coefficients: logit(p)={self.model.coef_[0][0]:.3f}, "
            f"anomaly={self.model.coef_[0][1]:.3f}, rules={self.model.coef_[0][2]:.3f}, "
            f"intercept={self.model.intercept_[0]:.3f}"
        )
        return self

    def predict_risk(
        self,
        p_lgbm: np.ndarray,
        anomaly_scores: np.ndarray,
        rules_hit_counts: np.ndarray,
    ) -> np.ndarray:
        """Predict fused risk score in [0.0, 1.0]."""
        if self.model is None:
            raise RuntimeError("Fusion model is not fitted.")

        X_fused = self.transform_features(p_lgbm, anomaly_scores, rules_hit_counts)
        risk_scores = self.model.predict_proba(X_fused)[:, 1]
        return risk_scores

    def save(self, path: Path | str) -> None:
        """Persist fusion model."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "regularization_c": self.regularization_c,
                "random_state": self.random_state,
            },
            p,
        )
        logger.info(f"Saved FusionModel to {p}")

    @classmethod
    def load(cls, path: Path | str) -> "FusionModel":
        """Load persisted fusion model."""
        p = Path(path)
        data = joblib.load(p)
        instance = cls(
            regularization_c=data["regularization_c"],
            random_state=data["random_state"],
        )
        instance.model = data["model"]
        return instance
