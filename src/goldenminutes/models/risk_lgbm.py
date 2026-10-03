"""LightGBM Risk Model for GoldenMinutes (Variants B & C).

Trains a binary classifier for fraud prediction with class weighting, early stopping
on validation only, and probability output.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

logger = logging.getLogger("goldenminutes.models.risk_lgbm")


class RiskLGBM:
    """LightGBM classifier wrapper for transaction fraud detection."""

    def __init__(
        self,
        feature_names: List[str],
        params: Optional[Dict[str, Any]] = None,
        random_state: int = 42,
    ):
        self.feature_names = list(feature_names)
        self.random_state = random_state

        default_params: Dict[str, Any] = {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "class_weight": "balanced",
            "random_state": self.random_state,
            "n_jobs": -1,
            "verbosity": -1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        }
        if params:
            default_params.update(params)
        self.params = default_params
        self.model: Optional[lgb.LGBMClassifier] = None

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: np.ndarray,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> "RiskLGBM":
        """Fit model with early stopping on validation split if provided."""
        X_tr = X_train[self.feature_names]

        self.model = lgb.LGBMClassifier(**self.params)

        if X_val is not None and y_val is not None:
            X_v = X_val[self.feature_names]
            callbacks = [lgb.early_stopping(stopping_rounds=50, verbose=False)]
            self.model.fit(
                X_tr,
                y_train,
                eval_set=[(X_v, y_val)],
                eval_metric="binary_logloss",
                callbacks=callbacks,
            )
            best_iteration = getattr(self.model, "best_iteration_", None)
            logger.info(f"Fitted RiskLGBM ({len(self.feature_names)} features) with early stopping. Best iteration: {best_iteration}")
        else:
            self.model.fit(X_tr, y_train)
            logger.info(f"Fitted RiskLGBM ({len(self.feature_names)} features).")

        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return estimated positive class probabilities in [0.0, 1.0]."""
        if self.model is None:
            raise RuntimeError("Model is not fitted.")
        X_sub = X[self.feature_names]
        probs = self.model.predict_proba(X_sub)[:, 1]
        return probs

    def save(self, path: Path | str) -> None:
        """Persist model and feature metadata."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "feature_names": self.feature_names,
                "params": self.params,
                "random_state": self.random_state,
            },
            p,
        )
        logger.info(f"Saved RiskLGBM to {p}")

    @classmethod
    def load(cls, path: Path | str) -> "RiskLGBM":
        """Load persisted model and feature metadata."""
        p = Path(path)
        data = joblib.load(p)
        instance = cls(
            feature_names=data["feature_names"],
            params=data["params"],
            random_state=data["random_state"],
        )
        instance.model = data["model"]
        return instance
