"""TreeSHAP explainer for GoldenMinutes risk models.

Computes exact tree feature contributions natively in LightGBM and aggregates them
into reason codes via explain/reasons.py.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from goldenminutes.common.schemas import ReasonCode
from goldenminutes.explain.reasons import map_contributions_to_reasons
from goldenminutes.features.specs import ALL_FEATURE_NAMES
from goldenminutes.models.risk_lgbm import RiskLGBM

logger = logging.getLogger("goldenminutes.explain.shap")


class TreeShapExplainer:
    """Exact TreeSHAP attribution using native LightGBM feature contributions."""

    def __init__(self, model: Optional[RiskLGBM] = None) -> None:
        self.model = model
        self.feature_names: List[str] = (
            model.feature_names if model is not None else list(ALL_FEATURE_NAMES)
        )

    def explain_instance(self, features_dict: Dict[str, Any] | pd.DataFrame) -> Dict[str, float]:
        """Compute exact TreeSHAP feature contributions for a single transaction instance.

        Returns:
            Dict mapping feature_name -> shap_value (in log-odds space).
            Positive values indicate features that increased predicted fraud risk.
        """
        if isinstance(features_dict, dict):
            df = pd.DataFrame([features_dict])
        else:
            df = features_dict.copy()

        # Ensure all required features are present
        for col in self.feature_names:
            if col not in df.columns:
                df[col] = 0.0

        X = df[self.feature_names]

        if self.model is not None and self.model.model is not None:
            booster = self.model.model.booster_
            # LightGBM native TreeSHAP: returns shape (1, n_features + 1)
            contribs = booster.predict(X, pred_contrib=True)
            # The first n_features columns are feature contributions; last is the bias
            feat_contribs = contribs[0, :-1]
            return {
                feat_name: float(feat_contribs[i])
                for i, feat_name in enumerate(self.feature_names)
            }

        # Fallback heuristic contributions if ML model is unavailable
        logger.warning("No fitted RiskLGBM model supplied to TreeShapExplainer; using heuristics.")
        heuristics: Dict[str, float] = {}
        for col in self.feature_names:
            val = float(df[col].iloc[0])
            if "count" in col or "unique" in col:
                heuristics[col] = float(np.log1p(val))
            elif "ratio" in col:
                heuristics[col] = float(val - 1.0)
            elif col == "two_hop_confirmed_mule_share":
                heuristics[col] = float(val * 5.0)
            else:
                heuristics[col] = 0.0
        return heuristics

    def get_top_reasons(
        self,
        features_dict: Dict[str, Any] | pd.DataFrame,
        top_k: int = 3,
    ) -> List[ReasonCode]:
        """Compute top positive contributing reason codes for a transaction."""
        contributions = self.explain_instance(features_dict)
        return map_contributions_to_reasons(contributions, top_k=top_k)
