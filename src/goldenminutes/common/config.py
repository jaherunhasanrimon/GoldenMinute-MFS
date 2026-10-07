"""GoldenMinutes configuration loader and validator."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application-level environment configuration."""

    gm_env: str = Field(default="dev", alias="GM_ENV")
    gm_db_url: str = Field(default="sqlite:///./goldenminutes.db", alias="GM_DB_URL")
    gm_model_dir: str = Field(default="./models", alias="GM_MODEL_DIR")
    gm_llm_provider: str = Field(default="template", alias="GM_LLM_PROVIDER")
    gm_llm_api_key: Optional[str] = Field(default=None, alias="GM_LLM_API_KEY")
    gm_default_lang: str = Field(default="bn", alias="GM_DEFAULT_LANG")
    gm_seed: int = Field(default=42, alias="GM_SEED")
    gm_customer_key: str = Field(default="demo_customer_secret_key", alias="GM_CUSTOMER_KEY")
    gm_analyst_key: str = Field(default="demo_analyst_secret_key", alias="GM_ANALYST_KEY")
    gm_public_demo_key: str = Field(default="demo_public_key", alias="GM_PUBLIC_DEMO_KEY")
    gm_warmup_cutoff: Optional[str] = Field(default=None, alias="GM_WARMUP_CUTOFF")
    gm_cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        alias="GM_CORS_ORIGINS",
    )
    gm_jwt_secret: str = Field(
        default="gm_super_secret_jwt_key_2026_production",
        alias="GM_JWT_SECRET",
    )
    gm_jwt_algorithm: str = Field(default="HS256", alias="GM_JWT_ALGORITHM")
    gm_access_token_expire_minutes: int = Field(default=60, alias="GM_ACCESS_TOKEN_EXPIRE_MINUTES")
    gm_refresh_token_expire_days: int = Field(default=7, alias="GM_REFRESH_TOKEN_EXPIRE_DAYS")
    gm_max_login_attempts: int = Field(default=5, alias="GM_MAX_LOGIN_ATTEMPTS")
    gm_lockout_duration_minutes: int = Field(default=15, alias="GM_LOCKOUT_DURATION_MINUTES")
    gm_four_eyes_threshold_bdt: float = Field(default=50000.0, alias="GM_FOUR_EYES_THRESHOLD_BDT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class SimulatorProfile(BaseModel):
    customers: int
    agents: int
    merchants: int
    days: int
    target_fraud_rate: float = 0.004
    min_typology_positives: int = 300

    model_config = {"extra": "ignore"}


class SimulatorConfig(BaseModel):
    seed: int = 42
    profiles: Dict[str, SimulatorProfile]
    personas: Dict[str, Any] = Field(default_factory=dict)
    seasonality: Dict[str, Any] = Field(default_factory=dict)
    typologies: Dict[str, Any] = Field(default_factory=dict)
    confirmation_lag_hours: int = 24
    detection_rate: float = 0.8
    held_out_typology: str = "agent_collusion"
    realism: Dict[str, Any] = Field(default_factory=dict)
    networks: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class PolicyConfig(BaseModel):
    version: str = "0.1"
    actions: List[str] = ["allow", "warn", "verify", "hold"]
    effectiveness: Dict[str, float]
    friction_cost_bdt: Dict[str, float]
    min_amount_bdt_for_intervention: float = 300.0
    hold_capacity_per_hour: int = 20
    golden_window_minutes: int = 30
    hard_rules: List[str] = ["recipient_blocklisted"]


class FeaturesConfig(BaseModel):
    graph_window_days: int = 7
    amount_norm_window_days: int = 30
    rapid_cashout_minutes: int = 10
    hour_window_1h: int = 1
    hour_window_24h: int = 24
    balance_drain_threshold: float = 0.8
    pin_reset_recent_minutes: int = 60
    sim_change_recent_minutes: int = 60


class ModelsConfig(BaseModel):
    rules: Dict[str, Any]
    risk_lgbm: Dict[str, Any]
    anomaly_iforest: Dict[str, Any]
    fusion: Dict[str, Any]


def find_project_root() -> Path:
    """Locate the project root directory."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "configs").is_dir() and (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


PROJECT_ROOT = find_project_root()
CONFIG_DIR = PROJECT_ROOT / "configs"


def load_yaml(file_name: str) -> Dict[str, Any]:
    """Safely load a YAML config file from the configs directory."""
    path = CONFIG_DIR / file_name
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


# Lazy / cached config loaders
_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """Return validated application settings."""
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def get_simulator_config() -> SimulatorConfig:
    data = load_yaml("simulator.yaml")
    return SimulatorConfig.model_validate(data)


def get_policy_config() -> PolicyConfig:
    data = load_yaml("policy.yaml")
    return PolicyConfig.model_validate(data)


def get_features_config() -> FeaturesConfig:
    data = load_yaml("features.yaml")
    return FeaturesConfig.model_validate(data)


def get_models_config() -> ModelsConfig:
    data = load_yaml("models.yaml")
    return ModelsConfig.model_validate(data)


def get_reasons_config() -> Dict[str, Dict[str, str]]:
    return load_yaml("reasons.yaml")


# Expose GM_SEED as required by task P0.2
GM_SEED: int = get_settings().gm_seed
