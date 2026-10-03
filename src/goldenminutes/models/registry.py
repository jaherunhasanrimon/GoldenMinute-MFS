"""Model registry managing versioned model artifacts and metadata.

Saves and reads active versions from models/registry.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("goldenminutes.models.registry")

REPO_ROOT = Path(__file__).resolve().parents[3]


def _to_relative(path_str: str) -> str:
    """Store artifact paths relative to the repo root so a fresh clone can load them."""
    p = Path(path_str)
    if p.is_absolute():
        try:
            return p.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return path_str
    return p.as_posix()


def _to_absolute(path_str: str) -> str:
    p = Path(path_str)
    return str(p if p.is_absolute() else REPO_ROOT / p)


class ModelRegistry:
    """Registry for model version metadata and artifacts."""

    def __init__(self, registry_path: Optional[Path | str] = None):
        if registry_path is None:
            self.registry_path = REPO_ROOT / "models" / "registry.json"
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
        """Register a new trained model version."""
        metadata = dict(metadata)
        if "artifacts" in metadata:
            metadata["artifacts"] = {k: _to_relative(v) for k, v in metadata["artifacts"].items()}
        self.data["versions"][version] = metadata
        if set_active or self.data.get("active_version") is None:
            self.data["active_version"] = version
        self.save()
        logger.info(f"Registered model version {version} (active: {set_active})")

    def get_active_metadata(self) -> Optional[Dict[str, Any]]:
        """Get metadata of the currently active model."""
        active = self.data.get("active_version")
        if active and active in self.data["versions"]:
            return self.get_version_metadata(active)
        return None

    def get_version_metadata(self, version: str) -> Optional[Dict[str, Any]]:
        """Metadata for a version with artifact paths resolved to absolute paths."""
        meta = self.data["versions"].get(version)
        if meta is None:
            return None
        meta = dict(meta)
        if "artifacts" in meta:
            meta["artifacts"] = {k: _to_absolute(v) for k, v in meta["artifacts"].items()}
        return meta
