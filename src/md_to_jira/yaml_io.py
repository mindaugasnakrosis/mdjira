"""Thin wrappers around PyYAML to keep loader choice consistent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a YAML mapping")
    return data


def dump(data: Any, path: str | Path) -> None:
    Path(path).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
