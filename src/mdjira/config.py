"""User-level configuration at `~/.config/mdjira/config.yaml`.

Convention follows what `gh`, `aws`, `gcloud`, etc. do — one XDG-compliant
config file holds non-secret defaults. The actual API token still lives
in `~/.jira-token` (chmod 600) because it has a different lifecycle and
should never end up in a config dump or backup of plain dotfiles.

Resolution order, lowest priority first:

    config.yaml `defaults`  ←  intake.yaml `defaults`  ←  CLI flags / env

So the user can leave `defaults: {}` empty in intake.yaml and have
everything inherited from the global config.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILE_NAME = "config.yaml"
APP_DIR_NAME = "mdjira"


def config_dir() -> Path:
    """Return the XDG config dir for this app, respecting $XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def load_config() -> dict[str, Any]:
    """Load config.yaml, returning {} if absent or empty."""
    p = config_path()
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{p}: invalid YAML — {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top level must be a mapping, got {type(data).__name__}")
    return data


def save_config(data: dict[str, Any]) -> Path:
    """Write data to config.yaml, creating the dir if needed. Returns the path."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = config_path()
    p.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return p


def merge_intake_with_config(intake_raw: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Merge config.defaults UNDER intake.defaults. Intake wins per key.

    The config-level email is intentionally kept here too (used by
    load_auth as a fallback) — `parse_intake` ignores unknown keys, so
    leaving `email` in the merged defaults is harmless.
    """
    merged = dict(intake_raw)
    intake_defaults = dict(intake_raw.get("defaults") or {})
    config_defaults = dict(config.get("defaults") or {})
    final_defaults: dict[str, Any] = {}
    final_defaults.update(config_defaults)
    final_defaults.update(intake_defaults)  # intake wins
    merged["defaults"] = final_defaults
    return merged


def config_email() -> str | None:
    """Return the email from config.yaml's defaults, if any."""
    cfg = load_config()
    defaults = cfg.get("defaults") or {}
    email = defaults.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None
