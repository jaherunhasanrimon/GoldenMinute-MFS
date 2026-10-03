"""Tests for configuration loader, Pydantic validation, and GM_SEED."""

from goldenminutes.common.config import (
    GM_SEED,
    get_features_config,
    get_models_config,
    get_policy_config,
    get_reasons_config,
    get_settings,
    get_simulator_config,
)


def test_settings_loader():
    settings = get_settings()
    assert settings.gm_env in ["dev", "prod", "test"]
    assert settings.gm_seed == 42
    assert settings.gm_customer_key != ""
    assert settings.gm_analyst_key != ""


def test_gm_seed_exposed():
    assert GM_SEED == 42
    assert isinstance(GM_SEED, int)


def test_simulator_config():
    sim = get_simulator_config()
    assert "small" in sim.profiles
    assert "full" in sim.profiles
    assert sim.profiles["small"].customers == 2000
    assert sim.profiles["full"].customers == 20000
    assert sim.held_out_typology == "agent_collusion"


def test_policy_config():
    policy = get_policy_config()
    assert policy.version == "0.1"
    assert "allow" in policy.actions
    assert "hold" in policy.actions
    assert policy.effectiveness["hold"] >= 0.8
    assert policy.friction_cost_bdt["hold"] > policy.friction_cost_bdt["allow"]
    assert policy.hold_capacity_per_hour == 20
    assert policy.golden_window_minutes == 30


def test_features_config():
    feat = get_features_config()
    assert feat.graph_window_days == 7
    assert feat.amount_norm_window_days == 30
    assert feat.rapid_cashout_minutes == 10


def test_models_config():
    models = get_models_config()
    assert "rules" in models.model_dump()
    assert models.rules["r1_recipient_age_days"] == 3
    assert models.risk_lgbm["class_weight"] == "balanced"


def test_reasons_config():
    reasons = get_reasons_config()
    assert "RECIPIENT_NEW" in reasons
    assert "en" in reasons["RECIPIENT_NEW"]
    assert "bn" in reasons["RECIPIENT_NEW"]
    assert "SAFE_ACTION_HINT" in reasons
