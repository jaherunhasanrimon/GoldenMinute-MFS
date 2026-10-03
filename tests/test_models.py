"""Unit tests for machine learning models, calibration, fusion, and training invariants."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from goldenminutes.features.specs import ALL_FEATURE_NAMES, NON_GRAPH_FEATURE_NAMES
from goldenminutes.models.anomaly import AnomalyIsolationForest
from goldenminutes.models.calibration import IsotonicCalibrator
from goldenminutes.models.fusion import FusionModel
from goldenminutes.models.registry import ModelRegistry
from goldenminutes.models.risk_lgbm import RiskLGBM


def test_risk_lgbm_fit_predict_save_load():
    """Verify RiskLGBM training, inference bounds, and persistence."""
    rng = np.random.default_rng(42)
    n = 200

    data = {feat: rng.normal(0, 1, size=n) for feat in NON_GRAPH_FEATURE_NAMES}
    X = pd.DataFrame(data)
    y = (rng.uniform(0, 1, size=n) > 0.8).astype(int)

    model = RiskLGBM(feature_names=NON_GRAPH_FEATURE_NAMES, params={"n_estimators": 10})
    model.fit(X.iloc[:150], y[:150], X.iloc[150:], y[150:])

    probs = model.predict_proba(X)
    assert len(probs) == n
    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "model.joblib"
        model.save(save_path)
        loaded = RiskLGBM.load(save_path)
        probs_loaded = loaded.predict_proba(X)
        np.testing.assert_allclose(probs, probs_loaded)


def test_anomaly_isolation_forest():
    """Verify Isolation Forest anomaly detector outputs calibrated percentile ranks."""
    rng = np.random.default_rng(42)
    n = 300

    data = {feat: rng.normal(0, 1, size=n) for feat in ALL_FEATURE_NAMES}
    X = pd.DataFrame(data)

    model = AnomalyIsolationForest(feature_names=ALL_FEATURE_NAMES, params={"n_estimators": 20})
    model.fit(X)

    scores = model.predict_anomaly_score(X)
    assert len(scores) == n
    assert np.all(scores >= 0.0)
    assert np.all(scores <= 1.0)
    # Calibrated ranks should span from low to high
    assert scores.max() > 0.90
    assert scores.min() < 0.10


def test_isotonic_calibration():
    """Verify isotonic calibrator monotonicity and bounds."""
    rng = np.random.default_rng(42)
    raw_probs = np.linspace(0.05, 0.95, 100)
    y_val = (raw_probs + rng.normal(0, 0.1, size=100) > 0.5).astype(int)

    calibrator = IsotonicCalibrator()
    calibrator.fit(raw_probs, y_val)
    calibrated = calibrator.predict(raw_probs)

    assert len(calibrated) == 100
    assert np.all(calibrated >= 0.0)
    assert np.all(calibrated <= 1.0)
    # Check monotonicity
    assert np.all(np.diff(calibrated) >= 0.0)


def test_fusion_model():
    """Verify fusion stacker combines inputs into calibrated risk scores."""
    rng = np.random.default_rng(42)
    n = 100

    p_lgbm = rng.uniform(0.01, 0.99, size=n)
    anom = rng.uniform(0.0, 1.0, size=n)
    rules = rng.integers(0, 4, size=n).astype(float)
    y = (p_lgbm * 0.6 + anom * 0.2 + rules * 0.1 > 0.5).astype(int)

    fusion = FusionModel()
    fusion.fit(p_lgbm, anom, rules, y)
    risk = fusion.predict_risk(p_lgbm, anom, rules)

    assert len(risk) == n
    assert np.all(risk >= 0.0)
    assert np.all(risk <= 1.0)


def test_registry_registration_and_lookup():
    """Verify model registry records and retrieves version metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_file = Path(tmpdir) / "registry.json"
        reg = ModelRegistry(registry_path=reg_file)

        meta = {"version": "m-test-0.1", "profile": "small", "artifacts": {"a": "path_a"}}
        reg.register_version("m-test-0.1", meta, set_active=True)

        active = reg.get_active_metadata()
        assert active is not None
        assert active["version"] == "m-test-0.1"
