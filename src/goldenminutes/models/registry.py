"""Model registry managing versioned model artifacts, SHA-256 checksums, and fallbacks.

Resolves active versions with validation, fallback to demo_assets, and fail-loud semantics in production.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("goldenminutes.models.registry")

REPO_ROOT = Path(__file__).resolve().parents[3]


def _compute_sha256(path: Path | str) -> str:
    """Compute sha256 hex digest of a file."""
    p = Path(path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _to_relative(path_str: str, base_dir: Optional[Path] = None) -> str:
    """Store artifact paths relative to the repo root so a fresh clone can load them."""
    base = base_dir or REPO_ROOT
    p = Path(path_str)
    if p.is_absolute():
        try:
            return p.relative_to(base).as_posix()
        except ValueError:
            return path_str
    return p.as_posix()


def _to_absolute(path_str: str, base_dir: Optional[Path] = None) -> str:
    base = base_dir or REPO_ROOT
    p = Path(path_str)
    return str(p if p.is_absolute() else base / p)


class ModelRegistry:
    """Registry for model version metadata, artifacts, and verifiable checksums."""

    def __init__(
        self,
        registry_path: Optional[Path | str] = None,
        model_dir: Optional[Path | str] = None,
    ):
        env_model_dir = os.environ.get("GM_MODEL_DIR")
        if model_dir is not None:
            self.model_dir = Path(model_dir)
        elif env_model_dir:
            self.model_dir = Path(env_model_dir)
        else:
            self.model_dir = REPO_ROOT / "models"

        if registry_path is None:
            self.registry_path = self.model_dir / "registry.json"
        else:
            self.registry_path = Path(registry_path)

        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read {self.registry_path}: {e}")
        return {"active_version": None, "versions": {}}

    def save(self) -> None:
        """Persist registry to JSON."""
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        logger.info(f"Updated model registry at {self.registry_path}")

    def register_version(
        self,
        version: str,
        metadata: Dict[str, Any],
        set_active: bool = True,
    ) -> None:
        """Register a new trained model version with computed SHA-256 checksums."""
        metadata = dict(metadata)
        checksums: Dict[str, str] = {}
        if "artifacts" in metadata:
            for k, v in list(metadata["artifacts"].items()):
                p = Path(_to_absolute(v, self.model_dir.parent))
                if p.exists():
                    checksums[k] = _compute_sha256(p)
            metadata["artifacts"] = {
                k: _to_relative(v, self.model_dir.parent) for k, v in metadata["artifacts"].items()
            }
        metadata["checksums"] = checksums
        self.data["versions"][version] = metadata
        if set_active or self.data.get("active_version") is None:
            self.data["active_version"] = version
        self.save()
        logger.info(
            f"Registered model version {version} with {len(checksums)} verified checksums (active: {set_active})"
        )

    def verify_artifacts(
        self,
        meta: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Verify that all required artifacts exist and match their SHA-256 checksums."""
        artifacts = meta.get("artifacts", {})
        if not artifacts:
            return False, "No artifacts defined in version metadata"

        checksums = meta.get("checksums", {})

        # Core required artifacts for running inference
        required_keys = ["thresholds"]
        for rk in required_keys:
            if rk not in artifacts:
                return False, f"Missing required artifact specification: {rk}"

        # Must have at least one ML model
        ml_keys = ["variant_e_lgbm", "variant_c_lgbm", "variant_b_lgbm"]
        if not any(k in artifacts for k in ml_keys):
            return False, f"Version metadata has no ML model artifact among {ml_keys}"

        for name, path_str in artifacts.items():
            p = Path(_to_absolute(path_str, self.model_dir.parent))
            if not p.exists():
                return False, f"Artifact file does not exist: {p}"

            if name in checksums:
                expected_sha = checksums[name]
                actual_sha = _compute_sha256(p)
                if actual_sha != expected_sha:
                    return (
                        False,
                        f"Checksum mismatch for {name}: expected {expected_sha[:8]}, got {actual_sha[:8]}",
                    )

        return True, "OK"

    def get_version_metadata(self, version: str) -> Optional[Dict[str, Any]]:
        """Metadata for a version with artifact paths resolved to absolute paths."""
        meta = self.data.get("versions", {}).get(version)
        if meta is None:
            return None
        meta = dict(meta)
        if "artifacts" in meta:
            meta["artifacts"] = {
                k: _to_absolute(v, self.model_dir.parent) for k, v in meta["artifacts"].items()
            }
        return meta

    def get_active_metadata(self) -> Optional[Dict[str, Any]]:
        """Get metadata of the currently registered active model."""
        active_ver = self.data.get("active_version")
        if not active_ver:
            return None
        return self.get_version_metadata(active_ver)

    def resolve_active_model(self) -> Tuple[Optional[Dict[str, Any]], str, bool]:
        """Resolve active model version following priority:
        1. GM_MODEL_VERSION environment override
        2. Active version from registry (if artifacts exist and pass checksums)
        3. Other versions in registry with verified artifacts
        4. demo_assets fallback
        5. Degraded mode (or raise in prod)

        Returns:
            (metadata, artifact_source, degraded)
        """
        is_prod = os.environ.get("GM_ENV") == "prod"

        # 1. Environment variable override
        env_version = os.environ.get("GM_MODEL_VERSION")
        if env_version:
            meta = self.get_version_metadata(env_version)
            if meta:
                valid, reason = self.verify_artifacts(meta)
                if valid:
                    logger.info(f"Using environment-pinned model version: {env_version}")
                    return meta, "env", False
                else:
                    logger.warning(
                        f"GM_MODEL_VERSION '{env_version}' failed verification: {reason}"
                    )
            else:
                logger.warning(f"GM_MODEL_VERSION '{env_version}' not found in registry")

        # 2. Check active version in registry
        active_ver = self.data.get("active_version")
        if active_ver:
            meta = self.get_version_metadata(active_ver)
            if meta:
                valid, reason = self.verify_artifacts(meta)
                if valid:
                    return meta, "registry", False
                else:
                    logger.warning(
                        f"Active version '{active_ver}' artifacts invalid or missing ({reason}). Searching fallbacks..."
                    )

        # 3. Check other versions in registry
        for v_name in self.data.get("versions", {}):
            if v_name == active_ver:
                continue
            meta = self.get_version_metadata(v_name)
            if meta:
                valid, _ = self.verify_artifacts(meta)
                if valid:
                    logger.info(f"Falling back to verified registered version: {v_name}")
                    return meta, "registry", False

        # 4. Fallback to demo_assets bundle
        demo_reg_path = REPO_ROOT / "demo_assets" / "registry.json"
        demo_models_dir = REPO_ROOT / "demo_assets" / "models"
        if demo_reg_path.exists() and demo_models_dir.exists():
            try:
                with open(demo_reg_path, "r", encoding="utf-8") as f:
                    demo_data = json.load(f)
                demo_active = demo_data.get("active_version")
                if demo_active and demo_active in demo_data.get("versions", {}):
                    demo_meta = demo_data["versions"][demo_active]
                    demo_meta = dict(demo_meta)
                    resolved_artifacts = {}
                    for k, v in demo_meta.get("artifacts", {}).items():
                        p = Path(v)
                        if not p.is_absolute():
                            # Point to demo_assets directory
                            resolved_p = REPO_ROOT / "demo_assets" / p
                            if not resolved_p.exists():
                                resolved_p = REPO_ROOT / p
                        else:
                            resolved_p = p
                        resolved_artifacts[k] = str(resolved_p)
                    demo_meta["artifacts"] = resolved_artifacts
                    valid, reason = self.verify_artifacts(demo_meta)
                    if valid:
                        logger.info(
                            f"Loaded verified fallback model from demo_assets: {demo_active}"
                        )
                        return demo_meta, "demo_assets", False
                    else:
                        logger.warning(f"demo_assets model failed verification: {reason}")
            except Exception as e:
                logger.warning(f"Failed loading demo_assets fallback: {e}")

        # 5. Degraded mode
        if is_prod:
            raise RuntimeError(
                "FATAL: Production environment (GM_ENV=prod) requires a verified ML model artifact, "
                "but no valid model was found in registry or demo_assets!"
            )

        logger.warning(
            "No verified model artifacts found. Operating in explicit DEGRADED rules-only mode."
        )
        return None, "none", True
