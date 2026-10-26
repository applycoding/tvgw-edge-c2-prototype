"""Load YAML configuration."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[2]
    path = root / "config" / "default.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
