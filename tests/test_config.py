"""Tests for the XDG-style config layer.

Use $XDG_CONFIG_HOME redirection to keep tests hermetic — never touch
the real ~/.config dir during a test run.
"""

from __future__ import annotations

import pytest

from md_to_jira.config import (
    config_path,
    load_config,
    merge_intake_with_config,
    save_config,
)


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "md-to-jira" / "config.yaml"


def test_config_path_respects_xdg(isolated_config):
    assert config_path() == isolated_config


def test_load_config_returns_empty_when_missing(isolated_config):
    assert load_config() == {}


def test_save_then_load_roundtrip(isolated_config):
    data = {"defaults": {"jira_site": "https://x.atlassian.net", "project": "CW"}}
    written = save_config(data)
    assert written == isolated_config
    assert load_config() == data


def test_merge_intake_wins_per_key(isolated_config):
    config = {
        "defaults": {"jira_site": "https://global.atlassian.net", "project": "GLOBAL", "email": "g@x.io"}
    }
    intake = {
        "defaults": {"project": "OVERRIDE"},  # intake overrides project
        "epics": [],
        "stories": [],
    }
    merged = merge_intake_with_config(intake, config)
    # Intake's project wins.
    assert merged["defaults"]["project"] == "OVERRIDE"
    # Keys not in intake are filled from config.
    assert merged["defaults"]["jira_site"] == "https://global.atlassian.net"
    assert merged["defaults"]["email"] == "g@x.io"
    # Non-defaults sections passed through.
    assert merged["epics"] == []


def test_merge_handles_empty_intake_defaults(isolated_config):
    config = {"defaults": {"jira_site": "https://x.atlassian.net", "project": "CW"}}
    intake = {"defaults": {}, "epics": [], "stories": []}
    merged = merge_intake_with_config(intake, config)
    assert merged["defaults"]["jira_site"] == "https://x.atlassian.net"
    assert merged["defaults"]["project"] == "CW"


def test_merge_handles_intake_with_no_defaults_key(isolated_config):
    config = {"defaults": {"jira_site": "https://x.atlassian.net", "project": "CW"}}
    intake = {"epics": [], "stories": []}
    merged = merge_intake_with_config(intake, config)
    assert merged["defaults"]["jira_site"] == "https://x.atlassian.net"
