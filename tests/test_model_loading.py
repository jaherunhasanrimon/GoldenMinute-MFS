"""Tests for model registry verification, checksums, fresh-clone fallback, and fail-loud semantics."""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goldenminutes.api.main import create_app
from goldenminutes.models.registry import ModelRegistry


def test_registry_fallback_to_demo_assets_on_missing_artifacts():
    """Verify that when the primary registry points to missing files, resolve_active_model falls back to demo_assets."""
    with tempfile.TemporaryDirectory() as td:
        fake_reg = Path(td) / "registry.json"
        with open(fake_reg, "w") as f:
            json.dump(
                {
                    "active_version": "m-missing",
                    "versions": {
                        "m-missing": {
                            "version": "m-missing",
                            "artifacts": {
                                "variant_e_lgbm": "models/nonexistent/variant_e_lgbm.joblib",
                                "thresholds": "models/nonexistent/thresholds.json",
                            },
                        }
                    },
                },
                f,
            )

        reg = ModelRegistry(registry_path=fake_reg, model_dir=td)
        meta, source, degraded = reg.resolve_active_model()
        assert meta is not None
        assert source == "demo_assets"
        assert degraded is False
        assert meta["version"] == "m-1.0.0-small"


def test_registry_rejects_tampered_artifact_checksum():
    """Verify that an artifact whose checksum does not match is rejected."""
    with tempfile.TemporaryDirectory() as td:
        dummy_model = Path(td) / "dummy.joblib"
        dummy_model.write_text("tampered model content")
        dummy_thresh = Path(td) / "thresholds.json"
        dummy_thresh.write_text("{}")

        fake_reg = Path(td) / "registry.json"
        with open(fake_reg, "w") as f:
            json.dump(
                {
                    "active_version": "m-tampered",
                    "versions": {
                        "m-tampered": {
                            "version": "m-tampered",
                            "artifacts": {
                                "variant_e_lgbm": str(dummy_model),
                                "thresholds": str(dummy_thresh),
                            },
                            "checksums": {
                                "variant_e_lgbm": "0000000000000000000000000000000000000000000000000000000000000000",
                                "thresholds": "1111111111111111111111111111111111111111111111111111111111111111",
                            },
                        }
                    },
                },
                f,
            )

        reg = ModelRegistry(registry_path=fake_reg, model_dir=td)
        valid, reason = reg.verify_artifacts(reg.get_version_metadata("m-tampered"))
        assert valid is False
        assert "Checksum mismatch" in reason


def test_prod_env_fails_loud_when_no_valid_model(monkeypatch):
    """In production (GM_ENV=prod), missing or unverified models must raise RuntimeError."""
    monkeypatch.setenv("GM_ENV", "prod")
    with tempfile.TemporaryDirectory() as td:
        fake_reg = Path(td) / "registry.json"
        with open(fake_reg, "w") as f:
            json.dump({"active_version": None, "versions": {}}, f)

        # Point demo_assets to empty directory as well
        monkeypatch.setattr("goldenminutes.models.registry.REPO_ROOT", Path(td))

        reg = ModelRegistry(registry_path=fake_reg, model_dir=td)
        with pytest.raises(
            RuntimeError, match="Production environment .* requires a verified ML model"
        ):
            reg.resolve_active_model()


def test_health_reports_model_status():
    """Verify that /health reflects models_loaded, degraded, and artifact_source."""
    app = create_app()
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "models_loaded" in data
    assert "degraded" in data
    assert "artifact_source" in data
    assert data["models_loaded"] is True
    assert data["degraded"] is False
    assert data["artifact_source"] in ("registry", "demo_assets", "env")


def test_score_executes_loaded_model():
    """Verify that scoring uses the loaded champion model rather than failing."""
    app = create_app()
    client = TestClient(app)
    res = client.post(
        "/v1/score",
        json={
            "txn_id": "T_LOAD_TEST",
            "type": "send_money",
            "sender_wallet_id": "W_SENDER_1",
            "recipient_wallet_id": "W_RECIPIENT_1",
            "amount_bdt": 25000.0,
            "device_id": "DEV_TEST_1",
            "balance_before": 30000.0,
        },
        headers={"X-API-Key": "demo_public_key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "risk_score" in data
    assert 0.0 <= data["risk_score"] <= 1.0
    assert "action" in data
    assert "reason_codes" in data
