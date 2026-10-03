"""Isotonic probability calibration for GoldenMinutes risk models.

Fitted strictly on validation split predictions to produce calibrated probabilities.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression

logger = logging.getLogger("goldenminutes.models.calibration")


class IsotonicCalibrator:
    """Isotonic regression calibrator fitted on validation predictions."""

    def __init__(self):
        self.calibrator: Optional[IsotonicRegression] = None

    def fit(self, y_prob_val: np.ndarray, y_true_val: np.ndarray) -> "IsotonicCalibrator":
        """Fit isotonic regression strictly on validation predictions."""
        logger.info(f"Fitting IsotonicCalibrator on {len(y_prob_val):,} validation predictions...")
        self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.calibrator.fit(y_prob_val, y_true_val)
        return self

    def predict(self, y_prob: np.ndarray) -> np.ndarray:
        """Calibrate input probabilities."""
        if self.calibrator is None:
            raise RuntimeError("Calibrator is not fitted.")
        calibrated = self.calibrator.predict(y_prob)
        return np.clip(calibrated, 0.0, 1.0)

    def save(self, path: Path | str) -> None:
        """Persist calibrator."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"calibrator": self.calibrator}, p)
        logger.info(f"Saved IsotonicCalibrator to {p}")

    @classmethod
    def load(cls, path: Path | str) -> "IsotonicCalibrator":
        """Load persisted calibrator."""
        p = Path(path)
        data = joblib.load(p)
        instance = cls()
        instance.calibrator = data["calibrator"]
        return instance
